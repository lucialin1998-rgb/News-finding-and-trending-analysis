# Music News Weekly Trend Analyzer (EN + ZH)

Beginner-friendly project to collect public news from:
- Music Week: https://www.musicweek.com/news
- Music Business Worldwide: https://www.musicbusinessworldwide.com/category/news/

Then generate bilingual weekly outputs:
- `output/weekly_report_YYYY-MM-DD.md`
- `output/articles_YYYY-MM-DD.csv`
- `output/entities_YYYY-MM-DD.csv`

## Quick start (Windows / Linux / macOS)

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python main.py --days 7 --verbose
```

Single-command run after setup:

```bash
python main.py
```

## What changed to avoid empty outputs

- Stronger diagnostics in logs per source:
  - URLs discovered
  - URLs attempted
  - Articles fetched
  - Kept in range
  - Dropped out-of-range
  - Kept with missing/unparseable dates
  - Request failures / robots blocks
- Missing/unparseable date **no longer causes drop**. Date is kept empty.
- MBW uses RSS primary (`/feed/`) with listing fallback.
- Music Week uses HTML listing primary.

## Translation behavior

- Uses `argos-translate` (free).
- Tries to auto-install EN→ZH model once and cache under `cache/argos_models`.
- If translation fails, output remains English and Chinese fields stay empty.

## Compliance

- Public pages only.
- Respects robots.txt.
- No login/paywall bypass.
- Stores only title, URL, date, short excerpt (<=300 chars), and generated summary.
