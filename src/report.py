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
    entity_rankings_bilingual: List[dict],
    trends_en: List[str],
    trends_zh: List[str],
    diagnostics: Dict[str, dict],
) -> Tuple[Path, Path, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    md_path = outdir / f"weekly_report_{run_date}.md"
    articles_csv = outdir / f"articles_{run_date}.csv"
    entities_csv = outdir / f"entities_{run_date}.csv"

    _write_articles_csv(articles_csv, articles)
    _write_entities_csv(entities_csv, entity_rankings_bilingual)
    _write_markdown(md_path, articles, entity_rankings_bilingual, trends_en, trends_zh, diagnostics)
    return md_path, articles_csv, entities_csv


def _write_articles_csv(path: Path, articles: List[Article]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "source", "date", "title_en", "title_zh", "url", "excerpt_en", "excerpt_zh", "auto_summary_en", "auto_summary_zh"
        ])
        rows = 0
        for a in articles:
            writer.writerow([
                a.source,
                a.date,
                a.title_en,
                a.title_zh,
                a.url,
                a.excerpt_en,
                a.excerpt_zh,
                " | ".join(a.summary_en),
                " | ".join(a.summary_zh),
            ])
            rows += 1
    if rows == 0:
        # intentionally keep header-only file, but with explicit known behavior
        pass


def _write_entities_csv(path: Path, ranking_rows: List[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["entity_en", "entity_zh", "category", "count"])
        for row in ranking_rows:
            writer.writerow([row["entity_en"], row.get("entity_zh", ""), row["category"], row["count"]])


def _write_markdown(
    path: Path,
    articles: List[Article],
    entity_ranking: List[dict],
    trends_en: List[str],
    trends_zh: List[str],
    diagnostics: Dict[str, dict],
) -> None:
    lines: List[str] = []
    lines.append("# Weekly Music Industry Report / 每周音乐行业报告")
    lines.append("")
    lines.append(f"Generated: {datetime.utcnow().isoformat()}Z")

    lines.append("\n## Articles (last 7 days) / 近7天文章")
    lines.append("")
    lines.append("| Source | Date | Title (EN) | 标题(中文) | URL | Excerpt (EN) | 摘要(中文) | Auto summary (EN) | 自动总结(中文) |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for a in articles:
        lines.append(
            f"| {a.source} | {a.date or ''} | {a.title_en.replace('|',' ')} | {a.title_zh.replace('|',' ')} | {a.url} | {a.excerpt_en.replace('|',' ')} | {a.excerpt_zh.replace('|',' ')} | {'<br>'.join(s.replace('|',' ') for s in a.summary_en)} | {'<br>'.join(s.replace('|',' ') for s in a.summary_zh)} |"
        )

    lines.append("\n## Top entities this week / 本周高频实体")
    lines.append("")
    lines.append("| Rank | Entity (EN) | 实体(中文) | Category | Count |")
    lines.append("|---|---|---|---|---|")
    for idx, row in enumerate(entity_ranking[:60], start=1):
        lines.append(f"| {idx} | {row['entity_en']} | {row.get('entity_zh','')} | {row['category']} | {row['count']} |")

    lines.append("\n## Trend analysis / 趋势分析")
    lines.append("")
    for en, zh in zip(trends_en, trends_zh):
        lines.append(en)
        if zh:
            lines.append(zh)

    lines.append("\n## Why output may be empty / 输出可能为空的原因")
    lines.append("")
    for source, diag in diagnostics.items():
        lines.append(
            f"- {source}: robots disallow={diag.get('robots_disallow',0)}, request failed={diag.get('request_failed',0)}, listing page changed={diag.get('listing_changed',0)}, paywall/no content={diag.get('paywall_or_no_content',0)}, date parse failures kept={diag.get('kept_missing_date',0)}"
        )

    lines.append("\n## Limitations & compliance note / 合规说明")
    lines.append("- Public pages only. Respect robots.txt. No login/paywall bypass.")
    lines.append("- Stored data: title, URL, date (if available), excerpt <= 300 chars, generated summary.")

    path.write_text("\n".join(lines), encoding="utf-8")
