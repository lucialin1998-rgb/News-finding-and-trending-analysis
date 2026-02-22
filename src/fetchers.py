from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from .parser import extract_article_metadata
from .utils import (
    Article,
    DomainLimiter,
    cache_path_for_url,
    dedupe_articles,
    in_date_window,
    parse_date_to_iso,
    safe_excerpt,
)

LOGGER = logging.getLogger(__name__)
USER_AGENT = "NewsTrendBot/1.0 (+educational-project; respectful scraping)"

SOURCES = {
    "Music Week": {
        "listing_url": "https://www.musicweek.com/news",
        "feed_candidates": [
            "https://www.musicweek.com/rss/news",
            "https://www.musicweek.com/rss",
            "https://www.musicweek.com/news/rss",
        ],
    },
    "Music Business Worldwide": {
        "listing_url": "https://www.musicbusinessworldwide.com/category/news/",
        "feed_candidates": [
            "https://www.musicbusinessworldwide.com/feed/",
            "https://www.musicbusinessworldwide.com/category/news/feed/",
        ],
    },
}


class NewsCollector:
    def __init__(self, start_dt, end_dt, max_articles_per_source: int, cache_dir: Path, use_cache: bool, timeout: int = 20):
        self.start_dt = start_dt
        self.end_dt = end_dt
        self.max_articles_per_source = max_articles_per_source
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.timeout = timeout
        self.limiter = DomainLimiter(1.0)
        self._robots: Dict[str, Optional[RobotFileParser]] = {}

    def collect(self) -> Dict[str, List[Article]]:
        out = {}
        for source, config in SOURCES.items():
            articles = self._collect_source(source, config)
            out[source] = sorted(dedupe_articles(articles), key=lambda a: a.date_iso, reverse=True)
        return out

    def _collect_source(self, source: str, config: dict) -> List[Article]:
        seen_urls: Set[str] = set()
        collected: List[Article] = []

        for feed_url in self._discover_feed_urls(config["listing_url"], config["feed_candidates"]):
            collected.extend(self._collect_from_feed(source, feed_url, seen_urls))
            if len(collected) >= self.max_articles_per_source:
                return collected[: self.max_articles_per_source]

        if len(collected) < self.max_articles_per_source:
            remaining = self.max_articles_per_source - len(collected)
            collected.extend(self._collect_from_listing(source, config["listing_url"], seen_urls, remaining))

        return collected[: self.max_articles_per_source]

    def _discover_feed_urls(self, listing_url: str, candidates: List[str]) -> List[str]:
        urls = list(candidates)
        html = self._fetch_text(listing_url)
        if not html:
            return urls
        for m in re.finditer(r"<link[^>]+rel=['\"]alternate['\"][^>]*>", html, flags=re.I):
            tag = m.group(0)
            if not re.search(r"type=['\"][^'\"]*(rss|atom)[^'\"]*['\"]", tag, flags=re.I):
                continue
            href_m = re.search(r"href=['\"]([^'\"]+)['\"]", tag, flags=re.I)
            if href_m:
                feed = urljoin(listing_url, href_m.group(1))
                if feed not in urls:
                    urls.insert(0, feed)
        return urls

    def _collect_from_feed(self, source: str, feed_url: str, seen_urls: Set[str]) -> List[Article]:
        if not self._can_fetch(feed_url):
            return []
        xml_text = self._fetch_text(feed_url)
        if not xml_text:
            return []

        results = []
        for item in self._parse_feed_items(xml_text):
            url = item.get("link")
            if not url or url in seen_urls:
                continue
            date_iso = parse_date_to_iso(item.get("date"))
            if not date_iso or not in_date_window(date_iso, self.start_dt, self.end_dt):
                continue
            article = Article(
                source=source,
                title=item.get("title") or "Untitled",
                url=url,
                date_iso=date_iso,
                excerpt=safe_excerpt(item.get("summary") or ""),
                text_for_nlp=f"{item.get('title','')}. {item.get('summary','')}",
            )
            seen_urls.add(url)
            results.append(self._enrich_article(article))
        if results:
            LOGGER.info("Feed strategy succeeded for %s (%d)", source, len(results))
        return results

    def _parse_feed_items(self, xml_text: str) -> List[dict]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        items = []
        for node in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            title = _text(node, ["title", "{http://www.w3.org/2005/Atom}title"])
            link = _text(node, ["link", "{http://www.w3.org/2005/Atom}link"])
            if not link:
                atom_link = node.find("{http://www.w3.org/2005/Atom}link")
                if atom_link is not None:
                    link = atom_link.attrib.get("href")
            date = _text(node, ["pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published"])
            summary = _text(node, ["description", "summary", "{http://www.w3.org/2005/Atom}summary"])
            items.append({"title": title, "link": link, "date": date, "summary": summary})
        return items

    def _collect_from_listing(self, source: str, listing_url: str, seen_urls: Set[str], limit: int) -> List[Article]:
        if not self._can_fetch(listing_url):
            return []
        html = self._fetch_text(listing_url)
        if not html:
            return []

        links = []
        for m in re.finditer(r"<a[^>]+href=['\"]([^'\"]+)['\"]", html, flags=re.I):
            url = urljoin(listing_url, m.group(1))
            if urlparse(url).netloc != urlparse(listing_url).netloc:
                continue
            if "/news/" not in url and "/category/news/" not in url:
                continue
            links.append(url)

        unique_links = list(dict.fromkeys(links))
        results = []
        for url in unique_links:
            if len(results) >= limit or url in seen_urls or not self._can_fetch(url):
                continue
            page = self._fetch_text(url)
            if not page:
                continue
            meta = extract_article_metadata(page, url)
            if not meta.get("date_iso") or not in_date_window(meta["date_iso"], self.start_dt, self.end_dt):
                continue
            results.append(
                Article(
                    source=source,
                    title=meta["title"],
                    url=url,
                    date_iso=meta["date_iso"],
                    excerpt=safe_excerpt(meta["excerpt"]),
                    text_for_nlp=meta.get("full_text") or f"{meta['title']}. {meta['excerpt']}",
                )
            )
            seen_urls.add(url)
        if results:
            LOGGER.info("HTML fallback collected %d for %s", len(results), source)
        return results

    def _enrich_article(self, article: Article) -> Article:
        if not self._can_fetch(article.url):
            return article
        html = self._fetch_text(article.url)
        if not html:
            return article
        meta = extract_article_metadata(html, article.url)
        if meta.get("title") and meta["title"] != "Untitled":
            article.title = meta["title"]
        if meta.get("date_iso"):
            article.date_iso = meta["date_iso"]
        if meta.get("excerpt"):
            article.excerpt = safe_excerpt(meta["excerpt"])
        if meta.get("full_text"):
            article.text_for_nlp = meta["full_text"]
        return article

    def _fetch_text(self, url: str) -> Optional[str]:
        cache_file = cache_path_for_url(self.cache_dir, url)
        if self.use_cache and cache_file.exists():
            return cache_file.read_text(encoding="utf-8", errors="ignore")
        self.limiter.wait(url)
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.8"})
            with urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                if self.use_cache:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(body, encoding="utf-8")
                return body
        except Exception as exc:
            LOGGER.warning("Network error for %s: %s", url, exc)
            return None

    def _can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._robots:
            rp = RobotFileParser()
            rp.set_url(f"{root}/robots.txt")
            try:
                rp.read()
                self._robots[root] = rp
            except Exception:
                self._robots[root] = None
        rp = self._robots[root]
        if rp is None:
            return True
        return rp.can_fetch(USER_AGENT, url)


def _text(node, tags: List[str]) -> str:
    for t in tags:
        found = node.find(t)
        if found is not None and found.text:
            return found.text.strip()
    return ""
