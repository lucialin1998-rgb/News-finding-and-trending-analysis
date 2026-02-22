from __future__ import annotations

import json
import re
from typing import Optional

from bs4 import BeautifulSoup

from .utils import parse_date_to_iso, safe_excerpt


def extract_article_metadata(html: str, original_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    canonical_url = _extract_canonical_url(soup) or original_url
    title = _extract_title(soup)
    date_iso = _extract_date(soup)
    excerpt = _extract_excerpt(soup)
    visible_text = _extract_visible_text(soup)
    return {
        "canonical_url": canonical_url,
        "title": title,
        "date": date_iso or "",
        "excerpt": safe_excerpt(excerpt or visible_text),
        "text": visible_text,
    }


def _extract_canonical_url(soup: BeautifulSoup) -> Optional[str]:
    link = soup.select_one("link[rel='canonical']")
    if link and link.get("href"):
        return link["href"].strip()
    og = soup.select_one("meta[property='og:url']")
    if og and og.get("content"):
        return og["content"].strip()
    return None


def _extract_title(soup: BeautifulSoup) -> str:
    for selector in ["meta[property='og:title']", "meta[name='twitter:title']", "h1", "title"]:
        node = soup.select_one(selector)
        if not node:
            continue
        value = node.get("content") if node.name == "meta" else node.get_text(" ", strip=True)
        if value:
            return value.strip()
    return "Untitled"


def _extract_date(soup: BeautifulSoup) -> Optional[str]:
    for selector in ["meta[property='article:published_time']", "time[datetime]"]:
        node = soup.select_one(selector)
        if not node:
            continue
        raw = node.get("content") or node.get("datetime") or node.get_text(" ", strip=True)
        parsed = parse_date_to_iso(raw)
        if parsed:
            return parsed

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        found = _date_from_jsonld(payload)
        if found:
            return found
    return None


def _date_from_jsonld(payload) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("datePublished", "dateCreated", "uploadDate"):
            if key in payload:
                parsed = parse_date_to_iso(str(payload[key]))
                if parsed:
                    return parsed
        for value in payload.values():
            nested = _date_from_jsonld(value)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _date_from_jsonld(item)
            if nested:
                return nested
    return None


def _extract_excerpt(soup: BeautifulSoup) -> str:
    for selector in ["meta[property='og:description']", "meta[name='description']", "article p", "p"]:
        node = soup.select_one(selector)
        if not node:
            continue
        text = node.get("content") if node.name == "meta" else node.get_text(" ", strip=True)
        if text:
            return text
    return ""


def _extract_visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    container = soup.select_one("article") or soup.body
    if not container:
        return ""
    chunks = [node.get_text(" ", strip=True) for node in container.select("p, h2, h3")]
    text = " ".join(chunk for chunk in chunks if chunk)
    return re.sub(r"\s+", " ", text).strip()
