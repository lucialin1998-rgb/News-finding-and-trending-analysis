# Music News Weekly Trend Analyzer (Beginner Friendly)

This project collects **public** music-industry news from the last 7 days (Europe/London time) from:

1. Music Week — https://www.musicweek.com/news
2. Music Business Worldwide (MBW) — https://www.musicbusinessworldwide.com/category/news/

It produces:
- A markdown weekly report
- CSV of articles
- CSV of extracted entities

> Legal/ethical design: the scraper checks `robots.txt`, uses polite rate limits, does not bypass login/paywalls, and stores only limited metadata + short excerpts (<=300 chars).

---

## What gets generated

In `output/`:
- `weekly_report_YYYY-MM-DD.md`
- `articles_YYYY-MM-DD.csv`
- `entities_YYYY-MM-DD.csv`

The report includes:
- Articles table
- Entities per article
- Top entities by frequency
- Trend analysis with evidence (article title + source + date)
- Compliance/limitations note

---

## Windows setup (Python 3.11+)

### 1) Install Python
- Download Python 3.11 or newer from: https://www.python.org/downloads/
- During install, check **"Add Python to PATH"**.

### 2) Open terminal in the project folder
Use **PowerShell** or **Command Prompt**, then:

```powershell
cd path\to\News-finding-and-trending-analysis
```

### 3) Create a virtual environment
```powershell
python -m venv .venv
```

### 4) Activate the virtual environment
PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```

Command Prompt:
```cmd
.venv\Scripts\activate.bat
```

### 5) Install dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 6) (Optional but recommended) Install spaCy English model
Entity extraction works without it (fallback mode), but better with model:

```powershell
python -m spacy download en_core_web_sm
```

### 7) Run with one command
```powershell
python main.py
```

That is the default run for the last 7 days.

---

## CLI options

```bash
python main.py --days 7 --outdir output --max-articles-per-source 80 --verbose
```

Flags:
- `--days 7`: number of days to include (default 7)
- `--outdir output`: output folder
- `--max-articles-per-source 80`: cap articles per source
- `--no-cache`: disable local HTML cache
- `--verbose`: extra logs

---

## Troubleshooting

### "No articles found"
Possible causes:
- No posts in date range
- Website structure changed
- Temporary network issue
- robots.txt disallows a route

Try:
```bash
python main.py --days 14 --verbose --no-cache
```

### SSL / connection errors
- Check internet connectivity
- Try again after a few minutes
- Some environments block outbound requests

### spaCy model warning
If you see a warning about `en_core_web_sm`, install it:
```bash
python -m spacy download en_core_web_sm
```
If not installed, the app still runs with rule-based fallback extraction.

---

## Notes on compliance

- Public pages only
- No login/paywall bypass
- robots.txt respected for feed/listing/article fetches
- Stored data intentionally limited to metadata + short excerpt + generated summary

