"""
GROK ALPHA TERMINAL v4 — Holistic Global Momentum Dashboard
============================================================

Institutional-grade refinement:
  • Pluggable data providers: EODHD primary, yfinance fallback (adapter pattern)
  • DuckDB persistent price store (all historical & daily values, every fetch)
  • Settings panel: editable timeframes, score weights, breadth thresholds,
    RRG params — all from the UI
  • Named presets: save/load entire configurations (tickers + settings)
  • Skip-month (12-1) momentum option per Jegadeesh-Titman (1993)
  • RRG (de Kempenaer) holistic view + dual momentum (Antonacci) decomposition
  • Equity drill-down: geography, sector, top-N, market breadth (configurable)
  • Wikipedia-driven index constituent fetching
  • Data Status panel: ticker count, date range, last fetch, staleness flags

Run:    streamlit run grok_alpha_terminal.py
Deps:   see requirements.txt
"""

from __future__ import annotations

import json
import os
import warnings
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

# ═══════════════════════════════════════════════════════════════════════════════
# 0. PAGE & THEME
# ═══════════════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="Grok Alpha Terminal", layout="wide", page_icon="⚡")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #06080d; color: #c9d1d9; }

[data-testid="stMetricValue"] {
    color: #58e2a0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.05rem !important; font-weight: 600 !important;
}
[data-testid="stMetricLabel"] {
    color: #6e7681 !important;
    font-size: 0.65rem !important;
    text-transform: uppercase; letter-spacing: 0.08em;
}

