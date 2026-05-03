"""
Headless price refresh — runs in GitHub Actions on a schedule.

Pulls EOD prices for every ticker referenced anywhere in the default
asset-class config (plus the risk-free benchmark and constituents from major
indices), and upserts into data/alpha_terminal.db.

Idempotent: re-running on the same day just no-ops the rows that are already
fresh. Designed to be committed back to the repo by the GitHub Action.

Usage (locally to test):
    python scripts/refresh_data.py
    python scripts/refresh_data.py --max-constituents 200

Environment variables:
    EODHD_KEY          - if set, use EODHD as primary (recommended for cron)
    LOOKBACK_DAYS      - default 1100 (~3y of history)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, date
from pathlib import Path

import duckdb
import pandas as pd

# ─────────────────────────────────────────────────────────────────
# Match app.py's defaults (kept in sync manually — small surface)
# ─────────────────────────────────────────────────────────────────
DEFAULT_TICKERS: dict[str, dict[str, str]] = {
    "Equity": {
        "S&P 500": "^GSPC", "Nasdaq 100": "^NDX", "Russell 2000": "^RUT",
        "FTSE 100": "^FTSE", "DAX": "^GDAXI", "Nikkei 225": "^N225",
        "Nifty 50": "^NSEI", "Hang Seng": "^HSI",
    },
    "Fixed Income": {
        "US 10Y Yield": "^TNX", "US 2Y Yield": "^IRX", "US Treasuries": "TLT",
        "IG Corp": "LQD", "HY Corp": "HYG", "EM Bonds": "EMB",
        "TIPS": "TIP", "Mortgage": "MBB",
    },
    "Commodity": {
        "Gold": "GC=F", "Silver": "SI=F", "Platinum": "PL=F",
        "Crude Oil (WTI)": "CL=F", "Brent": "BZ=F", "Natural Gas": "NG=F",
        "Copper": "HG=F", "Corn": "ZC=F",
    },
    "Alternative": {
        "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD", "DXY": "DX-Y.NYB",
        "EUR/USD": "EURUSD=X", "USD/JPY": "JPY=X", "VIX": "^VIX",
        "Global REIT": "VNQI", "US REIT": "VNQ",
    },
}
DEFAULT_BENCHMARKS = ["AGG", "DJP"]  # extras referenced as RRG benchmarks
RISK_FREE_TICKER = "^IRX"

WIKI_INDEX_MAP = {
    "S&P 500":    ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 0, "Symbol", "GICS Sector", "US"),
    "Nifty 50":   ("https://en.wikipedia.org/wiki/NIFTY_50", 2, "Symbol", "Sector", "India"),
    "FTSE 100":   ("https://en.wikipedia.org/wiki/FTSE_100_Index", 4, "Ticker", "FTSE industry classification benchmark sector[18]", "UK"),
    "DAX":        ("https://en.wikipedia.org/wiki/DAX", 4, "Ticker", "Prime Standard Sector", "Germany"),
    "Dow Jones":  ("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average", 2, "Symbol", "Industry", "US"),
    "Nasdaq 100": ("https://en.wikipedia.org/wiki/Nasdaq-100", 4, "Ticker", "GICS Sector", "US"),
}
YAHOO_SUFFIX = {"Nifty 50": ".NS", "FTSE 100": ".L", "DAX": ".DE"}
DEFAULT_CONSTITUENT_INDICES = ["S&P 500", "Nifty 50", "FTSE 100", "DAX", "Dow Jones"]

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "alpha_terminal.db"


# ─────────────────────────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────────────────────────
def get_db() -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            ticker     VARCHAR NOT NULL,
            date       DATE     NOT NULL,
            close      DOUBLE,
            provider   VARCHAR,
            fetched_at TIMESTAMP,
            PRIMARY KEY (ticker, date)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS presets (
            name        VARCHAR PRIMARY KEY,
            config_json VARCHAR NOT NULL,
            created_at  TIMESTAMP
        )
    """)
    return con


