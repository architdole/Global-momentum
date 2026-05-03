# Global Momentum + CANSLIM + ROE + Backtester (Refined v2.0)

Professional EOD dashboard with hierarchical momentum tracking, full CANSLIM scoring (EPS/Sales growth, ROE), and integrated backtesting module.

## Features
- **Dashboard Tabs**: Asset Classes → DM/EM → Countries → Ticker Drill-Down (CANSLIM + ROE) → Leaders → **Backtester** → Grok AI
- **Backtester**: Full RSI Breakout + Momentum 50 strategy (your original code, refined for modularity)
- **Better Design**: Clean forms, Plotly charts, metric cards, responsive layout, Excel downloads
- **Data**: EODHD fundamentals (ROE, EPS, Sales) + yfinance prices
- **Deployment**: Free on Streamlit Community Cloud

## Setup (GitHub + Streamlit)
1. Create repo `Global-momentum`
2. Add these files: `app.py`, `backtester.py`, `requirements.txt`, `README.md`
3. Deploy on share.streamlit.io
4. Add secrets: `EODHD_KEY`, `XAI_API_KEY`
5. Run the app!

## Run Locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Backtester Usage (in code)
```python
import backtester
results = backtester.run_backtest(
    ["RELIANCE.NS", "AAPL.US"],
    start="2015-01-01",
    mom_top_n=50,
    rsi_entry_threshold=58.0
)
print(results["summary"])
```

## Refined Improvements
- Fixed Windows paths → cross-platform
- Added `run_backtest()` API for Streamlit
- Better logging, error handling, type hints
- Professional UI with forms, tabs, downloads
- Integrated with CANSLIM + ROE dashboard

Built for CA Archit Dole | Hyderabad | May 2026
