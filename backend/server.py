"""FastAPI backend wrapping the face-search and evidence services.

Run from the repository root with ``python3 backend/server.py`` or
``uvicorn backend.server:app --port 8011``.
"""
import shutil
import sys
import time
import os
import urllib.parse
import uuid
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bs4 import BeautifulSoup

# Keep the pipeline modules importable both when this file is executed directly
# and when the app is started with ``uvicorn backend.server:app``.
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from face_detection import process_face_scan
from social_search import CATEGORY_ORDER, process_matches
from blockchain_service import register as register_evidence, verify as verify_evidence

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


class SearchRequest(BaseModel):
    image_url: str
    engine: str = "both"  # google | yandex | both
    amount: int = 20


class FaceSearchRequest(BaseModel):
    image_url: str
    engine: str = "both"  # google | yandex | both
    amount: int = 20


class EvidenceRequest(BaseModel):
    post: dict
    face_fingerprint: str = ""


def _crop_dataurl(crop_path: str | None) -> str | None:
    """Read face crop jpg and return data: URL so frontend can show it."""
    import base64
    if not crop_path:
        return None
    try:
        raw = Path(crop_path).read_bytes()
        if len(raw) > 800_000:  # keep API payloads small
            return None
        return "data:image/jpeg;base64," + base64.b64encode(raw).decode()
    except Exception:
        return None


def _run_face_pipeline(source: str, engine: str, amount: int) -> dict:
    """Shared Step 1+2: face scan -> reverse-image search -> social filter+rerank."""
    face = process_face_scan(source, out_dir=str(REPO_ROOT / "data" / "faces"))
    # engines need a public URL; uploads pass their local path for face step
    # but search with the original URL when available
    search_url = face.get("source") if face.get("source", "").startswith("http") \
        else face.get("image_path")
    y_res, g_res = None, None
    # local file without public URL: skip live search, return face only
    # (caller can still anchor manually; genuine search needs a URL)
    if isinstance(search_url, str) and search_url.startswith("http"):
        if engine in ("yandex", "both"):
            y_res = search_yandex(search_url, amount)
        if engine in ("google", "both"):
            g_res = search_google(search_url, amount)
    matched = process_matches(y_res, g_res, face.get("query_encoding"))
    return {
        "face": {k: v for k, v in face.items() if k != "query_encoding"},
        "face_phash": (face.get("query_encoding") or {}).get("phash"),
        "face_crop_dataurl": _crop_dataurl(face.get("face_crop_path")),
        "social_matches": matched["social_matches"],
        "best_match": matched["best_match"],
        "grouped": matched["grouped"],
        "category_order": CATEGORY_ORDER,
        "yandex": y_res,
        "google": g_res,
    }


def make_driver():
    from selenium.webdriver.chrome.service import Service

    driver_path = Path(os.environ.get(
        "CHROMEDRIVER_PATH", REPO_ROOT / "chromedriver-mac-arm64" / "chromedriver"
    ))
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
    # Selenium 4 uses a ``Service`` object, whereas Selenium 3.141 (still
    # commonly bundled with older Python environments) rejects ``service``.
    # Keep both invocation forms working while the project transitions.
    try:
        service = Service(executable_path=str(driver_path)) if driver_path.exists() else Service()
        driver = webdriver.Chrome(service=service, options=options)
    except TypeError as exc:
        if "service" not in str(exc):
            raise
        legacy_kwargs = {"options": options}
        if driver_path.exists():
            legacy_kwargs["executable_path"] = str(driver_path)
        driver = webdriver.Chrome(**legacy_kwargs)
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


def _unwrap_google_url(href: str | None) -> str | None:
    """Unwrap Google redirect links to the real destination URL.

    Handles two cases:
    1. Simple query-param redirects: /url?q=<real>, ?url=<real_http_url>
    2. Encrypted redirects: /goto?url=CAES... (encoded blob) — resolved
       by following the HTTP redirect chain.
    """
    if not href or not isinstance(href, str):
        return href
    try:
        q = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(q.query)
        # Case 1: plain-text URL in a query param
        for key in ("q", "url", "u", "redirect", "target"):
            vals = qs.get(key)
            if vals and isinstance(vals[0], str) and vals[0].startswith("http"):
                return vals[0]
        # Case 2: encrypted Google redirect (/goto, /url with encoded blob)
        # The url param exists but isn't a plain http link — follow the redirect
        if q.hostname and "google" in q.hostname and q.path in ("/goto", "/url", "/away"):
            return _follow_redirect(href) or href
    except Exception:
        pass
    return href


def _follow_redirect(url: str, timeout: int = 10) -> str | None:
    """Follow HTTP redirect chain and return the final destination URL.

    Google Lens' encrypted ``/goto?url=CAES...`` links are not regular HTTP
    redirects: a HEAD request gets a 200 response, while the GET response
    contains a small page whose ``here`` link is the real destination. Use a
    GET so both ordinary redirects and that page form are handled.
    """
    import requests as _req
    try:
        r = _req.get(url, allow_redirects=True, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/152.0.0.0 Safari/537.36"
        })
        final = r.url
        # Only return if we actually ended up somewhere different
        if final and final != url and not ("google.com" in final and "/sorry/" in final):
            return final
        # Some Google /goto responses use an HTML handoff instead of a 3xx.
        # Select only an absolute, non-Google destination so navigation and
        # result metadata use the actual matching page rather than Google.
        for link in BeautifulSoup(r.text, "html.parser").find_all("a", href=True):
            destination = link["href"]
            parsed = urllib.parse.urlparse(destination)
            if (parsed.scheme in ("http", "https") and parsed.hostname and
                    not parsed.hostname.lower().endswith("google.com")):
                return destination
    except Exception:
        pass
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
                href = _unwrap_google_url(href)
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
                href = _unwrap_google_url(href)
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


@app.post("/api/face/search")
def face_search(req: FaceSearchRequest):
    """Step 1+2 via image URL: face scan -> live search -> social best match."""
    try:
        return _run_face_pipeline(req.image_url, req.engine, req.amount)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/face/upload-search")
async def face_upload_search(file: UploadFile = File(...),
                             engine: str = "both", amount: int = 20):
    """Step 1+2 via file upload: saves to data/uploads, runs face scan.

    Note: engines need a public URL, so live search runs only when the
    upload is accompanied by a reachable URL. Face detect/encode always runs.
    Use /api/face/search with a public URL for the genuine end-to-end search.
    """
    updir = REPO_ROOT / "data" / "uploads"
    updir.mkdir(parents=True, exist_ok=True)
    dest = updir / f"{uuid.uuid4().hex}_{Path(file.filename or 'upload.jpg').name}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        return _run_face_pipeline(str(dest), engine, amount)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/evidence/register")
def evidence_register(req: EvidenceRequest):
    """Hash selected live-search evidence and store only its hash on local chain."""
    try:
        if not req.post.get("url"):
            raise ValueError("A selected post URL is required")
        return register_evidence(req.post, req.face_fingerprint)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/evidence/verify")
def evidence_verify(req: EvidenceRequest):
    """Re-hash evidence and compare it with the on-chain fingerprint."""
    try:
        if not req.post.get("url"):
            raise ValueError("A selected post URL is required")
        return verify_evidence(req.post, req.face_fingerprint)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8011")))
