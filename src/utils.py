from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")


@dataclass
class Article:
    source: str
    title_en: str
    url: str
    date: str = ""
    excerpt_en: str = ""
    summary_en: List[str] = field(default_factory=list)
    title_zh: str = ""
    excerpt_zh: str = ""
    summary_zh: List[str] = field(default_factory=list)
    text_for_nlp: str = ""


class DomainLimiter:
    def __init__(self, min_interval_seconds: float = 1.0):
        self.min_interval_seconds = min_interval_seconds
        self._last_request_by_domain: Dict[str, float] = {}

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        now = time.time()
        last = self._last_request_by_domain.get(domain, 0.0)
        sleep_for = self.min_interval_seconds - (now - last)
        if sleep_for > 0:
            time.sleep(sleep_for)
        self._last_request_by_domain[domain] = time.time()


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def date_range_london(days: int) -> Tuple[datetime, datetime]:
    end = datetime.now(LONDON_TZ)
    start = (end - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, end


def today_london_str() -> str:
    return datetime.now(LONDON_TZ).strftime("%Y-%m-%d")


def parse_date_to_iso(raw: str | None) -> Optional[str]:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    # dateutil handles broad formats.
    try:
        from dateutil import parser as date_parser

        dt = date_parser.parse(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LONDON_TZ)
    return dt.astimezone(LONDON_TZ).isoformat()


def in_date_window(date_iso: str, start_dt: datetime, end_dt: datetime) -> bool:
    try:
        dt = datetime.fromisoformat(date_iso)
    except Exception:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LONDON_TZ)
    dt = dt.astimezone(LONDON_TZ)
    return start_dt <= dt <= end_dt


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = re.sub(r"/+", "/", parsed.path or "/")
    path = path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", "", ""))


def dedupe_articles(articles: Iterable[Article]) -> List[Article]:
    seen = set()
    unique: List[Article] = []
    for article in articles:
        key = canonicalize_url(article.url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


def safe_excerpt(text: str, max_len: int = 300) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."


def cache_path_for_url(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.html"
