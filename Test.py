import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

st.set_page_config(page_title="Momentum Scanner PRO", layout="wide")

st.title("⚡ Momentum Scanner PRO (Stable + Expanded)")

# ---------------- DATA SOURCES ----------------

@st.cache_data(ttl=3600)
def get_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers)
        tables = pd.read_html(response.text)
        return tables[0]['Symbol'].tolist()
    except:
        st.warning("⚠️ Failed to load S&P 500 list. Using fallback.")
        return [
            "AAPL","MSFT","NVDA","AMZN","META","TSLA","GOOGL","AMD",
            "NFLX","INTC","PLTR","SOFI","BAC","F","CCL"
        ]

@st.cache_data(ttl=300)
def get_top_gainers():
    url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        quotes = data['finance']['result'][0]['quotes']
        return [q['symbol'] for q in quotes]
    except:
        st.warning("⚠️ Failed to load top gainers.")
        return []

# ---------------- BUILD UNIVERSE ----------------

sp500 = get_sp500()
gainers = get_top_gainers()

st.write(f"Gainers: {len(gainers)} | SP500: {len(sp500)}")

tickers = list(set(gainers + sp500))

# User control (VERY IMPORTANT)
MAX_TICKERS = st.slider("Max Stocks to Scan", 50, 1000, 300)
tickers = tickers[:MAX_TICKERS]

st.write(f"🔍 Scanning {len(tickers)} stocks...")

# ---------------- DATA FETCH ----------------

@st.cache_data(ttl=300)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="2d", interval="5m", progress=False)
        return df
    except:
        return None

# ---------------- LOGIC ----------------

def relative_volume(df):
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    if avg_vol == 0 or np.isnan(avg_vol):
        return 0
    return df['Volume'].iloc[-1] / avg_vol

def momentum(df):
    return (df['Close'].iloc[-1] - df['Close'].iloc[-4]) / df['Close'].iloc[-4] * 100

def breakout(df):
    hod = df['High'].max()
    price = df['Close'].iloc[-1]
    return price >= hod * 0.98, hod

def score(rel_vol, mom, is_breakout):
    return round(rel_vol*2 + mom*3 + (2 if is_breakout else 0), 2)

# ---------------- SCAN ----------------

results = []

progress = st.progress(0)

for i, ticker in enumerate(tickers):
    df = get_data(ticker)

    if df is None or len(df) < 20:
        continue

    price = df['Close'].iloc[-1]

    # Ross-style price filter
    if price < 2 or price > 50:
        continue

    rel_vol = relative_volume(df)
    mom = momentum(df)
    is_breakout, hod = breakout(df)

    # Core momentum filter
    if rel_vol > 2 and mom > 1:
        entry = price
        stop = price * 0.97
        target = price * 1.05

        results.append({
            "Ticker": ticker,
            "Price": round(price, 2),
            "Rel Vol": round(rel_vol, 2),
            "Momentum %": round(mom, 2),
            "Setup": "HOD Breakout" if is_breakout else "Momentum Build",
            "Entry": round(entry, 2),
            "Stop": round(stop, 2),
            "Target": round(target, 2),
            "Score": score(rel_vol, mom, is_breakout)
        })

    # Progress bar update
    progress.progress((i + 1) / len(tickers))

# ---------------- DISPLAY ----------------

df_results = pd.DataFrame(results)

if not df_results.empty:
    df_results = df_results.sort_values(by="Score", ascending=False)
    st.success(f"✅ Found {len(df_results)} momentum setups")
    st.dataframe(df_results, use_container_width=True)
else:
    st.warning("⚠️ No strong setups right now.")