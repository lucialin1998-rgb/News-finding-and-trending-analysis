from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.fetchers import NewsCollector
from src.nlp import aggregate_entity_frequency, extract_entities, extract_trends, load_spacy_model, summarize_article
from src.report import generate_reports
from src.translate import Translator
from src.utils import date_range_london, dedupe_articles, setup_logging, today_london_str

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Music Week/MBW news and generate EN+ZH weekly report.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--outdir", type=str, default="output")
    parser.add_argument("--max-articles-per-source", type=int, default=80)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    start_dt, end_dt = date_range_london(args.days)
    LOGGER.info("Date range (Europe/London): %s -> %s", start_dt.isoformat(), end_dt.isoformat())

    collector = NewsCollector(
        start_dt=start_dt,
        end_dt=end_dt,
        max_articles_per_source=args.max_articles_per_source,
        cache_dir=Path("cache"),
        use_cache=not args.no_cache,
    )

    by_source = collector.collect()
    all_articles = dedupe_articles([item for rows in by_source.values() for item in rows])
    all_articles.sort(key=lambda a: a.date or "", reverse=True)

    LOGGER.info("Total articles after dedupe: %d", len(all_articles))
    if not all_articles:
        LOGGER.warning("No articles collected. Check diagnostics in markdown report.")

    nlp = load_spacy_model()
    translator = Translator(cache_dir=Path("cache"))

    entities_by_article = {}
    for article in all_articles:
        article.summary_en = summarize_article(article)
        entities_by_article[article.url] = extract_entities(article, nlp=nlp)

        article.title_zh = translator.translate(article.title_en)
        article.excerpt_zh = translator.translate(article.excerpt_en)
        article.summary_zh = translator.translate_many(article.summary_en)

    entity_rank = aggregate_entity_frequency(entities_by_article)
    entity_rank_bilingual = [
        {
            "entity_en": name,
            "entity_zh": translator.translate(name),
            "category": cat,
            "count": count,
        }
        for name, cat, count in entity_rank
    ]

    trends_en = extract_trends(all_articles)
    trends_zh = translator.translate_many(trends_en)

    run_date = today_london_str()
    md_path, article_csv, entity_csv = generate_reports(
        outdir=Path(args.outdir),
        run_date=run_date,
        articles=all_articles,
        entity_rankings_bilingual=entity_rank_bilingual,
        trends_en=trends_en,
        trends_zh=trends_zh,
        diagnostics=collector.diagnostics,
    )

    LOGGER.info("Report written: %s", md_path)
    LOGGER.info("Articles CSV written: %s (rows=%d)", article_csv, len(all_articles))
    LOGGER.info("Entities CSV written: %s (rows=%d)", entity_csv, len(entity_rank_bilingual))
    print("Done. Run with: python main.py --days 7 --verbose")
    return 0


if __name__ == "__main__":
    sys.exit(main())
