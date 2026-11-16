"""Pull daily prices from Yahoo and write multi-period performance JSON.

Outputs (relative to this folder):
  data/latest.json               newest snapshot (dashboard reads this)
  data/history/YYYY-MM-DD.json   one snapshot per UTC day (overwritten intraday)
  data/history/index.json        list of snapshot dates
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from instruments import FACTORS, INDIA, INDIA_BENCH, INSTRUMENTS

HERE = Path(__file__).resolve().parent
OUT = HERE / "data"
HIST = OUT / "history"

PERIODS = {  # label -> pandas offset (None = special)
    "1D": None,
    "1W": pd.DateOffset(weeks=1),
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "YTD": "ytd",
    "1Y": pd.DateOffset(years=1),
    "3Y": pd.DateOffset(years=3),
    "5Y": pd.DateOffset(years=5),
}


def clean(x):
    if x is None:
        return None
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return round(float(x), 4)


def series_for(data: pd.DataFrame, ticker: str, field: str) -> pd.Series:
    try:
        s = data[(field, ticker)] if isinstance(data.columns, pd.MultiIndex) else data[field]
    except KeyError:
        return pd.Series(dtype=float)
    return s.dropna()


def perf(s: pd.Series, kind: str) -> dict:
    out = {p: None for p in PERIODS}
    if s.empty:
        return out
    last_dt, last = s.index[-1], float(s.iloc[-1])
    for label, off in PERIODS.items():
        if label == "1D":
            if len(s) < 2:
                continue
            base = float(s.iloc[-2])
        else:
            if off == "ytd":
                target = pd.Timestamp(year=last_dt.year, month=1, day=1) - pd.Timedelta(days=1)
            else:
                target = last_dt - off
            prior = s[s.index <= target]
            if prior.empty or (target - prior.index[-1]).days > 10:
                continue  # not enough history
            base = float(prior.iloc[-1])
        if kind == "yield":
            out[label] = clean((last - base) * 100)  # bps
        elif base:
            out[label] = clean((last / base - 1) * 100)
    return out


def ann(cum_pct, years):
    if cum_pct is None:
        return None
    return clean(((1 + cum_pct / 100) ** (1 / years) - 1) * 100)


def main():
    tickers = sorted({t for t, *_ in INSTRUMENTS} | {t for t, *_ in FACTORS}
                     | {c for cands, *_ in INDIA for c in cands} | set(INDIA_BENCH))
    data = yf.download(tickers, period="6y", interval="1d", auto_adjust=False,
                       group_by="column", progress=False, threads=True)
    data.index = pd.to_datetime(data.index).tz_localize(None)

    rows, missing = [], []
    for t, name, group, kind in INSTRUMENTS:
        s = series_for(data, t, "Adj Close" if kind == "tr" else "Close")
        if s.empty:
            missing.append(t)
        p = perf(s, kind)
        rows.append({
            "ticker": t, "name": name, "group": group, "kind": kind,
            "last": clean(s.iloc[-1]) if not s.empty else None,
            "asof": s.index[-1].strftime("%Y-%m-%d") if not s.empty else None,
            **{f"r_{k}": v for k, v in p.items()},
            "r_3Y_ann": ann(p["3Y"], 3) if kind != "yield" else None,
            "r_5Y_ann": ann(p["5Y"], 5) if kind != "yield" else None,
        })

    factor_rows = []
    bench = {}
    for t, geo, factor, role in FACTORS:
        s = series_for(data, t, "Adj Close")
        if s.empty:
            missing.append(t)
        p = perf(s, "tr")
        row = {"ticker": t, "geo": geo, "factor": factor, "role": role,
               "asof": s.index[-1].strftime("%Y-%m-%d") if not s.empty else None,
               **{f"r_{k}": v for k, v in p.items()}}
        if role == "benchmark":
            bench[geo] = p
        factor_rows.append(row)
    for row in factor_rows:  # excess return vs the region's market benchmark
        b = bench.get(row["geo"], {})
        for k in PERIODS:
            r, m = row[f"r_{k}"], b.get(k)
            row[f"x_{k}"] = clean(r - m) if r is not None and m is not None and row["role"] == "factor" else None

    # ── India: pick first candidate with data; relative to Nifty 500 ──
    bench_s, bench_t = pd.Series(dtype=float), None
    for b in INDIA_BENCH:
        bench_s = series_for(data, b, "Close")
        if not bench_s.empty:
            bench_t = b
            break
    bench_p = perf(bench_s, "price")
    india_rows = []
    for cands, name, group, kind in INDIA:
        s, used = pd.Series(dtype=float), None
        for c in cands:
            s = series_for(data, c, "Adj Close" if kind == "tr" else "Close")
            if not s.empty and len(s) > 30:
                used = c
                break
        if used is None:
            missing.append("|".join(cands))
        p = perf(s, kind)
        row = {"ticker": used or cands[0], "name": name, "group": group, "kind": kind,
               "proxy": bool(used and used != cands[0] and used.endswith(".NS") and group == "Factor"),
               "last": clean(s.iloc[-1]) if not s.empty else None,
               "asof": s.index[-1].strftime("%Y-%m-%d") if not s.empty else None,
               **{f"r_{k}": v for k, v in p.items()}}
        for k in PERIODS:  # excess return vs Nifty 500 (equity groups only)
            r, m = p[k], bench_p.get(k)
            row[f"x_{k}"] = clean(((1 + r / 100) / (1 + m / 100) - 1) * 100) if (group != "Debt" and r is not None and m is not None and name != "India VIX") else None
        if not s.empty:
            last = float(s.iloc[-1])
            yr = s[s.index > s.index[-1] - pd.DateOffset(years=1)]
            row["off_high_52w"] = clean((last / float(yr.max()) - 1) * 100) if len(yr) else None
            row["above_200dma"] = bool(last > float(s.iloc[-200:].mean())) if len(s) >= 200 else None
        india_rows.append(row)

    now = datetime.now(timezone.utc)
    snap = {
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Yahoo Finance daily closes via yfinance (GitHub Action)",
        "notes": "price = % change of close; tr = % total return (adj. close); yield = change in bps. 3Y/5Y cumulative, *_ann annualised.",
        "periods": list(PERIODS),
        "markets": rows,
        "factors": factor_rows,
        "india": india_rows,
        "india_benchmark": bench_t,
        "missing": sorted(set(missing)),
    }
    OUT.mkdir(exist_ok=True)
    HIST.mkdir(exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(snap, indent=1))
    day = now.strftime("%Y-%m-%d")
    (HIST / f"{day}.json").write_text(json.dumps(snap))
    idx = sorted(p.stem for p in HIST.glob("????-??-??.json"))
    (HIST / "index.json").write_text(json.dumps(idx))
    print(f"wrote {len(rows)} markets, {len(factor_rows)} factors; missing: {snap['missing']}")


if __name__ == "__main__":
    main()
