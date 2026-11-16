# market-feed

Daily price feed for Archit's global markets dashboard. A GitHub Action (`.github/workflows/market-feed.yml`) pulls Yahoo closes 3x a day, computes 1D–5Y returns for indices, bonds, FX, commodities, crypto and factor ETFs, and commits `data/latest.json` plus one snapshot per day in `data/history/`.

Edit `instruments.py` to add or remove tickers.
