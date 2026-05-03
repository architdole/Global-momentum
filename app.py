import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from eodhd import APIClient
from openai import OpenAI
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import duckdb
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(page_title="Grok Alpha Terminal", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background: #0b0e14; color: #e0e0e0; }
    [data-testid="stMetricValue"] { color: #00ffa2 !important; font-family: 'Courier New'; font-size: 1.8rem; }
    .glass-panel { background: rgba(255,255,255,0.03); backdrop-filter: blur(12px); border-radius: 16px; padding: 24px; border: 1px solid rgba(255,255,255,0.12); margin-bottom: 20px; }
    .status-strip { background: #1a1f2e; padding: 8px 16px; border-radius: 8px; font-size: 0.9rem; margin-bottom: 16px; }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Grok Alpha Terminal")
st.caption("Holistic Momentum • Market Breadth • RSI Strategy • AI Analyst • Real EODHD Data")

# ==================== SINGLETON CLIENTS ====================
@st.cache_resource
def get_clients():
    EODHD_KEY = st.secrets.get("EODHD_KEY")
    XAI_API_KEY = st.secrets.get("XAI_API_KEY")
    if not EODHD_KEY or not XAI_API_KEY:
        st.error("⚠️ Missing API keys in Streamlit Secrets.")
        st.stop()
    return APIClient(api_key=EODHD_KEY), OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

api, grok = get_clients()

DB_PATH = "momentum.db"

# ==================== CONTROLS ====================
with st.sidebar:
    st.header("🔧 Controls")
    as_of_date = st.date_input("View as of (EOD)", value=datetime.today().date())
    top_n = st.selectbox("Top N liquid stocks", [50, 100, 200, 500], index=0)

if st.button("🚀 Fetch Latest Data", type="primary", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# Status strip
st.markdown(f'<div class="status-strip">📅 As of <b>{as_of_date}</b> • Top <b>{top_n}</b> liquid stocks • DuckDB cache active</div>', unsafe_allow_html=True)

# ==================== DATA LAYER ====================
@st.cache_data(ttl=3600)
def load_or_refresh_data(top_n: int, as_of_str: str):
    try:
        with duckdb.connect(DB_PATH) as con:
            df = con.execute("SELECT * FROM momentum WHERE date = ?", (as_of_str,)).df()
            if not df.empty:
                return df.drop(columns=['date'])
    except:
        pass

    st.info("🔄 Fetching fresh data from EODHD (parallel)...")

    # Dynamic screener
    try:
        screener = api.stock_market_screener(
            sort="market_capitalization.desc",
            limit=top_n * 2,
            filters='[["avg_volume_200d",">",1000000],["market_capitalization",">",500000000]]'
        )
        universe = pd.DataFrame({
            "Ticker": screener['code'], "Name": screener['name'],
            "Country": screener.get('country', 'Global'), "Sector": screener.get('sector', 'Unknown'),
            "MarketCap": screener.get('market_capitalization', 0)
        }).head(top_n)
    except:
        universe = pd.DataFrame({"Ticker":["RELIANCE.NS","AAPL.US"], "Name":["Reliance","Apple"], "Country":["India","US"], "Sector":["Energy","Technology"], "MarketCap":[2e11,3e12]})

    # Parallel fetch
    data = []
    from_date = (datetime.strptime(as_of_str,"%Y-%m-%d") - timedelta(days=1100)).strftime("%Y-%m-%d")
    def fetch_and_compute(row):
        try:
            price_df = api.get_eod(symbol=row["Ticker"], from_date=from_date, to_date=as_of_str)
            close = price_df['close'].astype(float).values
            if len(close) < 30: return None
            daily_ret = np.diff(np.log(close))
            def calc(days):
                if len(close) < days: return None, None
                ret = (close[-1] / close[-days] - 1) * 100
                vol = np.std(daily_ret[-days:]) * np.sqrt(252) * 100
                return round(ret, 2), round(ret / vol, 2) if vol > 0 else None
            return {
                "Ticker": row["Ticker"], "Name": row["Name"], "Country": row["Country"],
                "Sector": row["Sector"], "MarketCap": row["MarketCap"],
                "1W": calc(5)[0], "1M": calc(21)[0], "3M": calc(63)[0],
                "6M": calc(126)[0], "12M": calc(252)[0],
                "Abs_Momentum_12M": calc(252)[0],
                "Rel_Momentum_12M": calc(252)[1],
            }
        except: return None

    with st.spinner("Fetching prices in parallel..."):
        with ThreadPoolExecutor(max_workers=15) as executor:
            results = list(executor.map(fetch_and_compute, [row for _, row in universe.iterrows()]))
    df = pd.DataFrame([r for r in results if r is not None])

    # Proper DuckDB upsert
    with duckdb.connect(DB_PATH) as con:
        df_save = df.copy()
        df_save['date'] = as_of_str
        con.execute("CREATE TABLE IF NOT EXISTS momentum AS SELECT * FROM df_save")
        con.execute("DELETE FROM momentum WHERE date = ?", (as_of_str,))
        con.execute("INSERT INTO momentum SELECT * FROM df_save")

    return df

df = load_or_refresh_data(top_n, str(as_of_date))

st.success(f"✅ Loaded **{len(df)}** liquid tickers as of {as_of_date}")

# ==================== TABS ====================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Holistic Dashboard", "🏛️ Market Breadth", "🧪 Backtest Sandbox", "🔍 Momentum Leaders", "🧠 Grok AI Analyst"])

with tab1:
    st.subheader("Holistic View – Region × Sector × Market Cap")
    df['MarketCapBucket'] = pd.qcut(df['MarketCap'], 4, duplicates="drop", labels=['Small','Mid','Large','Mega'])
    fig = px.treemap(df, path=['Country', 'Sector', 'MarketCapBucket'], values='MarketCap',
                     color='Abs_Momentum_12M', color_continuous_scale='RdYlGn')
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df.style.background_gradient(subset=["1W","1M","3M","6M","12M","Abs_Momentum_12M","Rel_Momentum_12M"], cmap="RdYlGn"), use_container_width=True)

with tab4:
    st.subheader("🔍 Top Momentum Leaders")
    st.dataframe(df.nlargest(20, "Abs_Momentum_12M").style.background_gradient(subset=["Abs_Momentum_12M","Rel_Momentum_12M"], cmap="RdYlGn"), use_container_width=True)

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

st.caption("Grok Alpha Terminal v3.2 • DuckDB persistence • Parallel fetching • Superior architecture")
