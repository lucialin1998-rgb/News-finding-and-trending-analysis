from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

LONDON_TZ = ZoneInfo("Europe/London")
UTC_TZ = timezone.utc


@dataclass
class Article:
    source: str
    title: str
    url: str
    date_iso: str
    excerpt: str
    summary_bullets: List[str] = field(default_factory=list)
    text_for_nlp: str = ""


class DomainLimiter:
    def __init__(self, min_interval_seconds: float = 1.0):
        self.min_interval_seconds = min_interval_seconds
        self._last_request: Dict[str, float] = {}

    def wait(self, url: str) -> None:
        domain = urlparse(url).netloc
        now = time.time()
        last = self._last_request.get(domain, 0.0)
        if now - last < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - (now - last))
        self._last_request[domain] = time.time()


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def today_london() -> datetime:
    return datetime.now(LONDON_TZ)


def date_range_london(days: int) -> Tuple[datetime, datetime]:
    end = today_london()
    start = (end - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, end


def parse_date_to_iso(date_str: str | None) -> Optional[str]:
    if not date_str:
        return None
    raw = date_str.strip()
    if not raw:
        return None

    # Try RFC 2822 / feed style
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=LONDON_TZ)
            return dt.astimezone(LONDON_TZ).isoformat()
    except Exception:
        pass

    # Try ISO
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LONDON_TZ)
        return dt.astimezone(LONDON_TZ).isoformat()
    except Exception:
        pass

    formats = [
        "%Y-%m-%d",
        "%d %B %Y",
        "%B %d, %Y",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=LONDON_TZ)
            return dt.isoformat()
        except Exception:
            continue

    return None


def in_date_window(date_iso: str, start: datetime, end: datetime) -> bool:
    try:
        dt = datetime.fromisoformat(date_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LONDON_TZ)
        dt = dt.astimezone(LONDON_TZ)
        return start <= dt <= end
    except Exception:
        return False


def canonicalize_url(url: str) -> str:
    p = urlparse(url)
    path = re.sub(r"/+", "/", p.path or "/").rstrip("/") or "/"
    return urlunparse((p.scheme, p.netloc.lower(), path, "", "", ""))


def dedupe_articles(articles: Iterable[Article]) -> List[Article]:
    seen, out = set(), []
    for a in articles:
        key = canonicalize_url(a.url)
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def safe_excerpt(text: str, max_chars: int = 300) -> str:
    compact = " ".join((text or "").split())
    return compact if len(compact) <= max_chars else compact[: max_chars - 3].rstrip() + "..."


def cache_path_for_url(cache_dir: Path, url: str) -> Path:
    return cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".html")
