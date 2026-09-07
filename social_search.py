"""Step 2: Social-media search — filter + face re-rank on top of reverse-image results.

Works with the existing scrapers in dashboard/backend/server.py:
  search_yandex(image_url) -> {info_pages:[...], similar_images:[...]}
  search_google(image_url) -> {matching_pages:[...], similar_images:[...]}

Functions:
  filter_social_posts(yandex, google) -> list of social-only matches
  rerank_by_face(matches, query_encoding) -> matches sorted by face similarity
  select_best_match(ranked) -> single best dict or None
  process_matches(yandex, google, query_encoding) -> {social_matches, best_match}
"""
import base64
import hashlib
import tempfile
import urllib.parse
from pathlib import Path

import requests

try:
    from face_detection import compare_faces, encode_face
except ImportError:  # when imported as dashboard module
    from pathlib import Path as _P
    import sys as _sys
    _sys.path.insert(0, str(_P(__file__).resolve().parent))
    from face_detection import compare_faces, encode_face


SOCIAL_DOMAINS = [
    "instagram.com",
    "facebook.com", "fb.com",
    "x.com", "twitter.com",
    "tiktok.com",
    "linkedin.com",
    "youtube.com", "youtu.be",
    "pinterest.com", "pin.it",
    "reddit.com",
    "threads.net",
    "snapchat.com",
    "vk.com",
    "weibo.com",
]


def _follow_redirect(url: str, timeout: int = 10) -> str | None:
    """Follow HTTP redirect chain and return the final destination URL."""
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/152.0.0.0 Safari/537.36"
        })
        final = r.url
        if final and final != url and not ("google.com" in final and "/sorry/" in final):
            return final
    except Exception:
        pass
    return None


def _unwrap_any_url(href: str | None) -> str | None:
    """Unwrap redirect links (/url?q=<real>, ?url=<real>) to the real URL.

    Also follows encrypted Google redirects (/goto?url=CAES...) by
    resolving the HTTP redirect chain.
    """
    if not href or not isinstance(href, str):
        return href
    try:
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        for key in ("q", "url", "u", "redirect", "target"):
            vals = qs.get(key)
            if vals and isinstance(vals[0], str) and vals[0].startswith("http"):
                return vals[0]
        # Encrypted Google redirect (/goto, /url with encoded blob)
        if (parsed.hostname and "google" in parsed.hostname
                and parsed.path in ("/goto", "/url", "/away")):
            return _follow_redirect(href) or href
    except Exception:
        pass
    return href


def _domain_of(item: dict) -> str:
    d = (item.get("domain") or "").lower()
    if d:
        return d
    url = (item.get("url") or "").lower()
    return url


def _haystack(item: dict) -> str:
    """Combined lowercase string to detect the platform from.

    Checks domain + full link + unwrapped redirect target + title, so a
    Google redirect like https://www.google.com/url?q=https://www.instagram.com/...
    still buckets as Instagram.
    """
    url = item.get("url") or ""
    parts = [item.get("domain") or "", url, item.get("title") or ""]
    unwrapped = _unwrap_any_url(url)
    if unwrapped and unwrapped != url:
        parts.append(unwrapped)
    return " ".join(parts).lower()


def _platform_of(item: dict) -> str | None:
    """Platform category from the link string. First CATEGORY_RULES hit wins.

    Matches the platform name inside the full link (domain + url + unwrapped
    redirect target), e.g. https://www.google.com/url?q=https://www.instagram.com/...
    buckets as Instagram. Hosts are compared exactly (subdomain-aware) so
    short names like x.com don't false-hit box.com.
    """
    import re
    hay = _haystack(item)
    hosts = {m.lower().split("@")[-1].split(":")[0]
             for m in re.findall(r"https?://([^/\s'\"<>?#]+)", hay)}

    def host_hit(d: str) -> bool:
        return any(h == d or h.endswith("." + d) for h in hosts)

    for name, doms in CATEGORY_RULES:
        for d in doms:
            if d == "x.com":
                if host_hit("x.com") or "twitter.com" in hay:
                    return name
            elif d in hay or host_hit(d):
                return name
    return None


def is_social(item: dict) -> bool:
    return _platform_of(item) is not None


def filter_social_posts(yandex: dict | None, google: dict | None) -> list[dict]:
    """Collect social-only matches, tagged with _source. Order preserved."""
    out: list[dict] = []

    def _push(items, source):
        for r in items or []:
            if not isinstance(r, dict):
                continue
            if not r.get("url"):
                continue
            if is_social(r):
                c = dict(r)
                c["_source"] = source
                out.append(c)

    yandex = yandex or {}
    google = google or {}
    _push(yandex.get("info_pages"), "yandex-info")
    _push(yandex.get("similar_images"), "yandex-sim")
    _push(google.get("matching_pages"), "google-match")
    _push(google.get("similar_images"), "google-sim")
    return out


# Platform buckets for the dashboard: (category, domain substrings).
# Checked in order — first match wins.
CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Instagram", ["instagram.com"]),
    ("Facebook", ["facebook.com", "fb.com", "fb.watch"]),
    ("X / Twitter", ["x.com", "twitter.com", "t.co"]),
    ("YouTube", ["youtube.com", "youtu.be"]),
    ("TikTok", ["tiktok.com"]),
    ("LinkedIn", ["linkedin.com"]),
    ("Pinterest", ["pinterest.com", "pin.it"]),
    ("Reddit", ["reddit.com"]),
    ("Threads", ["threads.net"]),
    ("Snapchat", ["snapchat.com"]),
    ("VK", ["vk.com"]),
    ("Weibo", ["weibo.com"]),
    ("Tumblr", ["tumblr.com"]),
    ("Quora", ["quora.com"]),
    ("Medium", ["medium.com"]),
    ("Telegram", ["t.me", "telegram.org"]),
    ("WhatsApp", ["whatsapp.com"]),
    ("Discord", ["discord.com", "discord.gg"]),
    ("Twitch", ["twitch.tv"]),
    ("Spotify", ["spotify.com"]),
]