def upsert_prices(con, rows: list[tuple], provider: str) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows, columns=["ticker", "date", "close"])
    df["provider"] = provider
    df["fetched_at"] = datetime.now()
    con.register("incoming", df)
    con.execute("""
        INSERT INTO prices SELECT * FROM incoming
        ON CONFLICT (ticker, date) DO UPDATE
            SET close = EXCLUDED.close,
                provider = EXCLUDED.provider,
                fetched_at = EXCLUDED.fetched_at
    """)
    con.unregister("incoming")


# ─────────────────────────────────────────────────────────────────
# Wikipedia constituent scraper
# ─────────────────────────────────────────────────────────────────
def scrape_index_constituents(index_name: str) -> list[str]:
    if index_name not in WIKI_INDEX_MAP:
        return []
    url, tbl_idx, ticker_col, _, _ = WIKI_INDEX_MAP[index_name]
    try:
        tables = pd.read_html(url)
        df = tables[tbl_idx].copy()
    except Exception as e:
        print(f"  ⚠️  Wikipedia scrape failed for {index_name}: {e}", file=sys.stderr)
        return []
    df.columns = [str(c).strip() for c in df.columns]
    if ticker_col not in df.columns:
        for c in df.columns:
            if "symbol" in c.lower() or "ticker" in c.lower():
                ticker_col = c; break
    if ticker_col not in df.columns:
        return []
    tickers = df[ticker_col].astype(str).str.strip().tolist()
    suffix = YAHOO_SUFFIX.get(index_name, "")
    if suffix:
        tickers = [t if t.endswith(suffix) else f"{t}{suffix}" for t in tickers]
    return list(dict.fromkeys(tickers))  # dedup, preserve order


# ─────────────────────────────────────────────────────────────────
# Providers
# ─────────────────────────────────────────────────────────────────
def fetch_yfinance(tickers: list[str], start: date, end: date) -> dict[str, pd.Series]:
    import yfinance as yf
    out: dict[str, pd.Series] = {}
    if not tickers:
        return out
    chunk_size = 50
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            df = yf.download(
                tickers=chunk,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False, auto_adjust=True,
                threads=True, group_by="column",
            )
        except Exception as e:
            print(f"  ⚠️  yfinance chunk {i//chunk_size} failed: {e}", file=sys.stderr)
            df = None
        if df is None or df.empty:
            for t in chunk: out[t] = pd.Series(dtype=float, name=t)
            continue
        if len(chunk) == 1:
            out[chunk[0]] = _yf_extract(df, chunk[0])
        else:
            for t in chunk:
                out[t] = _yf_extract(df, t)
        time.sleep(0.5)  # gentle throttle between chunks
    return out


def _yf_extract(df, ticker: str) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(df.columns, pd.MultiIndex):
        try:    close = df["Close"][ticker]
        except (KeyError, TypeError):
            try:    close = df[ticker]["Close"]
            except (KeyError, TypeError): return pd.Series(dtype=float, name=ticker)
    else:
        close = df.get("Close", pd.Series(dtype=float))
    close = pd.to_numeric(close, errors="coerce").dropna()
    close.name = ticker
    return close


