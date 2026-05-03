# ⚡ Grok Alpha Terminal

Holistic global momentum dashboard. Tracks **absolute** and **relative** momentum across Equity, Fixed Income, Commodity, and Alternative asset classes — backed by an academically grounded methodology stack (RRG, Antonacci dual momentum, Jegadeesh-Titman 12-1).

![status](https://img.shields.io/badge/status-personal--use-orange) ![python](https://img.shields.io/badge/python-3.10%2B-blue) ![streamlit](https://img.shields.io/badge/streamlit-cloud--ready-red)

---

## How persistence works (read this first)

Streamlit Community Cloud's filesystem is ephemeral — every redeploy wipes runtime files. So we use a **GitHub-Actions-driven persistence pattern**:

```
┌─────────────────────────────────────────────────────────┐
│  GitHub repository                                       │
│  ┌─────────────────────────────────────────────────┐    │
│  │ data/alpha_terminal.db   ← committed; durable   │    │
│  └─────────────────────────────────────────────────┘    │
│             ▲                            │               │
│             │ commits                    │ reads on      │
│             │ daily                      │ deploy        │
│  ┌──────────┴───────────┐   ┌────────────▼──────────┐   │
│  │ GitHub Actions cron  │   │ Streamlit Cloud app   │   │
│  │ scripts/refresh_     │   │ Bootstraps from repo  │   │
│  │ data.py              │   │ → /tmp/ for runtime   │   │
│  └──────────────────────┘   └───────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**The result:**
- ✅ **Data survives every redeploy.** When you push code, Cloud rebuilds; the DB is in the repo, so it's there.
- ✅ **Daily auto-updates** at 22:30 UTC weekdays (after US market close).
- ✅ **Free.** GitHub Actions and Streamlit Cloud are both free for personal use.
- ✅ **Version-controlled history.** Git history is a backup — every nightly DB state is recoverable.
- ⚠️ Repo grows ~1–2 MB/year. Negligible.

You can also trigger a refresh manually any time from the GitHub Actions tab → "Run workflow."

---

## Quickstart — Local

```bash
git clone https://github.com/<your-username>/grok-alpha-terminal.git
cd grok-alpha-terminal

pip install -r requirements.txt

# Optional: pre-populate the DB locally
python scripts/refresh_data.py

streamlit run app.py
```

For EODHD as primary provider:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit with your EODHD_KEY
```

`yfinance` is the default and needs no key.

---

## Deploy to GitHub + Streamlit Cloud

### One-time setup

1. **Push the repo** to GitHub (private or public both work).
2. **Enable workflow permissions:**
   Repo → Settings → Actions → General → Workflow permissions → select **"Read and write permissions"** → Save. (This lets the cron job commit the DB back.)
3. **(Optional) Add EODHD key** as a repo secret:
   Repo → Settings → Secrets and variables → Actions → New repository secret → name `EODHD_KEY`, paste your token.
4. **Trigger first refresh manually** to populate the DB:
   Repo → Actions tab → "Daily Price Refresh" → "Run workflow" → wait ~3 min. You'll see a new commit `📈 Daily price refresh ...`.
5. **Deploy on Streamlit Cloud:**
   - Go to [share.streamlit.io](https://share.streamlit.io) → **Create app**
   - Repository: `<your-username>/grok-alpha-terminal`
   - Branch: `main`
   - Main file: `app.py`
   - Advanced settings → Secrets (if using EODHD): paste
     ```toml
     EODHD_KEY = "your_eodhd_token_here"
     ```
   - Deploy. ~3 minutes for first build.

### Ongoing

- **Code changes** — push to `main` → Cloud auto-redeploys in ~1 min.
- **Daily data refresh** — happens automatically at 22:30 UTC. Each refresh triggers a Cloud redeploy with fresh data.
- **Manual data refresh** — Actions tab → Run workflow.

⚠️ **Watch the Actions minutes** if your repo is private: free tier gives 2,000 min/month. This workflow takes ~3–5 min/run × ~22 weekdays = ~110 min/month. Public repos have unlimited Actions minutes.

⚠️ **60-day inactivity rule:** GitHub disables scheduled workflows after 60 days of repo inactivity. Our daily commit prevents this — but be aware if you stop using the app for >60 days, the cron stops.

---

## What it does

### Holistic dashboard — three switchable views
- **Heatmap** — 4 asset classes × N timeframes
- **RRG (Relative Rotation Graph)** — JdK RS-Ratio (X) vs RS-Momentum (Y), 12-week tails, configurable benchmark
- **Sparklines** — 90-day mini-charts color-coded by 1M sign

### Drill-down per asset class
- Instrument table with all timeframes + Antonacci absolute momentum + cross-sectional relative-momentum z-score
- For Equity: Wikipedia-driven constituent fetching (S&P 500, Nifty 50, FTSE 100, DAX, Dow, Nasdaq 100)
  - Sub-tabs: By Geography · By Sector · Top-N Momentum · Market Breadth

### Configurable from the UI (Settings page)
- Tickers per asset class
- Timeframes (add/remove freely — labels propagate everywhere)
- Composite score weights
- Skip-month toggle (12-1 Jegadeesh-Titman convention)
- Breadth thresholds (DMA periods, RSI levels)
- RRG parameters (smoothing windows, tail length)
- Primary data provider (yfinance ↔ EODHD)

### Presets page
Save/load entire configurations under a name.

### Data Status page
Inspect what's cached: ticker counts, date ranges, staleness flags, prune controls.

---

## File structure

```
grok-alpha-terminal/
├── app.py                              # main Streamlit app
├── requirements.txt                    # used by both app and refresh script
├── README.md
├── .gitignore                          # commits data/alpha_terminal.db; ignores everything else
├── scripts/
│   └── refresh_data.py                 # headless price refresher (cron)
├── data/
│   ├── README.md
│   └── alpha_terminal.db               # ← created on first refresh, committed
├── .github/
│   └── workflows/
│       └── daily_refresh.yml           # GitHub Actions cron
└── .streamlit/
    ├── config.toml                     # dark theme
    └── secrets.toml.example            # template — real secrets stay local
```

---

## DB path resolution

The app picks the DuckDB file location based on environment:

1. `ALPHA_TERMINAL_DB` env var (explicit override)
2. **On Streamlit Cloud** → `/tmp/alpha_terminal.db`, bootstrapped from `data/alpha_terminal.db` on first run.
3. **Local dev** → `data/alpha_terminal.db` directly (the same file the GH Action commits).

This means: locally you see the same data as production. After running the daily cron once, your local repo has the up-to-date DB on every `git pull`.

---

## Methodology references

- **RRG**: de Kempenaer, J. — [relativerotationgraphs.com](https://relativerotationgraphs.com), StockCharts ChartSchool
- **Dual Momentum**: Antonacci, G. (2014) — *Dual Momentum Investing: An Innovative Strategy for Higher Returns with Lower Risk*
- **12-1 Convention**: Jegadeesh, N., & Titman, S. (1993) — *Returns to Buying Winners and Selling Losers*

---

## Caveats

- **yfinance is a scraper** — subject to rate limits. Bulk-download chunks of 50 mitigates this. EODHD is the production-grade alternative.
- **EODHD futures** (`GC=F`, etc.) aren't wired through the translator yet — they fall back to yfinance even when EODHD is primary.
- **Wikipedia scraping** depends on stable table structure. If a scrape fails, fix the entry in `WIKI_INDEX_MAP` in `app.py` and `scripts/refresh_data.py` (kept in sync manually).
- **DuckDB is single-writer.** The cron job and the Cloud app never write the DB simultaneously (the app writes to `/tmp/`, the cron writes to the repo file), so there's no contention. But for multi-user deployment, swap to Postgres / TimescaleDB.
- **Refresh script is read-mostly.** If you change tickers in the UI of the live app, those preferences live in user-session state and don't propagate to the cron. To add new tickers to the daily refresh, edit `DEFAULT_TICKERS` in `scripts/refresh_data.py`. (The two files keep ticker lists in sync; future refactor could move both into a shared `config.py`.)
