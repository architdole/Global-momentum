import streamlit as st
import pandas as pd

st.set_page_config(page_title="Grok Alpha Terminal", layout="wide")

st.title("⚡ Grok Alpha Terminal")
st.caption("Holistic Momentum • Safe Debug Version")

st.info("✅ Sidebar loaded. Now testing main content...")

# Guaranteed fallback data (no API calls, no DuckDB, no errors)
df = pd.DataFrame({
    "Ticker": ["RELIANCE.NS", "AAPL.US", "MSFT.US", "INFY.NS", "HDFCBANK.NS"],
    "Name": ["Reliance Industries", "Apple Inc.", "Microsoft", "Infosys", "HDFC Bank"],
    "Country": ["India", "US", "US", "India", "India"],
    "Sector": ["Energy", "Technology", "Technology", "Technology", "Financial"],
    "1W": [1.8, 2.3, 1.5, 0.7, 0.9],
    "1M": [4.2, 5.1, 3.9, 1.9, 2.8],
    "3M": [9.8, 11.2, 8.7, 4.5, 6.4],
    "6M": [15.6, 18.4, 14.2, 7.8, 11.2],
    "12M": [28.4, 32.1, 26.8, 12.3, 19.5],
    "Abs_Momentum_12M": [28.4, 32.1, 26.8, 12.3, 19.5],
    "Rel_Momentum_12M": [1.8, 2.1, 1.7, 0.8, 1.2]
})

st.success(f"✅ Safe fallback data loaded successfully ({len(df)} tickers)")

st.subheader("Test Table")
st.dataframe(df.style.background_gradient(subset=["1W","1M","3M","6M","12M"], cmap="RdYlGn"), use_container_width=True)

st.info("If you see this table, the app is working. The full version with EODHD data and all tabs will be added next.")

st.caption("Debug Version v3.4 • No API / DuckDB calls • Guaranteed to render")
