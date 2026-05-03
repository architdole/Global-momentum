import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from eodhd import APIClient
from openai import OpenAI
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import warnings
warnings.filterwarnings("ignore")

# --- 1. CONFIGURATION & TERMINAL THEME ---
st.set_page_config(page_title="Grok Alpha Terminal", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background: #0b0e14; color: #e0e0e0; }
    [data-testid="stMetricValue"] { color: #00ffa2 !important; font-family: 'Courier New'; font-size: 1.8rem; }
    .glass-panel {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(12px);
        border-radius: 16px;
        padding: 24px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. API INITIALIZATION ---
EODHD_KEY = st.secrets.get("EODHD_KEY")
XAI_API_KEY = st.secrets.get("XAI_API_KEY")

if not EODHD_KEY or not XAI_API_KEY:
    st.error("⚠️ Missing API keys in Streamlit secrets. Add EODHD_KEY and XAI_API_KEY to continue.")
    st.stop()

api = APIClient(api_key=EODHD_KEY)
grok = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

INDEX_MAP = {
    "S&P 500 (US)": "GSPC.INDX",
    "NIFTY 50 (IN)": "NIFTY50.INDX",
    "NASDAQ 100": "NDX.INDX",
    "FTSE 100 (UK)": "FTSE.INDX"
}

# --- 3. DATA ENGINE ---
@st.cache_data(ttl=3600)
def get_technical_breadth(index_label: str, max_components: int = 50):
    """Calculates % > 200DMA and RSI status for index components."""
    index_symbol = INDEX_MAP[index_label]
    
    try:
        fund = api.get_fundamentals_data(index_symbol)
        components = fund.get('Components', {}) if isinstance(fund, dict) else {}
        
        # Get tickers (Code.Exchange format)
        tickers = [f"{v.get('Code', '')}.{v.get('Exchange', '')}" 
                  for k, v in list(components.items())[:max_components]]
    except Exception as e:
        st.error(f"Failed to fetch index components: {str(e)}")
        return pd.DataFrame()

    def fetch_tech(t):
        try:
            # Latest RSI & SMA200
            rsi_data = api.get_technical_indicator_data(t, function='rsi', period=14)
            sma_data = api.get_technical_indicator_data(t, function='sma', period=200)
            
            # Latest price (single EOD call)
            eod_data = api.get_eod_historical_stock_market_data(t, limit=1)
            
            if not rsi_data or not sma_data or not eod_data:
                return None
                
            rsi = rsi_data[0]['rsi'] if isinstance(rsi_data, list) else rsi_data.get('rsi')
            sma = sma_data[0]['sma'] if isinstance(sma_data, list) else sma_data.get('sma')
            price = eod_data[0]['close'] if isinstance(eod_data, list) else eod_data.get('close')
            
            return {
                "Ticker": t,
                "RSI": float(rsi),
                "SMA200": float(sma),
                "Price": float(price),
                "Above_200DMA": price > sma
            }
        except Exception:
            return None

    with st.spinner(f"Scanning {len(tickers)} components..."):
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(fetch_tech, tickers))
    
    df = pd.DataFrame([r for r in results if r])
    return df

@st.cache_data(ttl=3600)
def run_backtest(ticker: str, yrs: int = 3):
    """Backtests RSI 55/45 Strategy with SMA200 filter. Returns full DataFrame."""
    start = (datetime.today() - timedelta(days=365 * yrs)).strftime("%Y-%m-%d")
    
    try:
        # Historical prices
        prices = api.get_eod_historical_stock_market_data(
            ticker, from_date=start, order='a'
        )
        prices_df = pd.DataFrame(prices).set_index('date')
        
        # Technical indicators
        rsi_list = api.get_technical_indicator_data(ticker, function='rsi', period=14)
        sma_list = api.get_technical_indicator_data(ticker, function='sma', period=200)
        
        rsi_df = pd.DataFrame(rsi_list).set_index('date')
        sma_df = pd.DataFrame(sma_list).set_index('date')
        
        df = prices_df.join([rsi_df['rsi'], sma_df['sma']], how='inner')
        df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low',
                               'close': 'Close', 'volume': 'Volume'})
        df = df[['Open', 'High', 'Low', 'Close', 'Volume', 'rsi', 'sma']].dropna()
        
        # Strategy logic
        df['Signal'] = 0
        position = 0
        for i in range(len(df)):
            if df['rsi'].iloc[i] > 55 and df['Close'].iloc[i] > df['sma'].iloc[i]:
                position = 1
            elif df['rsi'].iloc[i] < 45:
                position = 0
            df.loc[df.index[i], 'Signal'] = position
        
        df['Market_Ret'] = df['Close'].pct_change()
        df['Strat_Ret'] = df['Signal'].shift(1) * df['Market_Ret']
        
        return df.dropna()
    except Exception as e:
        st.error(f"Backtest failed: {str(e)}")
        return pd.DataFrame()

# --- 4. UI ---
st.title("⚡ Grok Alpha Terminal")
st.caption("Real-time market breadth • RSI strategy backtesting • AI-powered insights")

