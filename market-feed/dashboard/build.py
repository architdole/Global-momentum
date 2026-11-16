"""Build the dashboard's data files from the repo.

Inputs (repo):
  market-feed/data/history/YYYY-MM-DD.json   market snapshots (GitHub Action)
  market-feed/news/YYYY-MM-DDTHHMM.json      one file per Claude news run:
      {run_at, market_brief, ai_brief, items: [{feed, category, region, headline,
       summary, source, url, date, importance, tickers}]}
Outputs (market-feed/dashboard/out/): markets, factors, india, rates, news, briefs (.json)
News run files may also carry "india_rates": [{metric, value, unit, change_bps, asof, source, url}]
Usage: python market-feed/dashboard/build.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

markets, factors, india = [], [], []
for f in sorted((ROOT / "data" / "history").glob("????-??-??.json")):
    snap = json.loads(f.read_text())
    day = f.stem
    for r in snap["markets"]:
        markets.append({"snap_date": day, **r})
    for r in snap["factors"]:
        factors.append({"snap_date": day, **r})
    for r in snap.get("india", []):
        india.append({"snap_date": day, **r})

news, briefs, rates = [], [], []
for f in sorted((ROOT / "news").glob("*.json")):
    run = json.loads(f.read_text())
    run_at = run["run_at"]
    briefs.append({"run_at": run_at, "market_brief": run.get("market_brief", ""),
                   "ai_brief": run.get("ai_brief", ""), "items": len(run.get("items", []))})
    for r in run.get("india_rates", []):
        rates.append({"run_at": run_at, **r})
    for i, it in enumerate(run.get("items", [])):
        news.append({"run_at": run_at, "id": f"{run_at}#{i}", **it,
                     "tickers": ", ".join(it.get("tickers", [])) if isinstance(it.get("tickers"), list) else it.get("tickers", "")})

for name, rows in [("markets", markets), ("factors", factors), ("india", india), ("rates", rates), ("news", news), ("briefs", briefs)]:
    (OUT / f"{name}.json").write_text(json.dumps(rows, separators=(",", ":")))
    print(name, len(rows))
