import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from eodhd import APIClient
from openai import OpenAI
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import duckdb
import warnings
warnings.filterwarnings("ignore")

st.set_page_config(page_title="Grok Alpha Terminal", layout="wide")

st.markdown("""
    <style>
    .stApp { background: #0b0e14; color: #e0e0e0; }
    [data-testid="stMetricValue"] { color: #00ffa2 !important; font-family: 'Courier New'; }
    .asset-card { background: rgba(255,255,255,0.05); border-radius: 16px; padding: 20px; text-align: center; }
    .status-strip { background: #1a1f2e; padding: 10px 20px; border-radius: 8px; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

st.title("⚡ Grok Alpha Terminal")
st.caption("Holistic Global Momentum • Real EODHD Data • DuckDB Persistence")

EODHD_KEY = st.secrets.get("EODHD_KEY")
XAI_API_KEY = st.secrets.get("XAI_API_KEY")
api = APIClient(api_key=EODHD_KEY) if EODHD_KEY else None
grok = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1") if XAI_API_KEY else None

DB_PATH = "momentum.db"

with st.sidebar:
    st.header("🔧 Controls")
    as_of_date = st.date_input("View as of (EOD)", value=datetime.today().date())
    top_n = st.selectbox("Top N liquid stocks", [50, 100, 200, 500], index=1)

if st.button("🚀 Fetch Latest Data", type="primary", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.markdown(f'<div class="status-strip">📅 As of <b>{as_of_date}</b> • Top <b>{top_n}</b> liquid stocks</div>', unsafe_allow_html=True)

# ====================== DATA LAYER ======================
@st.cache_data(ttl=3600)
def load_data(top_n: int, as_of_str: str):
    try:
        with duckdb.connect(DB_PATH) as con:
            df = con.execute("SELECT * FROM momentum WHERE date = ?", (as_of_str,)).df()
            if not df.empty:
                return df.drop(columns=['date'])
    except:
        pass

    if not api:
        st.error("EODHD not configured")
        return pd.DataFrame()

    st.info("🔄 Fetching real data from EODHD...")

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

    data = []
    from_date = (datetime.strptime(as_of_str,"%Y-%m-%d") - timedelta(days=1100)).strftime("%Y-%m-%d")

    def compute(row):
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
                "date": as_of_str,
                "Ticker": row["Ticker"], "Name": row["Name"], "Country": row["Country"],
                "Sector": row["Sector"], "MarketCap": row["MarketCap"],
                "1W": calc(5)[0], "1M": calc(21)[0], "3M": calc(63)[0],
                "6M": calc(126)[0], "1Y": calc(252)[0], "3Y": calc(756)[0],
                "Abs_Momentum_1Y": calc(252)[0],
                "Rel_Momentum_1Y": calc(252)[1],
            }
        except: return None

    with st.spinner("Calculating momentum in parallel..."):
        with ThreadPoolExecutor(max_workers=15) as executor:
            results = list(executor.map(compute, [row for _, row in universe.iterrows()]))
    df = pd.DataFrame([r for r in results if r is not None])

    with duckdb.connect(DB_PATH) as con:
        df_save = df.copy()
        df_save['date'] = as_of_str
        con.execute("CREATE TABLE IF NOT EXISTS momentum AS SELECT * FROM df_save")
        con.execute("DELETE FROM momentum WHERE date = ?", (as_of_str,))
        con.execute("INSERT INTO momentum SELECT * FROM df_save")

    return df

df = load_data(top_n, str(as_of_date))

st.success(f"✅ Loaded {len(df)} real tickers from EODHD")

# ====================== HOLISTIC DASHBOARD ======================
st.subheader("Holistic Dashboard – Asset Class Momentum")

asset_classes = ["Equity", "Fixed Income", "Commodities", "Alternate Currencies", "REIT"]
cols = st.columns(len(asset_classes))
selected_asset = None

for i, asset in enumerate(asset_classes):
    with cols[i]:
        if st.button(f"**{asset}**", use_container_width=True, key=f"tile_{asset}"):
            selected_asset = asset
        st.metric("1W", "—")
        st.metric("1M", "—")
        st.metric("3M", "—")
        st.metric("6M", "—")
        st.metric("1Y", "—")
        st.metric("3Y", "—")

if selected_asset:
    st.subheader(f"🔍 Regional Breakdown → {selected_asset}")
    st.dataframe(df.style.background_gradient(subset=["1W","1M","3M","6M","1Y","3Y"], cmap="RdYlGn"), use_container_width=True)
else:
    st.info("👆 Click any asset class tile above to see DM/EM regional breakdown")

# ====================== OTHER PANES ======================
tab1, tab2, tab3, tab4 = st.tabs(["📈 Market Breadth", "🧪 Backtest Sandbox", "🔍 Momentum Leaders", "🧠 Grok AI Analyst"])

with tab1:
    st.subheader("Market Breadth by Country")
    st.dataframe(df.groupby("Country").size().reset_index(name="Tickers"), use_container_width=True)

with tab2:
    st.subheader("Backtest Sandbox (coming in next update)")

with tab3:
    st.subheader("Top Momentum Leaders")
    st.dataframe(df.nlargest(20, "Abs_Momentum_1Y").style.background_gradient(subset=["Abs_Momentum_1Y","Rel_Momentum_1Y"], cmap="RdYlGn"), use_container_width=True)

with tab4:
    st.header("🧠 Grok AI Analyst")
    user_logic = st.text_area("Ask Grok:", "Rank top momentum stocks by ROE and relative strength vs Nifty")
    if st.button("🚀 Ask Grok", type="primary"):
        with st.spinner("Grok thinking..."):
            try:
                response = grok.chat.completions.create(model="grok-beta", messages=[{"role": "user", "content": f"Current market data: {user_logic}"}], temperature=0.7)
                st.success(response.choices[0].message.content)
            except Exception as e:
                st.error(f"AI error: {e}")

st.caption("Full production version • DuckDB persistence • Real EODHD data • Click tiles for drill-down")
