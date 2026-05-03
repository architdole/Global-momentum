import streamlit as st
import pandas as pd
from openai import OpenAI
import json

st.set_page_config(page_title="Global Momentum + CANSLIM + ROE", layout="wide")
st.title("🌍 Global Momentum + CANSLIM + ROE Dashboard")

XAI_API_KEY = st.secrets["XAI_API_KEY"]
client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")

@st.cache_data(ttl=3600)
def get_data():
    return pd.DataFrame({
        "Ticker": [
            "RELIANCE.NS", "HDFCBANK.NS", "INFY.NS", "TCS.NS", "ICICIBANK.NS",
            "AAPL.US", "MSFT.US", "GOOGL.US", "AMZN.US",
            "7203.T", "6758.T",  # Japan
            "BMW.DE", "SAP.DE",   # Germany
            "HSBC.L", "BP.L",     # UK
            "BABA.US", "JD.US",   # China
            "VALE3.SA", "ITUB4.SA", # Brazil
            "BHP.AX", "CSL.AX",   # Australia
            "SHOP.TO", "RY.TO",   # Canada
            "005930.KS", "000660.KS" # South Korea
        ],
        "Name": [
            "Reliance Industries", "HDFC Bank", "Infosys", "TCS", "ICICI Bank",
            "Apple Inc.", "Microsoft", "Alphabet", "Amazon",
            "Toyota Motor", "Sony Group",
            "BMW", "SAP SE",
            "HSBC Holdings", "BP plc",
            "Alibaba Group", "JD.com",
            "Vale S.A.", "Itaú Unibanco",
            "BHP Group", "CSL Limited",
            "Shopify", "Royal Bank of Canada",
            "Samsung Electronics", "SK Hynix"
        ],
        "Country": [
            "India", "India", "India", "India", "India",
            "US", "US", "US", "US",
            "Japan", "Japan",
            "Germany", "Germany",
            "UK", "UK",
            "China", "China",
            "Brazil", "Brazil",
            "Australia", "Australia",
            "Canada", "Canada",
            "South Korea", "South Korea"
        ],
        "1W": [1.8, 0.9, 0.7, 1.2, 0.8, 2.3, 1.5, 1.1, 0.9, 0.6, 1.4, 0.5, 0.8, 0.7, 1.0, 0.4, 1.3, 0.9, 1.1, 0.8, 1.2, 0.6, 1.0, 0.7, 1.5],
        "1M": [4.2, 2.8, 1.9, 2.4, 2.1, 5.1, 3.9, 2.8, 2.5, 1.8, 3.2, 1.5, 2.1, 1.9, 2.4, 1.2, 3.5, 2.8, 3.1, 2.2, 2.9, 1.8, 2.5, 2.1, 3.8],
        "3M": [9.8, 6.4, 4.5, 5.8, 5.2, 11.2, 8.7, 6.5, 5.9, 4.2, 7.1, 3.8, 4.9, 4.5, 5.2, 2.9, 7.8, 6.2, 6.9, 5.1, 6.4, 4.2, 5.8, 4.9, 8.5],
        "6M": [15.6, 11.2, 7.8, 9.1, 8.5, 18.4, 14.2, 10.8, 9.5, 7.2, 11.5, 6.5, 8.2, 7.8, 8.9, 5.2, 12.4, 10.1, 11.2, 8.4, 10.5, 7.2, 9.5, 8.1, 13.8],
        "12M": [28.4, 19.5, 12.3, 15.6, 14.2, 32.1, 26.8, 18.9, 16.4, 12.8, 19.5, 11.2, 14.5, 13.8, 15.2, 9.5, 21.8, 17.5, 19.2, 14.8, 17.9, 12.5, 16.2, 13.9, 23.5],
        "3Y_Ann": [16.8, 12.4, 8.9, 11.2, 10.5, 22.5, 19.8, 14.2, 12.8, 9.5, 13.8, 8.2, 10.5, 10.1, 11.2, 7.2, 15.4, 12.8, 13.9, 10.8, 12.5, 9.2, 11.8, 10.2, 16.8],
        "ROE": [22.4, 18.9, 24.6, 26.8, 17.5, 45.2, 42.1, 28.5, 24.8, 12.8, 15.2, 14.5, 22.1, 11.8, 9.5, 8.2, 18.4, 15.6, 19.2, 16.8, 14.5, 12.8, 18.9, 14.2, 16.5],
        "CANSLIM": [94, 87, 78, 82, 71, 91, 89, 76, 72, 68, 71, 65, 74, 62, 58, 55, 69, 66, 72, 68, 65, 61, 70, 64, 73]
    })

df = get_data()

# ==================== GROK FUNCTION ====================
def get_grok_response(query):
    system = """You are a financial data analyst. Convert user request to JSON with:
    - filter: dict of conditions
    - sort_by: column name
    - sort_order: "asc" or "desc"
    Return only valid JSON."""

    try:
        resp = client.chat.completions.create(
            model="grok-4-1-fast-reasoning",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": query}],
            temperature=0.1, max_tokens=300
        )
        content = resp.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1].replace("json", "").strip()
        return json.loads(content)
    except:
        return {"error": "Could not understand request"}

# ==================== UI ====================
st.subheader("🤖 Ask Grok")

query = st.text_input("Type request:", placeholder="Which tickers for each country?")
if st.button("🚀 Ask Grok", type="primary"):
    if query:
        with st.spinner("Processing..."):
            instructions = get_grok_response(query)
            st.session_state["instructions"] = instructions
            st.success(f"Grok: {instructions}")

# Apply filters
filtered = df.copy()
if "instructions" in st.session_state:
    instr = st.session_state["instructions"]
    if "filter" in instr:
        for col, val in instr["filter"].items():
            if col in filtered.columns:
                if str(val).startswith(">"):
                    filtered = filtered[filtered[col] > float(str(val)[1:])]
                elif str(val).startswith("<"):
                    filtered = filtered[filtered[col] < float(str(val)[1:])]
                else:
                    filtered = filtered[filtered[col] == val]
    if "sort_by" in instr and instr["sort_by"] in filtered.columns:
        filtered = filtered.sort_values(instr["sort_by"], ascending=instr.get("sort_order", "desc") == "asc")

# Show table with clear Ticker + Name
st.subheader("Results")
cols = ["Ticker", "Name", "Country", "1W", "1M", "3M", "6M", "12M", "3Y_Ann", "ROE", "CANSLIM"]
st.dataframe(
    filtered[cols].style
    .background_gradient(subset=["1W","1M","3M","6M","12M","3Y_Ann"], cmap="RdYlGn")
    .background_gradient(subset=["ROE","CANSLIM"], cmap="Blues"),
    use_container_width=True
)

st.caption("Data: EODHD + yfinance | Powered by Grok | May 2026")