.status-strip {
    background: linear-gradient(90deg, #0d1117 0%, #161b22 100%);
    border: 1px solid #21262d;
    padding: 10px 18px; border-radius: 8px;
    margin-bottom: 18px;
    font-size: 0.78rem; color: #8b949e;
    font-family: 'JetBrains Mono', monospace;
}

h1, h2, h3, h4 { font-family: 'Inter', sans-serif !important; font-weight: 600 !important; letter-spacing: -0.01em; }

[data-testid="stTabs"] button { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; }
section[data-testid="stSidebar"] { background: #0a0d13; border-right: 1px solid #21262d; }

.stButton > button {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.76rem !important;
    border-radius: 6px !important;
    border: 1px solid #21262d !important;
}
.stButton > button:hover { border-color: #58e2a0 !important; color: #58e2a0 !important; }

[data-testid="stDataFrame"] { border: 1px solid #21262d; border-radius: 8px; }

.section-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, #21262d, transparent);
    margin: 24px 0;
}

.badge {
    display: inline-block;
    padding: 2px 8px;
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    color: #8b949e;
    margin-right: 6px;
}
.badge.green { color: #58e2a0; border-color: rgba(88,226,160,0.3); }
.badge.red   { color: #f85149; border-color: rgba(248,81,73,0.3); }
.badge.amber { color: #f0883e; border-color: rgba(240,136,62,0.3); }
</style>
""",
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CONSTANTS & DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════════
def _resolve_db_path() -> str:
    """
    Resolve the DuckDB file path with this priority:
      1. ALPHA_TERMINAL_DB env var (explicit override)
      2. /tmp/alpha_terminal.db on Streamlit Cloud (writable + fast)
         — copied from the repo's data/alpha_terminal.db on first run if present.
         This pattern survives Cloud redeploys because the repo file is the source of truth.
      3. data/alpha_terminal.db locally (committed; persists with the repo)
    """
    if os.getenv("ALPHA_TERMINAL_DB"):
        return os.environ["ALPHA_TERMINAL_DB"]

    repo_db = os.path.join("data", "alpha_terminal.db")
    on_cloud = os.path.exists("/mount/src") or os.getenv("STREAMLIT_SHARING_MODE") or os.getenv("HOSTNAME", "").startswith("streamlit")

    if on_cloud:
        runtime_db = "/tmp/alpha_terminal.db"
        # Bootstrap from repo on first run (file from git is read-only-ish; copy to /tmp for writes)
        if not os.path.exists(runtime_db) and os.path.exists(repo_db):
            import shutil
            shutil.copy2(repo_db, runtime_db)
        return runtime_db

    # Local: use the repo file directly
    os.makedirs("data", exist_ok=True)
    return repo_db


DB_PATH = _resolve_db_path()
RISK_FREE_TICKER_YF = "^IRX"   # 13-week T-bill yield (Yahoo)
RISK_FREE_TICKER_EODHD = "IRX.INDX"

DEFAULT_TIMEFRAMES = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252, "3Y": 756}
DEFAULT_SCORE_WEIGHTS = {"1M": 0.15, "3M": 0.25, "6M": 0.30, "1Y": 0.30}
DEFAULT_BREADTH = {
    "dma_short": 50,
    "dma_long":  200,
    "rsi_period": 21,
    "rsi_strong": 55,
    "rsi_weak":   45,
    "rsi_oversold":   30,
    "rsi_overbought": 70,
}
DEFAULT_RRG = {
    "rs_window":  14,
    "mom_window": 14,
    "tail_weeks": 12,
}
DEFAULT_LOOKBACK_DAYS = 1100  # ~3y for 3Y timeframe + buffer

# ── Default tickers per asset class (Yahoo notation) ──
DEFAULT_TICKERS: dict[str, dict[str, str]] = {
    "Equity": {
        "S&P 500":      "^GSPC",
        "Nasdaq 100":   "^NDX",
        "Russell 2000": "^RUT",
        "FTSE 100":     "^FTSE",
        "DAX":          "^GDAXI",
        "Nikkei 225":   "^N225",
        "Nifty 50":     "^NSEI",
        "Hang Seng":    "^HSI",
    },
    "Fixed Income": {
        "US 10Y Yield":   "^TNX",
        "US 2Y Yield":    "^IRX",
        "US Treasuries":  "TLT",
        "IG Corp":        "LQD",
        "HY Corp":        "HYG",
        "EM Bonds":       "EMB",
        "TIPS":           "TIP",
        "Mortgage":       "MBB",
    },
    "Commodity": {
        "Gold":            "GC=F",
        "Silver":          "SI=F",
        "Platinum":        "PL=F",
        "Crude Oil (WTI)": "CL=F",
        "Brent":           "BZ=F",
        "Natural Gas":     "NG=F",
        "Copper":          "HG=F",
        "Corn":            "ZC=F",
    },
    "Alternative": {
        "Bitcoin":         "BTC-USD",
        "Ethereum":        "ETH-USD",
        "DXY":             "DX-Y.NYB",
        "EUR/USD":         "EURUSD=X",
        "USD/JPY":         "JPY=X",
        "VIX":             "^VIX",
        "Global REIT":     "VNQI",
        "US REIT":         "VNQ",
    },
}

DEFAULT_RRG_BENCHMARKS = {
    "Equity":      "^GSPC",
    "Fixed Income": "AGG",
    "Commodity":   "DJP",
    "Alternative": "^GSPC",
}

DEFAULT_CONSTITUENT_INDICES = {
    "Equity": ["S&P 500", "Nifty 50", "FTSE 100", "DAX", "Dow Jones"],
}

# Wikipedia constituent registry: index_name -> (url, table_idx, ticker_col, sector_col, country)
WIKI_INDEX_MAP: dict[str, tuple[str, int, str, str, str]] = {
    "S&P 500":     ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 0, "Symbol", "GICS Sector", "US"),
    "Nifty 50":    ("https://en.wikipedia.org/wiki/NIFTY_50", 2, "Symbol", "Sector", "India"),
    "FTSE 100":    ("https://en.wikipedia.org/wiki/FTSE_100_Index", 4, "Ticker", "FTSE industry classification benchmark sector[18]", "UK"),
    "DAX":         ("https://en.wikipedia.org/wiki/DAX", 4, "Ticker", "Prime Standard Sector", "Germany"),
    "Dow Jones":   ("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average", 2, "Symbol", "Industry", "US"),
    "Nasdaq 100":  ("https://en.wikipedia.org/wiki/Nasdaq-100", 4, "Ticker", "GICS Sector", "US"),
}
YAHOO_SUFFIX = {"Nifty 50": ".NS", "FTSE 100": ".L", "DAX": ".DE"}


# ═══════════════════════════════════════════════════════════════════════════════
# 2. CONFIG DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════
@dataclass
class TerminalConfig:
    tickers:               dict[str, dict[str, str]] = field(default_factory=lambda: json.loads(json.dumps(DEFAULT_TICKERS)))
    rrg_benchmarks:        dict[str, str]            = field(default_factory=lambda: dict(DEFAULT_RRG_BENCHMARKS))
    constituent_indices:   dict[str, list[str]]      = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_CONSTITUENT_INDICES.items()})
    timeframes:            dict[str, int]            = field(default_factory=lambda: dict(DEFAULT_TIMEFRAMES))
    score_weights:         dict[str, float]          = field(default_factory=lambda: dict(DEFAULT_SCORE_WEIGHTS))
    breadth:               dict[str, int]            = field(default_factory=lambda: dict(DEFAULT_BREADTH))
    rrg:                   dict[str, int]            = field(default_factory=lambda: dict(DEFAULT_RRG))
    skip_month:            bool                      = False  # 12-1 momentum (Jegadeesh-Titman)
    primary_provider:      str                       = "yfinance"  # "yfinance" | "eodhd"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TerminalConfig":
        # robust load with default-fallback for missing keys
        defaults = cls()
        merged = defaults.to_dict()
        for k, v in d.items():
            if k in merged:
                merged[k] = v
        return cls(**merged)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DUCKDB PERSISTENCE LAYER
# ═══════════════════════════════════════════════════════════════════════════════
@st.cache_resource
def get_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            ticker   VARCHAR NOT NULL,
            date     DATE     NOT NULL,
            close    DOUBLE,
            provider VARCHAR,
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


def db_upsert_prices(rows: list[tuple], provider: str) -> None:
    if not rows:
        return
    con = get_db()
    df = pd.DataFrame(rows, columns=["ticker", "date", "close"])
    df["provider"] = provider
    df["fetched_at"] = datetime.now()
    con.register("incoming", df)
    con.execute("""
        INSERT INTO prices
        SELECT * FROM incoming
        ON CONFLICT (ticker, date) DO UPDATE
            SET close = EXCLUDED.close,
                provider = EXCLUDED.provider,
                fetched_at = EXCLUDED.fetched_at
    """)
    con.unregister("incoming")


def db_load_prices(tickers: list[str], lookback_days: int) -> dict[str, pd.Series]:
    if not tickers:
        return {}
    con = get_db()
    cutoff = (datetime.today() - timedelta(days=lookback_days)).date()
    placeholders = ",".join(["?"] * len(tickers))
    df = con.execute(
        f"""
        SELECT ticker, date, close FROM prices
        WHERE ticker IN ({placeholders}) AND date >= ?
        ORDER BY ticker, date
        """,
        [*tickers, cutoff],
    ).df()
    out = {t: pd.Series(dtype=float, name=t) for t in tickers}
    if df.empty:
        return out
    for ticker, grp in df.groupby("ticker"):
        s = pd.Series(grp["close"].values, index=pd.to_datetime(grp["date"]))
        s.name = ticker
        out[ticker] = s.sort_index()
    return out


def db_status() -> pd.DataFrame:
    con = get_db()
    return con.execute("""
        SELECT
            ticker,
            COUNT(*)        AS rows,
            MIN(date)       AS first_date,
            MAX(date)       AS last_date,
            ANY_VALUE(provider) AS provider,
            MAX(fetched_at) AS last_fetched
        FROM prices
        GROUP BY ticker
        ORDER BY ticker
    """).df()


def db_save_preset(name: str, config: TerminalConfig) -> None:
    con = get_db()
    con.execute(
        """
        INSERT INTO presets (name, config_json, created_at) VALUES (?, ?, ?)
        ON CONFLICT (name) DO UPDATE SET config_json = EXCLUDED.config_json, created_at = EXCLUDED.created_at
        """,
        (name, json.dumps(config.to_dict()), datetime.now()),
    )


def db_load_preset(name: str) -> TerminalConfig | None:
    con = get_db()
    row = con.execute("SELECT config_json FROM presets WHERE name = ?", (name,)).fetchone()
    if row:
        return TerminalConfig.from_dict(json.loads(row[0]))
    return None


def db_list_presets() -> list[str]:
    con = get_db()
    rows = con.execute("SELECT name FROM presets ORDER BY name").fetchall()
    return [r[0] for r in rows]


def db_delete_preset(name: str) -> None:
    con = get_db()
    con.execute("DELETE FROM presets WHERE name = ?", (name,))


# ═══════════════════════════════════════════════════════════════════════════════
# 4. DATA PROVIDER ADAPTER PATTERN
# ═══════════════════════════════════════════════════════════════════════════════
class DataProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def fetch(self, tickers: list[str], start: date, end: date) -> dict[str, pd.Series]:
        """Return {yahoo_ticker: close_series}. Use the YAHOO ticker as the key
        regardless of provider, so the rest of the system stays one-vocabulary."""

    def healthy(self) -> bool:  # default: always
        return True


class YFinanceProvider(DataProvider):
    name = "yfinance"

    def fetch(self, tickers: list[str], start: date, end: date) -> dict[str, pd.Series]:
        import yfinance as yf
        out: dict[str, pd.Series] = {}
        if not tickers:
            return out
        chunk_size = 50  # avoid 429 rate limits
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
            except Exception:
                df = None
            if df is None or df.empty:
                for t in chunk: out[t] = pd.Series(dtype=float, name=t)
                continue
            if len(chunk) == 1:
                out[chunk[0]] = self._extract(df, chunk[0])
            else:
                for t in chunk:
                    out[t] = self._extract(df, t)
        return out

    @staticmethod
    def _extract(df: pd.DataFrame, ticker: str) -> pd.Series:
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


class EODHDProvider(DataProvider):
    """EODHD adapter. Translates Yahoo tickers → EODHD format, fetches, returns
    keyed by the original Yahoo ticker."""
    name = "eodhd"

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def healthy(self) -> bool:
        return bool(self.api_key)

    def fetch(self, tickers: list[str], start: date, end: date) -> dict[str, pd.Series]:
        if not self.healthy():
            return {t: pd.Series(dtype=float, name=t) for t in tickers}
        import requests
        out: dict[str, pd.Series] = {}
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(self._fetch_one, t, start, end): t for t in tickers}
            for fut in as_completed(futs):
                yt = futs[fut]
                try:
                    out[yt] = fut.result()
                except Exception:
                    out[yt] = pd.Series(dtype=float, name=yt)
        return out

    def _fetch_one(self, yahoo_ticker: str, start: date, end: date) -> pd.Series:
        import requests
        eodhd_ticker = self.yahoo_to_eodhd(yahoo_ticker)
        if not eodhd_ticker:
            return pd.Series(dtype=float, name=yahoo_ticker)
        url = f"https://eodhd.com/api/eod/{eodhd_ticker}"
        params = {
            "api_token": self.api_key,
            "fmt": "json",
            "from": start.strftime("%Y-%m-%d"),
            "to":   end.strftime("%Y-%m-%d"),
            "period": "d",
            "order":  "a",
        }
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code != 200:
                return pd.Series(dtype=float, name=yahoo_ticker)
            data = r.json()
        except Exception:
            return pd.Series(dtype=float, name=yahoo_ticker)
        if not data:
            return pd.Series(dtype=float, name=yahoo_ticker)
        df = pd.DataFrame(data)
        if "adjusted_close" in df.columns:
            close_col = "adjusted_close"
        elif "close" in df.columns:
            close_col = "close"
        else:
            return pd.Series(dtype=float, name=yahoo_ticker)
        df["date"] = pd.to_datetime(df["date"])
        s = pd.Series(df[close_col].astype(float).values, index=df["date"], name=yahoo_ticker)
        return s.sort_index()

    @staticmethod
    def yahoo_to_eodhd(yt: str) -> str | None:
        """Convert Yahoo ticker syntax → EODHD syntax.
            ^GSPC      -> GSPC.INDX
            AAPL       -> AAPL.US
            RELIANCE.NS-> RELIANCE.NSE
            BTC-USD    -> BTC-USD.CC
            EURUSD=X   -> EURUSD.FOREX
            GC=F       -> (futures: not directly supported on EODHD basic; skip)
        """
        if not yt: return None
        # Index (Yahoo "^XYZ")
        if yt.startswith("^"):
            return yt[1:] + ".INDX"
        # Crypto (Yahoo "BTC-USD" etc.)
        if yt.endswith("-USD") or yt.endswith("-EUR"):
            return yt + ".CC"
        # Forex (Yahoo "EURUSD=X")
        if yt.endswith("=X"):
            return yt.replace("=X", "") + ".FOREX"
        # Futures (Yahoo "GC=F"): EODHD has separate commodities endpoint, skip for now
        if yt.endswith("=F"):
            return None
        # Yahoo exchange-suffix mapping
        if yt.endswith(".NS"):  return yt[:-3] + ".NSE"
        if yt.endswith(".BO"):  return yt[:-3] + ".BSE"
        if yt.endswith(".L"):   return yt[:-2] + ".LSE"
        if yt.endswith(".DE"):  return yt[:-3] + ".XETRA"
        if yt.endswith(".PA"):  return yt[:-3] + ".PA"
        if yt.endswith(".HK"):  return yt[:-3] + ".HK"
        if yt.endswith(".TO"):  return yt[:-3] + ".TO"
        if yt.endswith(".AS"):  return yt[:-3] + ".AS"
        # Plain US ticker
        if "." not in yt:
            return yt + ".US"
        return yt  # unknown: pass through


def _resolve_secret(name: str) -> str:
    """Resolve a secret from Streamlit secrets first, then environment vars.
    Safe even if secrets.toml is absent (common on first-run / local dev)."""
    try:
        val = st.secrets.get(name, "") if hasattr(st, "secrets") else ""
    except (FileNotFoundError, KeyError, Exception):
        val = ""
    if not val:
        val = os.getenv(name, "")
    return val or ""


def get_provider(name: str) -> DataProvider:
    if name == "eodhd":
        return EODHDProvider(api_key=_resolve_secret("EODHD_KEY"))
    return YFinanceProvider()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. UNIFIED FETCH ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════════
def stale_tickers(cached: dict[str, pd.Series], staleness_days: int = 2) -> list[str]:
    """Tickers whose latest cached date is older than (today - staleness_days)."""
    cutoff = (datetime.today() - timedelta(days=staleness_days)).date()
    out = []
    for t, ser in cached.items():
        if ser.empty or ser.index.max().date() < cutoff:
            out.append(t)
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_prices(
    tickers_tuple: tuple[str, ...],
    primary: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    force_refresh: bool = False,
    _cache_key_date: str = "",  # used to invalidate cache on date change
) -> dict[str, pd.Series]:
    """
    Layered fetch:
      1. Read existing cached series from DuckDB.
      2. Identify stale or missing tickers.
      3. Fetch with primary provider; on missing/empty, retry with fallback.
      4. Persist to DuckDB.
      5. Return merged dict.
    """
    tickers = list(tickers_tuple)
    cached = {} if force_refresh else db_load_prices(tickers, lookback_days)
    for t in tickers:
        cached.setdefault(t, pd.Series(dtype=float, name=t))

    to_fetch = stale_tickers(cached) if not force_refresh else tickers
    if not to_fetch:
        return cached

    end = date.today()
    start = end - timedelta(days=lookback_days)

    primary_p = get_provider(primary)
    fallback_p = get_provider("yfinance" if primary == "eodhd" else "eodhd")

    # primary
    fresh = primary_p.fetch(to_fetch, start, end) if primary_p.healthy() else {}

    # fallback for tickers where primary returned empty
    missing_after_primary = [t for t in to_fetch if t not in fresh or fresh[t].empty]
    if missing_after_primary and fallback_p.healthy():
        fb = fallback_p.fetch(missing_after_primary, start, end)
        for t, s in fb.items():
            if not s.empty:
                fresh[t] = s

    # Persist
    rows_yf: list[tuple] = []
    rows_eo: list[tuple] = []
    for t, ser in fresh.items():
        if ser.empty:
            continue
        for dt, close in ser.items():
            row = (t, pd.Timestamp(dt).date(), float(close))
            # heuristic: which provider produced it? trust primary by default
            if primary == "eodhd" and t not in missing_after_primary:
                rows_eo.append(row)
            else:
                rows_yf.append(row)
    if rows_yf:
        db_upsert_prices(rows_yf, "yfinance")
    if rows_eo:
        db_upsert_prices(rows_eo, "eodhd")

    # Merge
    for t, ser in fresh.items():
        if not ser.empty:
            cached[t] = ser
    return cached


# ═══════════════════════════════════════════════════════════════════════════════
# 6. MOMENTUM, BREADTH & RRG MATH
# ═══════════════════════════════════════════════════════════════════════════════
def compute_returns(close: pd.Series, timeframes: dict[str, int], skip_month: bool = False) -> dict[str, float | None]:
    """Returns over each timeframe. If skip_month=True, applies Jegadeesh-Titman 12-1
    convention: skip the most recent month (~21d) when computing the return."""
    out: dict[str, float | None] = {}
    if close is None or len(close) < 5:
        for tf in timeframes:
            out[tf] = None; out[f"{tf}_sharpe"] = None
        return out
    arr = close.values.astype(float)
    daily_ret = np.diff(np.log(arr + 1e-10))
    skip = 21 if skip_month else 0
    for label, days in timeframes.items():
        # Need: arr[-1-skip] vs arr[-days-skip]
        if len(arr) < days + skip + 1:
            out[label] = None; out[f"{label}_sharpe"] = None
            continue
        end_px = arr[-1 - skip] if skip else arr[-1]
        start_px = arr[-days - skip] if (days + skip) <= len(arr) else arr[0]
        ret = (end_px / start_px - 1) * 100
        # Volatility window: full timeframe (skip not applied to vol — only to return endpoint)
        ann_vol = np.std(daily_ret[-days:]) * np.sqrt(252) * 100
        out[label] = round(float(ret), 2)
        out[f"{label}_sharpe"] = round(float(ret / ann_vol), 2) if ann_vol > 1e-6 else None
    return out


def absolute_momentum(close: pd.Series, rf_close: pd.Series | None,
                      lookback: int = 252, skip_month: bool = False) -> float | None:
    """Antonacci absolute momentum: 12M asset return − risk-free return."""
    if close is None or len(close) < lookback + 1:
        return None
    skip = 21 if skip_month else 0
    if len(close) < lookback + skip + 1:
        return None
    end_px = close.iloc[-1 - skip] if skip else close.iloc[-1]
    start_px = close.iloc[-lookback - skip]
    asset_ret = (end_px / start_px - 1) * 100
    if rf_close is None or len(rf_close) < lookback + 1:
        return round(float(asset_ret), 2)
    rf_yield = float(rf_close.iloc[-1])
    rf_ret = rf_yield * (lookback / 252)
    return round(float(asset_ret - rf_ret), 2)


def relative_momentum_zscore(returns: dict[str, float | None]) -> dict[str, float]:
    vals = np.array([v for v in returns.values() if v is not None])
    if len(vals) < 2:
        return {k: 0.0 for k in returns}
    mean, std = float(np.mean(vals)), float(np.std(vals))
    if std < 1e-6:
        return {k: 0.0 for k in returns}
    return {k: round((v - mean) / std, 2) if v is not None else 0.0 for k, v in returns.items()}


def composite_score(returns: dict[str, float | None], weights: dict[str, float]) -> float | None:
    parts = []
    for tf, w in weights.items():
        v = returns.get(tf)
        if v is None:
            return None
        parts.append(v * w)
    return round(float(sum(parts)), 2)


def compute_breadth(close: pd.Series, breadth_cfg: dict[str, int]) -> dict[str, Any]:
    dma_s, dma_l, rsi_n = breadth_cfg["dma_short"], breadth_cfg["dma_long"], breadth_cfg["rsi_period"]
    if close is None or len(close) < dma_l:
        return {f"above_{dma_s}dma": None, f"above_{dma_l}dma": None, f"rsi_{rsi_n}": None}
    last = float(close.iloc[-1])
    dma_short = float(close.rolling(dma_s).mean().iloc[-1])
    dma_long = float(close.rolling(dma_l).mean().iloc[-1])
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(rsi_n).mean()
    loss = -delta.where(delta < 0, 0).rolling(rsi_n).mean()
    rs = gain / (loss + 1e-10)
    rsi = (100 - 100 / (1 + rs)).iloc[-1]
    return {
        f"above_{dma_s}dma":  bool(last > dma_short) if pd.notna(dma_short) else None,
        f"above_{dma_l}dma":  bool(last > dma_long)  if pd.notna(dma_long)  else None,
        f"rsi_{rsi_n}":       round(float(rsi), 1)   if pd.notna(rsi)       else None,
    }


def compute_rrg(asset_close: pd.Series, bench_close: pd.Series,
                rs_window: int, mom_window: int, tail_weeks: int) -> pd.DataFrame:
    if asset_close is None or bench_close is None:
        return pd.DataFrame()
    df = pd.concat([asset_close.rename("asset"), bench_close.rename("bench")], axis=1).dropna()
    if len(df) < (rs_window + mom_window + tail_weeks * 5):
        return pd.DataFrame()
    df_w = df.resample("W-FRI").last().dropna()
    if len(df_w) < (rs_window + mom_window + tail_weeks):
        return pd.DataFrame()
    pr = df_w["asset"] / df_w["bench"]

    def wma(s: pd.Series, w: int) -> pd.Series:
        weights = np.arange(1, w + 1)
        return s.rolling(w).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

    rs = (pr / wma(pr, rs_window)) * 100
    rs_ratio = 100 + (rs - rs.rolling(rs_window).mean()) / rs.rolling(rs_window).std().replace(0, np.nan)
    rs_mom = (rs_ratio / wma(rs_ratio, mom_window)) * 100
    rs_mom = 100 + (rs_mom - rs_mom.rolling(mom_window).mean()) / rs_mom.rolling(mom_window).std().replace(0, np.nan)
    out = pd.DataFrame({"rs_ratio": rs_ratio, "rs_momentum": rs_mom}).dropna()
    return out.tail(tail_weeks)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. WIKIPEDIA CONSTITUENT SCRAPER
# ═══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=86400, show_spinner=False)
def scrape_index_constituents(index_name: str) -> pd.DataFrame:
    if index_name not in WIKI_INDEX_MAP:
        return pd.DataFrame()
    url, tbl_idx, ticker_col, sector_col, country = WIKI_INDEX_MAP[index_name]
    try:
        tables = pd.read_html(url)
        df = tables[tbl_idx].copy()
    except Exception as e:
        st.warning(f"Wikipedia scrape failed for {index_name}: {e}")
        return pd.DataFrame()
    df.columns = [str(c).strip() for c in df.columns]
    if ticker_col not in df.columns:
        for c in df.columns:
            if "symbol" in c.lower() or "ticker" in c.lower(): ticker_col = c; break
    if sector_col not in df.columns:
        for c in df.columns:
            if "sector" in c.lower() or "industry" in c.lower(): sector_col = c; break
    if ticker_col not in df.columns:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["Ticker"] = df[ticker_col].astype(str).str.strip()
    suffix = YAHOO_SUFFIX.get(index_name, "")
    if suffix:
        out["Ticker"] = out["Ticker"].apply(lambda x: x if x.endswith(suffix) else f"{x}{suffix}")
    name_col = next((c for c in df.columns if "company" in c.lower() or "security" in c.lower() or "name" in c.lower()), None)
    out["Name"]    = df[name_col].astype(str).str.strip() if name_col else out["Ticker"]
    out["Sector"]  = df[sector_col].astype(str).str.strip() if sector_col in df.columns else "Unknown"
    out["Country"] = country
    out["Index"]   = index_name
    return out.drop_duplicates(subset=["Ticker"]).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SESSION STATE BOOTSTRAP
# ═══════════════════════════════════════════════════════════════════════════════
def init_state() -> None:
    if "config" not in st.session_state:
        st.session_state.config = TerminalConfig()
    if "tile_view" not in st.session_state:
        st.session_state.tile_view = "Heatmap"
    if "preset_msg" not in st.session_state:
        st.session_state.preset_msg = ""

init_state()
cfg: TerminalConfig = st.session_state.config


# ═══════════════════════════════════════════════════════════════════════════════
# 9. TILE METRICS LOADER
# ═══════════════════════════════════════════════════════════════════════════════
def load_tile_metrics(asset: str) -> dict:
    tickers_dict = cfg.tickers[asset]
    tickers = list(tickers_dict.values()) + [RISK_FREE_TICKER_YF]
    prices = fetch_prices(
        tuple(sorted(set(tickers))),
        primary=cfg.primary_provider,
        lookback_days=DEFAULT_LOOKBACK_DAYS,
        _cache_key_date=str(date.today()),
    )
    rf = prices.get(RISK_FREE_TICKER_YF, pd.Series(dtype=float))
    out = {}
    for label, tkr in tickers_dict.items():
        close = prices.get(tkr, pd.Series(dtype=float))
        rets = compute_returns(close, cfg.timeframes, cfg.skip_month)
        out[label] = {
            "ticker":     tkr,
            "metrics":    rets,
            "abs_mom":    absolute_momentum(close, rf, skip_month=cfg.skip_month),
            "sparkline":  close.tail(90).tolist() if len(close) >= 5 else [],
            "last_price": float(close.iloc[-1]) if len(close) else None,
        }
    one_y = {label: info["metrics"].get("1Y") for label, info in out.items()}
    z = relative_momentum_zscore(one_y)
    for label in out:
        out[label]["rel_mom_z"] = z.get(label, 0.0)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 10. RENDERING — DASHBOARD VIEWS
# ═══════════════════════════════════════════════════════════════════════════════
def render_heatmap(matrix: pd.DataFrame, height: int = 320, title: str | None = None) -> go.Figure:
    fig = go.Figure(data=go.Heatmap(
        z=matrix.values,
        x=list(matrix.columns),
        y=matrix.index.tolist(),
        text=[[f"{v:+.1f}%" if pd.notna(v) else "—" for v in row] for row in matrix.values],
        texttemplate="%{text}",
        colorscale=[[0, "#f85149"], [0.5, "#161b22"], [1, "#58e2a0"]],
        zmid=0, zmin=-30, zmax=30,
        textfont=dict(family="JetBrains Mono", size=12, color="white"),
        colorbar=dict(title="Return %", thickness=12, len=0.7,
                      tickfont=dict(family="JetBrains Mono", size=10, color="#8b949e")),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono", color="#c9d1d9", size=11),
        margin=dict(l=0, r=0, t=30 if title else 20, b=0), height=height,
        title=dict(text=title, x=0.5, font=dict(size=12)) if title else None,
    )
    return fig


def render_rrg(rrg_data: dict[str, pd.DataFrame], asset_class: str, benchmark: str) -> go.Figure:
    fig = go.Figure()
    fig.add_shape(type="rect", x0=100, y0=100, x1=140, y1=140, fillcolor="rgba(88,226,160,0.06)", line_width=0, layer="below")
    fig.add_shape(type="rect", x0=60,  y0=100, x1=100, y1=140, fillcolor="rgba(121,192,255,0.06)", line_width=0, layer="below")
    fig.add_shape(type="rect", x0=60,  y0=60,  x1=100, y1=100, fillcolor="rgba(248,81,73,0.06)",   line_width=0, layer="below")
    fig.add_shape(type="rect", x0=100, y0=60,  x1=140, y1=100, fillcolor="rgba(240,136,62,0.06)",  line_width=0, layer="below")
    palette = px.colors.qualitative.Vivid + px.colors.qualitative.Set2
    for i, (label, df) in enumerate(rrg_data.items()):
        if df.empty: continue
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatter(
            x=df["rs_ratio"], y=df["rs_momentum"], mode="lines+markers",
            line=dict(color=color, width=1.2),
            marker=dict(size=5, color=color, opacity=0.5),
            name=label, legendgroup=label,
            hovertemplate=f"<b>{label}</b><br>RS-Ratio: %{{x:.2f}}<br>RS-Mom: %{{y:.2f}}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[df["rs_ratio"].iloc[-1]], y=[df["rs_momentum"].iloc[-1]],
            mode="markers+text",
            marker=dict(size=14, color=color, line=dict(color="white", width=1.5)),
            text=[label], textposition="top right",
            textfont=dict(family="JetBrains Mono", size=10, color="#c9d1d9"),
            showlegend=False, legendgroup=label, hoverinfo="skip",
        ))
    fig.add_hline(y=100, line_dash="solid", line_color="#30363d", line_width=1)
    fig.add_vline(x=100, line_dash="solid", line_color="#30363d", line_width=1)
    fig.add_annotation(x=138, y=138, text="<b>LEADING</b>",   showarrow=False, font=dict(color="#58e2a0", size=11, family="JetBrains Mono"), opacity=0.85)
    fig.add_annotation(x=62,  y=138, text="<b>IMPROVING</b>", showarrow=False, font=dict(color="#79c0ff", size=11, family="JetBrains Mono"), opacity=0.85)
    fig.add_annotation(x=62,  y=62,  text="<b>LAGGING</b>",   showarrow=False, font=dict(color="#f85149", size=11, family="JetBrains Mono"), opacity=0.85)
    fig.add_annotation(x=138, y=62,  text="<b>WEAKENING</b>", showarrow=False, font=dict(color="#f0883e", size=11, family="JetBrains Mono"), opacity=0.85)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono", color="#c9d1d9", size=11),
        margin=dict(l=0, r=0, t=40, b=0), height=520,
        title=dict(text=f"{asset_class} RRG (vs {benchmark}, {cfg.rrg['tail_weeks']}-week tails)",
                   x=0.5, font=dict(size=12, color="#c9d1d9")),
        xaxis=dict(title="JdK RS-Ratio →  (relative strength)", range=[60, 140], gridcolor="#21262d", zeroline=False),
        yaxis=dict(title="JdK RS-Momentum →  (rate of change)", range=[60, 140], gridcolor="#21262d", zeroline=False),
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02,
                    font=dict(size=9, family="JetBrains Mono")),
    )
    return fig


def render_sparklines(all_data: dict, n_cols: int = 4) -> go.Figure:
    items = [(asset, label, info) for asset, d in all_data.items() for label, info in d.items()]
    n_rows = (len(items) + n_cols - 1) // n_cols
    fig = make_subplots(rows=n_rows, cols=n_cols,
                        subplot_titles=[""] * (n_rows * n_cols),
                        vertical_spacing=0.10, horizontal_spacing=0.04)
    titles = []
    for idx, (asset, label, info) in enumerate(items):
        r, c = idx // n_cols + 1, idx % n_cols + 1
        spark = info.get("sparkline", [])
        mom_1m = info.get("metrics", {}).get("1M")
        color = "#58e2a0" if (mom_1m or 0) > 0 else "#f85149"
        fill = "rgba(88,226,160,0.12)" if color == "#58e2a0" else "rgba(248,81,73,0.12)"
        if spark:
            fig.add_trace(go.Scatter(y=spark, mode="lines",
                line=dict(color=color, width=1.6), fill="tozeroy", fillcolor=fill,
                showlegend=False, hoverinfo="skip"), row=r, col=c)
        mom_str = f"{mom_1m:+.1f}%" if mom_1m is not None else "—"
        titles.append(f"<b>{label}</b><br><span style='font-size:9px;color:{color}'>{mom_str} 1M · {asset}</span>")
        fig.update_xaxes(visible=False, row=r, col=c)
        fig.update_yaxes(visible=False, row=r, col=c)
    for i, ann in enumerate(fig.layout.annotations):
        if i < len(titles):
            ann.text = titles[i]
            ann.font = dict(family="JetBrains Mono", size=10, color="#c9d1d9")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=0, r=0, t=20, b=0), height=max(180, 140 * n_rows))
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# 11. SIDEBAR — NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚡ Grok Alpha Terminal")
    page = st.radio("Page", ["Dashboard", "Settings", "Presets", "Data Status"],
                    horizontal=False, label_visibility="collapsed")
    st.divider()
    st.caption(f"📅 {date.today()}")
    st.caption(f"🔌 Provider: **{cfg.primary_provider}**")
    st.caption(f"🧮 Skip-month: **{'on (12-1)' if cfg.skip_month else 'off'}**")
    st.divider()
    if st.button("🔄 Refresh All", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# 12. PAGE — SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════
def page_settings() -> None:
    st.markdown("# ⚙️ Settings")
    st.caption("All controls below directly affect dashboard calculations.")

    # ── Provider ──
    st.subheader("Data Provider")
    col1, col2 = st.columns([2, 3])
    with col1:
        prov = st.radio("Primary provider", ["yfinance", "eodhd"],
                        index=0 if cfg.primary_provider == "yfinance" else 1,
                        horizontal=True)
    with col2:
        if prov == "eodhd":
            has_key = bool(_resolve_secret("EODHD_KEY"))
            if has_key:
                st.success("EODHD_KEY found.")
            else:
                st.warning("Set `EODHD_KEY` env var or `.streamlit/secrets.toml`. Will fall back to yfinance.")
        else:
            st.info("yfinance is free, no key needed. Subject to occasional rate limits on heavy fetches.")
    cfg.primary_provider = prov

    st.divider()

    # ── Tickers per asset class ──
    st.subheader("Tickers per Asset Class")
    st.caption("Format: `Label = TICKER`, one per line. Yahoo notation.")
    for asset in cfg.tickers:
        with st.expander(f"📊 {asset}", expanded=False):
            text = "\n".join(f"{k} = {v}" for k, v in cfg.tickers[asset].items())
            new_text = st.text_area(f"{asset}", value=text, height=160,
                                    key=f"ta_{asset}", label_visibility="collapsed")
            new_bench = st.text_input("RRG benchmark ticker",
                                       value=cfg.rrg_benchmarks.get(asset, "^GSPC"),
                                       key=f"bench_{asset}")
            if asset == "Equity":
                new_indices = st.multiselect("Constituent indices to fetch",
                                             list(WIKI_INDEX_MAP.keys()),
                                             default=cfg.constituent_indices.get("Equity", []),
                                             key=f"idx_{asset}")
            if st.button(f"Apply {asset}", key=f"apply_{asset}", use_container_width=True):
                parsed = {}
                for line in new_text.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        parsed[k.strip()] = v.strip()
                if parsed:
                    cfg.tickers[asset] = parsed
                cfg.rrg_benchmarks[asset] = new_bench.strip()
                if asset == "Equity":
                    cfg.constituent_indices["Equity"] = new_indices
                st.cache_data.clear()
                st.success(f"{asset} updated.")
                st.rerun()

    st.divider()

    # ── Timeframes ──
    st.subheader("Timeframes")
    st.caption("Edit lookback windows in trading days. Add or remove timeframes; "
               "labels become column headers throughout the app.")
    tf_text = "\n".join(f"{k} = {v}" for k, v in cfg.timeframes.items())
    new_tf = st.text_area("Timeframes (label = days)", value=tf_text, height=180, key="tf_area")
    if st.button("Apply Timeframes", use_container_width=True):
        try:
            parsed: dict[str, int] = {}
            for line in new_tf.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    parsed[k.strip()] = int(v.strip())
            if parsed:
                cfg.timeframes = parsed
                st.success(f"Timeframes updated: {list(parsed.keys())}")
                st.rerun()
        except ValueError:
            st.error("Each value must be an integer (number of trading days).")

    st.divider()

    # ── Skip-month / 12-1 momentum ──
    st.subheader("Momentum Convention")
    cfg.skip_month = st.checkbox(
        "Skip most recent month (Jegadeesh-Titman 12-1 convention)",
        value=cfg.skip_month,
        help=(
            "When enabled, returns measure t-{N+1m} → t-1m instead of t-N → t. "
            "The most recent month is excluded to avoid short-term reversal noise. "
            "This is the academic standard for momentum factor research."
        ),
    )

    st.divider()

    # ── Composite score weights ──
    st.subheader("Composite Score Weights")
    st.caption("Weights blend per-timeframe returns into a single momentum score. "
               "Only timeframes listed below are blended; weights need not sum to 1.")
    weight_cols = st.columns(min(6, max(1, len(cfg.score_weights))))
    new_weights: dict[str, float] = {}
    for i, (tf, w) in enumerate(cfg.score_weights.items()):
        with weight_cols[i % len(weight_cols)]:
            new_weights[tf] = st.number_input(f"{tf}", value=float(w), min_value=0.0, max_value=2.0,
                                               step=0.05, key=f"w_{tf}", format="%.2f")
    edit_weights_text = st.text_input(
        "Add/remove weight entries (label=value, comma-separated)",
        value="", key="weights_extra",
        placeholder="e.g. 1M=0.10, 12-1=0.40",
    )
    if st.button("Apply Weights", use_container_width=True):
        if edit_weights_text.strip():
            for token in edit_weights_text.split(","):
                if "=" in token:
                    k, v = token.split("=", 1)
                    try:
                        new_weights[k.strip()] = float(v.strip())
                    except ValueError:
                        pass
        cfg.score_weights = new_weights
        st.success("Score weights updated.")
        st.rerun()

    st.divider()

    # ── Breadth thresholds ──
    st.subheader("Market Breadth Thresholds")
    bcol = st.columns(4)
    with bcol[0]:
        cfg.breadth["dma_short"] = st.number_input("Short DMA", min_value=5, max_value=200,
                                                    value=cfg.breadth["dma_short"], step=5)
        cfg.breadth["dma_long"]  = st.number_input("Long DMA",  min_value=50, max_value=400,
                                                    value=cfg.breadth["dma_long"], step=10)
    with bcol[1]:
        cfg.breadth["rsi_period"]    = st.number_input("RSI period", min_value=2, max_value=60,
                                                        value=cfg.breadth["rsi_period"])
        cfg.breadth["rsi_strong"]    = st.number_input("RSI strong threshold",   min_value=50,
                                                        max_value=80, value=cfg.breadth["rsi_strong"])
    with bcol[2]:
        cfg.breadth["rsi_weak"]      = st.number_input("RSI weak threshold",     min_value=20,
                                                        max_value=50, value=cfg.breadth["rsi_weak"])
        cfg.breadth["rsi_overbought"] = st.number_input("RSI overbought",        min_value=50,
                                                         max_value=90, value=cfg.breadth["rsi_overbought"])
    with bcol[3]:
        cfg.breadth["rsi_oversold"]   = st.number_input("RSI oversold",          min_value=10,
                                                         max_value=50, value=cfg.breadth["rsi_oversold"])

    st.divider()

    # ── RRG params ──
    st.subheader("RRG Parameters")
    rcol = st.columns(3)
    with rcol[0]:
        cfg.rrg["rs_window"]  = st.number_input("RS-Ratio window (weeks)",   min_value=4,
                                                 max_value=52, value=cfg.rrg["rs_window"])
    with rcol[1]:
        cfg.rrg["mom_window"] = st.number_input("RS-Momentum window (weeks)", min_value=4,
                                                 max_value=52, value=cfg.rrg["mom_window"])
    with rcol[2]:
        cfg.rrg["tail_weeks"] = st.number_input("Tail length (weeks)",       min_value=4,
                                                 max_value=52, value=cfg.rrg["tail_weeks"])

    st.divider()
    if st.button("↻ Reset ALL settings to defaults", use_container_width=True):
        st.session_state.config = TerminalConfig()
        st.cache_data.clear()
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# 13. PAGE — PRESETS
# ═══════════════════════════════════════════════════════════════════════════════
def page_presets() -> None:
    st.markdown("# 🗂️ Presets")
    st.caption("Save the entire current configuration (tickers + settings) under a name. "
               "Load it back any time. Stored in DuckDB.")

    presets = db_list_presets()

    # Save
    save_col, save_btn = st.columns([4, 1])
    with save_col:
        new_name = st.text_input("Preset name to save", value="", placeholder="e.g. 'jt_12_1_global'", key="preset_save_name")
    with save_btn:
        st.write("")
        st.write("")
        if st.button("💾 Save current", use_container_width=True):
            if not new_name.strip():
                st.error("Name required.")
            else:
                db_save_preset(new_name.strip(), cfg)
                st.session_state.preset_msg = f"✅ Preset `{new_name.strip()}` saved."
                st.rerun()

    if st.session_state.preset_msg:
        st.success(st.session_state.preset_msg)
        st.session_state.preset_msg = ""

    st.divider()

    # Load / Delete
    if presets:
        st.subheader("Saved Presets")
        for name in presets:
            row = st.columns([5, 1, 1])
            row[0].markdown(f"**{name}**")
            if row[1].button("Load", key=f"load_{name}", use_container_width=True):
                loaded = db_load_preset(name)
                if loaded:
                    st.session_state.config = loaded
                    st.cache_data.clear()
                    st.session_state.preset_msg = f"✅ Loaded preset `{name}`."
                    st.rerun()
            if row[2].button("🗑️", key=f"del_{name}", use_container_width=True):
                db_delete_preset(name)
                st.rerun()
    else:
        st.info("No presets saved yet.")


# ═══════════════════════════════════════════════════════════════════════════════
# 14. PAGE — DATA STATUS
# ═══════════════════════════════════════════════════════════════════════════════
def page_data_status() -> None:
    st.markdown("# 📦 Data Status")
    st.caption("All EOD prices ever fetched are persisted in DuckDB at "
               f"`{DB_PATH}`. The dashboard reads from this store first; only "
               "stale or missing tickers trigger a network fetch.")

    df = db_status()
    if df.empty:
        st.info("No data cached yet. Open the Dashboard page to populate.")
        return

    # Headline metrics
    today = pd.Timestamp.today().normalize()
    fresh = df["last_date"].apply(lambda d: (today - pd.Timestamp(d)).days <= 3).sum()
    stale = len(df) - fresh
    total_rows = int(df["rows"].sum())
    earliest = df["first_date"].min()
    latest   = df["last_date"].max()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Tickers cached", f"{len(df):,}")
    m2.metric("Total rows", f"{total_rows:,}")
    m3.metric("Fresh (≤3d)", f"{fresh}")
    m4.metric("Stale (>3d)", f"{stale}")
    m5.metric("Date span", f"{earliest} → {latest}")

    st.divider()
    df_disp = df.copy()
    df_disp["staleness_days"] = (today - pd.to_datetime(df_disp["last_date"])).dt.days
    df_disp = df_disp.sort_values("staleness_days", ascending=False)

    st.dataframe(
        df_disp.style.background_gradient(subset=["staleness_days"], cmap="Reds", vmin=0, vmax=30)
                     .background_gradient(subset=["rows"], cmap="Greens"),
        use_container_width=True, height=420,
    )

    st.divider()
    danger_col1, danger_col2 = st.columns(2)
    with danger_col1:
        if st.button("🗑️ Clear ALL price data", use_container_width=True):
            con = get_db()
            con.execute("DELETE FROM prices")
            st.cache_data.clear()
            st.success("Price store cleared.")
            st.rerun()
    with danger_col2:
        old_only = st.number_input("Delete data older than N days", value=1100, min_value=30, max_value=10000)
        if st.button("🧹 Prune old rows", use_container_width=True):
            cutoff = (datetime.today() - timedelta(days=old_only)).date()
            con = get_db()
            n = con.execute("DELETE FROM prices WHERE date < ?", (cutoff,)).fetchone()
            st.success(f"Pruned rows older than {cutoff}.")
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# 15. PAGE — DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
def page_dashboard() -> None:
    # Header
    st.markdown("# ⚡ Grok Alpha Terminal")
    skip_badge = '<span class="badge amber">12-1 (skip month)</span>' if cfg.skip_month else '<span class="badge">vanilla returns</span>'
    st.markdown(
        f'<div class="status-strip">📅 <b>{date.today()}</b> · '
        f'4 asset classes · {len(cfg.timeframes)} timeframes ({", ".join(cfg.timeframes.keys())}) · '
        f'{skip_badge} · provider: <b>{cfg.primary_provider}</b> · DuckDB cache</div>',
        unsafe_allow_html=True,
    )

    # Load tile data across asset classes
    all_tile_data: dict[str, dict] = {}
    with st.spinner("Loading market data…"):
        for asset in cfg.tickers:
            all_tile_data[asset] = load_tile_metrics(asset)

    # Asset summary matrix
    summary_rows: dict[str, dict] = {}
    for asset, items in all_tile_data.items():
        tf_means: dict[str, float | None] = {}
        for tf in cfg.timeframes:
            vals = [info["metrics"].get(tf) for info in items.values() if info["metrics"].get(tf) is not None]
            tf_means[tf] = round(float(np.mean(vals)), 2) if vals else None
        summary_rows[asset] = tf_means
    asset_summary = pd.DataFrame(summary_rows).T[list(cfg.timeframes.keys())]

    # Holistic dashboard
    st.subheader("Holistic Dashboard — Global Momentum")
    st.session_state.tile_view = st.radio(
        "View mode",
        ["Heatmap", "RRG (Relative Rotation)", "Sparklines"],
        horizontal=True, label_visibility="collapsed",
    )

    if st.session_state.tile_view == "Heatmap":
        st.plotly_chart(render_heatmap(asset_summary, height=300), use_container_width=True)
        st.caption("Asset class × timeframe matrix. Average return across each class's instruments.")
    elif st.session_state.tile_view == "RRG (Relative Rotation)":
        rrg_choice = st.selectbox("Asset class for RRG", list(cfg.tickers.keys()), index=0, key="rrg_choice")
        benchmark = cfg.rrg_benchmarks.get(rrg_choice, "^GSPC")
        tickers_dict = cfg.tickers[rrg_choice]
        all_tickers = list(set(list(tickers_dict.values()) + [benchmark]))
        with st.spinner(f"Computing RRG for {rrg_choice} vs {benchmark}…"):
            prices = fetch_prices(tuple(sorted(all_tickers)), primary=cfg.primary_provider,
                                  _cache_key_date=str(date.today()))
            bench_close = prices.get(benchmark, pd.Series(dtype=float))
            rrg_data = {label: compute_rrg(prices.get(t, pd.Series(dtype=float)), bench_close,
                                           cfg.rrg["rs_window"], cfg.rrg["mom_window"], cfg.rrg["tail_weeks"])
                        for label, t in tickers_dict.items()}
        if any(not df.empty for df in rrg_data.values()):
            st.plotly_chart(render_rrg(rrg_data, rrg_choice, benchmark), use_container_width=True)
            st.caption(
                "**JdK RS-Ratio** (X) = relative strength vs benchmark. "
                "**RS-Momentum** (Y) = rate of change of RS-Ratio. "
                "Center (100,100) = benchmark. Tails = recent trajectory; assets rotate clockwise. "
                "Quadrant **transitions** are the actionable signals."
            )
        else:
            st.warning(f"Insufficient data for RRG. Need ≥ {cfg.rrg['tail_weeks']} weeks of overlapping history.")
    else:
        st.plotly_chart(render_sparklines(all_tile_data), use_container_width=True)
        st.caption("90-day price trajectory per instrument. Green = positive 1M return.")

    # Drill-down
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.subheader("🔍 Asset Class Drill-Down")
    asset_choice = st.radio("Select asset class", list(cfg.tickers.keys()),
                            horizontal=True, key="drill_asset")
    render_drilldown(asset_choice, all_tile_data)


def render_drilldown(asset: str, all_tile_data: dict) -> None:
    st.markdown(f"#### {asset} — Instrument Performance")
    perf_df = render_instrument_table(asset, all_tile_data)
    if asset == "Equity" and cfg.constituent_indices.get("Equity"):
        render_equity_constituents(cfg.constituent_indices["Equity"])
    else:
        st.markdown("##### Top-N Within Asset Class")
        full = perf_df.copy()
        full["Score"] = full.apply(
            lambda r: composite_score({tf: r.get(tf) for tf in cfg.timeframes}, cfg.score_weights),
            axis=1,
        )
        # alias columns for the topn renderer (Name, Country, Sector required)
        full = full.rename(columns={"Instrument": "Name"})
        full["Country"] = "—"
        full["Sector"] = "—"
        full["Ticker"] = full["Ticker"].astype(str)
        render_topn(full)


def render_instrument_table(asset: str, all_tile_data: dict) -> pd.DataFrame:
    tile_data = all_tile_data[asset]
    rows = []
    for label, info in tile_data.items():
        m = info["metrics"]
        rows.append({
            "Instrument": label, "Ticker": info["ticker"], "Last": info["last_price"],
            **{tf: m.get(tf) for tf in cfg.timeframes},
            "Abs Mom (12M-Rf)": info["abs_mom"],
            "Rel Mom (z-1Y)":   info["rel_mom_z"],
        })
    df = pd.DataFrame(rows)
    momentum_cols = list(cfg.timeframes.keys()) + ["Abs Mom (12M-Rf)"]
    st.dataframe(
        df.style.background_gradient(subset=momentum_cols, cmap="RdYlGn", vmin=-30, vmax=30)
        .background_gradient(subset=["Rel Mom (z-1Y)"], cmap="RdYlGn", vmin=-2, vmax=2)
        .format({c: lambda x: f"{x:+.2f}%" if pd.notna(x) else "—" for c in momentum_cols})
        .format({"Last": lambda x: f"{x:,.2f}" if pd.notna(x) else "—",
                 "Rel Mom (z-1Y)": lambda x: f"{x:+.2f}σ" if pd.notna(x) else "—"}),
        use_container_width=True, height=320,
    )
    return df


@st.fragment
def render_topn(full_df: pd.DataFrame) -> None:
    col_a, col_b = st.columns([1, 3])
    with col_a:
        top_n = st.slider("Top N", 5, 50, 20, key="topn_n")
        sort_by = st.selectbox("Rank by", ["Score"] + list(cfg.timeframes.keys()), key="topn_sortby")
        show_bottom = st.checkbox("Also show bottom N", value=False, key="topn_showbot")
    with col_b:
        if sort_by not in full_df.columns:
            st.warning(f"Column `{sort_by}` not in data.")
            return
        valid = full_df.dropna(subset=[sort_by])
        cols = ["Ticker", "Name", "Country", "Sector", "Score"] + list(cfg.timeframes.keys())
        cols = [c for c in cols if c in valid.columns]
        top = valid.nlargest(top_n, sort_by)[cols]
        st.markdown(f"**🟢 Top {top_n} by {sort_by}**")
        fmt_cols = [c for c in cfg.timeframes if c in top.columns]
        st.dataframe(
            top.style.background_gradient(subset=fmt_cols + (["Score"] if "Score" in top.columns else []),
                                          cmap="RdYlGn", vmin=-30, vmax=30)
            .format({c: lambda x: f"{x:+.1f}%" if pd.notna(x) else "—" for c in fmt_cols})
            .format({"Score": lambda x: f"{x:+.1f}" if pd.notna(x) else "—"}),
            use_container_width=True, height=420,
        )
        if show_bottom:
            bot = valid.nsmallest(top_n, sort_by)[cols]
            st.markdown(f"**🔴 Bottom {top_n} by {sort_by}**")
            st.dataframe(
                bot.style.background_gradient(subset=fmt_cols + (["Score"] if "Score" in bot.columns else []),
                                              cmap="RdYlGn", vmin=-30, vmax=30)
                .format({c: lambda x: f"{x:+.1f}%" if pd.notna(x) else "—" for c in fmt_cols})
                .format({"Score": lambda x: f"{x:+.1f}" if pd.notna(x) else "—"}),
                use_container_width=True, height=420,
            )


@st.fragment
def render_breadth(full_df: pd.DataFrame) -> None:
    st.markdown("##### Market Breadth — Trend & Momentum Indicators")
    bc = cfg.breadth
    short_col = f"above_{bc['dma_short']}dma"
    long_col  = f"above_{bc['dma_long']}dma"
    rsi_col   = f"rsi_{bc['rsi_period']}"

    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        dma_filter = st.selectbox(
            "Trend filter",
            ["All", f"Above {bc['dma_short']}DMA", f"Above {bc['dma_long']}DMA", "Above both",
             f"Below {bc['dma_short']}DMA", f"Below {bc['dma_long']}DMA", "Below both"],
            key="dma_filter",
        )
    with fcol2:
        rsi_filter = st.selectbox(
            "RSI filter",
            ["All", f"RSI > {bc['rsi_strong']} (strong)", f"RSI < {bc['rsi_weak']} (weak)",
             f"{bc['rsi_oversold']} < RSI < {bc['rsi_overbought']} (neutral)",
             f"RSI > {bc['rsi_overbought']} (overbought)", f"RSI < {bc['rsi_oversold']} (oversold)"],
            key="rsi_filter",
        )
    with fcol3:
        group_by = st.selectbox("Group by", ["Country", "Sector", "Index"], key="breadth_group")

    df = full_df.copy()
    if dma_filter == f"Above {bc['dma_short']}DMA": df = df[df[short_col] == True]
    elif dma_filter == f"Above {bc['dma_long']}DMA": df = df[df[long_col] == True]
    elif dma_filter == "Above both": df = df[(df[short_col] == True) & (df[long_col] == True)]
    elif dma_filter == f"Below {bc['dma_short']}DMA": df = df[df[short_col] == False]
    elif dma_filter == f"Below {bc['dma_long']}DMA": df = df[df[long_col] == False]
    elif dma_filter == "Below both": df = df[(df[short_col] == False) & (df[long_col] == False)]

    if rsi_filter == f"RSI > {bc['rsi_strong']} (strong)": df = df[df[rsi_col] > bc["rsi_strong"]]
    elif rsi_filter == f"RSI < {bc['rsi_weak']} (weak)":   df = df[df[rsi_col] < bc["rsi_weak"]]
    elif rsi_filter == f"{bc['rsi_oversold']} < RSI < {bc['rsi_overbought']} (neutral)":
        df = df[(df[rsi_col] > bc["rsi_oversold"]) & (df[rsi_col] < bc["rsi_overbought"])]
    elif rsi_filter == f"RSI > {bc['rsi_overbought']} (overbought)": df = df[df[rsi_col] > bc["rsi_overbought"]]
    elif rsi_filter == f"RSI < {bc['rsi_oversold']} (oversold)":     df = df[df[rsi_col] < bc["rsi_oversold"]]

    total = len(full_df); n_filtered = len(df)
    pct_short  = round(full_df[short_col].mean() * 100, 1) if total else 0
    pct_long   = round(full_df[long_col].mean() * 100, 1) if total else 0
    pct_strong = round((full_df[rsi_col] > bc["rsi_strong"]).mean() * 100, 1) if total else 0
    pct_weak   = round((full_df[rsi_col] < bc["rsi_weak"]).mean() * 100, 1) if total else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Universe", f"{total}")
    m2.metric(f"% > {bc['dma_short']}DMA", f"{pct_short}%")
    m3.metric(f"% > {bc['dma_long']}DMA",  f"{pct_long}%")
    m4.metric(f"% RSI > {bc['rsi_strong']}", f"{pct_strong}%")
    m5.metric(f"% RSI < {bc['rsi_weak']}",   f"{pct_weak}%")

    st.caption(f"Showing **{n_filtered}** of **{total}** stocks after filters.")

    if n_filtered > 0:
        grp = full_df.groupby(group_by).agg(
            Total=("Ticker", "count"),
            Pct_Short=(short_col, lambda x: round(x.mean() * 100, 1)),
            Pct_Long=(long_col,  lambda x: round(x.mean() * 100, 1)),
            Pct_Strong=(rsi_col, lambda x: round((x > bc["rsi_strong"]).mean() * 100, 1)),
            Pct_Weak=(rsi_col,   lambda x: round((x < bc["rsi_weak"]).mean() * 100, 1)),
            Avg_RSI=(rsi_col,    lambda x: round(x.mean(), 1)),
        ).reset_index().sort_values("Pct_Long", ascending=False)
        grp = grp.rename(columns={
            "Pct_Short": f"% > {bc['dma_short']}DMA",
            "Pct_Long":  f"% > {bc['dma_long']}DMA",
            "Pct_Strong": f"% RSI > {bc['rsi_strong']}",
            "Pct_Weak":   f"% RSI < {bc['rsi_weak']}",
        })
        st.dataframe(grp.style.background_gradient(subset=[c for c in grp.columns if c.startswith("% >")], cmap="Greens")
                              .background_gradient(subset=[c for c in grp.columns if "RSI <" in c], cmap="Reds"),
                     use_container_width=True)

        fig = px.histogram(full_df.dropna(subset=[rsi_col]), x=rsi_col, nbins=30, color=group_by,
                           title=f"RSI({bc['rsi_period']}) Distribution",
                           color_discrete_sequence=px.colors.qualitative.Set2)
        fig.add_vline(x=bc["rsi_oversold"],   line_dash="dot", line_color="#f85149", annotation_text="Oversold")
        fig.add_vline(x=bc["rsi_overbought"], line_dash="dot", line_color="#f0883e", annotation_text="Overbought")
        fig.add_vline(x=bc["rsi_weak"],   line_dash="dot", line_color="#6e7681")
        fig.add_vline(x=bc["rsi_strong"], line_dash="dot", line_color="#6e7681")
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(family="JetBrains Mono", color="#c9d1d9", size=10),
                          margin=dict(l=0, r=0, t=36, b=0), height=320, bargap=0.05)
        fig.update_xaxes(gridcolor="#21262d"); fig.update_yaxes(gridcolor="#21262d")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander(f"📋 Filtered tickers ({n_filtered})"):
            cols_show = ["Ticker", "Name", "Country", "Sector", rsi_col, short_col, long_col, "Score"] + list(cfg.timeframes.keys())
            cols_show = [c for c in cols_show if c in df.columns]
            st.dataframe(df[cols_show], use_container_width=True, height=400)


def render_equity_constituents(default_indices: list) -> None:
    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown("#### Equity Constituents — Geography, Sector, Top-N, Breadth")

    sel = st.multiselect("Indices", list(WIKI_INDEX_MAP.keys()), default=default_indices, key="eq_idx_select")
    extra = st.text_input("Extra tickers (comma-separated)", value="", key="eq_extra",
                          placeholder="e.g. NVDA, ASML.AS, RELIANCE.NS")
    if not sel and not extra.strip():
        st.info("Select indices or add tickers above.")
        return

    constituents = [scrape_index_constituents(i) for i in sel]
    constituents = [c for c in constituents if not c.empty]
    cons_df = pd.concat(constituents, ignore_index=True) if constituents else \
              pd.DataFrame(columns=["Ticker", "Name", "Sector", "Country", "Index"])
    if extra.strip():
        extras = [t.strip() for t in extra.split(",") if t.strip()]
        cons_df = pd.concat([cons_df, pd.DataFrame({
            "Ticker": extras, "Name": extras,
            "Sector": ["Custom"] * len(extras), "Country": ["Custom"] * len(extras),
            "Index": ["User"] * len(extras),
        })], ignore_index=True).drop_duplicates(subset=["Ticker"])

    if cons_df.empty:
        st.warning("No constituents loaded.")
        return

    st.caption(f"Loaded **{len(cons_df)}** constituents.")
    max_fetch = st.slider("Max constituents to fetch", 20,
                           min(500, len(cons_df)), min(100, len(cons_df)),
                           key="eq_maxfetch")
    cons_df = cons_df.head(max_fetch)

    with st.spinner(f"Fetching prices for {len(cons_df)} tickers (provider: {cfg.primary_provider})…"):
        prices = fetch_prices(tuple(sorted(set(cons_df["Ticker"].tolist() + [RISK_FREE_TICKER_YF]))),
                              primary=cfg.primary_provider, _cache_key_date=str(date.today()))
    rf_close = prices.get(RISK_FREE_TICKER_YF, pd.Series(dtype=float))

    rows = []
    for _, r in cons_df.iterrows():
        close = prices.get(r["Ticker"], pd.Series(dtype=float))
        if len(close) < 5: continue
        rets = compute_returns(close, cfg.timeframes, cfg.skip_month)
        breadth = compute_breadth(close, cfg.breadth)
        score = composite_score(rets, cfg.score_weights)
        abs_m = absolute_momentum(close, rf_close, skip_month=cfg.skip_month)
        rows.append({"Ticker": r["Ticker"], "Name": r["Name"],
                     "Country": r["Country"], "Sector": r["Sector"], "Index": r["Index"],
                     **{tf: rets.get(tf) for tf in cfg.timeframes},
                     "Score": score, "Abs Mom": abs_m, **breadth})
    if not rows:
        st.warning("No price data returned.")
        return

    full_df = pd.DataFrame(rows)
    z = relative_momentum_zscore(full_df.set_index("Ticker")["1Y"].to_dict()
                                 if "1Y" in cfg.timeframes else
                                 full_df.set_index("Ticker")[list(cfg.timeframes.keys())[0]].to_dict())
    full_df["Rel Mom z"] = full_df["Ticker"].map(z)
    st.caption(f"Computed metrics for **{len(full_df)}** of **{len(cons_df)}** tickers.")

    sub1, sub2, sub3, sub4 = st.tabs(["🌍 Geography", "🏭 Sector", "🏆 Top-N", "🌡️ Breadth"])
    with sub1:
        geo = full_df.groupby("Country").agg(
            Tickers=("Ticker", "count"),
            **{tf: (tf, "mean") for tf in cfg.timeframes},
        ).round(2).reset_index().sort_values(list(cfg.timeframes.keys())[-1] if cfg.timeframes else "Tickers",
                                              ascending=False)
        st.dataframe(geo.style.background_gradient(subset=list(cfg.timeframes.keys()), cmap="RdYlGn", vmin=-30, vmax=30)
                              .format({tf: lambda x: f"{x:+.1f}%" if pd.notna(x) else "—" for tf in cfg.timeframes}),
                     use_container_width=True)
        if cfg.timeframes:
            geo_hm = geo.set_index("Country")[list(cfg.timeframes.keys())]
            st.plotly_chart(render_heatmap(geo_hm, height=max(220, 30 * len(geo_hm)), title="Geography × Timeframe"),
                            use_container_width=True)
    with sub2:
        sec = full_df.groupby("Sector").agg(
            Tickers=("Ticker", "count"),
            **{tf: (tf, "mean") for tf in cfg.timeframes},
        ).round(2).reset_index().sort_values(list(cfg.timeframes.keys())[-1] if cfg.timeframes else "Tickers",
                                              ascending=False)
        st.dataframe(sec.style.background_gradient(subset=list(cfg.timeframes.keys()), cmap="RdYlGn", vmin=-30, vmax=30)
                              .format({tf: lambda x: f"{x:+.1f}%" if pd.notna(x) else "—" for tf in cfg.timeframes}),
                     use_container_width=True)
        if cfg.timeframes:
            sec_hm = sec.set_index("Sector")[list(cfg.timeframes.keys())]
            st.plotly_chart(render_heatmap(sec_hm, height=max(280, 25 * len(sec_hm)), title="Sector × Timeframe"),
                            use_container_width=True)
    with sub3:
        render_topn(full_df)
    with sub4:
        render_breadth(full_df)


# ═══════════════════════════════════════════════════════════════════════════════
# 16. ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
if page == "Dashboard":
    page_dashboard()
elif page == "Settings":
    page_settings()
elif page == "Presets":
    page_presets()
elif page == "Data Status":
    page_data_status()


# ═══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.markdown(
    '<div style="text-align:center;font-size:0.7rem;color:#6e7681;font-family:\'JetBrains Mono\',monospace;">'
    "Grok Alpha Terminal · DuckDB persistent store · "
    "yfinance + EODHD adapter · RRG (de Kempenaer) · Dual Momentum (Antonacci) · 12-1 (Jegadeesh-Titman)</div>",
    unsafe_allow_html=True,
)
