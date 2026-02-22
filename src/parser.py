from __future__ import annotations

import json
import re
from html import unescape
from typing import Optional

from .utils import parse_date_to_iso, safe_excerpt


def extract_article_metadata(html: str, url: str) -> dict:
    title = _extract_title(html)
    date_iso = _extract_date_iso(html)
    excerpt = _extract_excerpt(html)
    full_text = _extract_visible_text(html)
    return {
        "title": title,
        "url": url,
        "date_iso": date_iso,
        "excerpt": safe_excerpt(excerpt or full_text or ""),
        "full_text": full_text,
    }


def _extract_title(html: str) -> str:
    for pattern in [
        r"<meta[^>]+property=['\"]og:title['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+name=['\"]twitter:title['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<h1[^>]*>(.*?)</h1>",
        r"<title[^>]*>(.*?)</title>",
    ]:
        m = re.search(pattern, html, flags=re.I | re.S)
        if m:
            return _clean(m.group(1))
    return "Untitled"


def _extract_date_iso(html: str) -> Optional[str]:
    patterns = [
        r"<meta[^>]+property=['\"]article:published_time['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+name=['\"]publish_date['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+name=['\"]date['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<time[^>]+datetime=['\"]([^'\"]+)['\"]",
    ]
    for p in patterns:
        m = re.search(p, html, flags=re.I | re.S)
        if m:
            iso = parse_date_to_iso(_clean(m.group(1)))
            if iso:
                return iso

    for m in re.finditer(r"<script[^>]+type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>", html, flags=re.I | re.S):
        chunk = m.group(1).strip()
        try:
            payload = json.loads(chunk)
        except Exception:
            continue
        iso = _jsonld_date(payload)
        if iso:
            return iso
    return None


def _jsonld_date(payload) -> Optional[str]:
    if isinstance(payload, dict):
        for k in ["datePublished", "dateCreated", "uploadDate"]:
            if k in payload:
                iso = parse_date_to_iso(str(payload[k]))
                if iso:
                    return iso
        for v in payload.values():
            nested = _jsonld_date(v)
            if nested:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _jsonld_date(item)
            if nested:
                return nested
    return None


def _extract_excerpt(html: str) -> str:
    for p in [
        r"<meta[^>]+property=['\"]og:description['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+name=['\"]description['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<p[^>]*>(.*?)</p>",
    ]:
        m = re.search(p, html, flags=re.I | re.S)
        if m:
            return _clean(m.group(1))
    return ""


def _extract_visible_text(html: str) -> str:
    cleaned = re.sub(r"<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", html, flags=re.I | re.S)
    blocks = re.findall(r"<(?:p|h2|h3)[^>]*>(.*?)</(?:p|h2|h3)>", cleaned, flags=re.I | re.S)
    text = " ".join(_clean(b) for b in blocks if _clean(b))
    return re.sub(r"\s+", " ", text).strip()


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return unescape(re.sub(r"\s+", " ", text)).strip()