CATEGORY_ORDER = [name for name, _ in CATEGORY_RULES] + [
    "Google results", "Yandex results", "Other Web",
]


def collect_all_results(yandex: dict | None,
                        google: dict | None) -> list[dict]:
    """Collect ALL raw hits (social + web), tagged with _source."""
    out: list[dict] = []

    def _push(items, source):
        for r in items or []:
            if not isinstance(r, dict):
                continue
            if not r.get("url"):
                continue
            c = dict(r)
            c["_source"] = source
            out.append(c)

    yandex = yandex or {}
    google = google or {}
    _push(yandex.get("info_pages"), "yandex-info")
    _push(yandex.get("similar_images"), "yandex-sim")
    _push(google.get("matching_pages"), "google-match")
    _push(google.get("similar_images"), "google-sim")
    return out


def categorize_results(yandex: dict | None,
                       google: dict | None) -> dict[str, list[dict]]:
    """    Bucket every raw hit by platform. Only non-empty buckets returned.

    Platform is read from the full link string (domain + url + unwrapped
    redirect target), so https://www.google.com/url?q=https://www.instagram.com/...
    buckets as Instagram. Leftover Google/Yandex hits fall into
    'Google results' / 'Yandex results' based on _source; anything else
    goes to 'Other Web'.
    """
    grouped: dict[str, list[dict]] = {}
    for item in collect_all_results(yandex, google):
        cat = _platform_of(item)
        if cat is None:
            src = item.get("_source", "")
            if src.startswith("google"):
                cat = "Google results"
            elif src.startswith("yandex"):
                cat = "Yandex results"
            else:
                cat = "Other Web"
        grouped.setdefault(cat, []).append(item)
    return grouped


def _encode_thumbnail(thumb_url: str | None, tmpdir: Path) -> dict | None:
    """Download/decode a thumbnail and encode it. Returns encoding or None."""
    if not thumb_url or not isinstance(thumb_url, str):
        return None
    try:
        if thumb_url.startswith("data:image") and ";base64," in thumb_url:
            raw = base64.b64decode(thumb_url.split(";base64,", 1)[1])
            fp = tmpdir / (hashlib.sha256(thumb_url[:512].encode()).hexdigest()[:12] + ".jpg")
            fp.write_bytes(raw)
            return encode_face(str(fp), None)
        if thumb_url.startswith("//"):
            thumb_url = "https:" + thumb_url
        if thumb_url.startswith("http"):
            r = requests.get(thumb_url, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "")
            if "image" not in ctype and len(r.content) < 500:
                return None
            fp = tmpdir / (hashlib.sha256(thumb_url.encode()).hexdigest()[:12] + ".jpg")
            fp.write_bytes(r.content)
            return encode_face(str(fp), None)
    except Exception:
        return None
    return None


def rerank_by_face(matches: list[dict], query_encoding: dict | None,
                   max_encode: int = 20) -> list[dict]:
    """Score each match thumbnail vs query face. Sorts best-first.

    Adds `face_score` (0-1) or None if unscorable. Unscorable items sink
    to the bottom, preserving their relative order.
    """
    if not matches:
        return []
    if query_encoding is None:
        return [{**m, "face_score": None} for m in matches]

    scored: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="rerank_") as td:
        tmpdir = Path(td)
        for m in matches[:max_encode] + matches[max_encode:]:
            if len(scored) >= max_encode and m in matches[max_encode:]:
                scored.append({**m, "face_score": None})
                continue
            enc = _encode_thumbnail(m.get("thumbnail_url"), tmpdir) \
                if len(scored) < max_encode else None
            score = compare_faces(query_encoding, enc) if enc else None
            scored.append({**m, "face_score": score})

    scored.sort(key=lambda m: (m["face_score"] is None,
                               -(m["face_score"] or 0)))
    return scored


def select_best_match(ranked: list[dict]) -> dict | None:
    """Pick the single evidence post. Prefers scored social matches."""
    if not ranked:
        return None
    return ranked[0]


def process_matches(yandex: dict | None, google: dict | None,
                    query_encoding: dict | None) -> dict:
    """One-call helper: filter -> rerank -> pick best + group all by platform."""
    social = filter_social_posts(yandex, google)
    ranked = rerank_by_face(social, query_encoding)
    return {"social_matches": ranked, "best_match": select_best_match(ranked),
            "grouped": categorize_results(yandex, google)}


if __name__ == "__main__":
    # smoke test with mock data (no selenium needed)
    mock_y = {"info_pages": [
        {"rank": 0, "url": "https://www.instagram.com/p/ABC123/",
         "domain": "instagram.com", "title": "Insta post",
         "thumbnail_url": None},
        {"rank": 1, "url": "https://example-blog.com/page",
         "domain": "example-blog.com", "title": "blog",
         "thumbnail_url": None},
    ], "similar_images": []}
    mock_g = {"matching_pages": [
        {"rank": 0, "url": "https://x.com/user/status/123",
         "domain": "x.com", "title": "tweet",
         "thumbnail_url": None},
    ], "similar_images": []}
    res = process_matches(mock_y, mock_g, None)
    print(f"social: {len(res['social_matches'])} (expect 2)")
    print(f"best: {res['best_match']['url'] if res['best_match'] else None}")
    print("grouped:", {k: len(v) for k, v in res["grouped"].items()})
