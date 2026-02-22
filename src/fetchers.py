from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import requests
from bs4 import BeautifulSoup

from .parser import extract_article_metadata
from .utils import (
    Article,
    DomainLimiter,
    cache_path_for_url,
    canonicalize_url,
    in_date_window,
    parse_date_to_iso,
    safe_excerpt,
)

LOGGER = logging.getLogger(__name__)
USER_AGENT = "NewsTrendBot/1.1 (+educational-project; respectful scraping)"

SOURCES = {
    "Music Week": {
        "listing_url": "https://www.musicweek.com/news",
        "mode": "html_primary",
    },
    "Music Business Worldwide": {
        "listing_url": "https://www.musicbusinessworldwide.com/category/news/",
        "rss_url": "https://www.musicbusinessworldwide.com/feed/",
        "mode": "rss_primary",
    },
}


class NewsCollector:
    def __init__(self, start_dt, end_dt, max_articles_per_source: int, cache_dir: Path, use_cache: bool, timeout: int = 25):
        self.start_dt = start_dt
        self.end_dt = end_dt
        self.max_articles_per_source = max_articles_per_source
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-GB,en;q=0.8"})
        self.limiter = DomainLimiter(1.0)
        self._robots: Dict[str, Optional[RobotFileParser]] = {}
        self.diagnostics: Dict[str, dict] = {}

    def collect(self) -> Dict[str, List[Article]]:
        result: Dict[str, List[Article]] = {}
        for source, cfg in SOURCES.items():
            articles, diag = self._collect_source(source, cfg)
            self.diagnostics[source] = diag
            result[source] = articles
        return result

    def _collect_source(self, source: str, cfg: dict) -> Tuple[List[Article], dict]:
        diag = {
            "urls_discovered": 0,
            "urls_attempted": 0,
            "articles_fetched": 0,
            "articles_kept": 0,
            "dropped_out_of_range": 0,
            "kept_missing_date": 0,
            "request_failed": 0,
            "robots_disallow": 0,
            "listing_changed": 0,
            "paywall_or_no_content": 0,
            "deduped": 0,
        }
        seen: Set[str] = set()
        collected: List[Article] = []

        mode = cfg.get("mode")
        if mode == "rss_primary":
            collected.extend(self._collect_from_rss(source, cfg.get("rss_url", ""), seen, diag))
            if len(collected) < self.max_articles_per_source:
                collected.extend(self._collect_from_listing(source, cfg["listing_url"], seen, diag))
        else:
            collected.extend(self._collect_from_listing(source, cfg["listing_url"], seen, diag))
            if len(collected) < self.max_articles_per_source and cfg.get("rss_url"):
                collected.extend(self._collect_from_rss(source, cfg.get("rss_url", ""), seen, diag))

        deduped = []
        for article in collected:
            key = canonicalize_url(article.url)
            if key in seen:
                diag["deduped"] += 1
                continue
            seen.add(key)
            deduped.append(article)

        deduped = deduped[: self.max_articles_per_source]
        diag["articles_kept"] = len(deduped)
        LOGGER.info(
            "%s diagnostics: discovered=%d attempted=%d fetched=%d kept=%d dropped_out_of_range=%d kept_missing_date=%d request_failed=%d robots_disallow=%d",
            source,
            diag["urls_discovered"],
            diag["urls_attempted"],
            diag["articles_fetched"],
            diag["articles_kept"],
            diag["dropped_out_of_range"],
            diag["kept_missing_date"],
            diag["request_failed"],
            diag["robots_disallow"],
        )
        return deduped, diag

    def _collect_from_rss(self, source: str, rss_url: str, seen: Set[str], diag: dict) -> List[Article]:
        if not rss_url:
            return []
        if not self._can_fetch(rss_url):
            diag["robots_disallow"] += 1
            return []
        xml = self._fetch_text(rss_url, diag)
        if not xml:
            return []

        feed = feedparser.parse(xml)
        output: List[Article] = []
        for entry in feed.entries:
            url = entry.get("link")
            if not url:
                continue
            diag["urls_discovered"] += 1
            if canonicalize_url(url) in seen:
                continue
            article = Article(
                source=source,
                title_en=(entry.get("title") or "Untitled").strip(),
                url=url,
                date=parse_date_to_iso(entry.get("published") or entry.get("updated") or "") or "",
                excerpt_en=safe_excerpt(BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True)),
                text_for_nlp="",
            )
            enriched = self._fetch_article_page(article, diag)
            if self._should_keep(enriched, diag):
                output.append(enriched)
        return output

    def _collect_from_listing(self, source: str, listing_url: str, seen: Set[str], diag: dict) -> List[Article]:
        if not self._can_fetch(listing_url):
            diag["robots_disallow"] += 1
            return []
        html = self._fetch_text(listing_url, diag)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for link in soup.select("a[href]"):
            href = link.get("href")
            if not href:
                continue
            full = urljoin(listing_url, href)
            if urlparse(full).netloc != urlparse(listing_url).netloc:
                continue
            if source == "Music Week" and "/news/" not in full:
                continue
            if source == "Music Business Worldwide" and "/" not in full:
                continue
            urls.append(full)

        unique_urls = list(dict.fromkeys(urls))
        diag["urls_discovered"] += len(unique_urls)
        if not unique_urls:
            diag["listing_changed"] += 1
            LOGGER.warning("%s listing page structure may have changed: no candidate links found", source)

        output: List[Article] = []
        for url in unique_urls:
            if len(output) >= self.max_articles_per_source:
                break
            if canonicalize_url(url) in seen:
                continue
            article = Article(source=source, title_en="Untitled", url=url)
            enriched = self._fetch_article_page(article, diag)
            if self._should_keep(enriched, diag):
                output.append(enriched)
        return output

    def _should_keep(self, article: Article, diag: dict) -> bool:
        if article.date:
            if not in_date_window(article.date, self.start_dt, self.end_dt):
                diag["dropped_out_of_range"] += 1
                return False
        else:
            diag["kept_missing_date"] += 1
        return True

    def _fetch_article_page(self, article: Article, diag: dict) -> Article:
        if not self._can_fetch(article.url):
            diag["robots_disallow"] += 1
            return article
        diag["urls_attempted"] += 1
        html = self._fetch_text(article.url, diag)
        if not html:
            return article
        diag["articles_fetched"] += 1
        parsed = extract_article_metadata(html, article.url)
        article.url = parsed.get("canonical_url") or article.url
        article.title_en = parsed.get("title") or article.title_en
        article.date = parsed.get("date") or article.date
        article.excerpt_en = safe_excerpt(parsed.get("excerpt", "") or article.excerpt_en)
        article.text_for_nlp = parsed.get("text") or f"{article.title_en}. {article.excerpt_en}"
        if not article.excerpt_en and not article.text_for_nlp:
            diag["paywall_or_no_content"] += 1
        return article

    def _fetch_text(self, url: str, diag: dict) -> Optional[str]:
        cache_file = cache_path_for_url(self.cache_dir, url)
        if self.use_cache and cache_file.exists():
            return cache_file.read_text(encoding="utf-8", errors="ignore")
        self.limiter.wait(url)
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code >= 400:
                diag["request_failed"] += 1
                LOGGER.warning("HTTP %s for %s", response.status_code, url)
                return None
            text = response.text
            if self.use_cache:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(text, encoding="utf-8")
            return text
        except requests.RequestException as exc:
            diag["request_failed"] += 1
            LOGGER.warning("Request failed for %s: %s", url, exc)
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
        return True if rp is None else rp.can_fetch(USER_AGENT, url)
