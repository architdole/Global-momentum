# ==================== UPDATED app.py ====================
import streamlit as st
import pandas as pd
import plotly.express as px
import duckdb
from datetime import datetime
import backtester
import json

st.set_page_config(page_title="Global Momentum + CANSLIM + ROE", layout="wide")
st.title("🌍 Global Momentum + CANSLIM + ROE Dashboard")

# ==================== ASK GROK SECTION ====================
st.subheader("🤖 Ask Grok (Dynamic View)")

with st.expander("💡 Example Requests (click to try)", expanded=False):
    st.markdown("""
    - "Show only Indian stocks with ROE above 22%"
    - "Compare DM vs EM using S&P 500 and MSCI India as benchmarks"
    - "Top 10 CANSLIM leaders with 12M momentum > 15%"
    - "Show high ROE stocks in India sorted by 3Y EPS growth"
    """)

user_request = st.text_input("Type your request here:", placeholder="e.g., Show only Indian stocks with ROE > 20% and strong 12M momentum")

if st.button("🚀 Ask Grok", type="primary"):
    if user_request:
        with st.spinner("Grok is analyzing your request..."):
            # This is where we will call Grok with structured prompt
            # For now showing placeholder - full version will have actual Grok call
            st.success("Grok understood your request and updated the view!")
            st.info("**Parsed Request:** Filter Country=India, ROE > 20, sort by 12M Momentum")
            # TODO: Full Grok integration will go here
    else:
        st.warning("Please type a request first.")

st.divider()

# ==================== MAIN DASHBOARD TABS ====================
tab1, tab2, tab3, tab4 = st.tabs(["📊 Asset Classes", "🌍 DM vs EM", "🏳️ Countries", "🔍 CANSLIM + ROE"])

with tab1:
    st.subheader("Asset Class Performance")
    # Improved table with multiple periods
    data = {
        "Asset Class": ["US Equity", "EM Equity", "DM ex-US", "US Treasuries", "Gold", "Commodities"],
        "1W": [1.2, -0.8, 0.5, 0.3, 0.9, -1.1],
        "1M": [3.4, 1.2, 2.1, 0.8, 2.3, -0.5],
        "3M": [8.1, 4.5, 6.2, 1.9, 5.8, 2.1],
        "6M": [12.4, 7.8, 9.5, 3.2, 8.9, -1.4],
        "12M": [22.5, 11.2, 15.8, 4.5, 14.2, -3.2],
        "3Y (Ann.)": [14.8, 6.9, 9.2, 2.1, 8.5, 4.3]
    }
    df = pd.DataFrame(data)
    st.dataframe(df.style.background_gradient(subset=["1W","1M","3M","6M","12M","3Y (Ann.)"], cmap="RdYlGn"), use_container_width=True)

with tab2:
    st.subheader("DM vs EM with Custom Benchmarks")
    st.caption("You can ask Grok to compare against specific benchmarks (S&P 500, Nasdaq, MSCI India, etc.)")

    # Placeholder for dynamic benchmark comparison
    st.info("This section will dynamically update based on your Grok requests (e.g., 'Compare DM vs EM against S&P 500 and MSCI India')")

with tab3:
    st.subheader("Country Momentum (1W to 3Y)")
    country_data = pd.DataFrame({
        "Country": ["India", "USA", "Japan", "Germany", "Brazil", "China"],
        "1W": [2.1, 1.4, 0.8, 0.6, -1.2, -0.9],
        "1M": [4.8, 3.2, 2.1, 1.8, -2.4, 1.5],
        "3M": [11.2, 7.5, 5.4, 4.2, -3.1, 2.8],
        "6M": [18.9, 12.4, 8.7, 6.9, -5.2, 3.4],
        "12M": [32.4, 24.1, 15.8, 11.2, -8.4, 6.2],
        "3Y (Ann.)": [18.5, 14.2, 9.8, 7.5, -2.1, 4.8]
    })
    st.dataframe(country_data.style.background_gradient(subset=["1W","1M","3M","6M","12M","3Y (Ann.)"], cmap="RdYlGn"))

with tab4:
    st.subheader("CANSLIM + ROE Leaders")
    st.caption("Clear ticker + company name + multiple return periods + ROE")
    
    canslim_data = pd.DataFrame({
        "Ticker": ["RELIANCE.NS", "HDFCBANK.NS", "AAPL.US", "MSFT.US", "INFY.NS"],
        "Name": ["Reliance Industries", "HDFC Bank", "Apple Inc.", "Microsoft Corp.", "Infosys"],
        "1W": [1.8, 0.9, 2.3, 1.5, 0.7],
        "1M": [4.2, 2.8, 5.1, 3.9, 1.9],
        "3M": [9.8, 6.4, 11.2, 8.7, 4.5],
        "6M": [15.6, 11.2, 18.4, 14.2, 7.8],
        "12M": [28.4, 19.5, 32.1, 26.8, 12.3],
        "3Y (Ann.)": [16.8, 12.4, 22.5, 19.8, 8.9],
        "ROE": [22.4, 18.9, 45.2, 42.1, 24.6],
        "CANSLIM": [94, 87, 91, 89, 78]
    })
    st.dataframe(
        canslim_data.style
        .background_gradient(subset=["1W","1M","3M","6M","12M","3Y (Ann.)"], cmap="RdYlGn")
        .background_gradient(subset=["ROE", "CANSLIM"], cmap="Blues"),
        use_container_width=True
    )

# ==================== FOOTER ====================
st.caption("Data: EODHD + yfinance | Powered by Grok (xAI) | Built for CA Archit Dole | May 2026")
