from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.fetchers import NewsCollector
from src.nlp import aggregate_entity_frequency, extract_entities, extract_trends, load_spacy_model, summarize_article
from src.report import generate_reports
from src.utils import date_range_london, dedupe_articles, setup_logging, today_london

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect music industry news and generate a weekly trend report.")
    parser.add_argument("--days", type=int, default=7, help="How many days to include (default: 7)")
    parser.add_argument("--outdir", type=str, default="output", help="Output directory for reports")
    parser.add_argument(
        "--max-articles-per-source",
        type=int,
        default=80,
        help="Maximum number of articles to keep per source",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable HTML cache")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
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
    for source, items in by_source.items():
        LOGGER.info("Collected %d article(s) from %s", len(items), source)
        if not items:
            LOGGER.warning(
                "%s yielded zero articles. Possible reasons: robots.txt restrictions, page structure changes, temporary network issues, or no posts in range.",
                source,
            )

    all_articles = dedupe_articles([article for articles in by_source.values() for article in articles])
    all_articles.sort(key=lambda x: x.date_iso, reverse=True)

    if not all_articles:
        LOGGER.error("No articles found in the selected window. Continuing to generate an empty report.")

    nlp_model = load_spacy_model()

    entities_by_article = {}
    for article in all_articles:
        article.summary_bullets = summarize_article(article)
        entities_by_article[article.url] = extract_entities(article, nlp=nlp_model)

    ranked_entities = aggregate_entity_frequency(entities_by_article)
    trends = extract_trends(all_articles)

    run_date = today_london().strftime("%Y-%m-%d")
    md_path, article_csv, entity_csv = generate_reports(
        outdir=Path(args.outdir),
        run_date=run_date,
        articles=all_articles,
        entities_by_article=entities_by_article,
        entity_rankings=ranked_entities,
        trends=trends,
    )

    LOGGER.info("Report written: %s", md_path)
    LOGGER.info("Articles CSV: %s", article_csv)
    LOGGER.info("Entities CSV: %s", entity_csv)
    print("Done. Run complete with command: python main.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