# Sidebar
with st.sidebar:
    st.header("🧠 AI Analyst Sandbox")
    user_logic = st.text_area("Custom logic prompt:", 
                              "Rank components by momentum but prioritize high ROE and low debt/equity.",
                              height=120)
    
    if st.button("🚀 Ask Grok Analyst", type="primary"):
        with st.spinner("Thinking..."):
            try:
                response = grok.chat.completions.create(
                    model="grok-beta",  # Update to "grok-4.3" if preferred
                    messages=[{"role": "user", "content": f"Current market breadth analysis for {user_logic}"}],
                    temperature=0.7
                )
                st.session_state.ai_response = response.choices[0].message.content
            except Exception as e:
                st.error(f"AI call failed: {str(e)}")
    
    if "ai_response" in st.session_state:
        st.info(st.session_state.ai_response)

tabs = st.tabs(["🏛️ Market Breadth", "🧪 Backtest Sandbox", "🧬 Sector Insights"])

# TAB 1: MARKET BREADTH
with tabs[0]:
    col1, col2 = st.columns([3, 1])
    with col1:
        idx_choice = st.selectbox("Select Index", list(INDEX_MAP.keys()))
    with col2:
        max_comp = st.slider("Max components", 20, 100, 50)
    
    if st.button("Run Breadth Scan", type="primary", use_container_width=True):
        b_df = get_technical_breadth(idx_choice, max_comp)
        
        if not b_df.empty:
            c1, c2, c3 = st.columns(3)
            breadth_pct = b_df['Above_200DMA'].mean() * 100
            c1.metric("Breadth (> 200DMA)", f"{breadth_pct:.1f}%", 
                     help="Percentage of components trading above their 200-day moving average")
            c2.metric("RSI > 55 (Bullish)", len(b_df[b_df['RSI'] > 55]))
            c3.metric("RSI < 45 (Bearish)", len(b_df[b_df['RSI'] < 45]))
            
            st.subheader("RSI Distribution")
            fig_rsi = px.histogram(b_df, x="RSI", nbins=25, template="plotly_dark",
                                 color_discrete_sequence=['#00ffa2'])
            fig_rsi.add_vline(x=55, line_dash="dash", line_color="#00ff00", annotation_text="Buy Zone")
            fig_rsi.add_vline(x=45, line_dash="dash", line_color="#ff4444", annotation_text="Sell Zone")
            st.plotly_chart(fig_rsi, use_container_width=True)
            
            st.subheader("Component Details")
            st.dataframe(
                b_df.style.background_gradient(subset=['RSI'], cmap='RdYlGn')
                          .format({"RSI": "{:.1f}", "SMA200": "{:.2f}", "Price": "{:.2f}"}),
                use_container_width=True
            )
        else:
            st.warning("No data returned. Check API key or index symbol.")

# TAB 2: BACKTEST SANDBOX
with tabs[1]:
    col_l, col_r = st.columns([1, 3])
    with col_l:
        bt_ticker = st.text_input("Ticker (e.g. AAPL.US)", "AAPL.US")
        bt_yrs = st.slider("Backtest Years", 1, 10, 3)
        run_bt = st.button("Execute Backtest", type="primary", use_container_width=True)
    
    if run_bt:
        with st.spinner("Running backtest..."):
            res = run_backtest(bt_ticker, bt_yrs)
            
            if not res.empty:
                with col_r:
                    cum_strat = (1 + res['Strat_Ret']).cumprod()
                    cum_mkt = (1 + res['Market_Ret']).cumprod()
                    
                    fig_bt = go.Figure()
                    fig_bt.add_trace(go.Scatter(x=res.index, y=cum_mkt, name="Buy & Hold", line=dict(color='gray')))
                    fig_bt.add_trace(go.Scatter(x=res.index, y=cum_strat, name="RSI 55/45 Strategy", 
                                              line=dict(color='#00ffa2', width=3)))
                    fig_bt.update_layout(template="plotly_dark", title=f"{bt_ticker} Strategy Performance",
                                       height=500)
                    st.plotly_chart(fig_bt, use_container_width=True)
                    
                    # Enhanced metrics
                    total_ret = (cum_strat.iloc[-1] - 1) * 100
                    mkt_ret = (cum_mkt.iloc[-1] - 1) * 100
                    alpha = total_ret - mkt_ret
                    
                    sharpe = res['Strat_Ret'].mean() / res['Strat_Ret'].std() * np.sqrt(252) if res['Strat_Ret'].std() != 0 else 0
                    max_dd = ((cum_strat.cummax() - cum_strat) / cum_strat.cummax()).max() * 100
                    
                    col_a, col_b, col_c = st.columns(3)
                    col_a.metric("Strategy Return", f"{total_ret:.1f}%")
                    col_b.metric("Alpha vs Market", f"{alpha:.1f}%", delta=f"{alpha:.1f}%")
                    col_c.metric("Sharpe Ratio", f"{sharpe:.2f}")
                    st.metric("Max Drawdown", f"{max_dd:.1f}%", help="Largest peak-to-trough decline")
            else:
                st.warning("Backtest returned no data.")

# TAB 3: SECTOR INSIGHTS (placeholder — ready for expansion)
with tabs[2]:
    st.markdown("<div class='glass-panel'><h4>Sector Momentum Leaders</h4><p>Coming soon: Real-time sector rotation signals powered by breadth data from Tab 1.</p></div>", 
                unsafe_allow_html=True)
    st.info("🔄 Select an index in the Market Breadth tab to auto-populate sector leaders here in future updates.")

st.caption("Grok Alpha Terminal v2.0 • Powered by EODHD + xAI Grok • Data refreshed hourly")
