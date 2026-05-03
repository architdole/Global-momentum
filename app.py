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

# ==================== TERMINAL THEME ====================
st.set_page_config(page_title="Grok Alpha Terminal", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
    <style>
    .stApp { background: #0b0e14; color: #e0e0e0; }
    [data-testid="stMetricValue"] { color: #00ffa2 !important; font-family: 'Courier New'; font-size: 1.8rem; }
    .glass-panel { background: rgba(255,255,255,0.03); backdrop-filter: blur(12px); border-radius: 16px; padding: 24px; border: 1px solid rgba(255,255,255,0.12); margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Grok Alpha Terminal")
st.caption("Holistic Momentum • Market Breadth • RSI Strategy • AI Analyst • Real EODHD Data")

# ==================== API KEYS ====================
EODHD_KEY = st.secrets.get("EODHD_KEY")
XAI_API_KEY = st.secrets.get("XAI_API_KEY")
if not EODHD_KEY or not XAI_API_KEY:
    st.error("⚠️ Missing API keys in Streamlit Secrets. Add EODHD_KEY and XAI_API_KEY.")
    st.stop()

api = APIClient(api_key=EODHD_KEY)
grok = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

# ==================== SIDEBAR CONTROLS ====================
with st.sidebar:
    st.header("🔧 Controls")
    as_of_date = st.date_input("View as of (EOD)", value=datetime.today().date())
    top_n = st.selectbox("Top N liquid stocks", [50, 100, 200, 500], index=1)

# ==================== DYNAMIC UNIVERSE + MOMENTUM ====================
@st.cache_data(ttl=3600)
def get_dynamic_universe(top_n: int):
    try:
        screener = api.stock_market_screener(
            sort="market_capitalization.desc",
            limit=top_n * 2,
            filters='[["avg_volume_200d",">",1000000],["market_capitalization",">",500000000]]'
        )
        return pd.DataFrame({
            "Ticker": screener['code'],
            "Name": screener['name'],
            "Country": screener.get('country', 'Global'),
            "Sector": screener.get('sector', 'Unknown'),
            "MarketCap": screener.get('market_capitalization', 0)
        }).head(top_n)
    except Exception as e:
        st.warning(f"Screener error: {e}. Using fallback.")
        return pd.DataFrame({"Ticker":["RELIANCE.NS","AAPL.US"], "Name":["Reliance","Apple"], "Country":["India","US"], "Sector":["Energy","Technology"], "MarketCap":[2e11,3e12]})

universe = get_dynamic_universe(top_n)

@st.cache_data(ttl=3600)
def compute_momentum(df_universe, as_of_str):
    data = []
    for _, row in df_universe.iterrows():
        try:
            price_df = api.get_eod(symbol=row["Ticker"], from_date=(datetime.strptime(as_of_str,"%Y-%m-%d") - timedelta(days=1100)).strftime("%Y-%m-%d"), to_date=as_of_str)
            close = price_df['close'].astype(float).values
            if len(close) < 30: continue
            daily_ret = np.diff(np.log(close))
            def calc(days):
                if len(close) < days: return None, None
                ret = (close[-1] / close[-days] - 1) * 100
                vol = np.std(daily_ret[-days:]) * np.sqrt(252) * 100
                return round(ret, 2), round(ret / vol, 2) if vol > 0 else None
            data.append({
                "Ticker": row["Ticker"], "Name": row["Name"], "Country": row["Country"],
                "Sector": row["Sector"], "MarketCap": row["MarketCap"],
                "1W": calc(5)[0], "1M": calc(21)[0], "3M": calc(63)[0],
                "6M": calc(126)[0], "12M": calc(252)[0],
                "Abs_Momentum_12M": calc(252)[0],
                "Rel_Momentum_12M": calc(252)[1],
            })
        except: continue
    return pd.DataFrame(data)

df = compute_momentum(universe, str(as_of_date))

# ==================== TABS ====================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Holistic Dashboard", "🏛️ Market Breadth", "🧪 Backtest Sandbox", "🔍 Momentum Leaders", "🧠 Grok AI Analyst"])

with tab1:
    st.subheader("Holistic View – Region × Sector × Market Cap")
    df['MarketCapBucket'] = pd.qcut(df['MarketCap'], 4, labels=['Small','Mid','Large','Mega'])
    fig = px.treemap(df, path=['Country', 'Sector', 'MarketCapBucket'], values='MarketCap',
                     color='Abs_Momentum_12M', color_continuous_scale='RdYlGn')
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df.style.background_gradient(subset=["1W","1M","3M","6M","12M","Abs_Momentum_12M","Rel_Momentum_12M"], cmap="RdYlGn"), use_container_width=True)

# ==================== MARKET BREADTH (your full code) ====================
with tab2:
    INDEX_MAP = {"S&P 500 (US)": "GSPC.INDX", "NIFTY 50 (IN)": "NIFTY50.INDX", "NASDAQ 100": "NDX.INDX", "FTSE 100 (UK)": "FTSE.INDX"}
    def get_technical_breadth(index_label: str, max_components: int = 50):
        index_symbol = INDEX_MAP[index_label]
        try:
            fund = api.get_fundamentals_data(index_symbol)
            components = fund.get('Components', {}) if isinstance(fund, dict) else {}
            tickers = [f"{v.get('Code', '')}.{v.get('Exchange', '')}" for k, v in list(components.items())[:max_components]]
        except Exception as e:
            st.error(f"Failed to fetch index components: {e}")
            return pd.DataFrame()
        def fetch_tech(t):
            try:
                rsi_data = api.get_technical_indicator_data(t, function='rsi', period=14)
                sma_data = api.get_technical_indicator_data(t, function='sma', period=200)
                eod_data = api.get_eod_historical_stock_market_data(t, limit=1)
                if not rsi_data or not sma_data or not eod_data: return None
                rsi = rsi_data[0]['rsi'] if isinstance(rsi_data, list) else rsi_data.get('rsi')
                sma = sma_data[0]['sma'] if isinstance(sma_data, list) else sma_data.get('sma')
                price = eod_data[0]['close'] if isinstance(eod_data, list) else eod_data.get('close')
                return {"Ticker": t, "RSI": float(rsi), "SMA200": float(sma), "Price": float(price), "Above_200DMA": price > sma}
            except: return None
        with st.spinner(f"Scanning {len(tickers)} components..."):
            with ThreadPoolExecutor(max_workers=12) as executor:
                results = list(executor.map(fetch_tech, tickers))
        return pd.DataFrame([r for r in results if r])
    col1, col2 = st.columns([3, 1])
    with col1: idx_choice = st.selectbox("Select Index", list(INDEX_MAP.keys()))
    with col2: max_comp = st.slider("Max components", 20, 100, 50)
    if st.button("Run Breadth Scan", type="primary", use_container_width=True):
        b_df = get_technical_breadth(idx_choice, max_comp)
        if not b_df.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Breadth (> 200DMA)", f"{b_df['Above_200DMA'].mean()*100:.1f}%")
            c2.metric("RSI > 55 (Bullish)", len(b_df[b_df['RSI'] > 55]))
            c3.metric("RSI < 45 (Bearish)", len(b_df[b_df['RSI'] < 45]))
            st.subheader("RSI Distribution")
            fig_rsi = px.histogram(b_df, x="RSI", nbins=25, template="plotly_dark", color_discrete_sequence=['#00ffa2'])
            st.plotly_chart(fig_rsi, use_container_width=True)
            st.subheader("Component Details")
            st.dataframe(b_df.style.background_gradient(subset=['RSI'], cmap='RdYlGn'), use_container_width=True)

# ==================== BACKTEST SANDBOX (your full code) ====================
with tab3:
    def run_backtest(ticker: str, yrs: int = 3):
        start = (datetime.today() - timedelta(days=365 * yrs)).strftime("%Y-%m-%d")
        try:
            prices = api.get_eod_historical_stock_market_data(ticker, from_date=start, order='a')
            prices_df = pd.DataFrame(prices).set_index('date')
            rsi_list = api.get_technical_indicator_data(ticker, function='rsi', period=14)
            sma_list = api.get_technical_indicator_data(ticker, function='sma', period=200)
            rsi_df = pd.DataFrame(rsi_list).set_index('date')
            sma_df = pd.DataFrame(sma_list).set_index('date')
            df = prices_df.join([rsi_df['rsi'], sma_df['sma']], how='inner')
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
            df = df[['Open', 'High', 'Low', 'Close', 'Volume', 'rsi', 'sma']].dropna()
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
            st.error(f"Backtest failed: {e}")
            return pd.DataFrame()
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
                    fig_bt.add_trace(go.Scatter(x=res.index, y=cum_strat, name="RSI 55/45 Strategy", line=dict(color='#00ffa2', width=3)))
                    fig_bt.update_layout(template="plotly_dark", title=f"{bt_ticker} Strategy Performance", height=500)
                    st.plotly_chart(fig_bt, use_container_width=True)

# ==================== MOMENTUM LEADERS ====================
with tab4:
    st.subheader("🔍 Top Momentum Leaders")
    st.dataframe(df.nlargest(20, "Abs_Momentum_12M").style.background_gradient(subset=["Abs_Momentum_12M","Rel_Momentum_12M"], cmap="RdYlGn"), use_container_width=True)

# ==================== GROK AI ANALYST ====================
with tab5:
    st.header("🧠 Grok AI Analyst")
    user_logic = st.text_area("Ask anything about the market or portfolio:", "Rank top momentum stocks by ROE and relative strength vs Nifty")
    if st.button("🚀 Ask Grok", type="primary"):
        with st.spinner("Grok thinking..."):
            try:
                response = grok.chat.completions.create(model="grok-beta", messages=[{"role": "user", "content": f"Current market data: {user_logic}"}], temperature=0.7)
                st.success(response.choices[0].message.content)
            except Exception as e:
                st.error(f"AI error: {e}")

st.caption("Grok Alpha Terminal v3.0 • Dynamic EODHD Screener • Holistic Momentum + Breadth + Backtesting • May 2026")