def fetch_eodhd(tickers: list[str], start: date, end: date, api_key: str) -> dict[str, pd.Series]:
    import requests
    out: dict[str, pd.Series] = {}

    def yahoo_to_eodhd(yt: str) -> str | None:
        if not yt: return None
        if yt.startswith("^"): return yt[1:] + ".INDX"
        if yt.endswith("-USD") or yt.endswith("-EUR"): return yt + ".CC"
        if yt.endswith("=X"): return yt.replace("=X", "") + ".FOREX"
        if yt.endswith("=F"): return None  # futures not on basic plan
        suffix_map = {".NS": ".NSE", ".BO": ".BSE", ".L": ".LSE", ".DE": ".XETRA",
                      ".PA": ".PA", ".HK": ".HK", ".TO": ".TO", ".AS": ".AS"}
        for ys, es in suffix_map.items():
            if yt.endswith(ys):
                return yt[: -len(ys)] + es
        if "." not in yt:
            return yt + ".US"
        return yt

    def fetch_one(yt: str) -> pd.Series:
        et = yahoo_to_eodhd(yt)
        if not et:
            return pd.Series(dtype=float, name=yt)
        try:
            r = requests.get(
                f"https://eodhd.com/api/eod/{et}",
                params={"api_token": api_key, "fmt": "json",
                        "from": start.strftime("%Y-%m-%d"),
                        "to":   end.strftime("%Y-%m-%d"),
                        "period": "d", "order": "a"},
                timeout=20,
            )
            if r.status_code != 200 or not r.json():
                return pd.Series(dtype=float, name=yt)
            df = pd.DataFrame(r.json())
            close_col = "adjusted_close" if "adjusted_close" in df.columns else "close"
            df["date"] = pd.to_datetime(df["date"])
            return pd.Series(df[close_col].astype(float).values, index=df["date"], name=yt).sort_index()
        except Exception as e:
            print(f"  ⚠️  EODHD fetch failed for {yt}: {e}", file=sys.stderr)
            return pd.Series(dtype=float, name=yt)

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, t): t for t in tickers}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                out[t] = fut.result()
            except Exception:
                out[t] = pd.Series(dtype=float, name=t)
    return out


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh price data into DuckDB.")
    parser.add_argument("--lookback-days", type=int, default=int(os.getenv("LOOKBACK_DAYS", "1100")),
                        help="Days of history to fetch (default 1100 ≈ 3y).")
    parser.add_argument("--max-constituents", type=int, default=int(os.getenv("MAX_CONSTITUENTS", "100")),
                        help="Max constituents to fetch per index (default 100).")
    parser.add_argument("--include-constituents", action="store_true", default=True,
                        help="Fetch index constituents too (default true).")
    parser.add_argument("--no-constituents", dest="include_constituents", action="store_false",
                        help="Skip constituent fetching (faster, smaller DB).")
    args = parser.parse_args()

    print(f"📦 DB: {DB_PATH}")
    print(f"📅 Lookback: {args.lookback_days} days")

    # Build the universe of tickers to fetch
    universe: set[str] = set()
    for asset in DEFAULT_TICKERS.values():
        universe.update(asset.values())
    universe.update(DEFAULT_BENCHMARKS)
    universe.add(RISK_FREE_TICKER)

    if args.include_constituents:
        print(f"🔍 Scraping constituents from {len(DEFAULT_CONSTITUENT_INDICES)} indices…")
        for idx in DEFAULT_CONSTITUENT_INDICES:
            cons = scrape_index_constituents(idx)
            print(f"  · {idx}: {len(cons)} constituents")
            universe.update(cons[: args.max_constituents])

    universe = sorted(universe)
    print(f"📈 Total tickers to fetch: {len(universe)}")

    # Determine provider
    eodhd_key = os.getenv("EODHD_KEY", "").strip()
    end = date.today()
    start = end - timedelta(days=args.lookback_days)

    print(f"🌐 Provider: {'eodhd' if eodhd_key else 'yfinance'}")
    t0 = time.time()
    if eodhd_key:
        prices = fetch_eodhd(universe, start, end, eodhd_key)
        # Backfill any empty results with yfinance
        missing = [t for t in universe if t not in prices or prices[t].empty]
        if missing:
            print(f"  ↪︎ Falling back to yfinance for {len(missing)} missing tickers…")
            yf_prices = fetch_yfinance(missing, start, end)
            for t, s in yf_prices.items():
                if not s.empty:
                    prices[t] = s
    else:
        prices = fetch_yfinance(universe, start, end)
    print(f"⏱️  Fetch took {time.time() - t0:.1f}s")

    # Upsert
    rows = []
    successful = 0
    for t, ser in prices.items():
        if ser.empty:
            continue
        successful += 1
        for dt, close in ser.items():
            rows.append((t, pd.Timestamp(dt).date(), float(close)))

    print(f"✅ Got data for {successful}/{len(universe)} tickers ({len(rows):,} rows)")

    if rows:
        con = get_db()
        provider_label = "eodhd" if eodhd_key else "yfinance"
        upsert_prices(con, rows, provider_label)
        # Final stats
        stats = con.execute("""
            SELECT COUNT(DISTINCT ticker) AS tickers, COUNT(*) AS rows,
                   MIN(date) AS first, MAX(date) AS last
            FROM prices
        """).fetchone()
        print(f"💾 DB now has: {stats[0]} tickers · {stats[1]:,} rows · {stats[2]} → {stats[3]}")
        con.close()
    else:
        print("⚠️  No rows to upsert (all fetches failed).")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
