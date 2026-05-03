"""
Global Capital Markets Momentum + CANSLIM + ROE Dashboard
Refined & Integrated with Backtester Module
Better Design: Clean tabs, forms, Plotly visuals, download buttons, responsive layout
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import duckdb
from datetime import datetime, date
import backtester  # Refined module

st.set_page_config(
    page_title="Global Momentum + CANSLIM + ROE + Backtester",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better design
st.markdown("""
<style>
    .main-header {font-size: 2.5rem; color: #00FFAA; font-weight: bold;}
    .metric-card {background-color: #1A1F2E; padding: 1rem; border-radius: 0.5rem; border: 1px solid #00FFAA;}
    .stTabs [data-baseweb="tab-list"] {gap: 8px;}
    .stTabs [data-baseweb="tab"] {height: 50px; padding: 0 24px; background-color: #0E1117; border-radius: 8px 8px 0 0;}
</style>
""", unsafe_allow_html=True)

st.title("🌍 Global Momentum Tracker + CANSLIM + ROE + Backtester")
st.caption("EOD-only | Hierarchical | AI-Powered | Professional Backtesting")

# Sidebar - Global Controls
with st.sidebar:
    st.header("⚙️ Global Settings")
    st.info("Data auto-updates nightly via GitHub Actions + EODHD")
    theme = st.selectbox("Theme", ["Dark (Default)", "Light"], index=0)
    if theme == "Light":
        st.warning("Light theme coming soon - current is optimized for finance dashboards")

# Main Tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Asset Classes", "🌍 DM/EM", "🏳️ Countries", 
    "🔍 Country Drill-Down (CANSLIM+ROE)", "🏆 CANSLIM Leaders",
    "🔬 Backtester", "🤖 Grok AI Analyst"
])

# ============ TAB 1-5: Existing Dashboard (Refined) ============
with tab1:
    st.subheader("Asset Class Momentum Heatmap")
    # Placeholder for real data from DuckDB - refined with better visuals
    sample_asset = pd.DataFrame({
        "Asset": ["US Equity", "EM Equity", "DM ex-US", "US Treasuries", "Gold", "Commodities"],
        "1M Ret": [2.1, -1.2, 0.8, 0.5, 1.8, -0.9],
        "12M Ret": [18.4, 8.2, 12.5, 4.1, 15.2, -3.4],
        "Vol": [15.2, 22.1, 18.3, 8.5, 14.8, 19.2]
    })
    fig = px.imshow(sample_asset.set_index("Asset")[["1M Ret", "12M Ret"]], 
                    color_continuous_scale="RdYlGn", text_auto=True,
                    title="Asset Class Returns Heatmap")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(sample_asset.style.background_gradient(subset=["1M Ret", "12M Ret"], cmap="RdYlGn"), use_container_width=True)

with tab2:
    st.subheader("DM vs EM Equity Momentum")
    st.metric("DM Equity Avg 12M", "14.2%", "+2.1% vs EM")
    st.metric("EM Equity Avg 12M", "9.8%", "Higher vol")

with tab3:
    st.subheader("Country Momentum Ranking")
    countries = pd.DataFrame({"Country": ["India", "USA", "Japan", "Germany", "Brazil"], 
                              "12M Mom": [32.4, 24.1, 18.9, 12.3, -4.2]})
    st.dataframe(countries.style.background_gradient(subset=["12M Mom"], cmap="RdYlGn"))

with tab4:
    st.subheader("Top Liquid Tickers - Full CANSLIM + ROE View")
    st.caption("EODHD fundamentals + yfinance prices | Last 4Q EPS/Sales Growth + 3Y EPS + ROE TTM")
    sample_stocks = pd.DataFrame({
        "Ticker": ["RELIANCE.NS", "HDFCBANK.NS", "AAPL.US", "MSFT.US"],
        "Country": ["India", "India", "US", "US"],
        "C_EPS_4Q": [38, 22, 25, 29],
        "C_Sales_4Q": [24, 15, 18, 22],
        "A_EPS_3Y": [35, 28, 24, 27],
        "ROE_Latest": [22.4, 18.9, 45.2, 42.1],
        "ROE_3Y_Avg": [19.8, 17.5, 38.9, 39.2],
        "CANSLIM_Score": [94, 87, 91, 89]
    })
    st.dataframe(sample_stocks.style.background_gradient(subset=["ROE_Latest", "CANSLIM_Score"], cmap="RdYlGn"), use_container_width=True)

with tab5:
    st.subheader("🏆 Global CANSLIM + ROE Leaders")
    leaders = sample_stocks.nlargest(10, "CANSLIM_Score")
    st.dataframe(leaders)

# ============ TAB 6: BACKTESTER (New Integrated) ============
with tab6:
    st.header("🔬 RSI Breakout + Momentum Backtester")
    st.markdown("**Refined v2.0** - Full integration of your momentum factor strategy. Run simulations with live parameters.")

    with st.form("backtest_form"):
        col1, col2 = st.columns(2)
        with col1:
            tickers = st.text_area("Tickers (comma-separated, .NS for India)", 
                                   "RELIANCE.NS, HDFCBANK.NS, INFY.NS, TCS.NS, ICICIBANK.NS", height=80)
            start_date = st.date_input("Start Date", value=date(2012, 1, 1))
            end_date = st.date_input("End Date", value=date.today())
        
        with col2:
            st.subheader("Key Parameters")
            mom_top_n = st.slider("Momentum Top-N", 20, 100, 50)
            rebalance_n = st.slider("Rebalance Every N Months", 1, 12, 6)
            rsi_entry = st.slider("RSI Entry Threshold", 40.0, 70.0, 58.0, 1.0)
            max_loss = st.slider("Hard Stop Max Loss %", 10.0, 40.0, 25.0, 1.0)
            scale_up_pct = st.slider("Scale-Up Trigger %", 10.0, 50.0, 20.0, 5.0)

        submitted = st.form_submit_button("🚀 Run Backtest", use_container_width=True, type="primary")

    if submitted:
        with st.spinner("Running backtest... (may take 1-3 minutes for first run)"):
            tickers_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            results = backtester.run_backtest(
                tickers_list,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                mom_top_n=mom_top_n,
                rebalance_every_n_months=rebalance_n,
                rsi_entry_threshold=rsi_entry,
                max_loss_pct=max_loss,
                scale_up_trigger_pct=scale_up_pct,
                use_nifty_momentum_method=True
            )

            if "error" in results:
                st.error(results["error"])
            else:
                st.success("Backtest completed!")

                # Results Display - Better Design
                st.subheader("📈 Performance Summary")
                summary = results["summary"]
                cols = st.columns(4)
                cols[0].metric("CAGR", f"{summary.get('CAGR', 0)*100:.1f}%")
                cols[1].metric("Sharpe (Ann)", f"{summary.get('Sharpe_Ann', 0):.2f}")
                cols[2].metric("Max DD", f"{summary.get('MaxDrawdown', 0)*100:.1f}%")
                cols[3].metric("Win Rate", f"{summary.get('WinRate', 0)*100:.1f}%")

                # Equity Curve
                st.subheader("Equity Curve & Drawdown")
                eq = results["equity_curve"].to_frame("Equity")
                fig_eq = px.line(eq, title="Portfolio Equity Curve", labels={"value": "₹"})
                st.plotly_chart(fig_eq, use_container_width=True)

                # Trades Table
                st.subheader("Trades Log")
                trades = results["trades_df"]
                if not trades.empty:
                    st.dataframe(trades.style.background_gradient(subset=["PnL", "ReturnPct"], cmap="RdYlGn"), use_container_width=True)
                else:
                    st.info("No closed trades in this run.")

                # Downloads
                st.download_button("📥 Download Full Excel Report", 
                                   data=results["trades_df"].to_csv(index=False), 
                                   file_name=f"backtest_{datetime.now().strftime('%Y%m%d')}.csv")

# ============ TAB 7: Grok AI Analyst ============
with tab7:
    st.subheader("🤖 Grok AI Analyst (CANSLIM + Momentum + Backtest Insights)")
    st.info("Ask anything about current market momentum, CANSLIM scores, or backtest results.")
    user_query = st.text_input("Your question:", "Which sectors show strongest CANSLIM + ROE setup right now?")
    if st.button("Ask Grok"):
        st.markdown("**Grok Response (demo):** Based on latest EOD data, India midcaps and US tech show strong C/A scores with ROE >25%. Consider scaling into leaders with momentum confirmation.")

# Footer
st.caption("Data: EODHD + yfinance | Backtester: Custom RSI Breakout + Momentum 50 | Updated: May 2026 | Built with ❤️ for Indian & Global Investors")

if __name__ == "__main__":
    pass  # Streamlit handles execution
