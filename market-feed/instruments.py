"""Instrument universe for the global markets dashboard.

kind:
  price  -> % return from Close (indices, FX, commodities, crypto)
  tr     -> % total return from Adj Close (ETFs; dividends reinvested)
  yield  -> change in basis points (government bond yields quoted in %)
"""

INSTRUMENTS = [
    # ── US equity indices ───────────────────────────────────────────
    ("^GSPC", "S&P 500", "US Equity", "price"),
    ("^NDX", "Nasdaq 100", "US Equity", "price"),
    ("^IXIC", "Nasdaq Composite", "US Equity", "price"),
    ("^DJI", "Dow Jones", "US Equity", "price"),
    ("^RUT", "Russell 2000", "US Equity", "price"),
    ("^SP400", "S&P MidCap 400", "US Equity", "price"),
    ("RSP", "S&P 500 Equal Weight", "US Equity", "tr"),
    ("^SOX", "PHLX Semiconductor", "US Equity", "price"),
    ("^VIX", "VIX", "US Equity", "price"),
    # ── Global equity indices ───────────────────────────────────────
    ("ACWI", "MSCI ACWI", "Global Equity", "tr"),
    ("^STOXX", "STOXX Europe 600", "Global Equity", "price"),
    ("^STOXX50E", "Euro Stoxx 50", "Global Equity", "price"),
    ("^FTSE", "FTSE 100", "Global Equity", "price"),
    ("^GDAXI", "DAX", "Global Equity", "price"),
    ("^FCHI", "CAC 40", "Global Equity", "price"),
    ("^N225", "Nikkei 225", "Global Equity", "price"),
    ("^HSI", "Hang Seng", "Global Equity", "price"),
    ("ASHR", "CSI 300 (ASHR, USD)", "Global Equity", "tr"),
    ("000001.SS", "Shanghai Composite", "Global Equity", "price"),
    ("^KS11", "KOSPI", "Global Equity", "price"),
    ("^TWII", "Taiwan Weighted", "Global Equity", "price"),
    ("^AXJO", "ASX 200", "Global Equity", "price"),
    ("^NSEI", "Nifty 50", "Global Equity", "price"),
    ("^BSESN", "Sensex", "Global Equity", "price"),
    ("^NSEBANK", "Nifty Bank", "Global Equity", "price"),
    ("^GSPTSE", "S&P/TSX", "Global Equity", "price"),
    ("^BVSP", "Bovespa", "Global Equity", "price"),
    ("^MXX", "Mexico IPC", "Global Equity", "price"),
    ("EEM", "MSCI Emerging Mkts", "Global Equity", "tr"),
    # ── Debt ─────────────────────────────────────────────────────────
    ("^IRX", "US 13-week T-bill yield", "Debt", "yield"),
    ("^FVX", "US 5Y yield", "Debt", "yield"),
    ("^TNX", "US 10Y yield", "Debt", "yield"),
    ("^TYX", "US 30Y yield", "Debt", "yield"),
    ("AGG", "US Aggregate Bond", "Debt", "tr"),
    ("SHY", "US Treasury 1-3Y", "Debt", "tr"),
    ("IEF", "US Treasury 7-10Y", "Debt", "tr"),
    ("TLT", "US Treasury 20Y+", "Debt", "tr"),
    ("TIP", "US TIPS", "Debt", "tr"),
    ("LQD", "US IG Corporate", "Debt", "tr"),
    ("HYG", "US High Yield", "Debt", "tr"),
    ("BNDX", "Intl Aggregate (hedged)", "Debt", "tr"),
    ("EMB", "EM USD Sovereign", "Debt", "tr"),
    # ── Dollar & currencies ─────────────────────────────────────────
    ("DX-Y.NYB", "US Dollar Index (DXY)", "Dollar & FX", "price"),
    ("EURUSD=X", "EUR/USD", "Dollar & FX", "price"),
    ("GBPUSD=X", "GBP/USD", "Dollar & FX", "price"),
    ("JPY=X", "USD/JPY", "Dollar & FX", "price"),
    ("CNY=X", "USD/CNY", "Dollar & FX", "price"),
    ("INR=X", "USD/INR", "Dollar & FX", "price"),
    ("AUDUSD=X", "AUD/USD", "Dollar & FX", "price"),
    ("CHF=X", "USD/CHF", "Dollar & FX", "price"),
    # ── Commodities ─────────────────────────────────────────────────
    ("GC=F", "Gold", "Commodities", "price"),
    ("SI=F", "Silver", "Commodities", "price"),
    ("PL=F", "Platinum", "Commodities", "price"),
    ("HG=F", "Copper", "Commodities", "price"),
    ("CL=F", "WTI Crude", "Commodities", "price"),
    ("BZ=F", "Brent Crude", "Commodities", "price"),
    ("NG=F", "Natural Gas", "Commodities", "price"),
    ("ZW=F", "Wheat", "Commodities", "price"),
    ("ZC=F", "Corn", "Commodities", "price"),
    ("DBC", "Broad Commodities (DBC)", "Commodities", "tr"),
    # ── Alternatives ────────────────────────────────────────────────
    ("BTC-USD", "Bitcoin", "Alternatives", "price"),
    ("ETH-USD", "Ether", "Alternatives", "price"),
    ("SOL-USD", "Solana", "Alternatives", "price"),
    ("VNQ", "US REITs", "Alternatives", "tr"),
]

# Factor ETFs by geography. role: benchmark | factor
FACTORS = [
    # US
    ("SPY", "US", "Market", "benchmark"),
    ("MTUM", "US", "Momentum", "factor"),
    ("VLUE", "US", "Value", "factor"),
    ("QUAL", "US", "Quality", "factor"),
    ("USMV", "US", "Min Volatility", "factor"),
    ("SIZE", "US", "Size", "factor"),
    ("IWF", "US", "Growth", "factor"),
    ("IWM", "US", "Small Cap", "factor"),
    ("SPHB", "US", "High Beta", "factor"),
    # International developed
    ("EFA", "Intl Developed", "Market", "benchmark"),
    ("IMTM", "Intl Developed", "Momentum", "factor"),
    ("IVLU", "Intl Developed", "Value", "factor"),
    ("IQLT", "Intl Developed", "Quality", "factor"),
    ("EFAV", "Intl Developed", "Min Volatility", "factor"),
    ("SCZ", "Intl Developed", "Small Cap", "factor"),
    # Emerging markets
    ("EEM", "Emerging", "Market", "benchmark"),
    ("EEMO", "Emerging", "Momentum", "factor"),
    ("FNDE", "Emerging", "Value", "factor"),
    ("EEMV", "Emerging", "Min Volatility", "factor"),
    ("EEMS", "Emerging", "Small Cap", "factor"),
    # India (NSE factor ETFs)
    ("NIFTYBEES.NS", "India", "Market", "benchmark"),
    ("MOM30IETF.NS", "India", "Momentum", "factor"),
    ("NV20IETF.NS", "India", "Value", "factor"),
    ("QUAL30IETF.NS", "India", "Quality", "factor"),
    ("LOWVOLIETF.NS", "India", "Min Volatility", "factor"),
    ("ALPHA.NS", "India", "Alpha", "factor"),
]
