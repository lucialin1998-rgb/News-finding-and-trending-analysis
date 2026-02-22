from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from .utils import Article


def generate_reports(
    outdir: Path,
    run_date: str,
    articles: List[Article],
    entities_by_article: Dict[str, List[dict]],
    entity_rankings: List[Tuple[str, str, int]],
    trends: List[str],
) -> Tuple[Path, Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)

    md_path = outdir / f"weekly_report_{run_date}.md"
    articles_csv = outdir / f"articles_{run_date}.csv"
    entities_csv = outdir / f"entities_{run_date}.csv"

    _write_articles_csv(articles_csv, articles)
    _write_entities_csv(entities_csv, entities_by_article)
    _write_markdown(md_path, articles, entities_by_article, entity_rankings, trends)

    return md_path, articles_csv, entities_csv


def _write_articles_csv(path: Path, articles: List[Article]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "date", "title", "url", "excerpt", "auto_summary"])
        for article in articles:
            writer.writerow(
                [
                    article.source,
                    article.date_iso,
                    article.title,
                    article.url,
                    article.excerpt,
                    " | ".join(article.summary_bullets),
                ]
            )


def _write_entities_csv(path: Path, entities_by_article: Dict[str, List[dict]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["article_url", "entity", "category"])
        for article_url, entities in entities_by_article.items():
            for entity in entities:
                writer.writerow([article_url, entity["entity"], entity["category"]])


def _write_markdown(
    path: Path,
    articles: List[Article],
    entities_by_article: Dict[str, List[dict]],
    entity_rankings: List[Tuple[str, str, int]],
    trends: List[str],
) -> None:
    lines = []
    lines.append("# Weekly News Report")
    lines.append("")
    lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")
    lines.append("")
    lines.append("## Articles (last 7 days)")
    lines.append("")
    lines.append("| Source | Date (ISO) | Title | URL | Excerpt | Auto-summary |")
    lines.append("|---|---|---|---|---|---|")
    for a in articles:
        summary = "<br>".join(bullet.replace("- ", "") for bullet in a.summary_bullets)
        lines.append(
            f"| {a.source} | {a.date_iso} | {a.title.replace('|', ' ')} | {a.url} | {a.excerpt.replace('|', ' ')} | {summary.replace('|', ' ')} |"
        )

    lines.append("")
    lines.append("## Entities by article")
    lines.append("")
    lines.append("| Article title | Source | Date | Entity | Category |")
    lines.append("|---|---|---|---|---|")
    article_lookup = {a.url: a for a in articles}
    for article_url, ents in entities_by_article.items():
        article = article_lookup.get(article_url)
        if not article:
            continue
        for e in ents:
            lines.append(
                f"| {article.title.replace('|', ' ')} | {article.source} | {article.date_iso[:10]} | {e['entity'].replace('|', ' ')} | {e['category']} |"
            )

    lines.append("")
    lines.append("## Top entities this week")
    lines.append("")
    lines.append("| Rank | Entity | Category | Frequency |")
    lines.append("|---|---|---|---|")
    for idx, (entity, category, count) in enumerate(entity_rankings[:50], start=1):
        lines.append(f"| {idx} | {entity.replace('|', ' ')} | {category} | {count} |")

    lines.append("")
    lines.append("## Trend analysis")
    lines.append("")
    lines.extend(trends)

    lines.append("")
    lines.append("## Limitations & compliance note")
    lines.append("")
    lines.append(
        "- This report uses only public pages and respects robots.txt checks before crawling feed/listing/article URLs."
    )
    lines.append("- No paywalls or login-protected areas are accessed.")
    lines.append("- Stored fields are limited to title, URL, date, short excerpt (<=300 chars), and generated summaries.")
    lines.append("- Trend analysis is non-LLM keyword-based and may miss nuance; uncertain findings are marked as insufficient evidence.")

    path.write_text("\n".join(lines), encoding="utf-8")
