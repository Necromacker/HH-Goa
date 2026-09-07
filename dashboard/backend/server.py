"""FastAPI backend wrapping the reverse-image scrapers.

Run:
    /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 server.py
    # or: uvicorn server:app --port 8000
"""
import time
import urllib.parse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


class SearchRequest(BaseModel):
    image_url: str
    engine: str = "both"  # google | yandex | both
    amount: int = 20


def make_driver():
    from pathlib import Path as _P
    driver_path = str(_P(__file__).resolve().parents[2] / "chromedriver")
    options = Options()
    options.add_argument("--incognito")
    options.add_argument("--headless=new")
    options.add_argument("window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(driver_path, options=options)
    try:
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception:
        pass
    return driver


def _domain(url):
    try:
        return url.replace("https://", "").replace("http://", "").replace(
            "www.", "").split("/")[0]
    except Exception:
        return None


def search_yandex(image_url, amount=20):
    """Returns {info_pages: [...], similar_images: [...]}."""
    driver = make_driver()
    info_pages, similar = [], []
    try:
        url = ("https://yandex.com/images/search?rpt=imageview&url="
               + urllib.parse.quote(image_url, safe=""))
        driver.get(url)
        time.sleep(8)
        for _ in range(3):
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # info pages: li.CbirSites-Item
        for i, r in enumerate(soup.find_all(class_="CbirSites-Item")):
            if len(info_pages) >= amount:
                break
            try:
                title_el = r.find(class_="CbirSites-ItemTitle")
                a = title_el.find("a") if title_el else None
                page_url = a["href"] if a and a.has_attr("href") else None
                title = a.get_text() if a else None
                dom_el = r.find(class_="CbirSites-ItemDomain")
                domain = dom_el.get_text().strip() if dom_el else _domain(page_url)
                desc_el = r.find(class_="CbirSites-ItemDescription")
                thumb_el = r.find(class_="Thumb-Image")
                thumb = None
                if thumb_el is not None:
                    if thumb_el.name == "img" and thumb_el.has_attr("src"):
                        s = thumb_el["src"]
                        thumb = s if s.startswith("http") else "https:" + s
                    elif thumb_el.has_attr("style"):
                        import re
                        m = re.search(r"url\(['\"]?(//[^'\")]+)", thumb_el["style"])
                        if m:
                            thumb = "https:" + m.group(1)
                info_pages.append({
                    "rank": len(info_pages), "url": page_url,
                    "domain": domain,
                    "country_code_tld": domain.split(".")[-1] if domain else None,
                    "title": title,
                    "description": desc_el.get_text() if desc_el else None,
                    "thumbnail_url": thumb,
                })
            except Exception:
                continue

        # similar: div.CbirSimilarList-Thumb
        for r in soup.find_all(class_="CbirSimilarList-Thumb"):
            if len(similar) >= amount:
                break
            try:
                a = r.find("a", href=True)
                href = a["href"] if a else ""
                if href.startswith("/"):
                    href = "https://yandex.com" + href
                q = urllib.parse.urlparse(href)
                qs = urllib.parse.parse_qs(q.query)
                page_url = qs.get("img_url", [None])[0]
                thumb = qs.get("url", [None])[0]
                if thumb and thumb.startswith("//"):
                    thumb = "https:" + thumb
                inner = r.find(attrs={"aria-label": True})
                title = inner.get("aria-label") if inner else None
                domain = _domain(page_url) if page_url else None
                similar.append({
                    "rank": len(similar), "url": page_url,
                    "domain": domain,
                    "country_code_tld": domain.split(".")[-1] if domain else None,
                    "title": title, "thumbnail_url": thumb,
                })
            except Exception:
                continue
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return {"info_pages": info_pages, "similar_images": similar}


def _lens_tab_url(driver, tab_name):
    for a in driver.find_elements(By.TAG_NAME, "a"):
        try:
            if (a.text or "").strip() == tab_name and a.get_attribute("href"):
                href = a.get_attribute("href")
                return href if href.startswith("http") else "https://www.google.com" + href
        except Exception:
            continue
    return None


def search_google(image_url, amount=20):
    """Returns {matching_pages: [...], similar_images: [...]}."""
    driver = make_driver()
    matching, similar = [], []
    try:
        lens = ("https://lens.google.com/uploadbyurl?url="
                + urllib.parse.quote(image_url, safe=""))
        driver.get(lens)
        time.sleep(10)
        if "/sorry/" in driver.current_url:
            return {"matching_pages": [], "similar_images": [],
                    "error": "Google bot-check blocked headless request"}

        exact = _lens_tab_url(driver, "Exact matches")
        visual = _lens_tab_url(driver, "Visual matches")

        if exact:
            driver.get(exact)
            time.sleep(8)
            for _ in range(2):
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            cands = [c for c in soup.find_all("div", {"class": "MjjYud"})
                     if c.find("a", {"class": "ngTNl"})]
            seen = set()
            for c in cands:
                if len(matching) >= amount:
                    break
                a = c.find("a", {"class": "ngTNl"})
                href = a.get("href") if a else None
                if href and href.startswith("/"):
                    href = "https://www.google.com" + href
                if not href or href in seen:
                    continue
                seen.add(href)
                t = c.find("div", {"class": "ZhosBf"})
                img = c.find("img")
                matching.append({
                    "rank": len(matching), "url": href,
                    "domain": _domain(href),
                    "country_code_tld": (_domain(href) or "").split(".")[-1] or None,
                    "title": t.get_text() if t else (a.get_text() if a else None),
                    "description": c.get_text(separator=" | ")[:500],
                    "thumbnail_url": img["src"] if img and img.has_attr("src") else None,
                })

        if visual:
            driver.get(visual)
            time.sleep(8)
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            links = [a for a in soup.find_all("a", href=True) if a.find("img")]
            for a in links:
                if len(similar) >= amount:
                    break
                href = a["href"]
                if href.startswith("/"):
                    href = "https://www.google.com" + href
                img = a.find("img")
                similar.append({
                    "rank": len(similar), "url": href,
                    "domain": _domain(href),
                    "country_code_tld": (_domain(href) or "").split(".")[-1] or None,
                    "title": img.get("alt") if img and img.has_attr("alt") else None,
                    "thumbnail_url": img["src"] if img and img.has_attr("src") else None,
                })
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return {"matching_pages": matching, "similar_images": similar}


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/search")
def search(req: SearchRequest):
    out = {"image_url": req.image_url, "engine": req.engine}
    if req.engine in ("yandex", "both"):
        out["yandex"] = search_yandex(req.image_url, req.amount)
    if req.engine in ("google", "both"):
        out["google"] = search_google(req.image_url, req.amount)
    return out


if __name__ == "__main__":
    import uvicorn
    # run from repo root so ./chromedriver resolves
    uvicorn.run(app, host="127.0.0.1", port=8000)
