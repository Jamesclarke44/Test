import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import time

from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator
from ta.volatility import BollingerBands

st.set_page_config(page_title="Options Strategy Engine", layout="wide")

st.title("🧠 Options Strategy Engine (Scanner + AI Logic)")

# ---------------- SAFE FLOAT ----------------
def safe_float(val):
    try:
        if isinstance(val, pd.Series):
            return float(val.iloc[0])
        return float(val)
    except:
        return None

# ---------------- UNIVERSE ----------------
@st.cache_data
def load_universe():
    return [
        "SPY","QQQ","IWM","DIA","VTI","XLF","XLK","XLE","XLV",
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA",
        "AMD","CRM","ORCL","ADBE","CSCO","JPM","BAC","GS",
        "WMT","COST","HD","NKE","SBUX","MCD","JNJ","UNH",
        "XOM","CVX","CAT","GE","VZ","T","PG","KO","PEP",
        "PLTR","COIN","RIOT","MARA","SOFI","SHOP","UBER"
    ]

# ---------------- DATA ----------------
@st.cache_data
def get_data(symbol):
    try:
        df = yf.download(symbol, period="6mo", interval="1d", progress=False)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except:
        return None

# ---------------- INDICATORS ----------------
def add_indicators(df):
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    df["RSI"] = RSIIndicator(close=close).rsi()
    df["ADX"] = ADXIndicator(high=high, low=low, close=close).adx()

    bb = BollingerBands(close=close)
    df["BB_High"] = bb.bollinger_hband()
    df["BB_Low"] = bb.bollinger_lband()

    return df

# ---------------- STRATEGY ENGINE ----------------
def recommend_strategy(rsi, adx, bb_position):

    # LOW RISK FIRST
    if adx < 20 and 0.45 <= bb_position <= 0.55:
        return "🟢 Single Calendar", "LOW RISK"

    if adx < 20 and 0.4 <= bb_position <= 0.6:
        return "🟢 Double Calendar", "LOW RISK"

    if adx < 22 and 0.35 <= bb_position <= 0.65:
        return "🟢 Broken Wing Butterfly", "LOW RISK"

    # MODERATE RISK
    if adx < 25 and 0.3 <= bb_position <= 0.7:
        return "🟡 Wide Iron Condor", "MODERATE"

    if adx < 25:
        return "🟡 Jade Lizard", "MODERATE"

    return "🟡 Wide Credit Spread", "MODERATE"

# ---------------- EXIT ENGINE ----------------
def exit_engine(rsi, adx, bb_position):

    if adx > 25:
        return "⚠️ Exit - Trend forming"

    if rsi < 40 or rsi > 60:
        return "⚠️ Exit - Momentum shift"

    if bb_position < 0.3 or bb_position > 0.7:
        return "⚠️ Exit - Range break"

    return "✅ Hold"

# ---------------- UI ----------------
tab1, tab2 = st.tabs(["🔍 Scanner", "📈 Analyzer"])

# ================= SCANNER =================
with tab1:

    auto = st.checkbox("Auto Refresh (60s)")
    
    if st.button("Run Scan") or auto:

        tickers = load_universe()

        progress = st.progress(0)
        status = st.empty()

        results = []

        for i, ticker in enumerate(tickers):

            status.write(f"Scanning {ticker} ({i+1}/{len(tickers)})")

            df = get_data(ticker)
            if df is None:
                continue

            df = add_indicators(df)
            last = df.iloc[-1]

            price = safe_float(last["Close"])
            rsi = safe_float(last["RSI"])
            adx = safe_float(last["ADX"])

            bb_range = last["BB_High"] - last["BB_Low"]
            bb_position = (price - last["BB_Low"]) / bb_range if bb_range != 0 else 0.5

            if 40 <= rsi <= 60 and adx < 25:

                strategy, risk = recommend_strategy(rsi, adx, bb_position)

                results.append({
                    "Ticker": ticker,
                    "RSI": round(rsi,1),
                    "ADX": round(adx,1),
                    "Strategy": strategy,
                    "Risk": risk
                })

            progress.progress((i+1)/len(tickers))

        if results:
            df_results = pd.DataFrame(results)
            st.session_state["scan"] = df_results
            st.success(f"Found {len(df_results)} setups")
            st.dataframe(df_results)

        else:
            st.warning("No setups found")

    if auto:
        time.sleep(60)
        st.rerun()

# ================= ANALYZER =================
with tab2:

    symbol = st.text_input("Ticker", value="AAPL")

    if st.button("Analyze"):

        df = get_data(symbol)
        if df is None:
            st.error("No data")
        else:
            df = add_indicators(df)
            last = df.iloc[-1]

            price = safe_float(last["Close"])
            rsi = safe_float(last["RSI"])
            adx = safe_float(last["ADX"])

            bb_range = last["BB_High"] - last["BB_Low"]
            bb_position = (price - last["BB_Low"]) / bb_range if bb_range != 0 else 0.5

            strategy, risk = recommend_strategy(rsi, adx, bb_position)
            exit_signal = exit_engine(rsi, adx, bb_position)

            st.subheader(f"{symbol} — {price:.2f}")

            st.write(f"RSI: {rsi:.1f}")
            st.write(f"ADX: {adx:.1f}")
            st.write(f"BB Position: {bb_position:.2f}")

            st.subheader("Strategy")
            st.success(f"{strategy} ({risk})")

            st.subheader("Exit Signal")
            st.warning(exit_signal)

            # Chart
            plt.figure()
            plt.plot(df["Close"])
            plt.plot(df["BB_High"], linestyle="--")
            plt.plot(df["BB_Low"], linestyle="--")
            plt.title(symbol)
            st.pyplot(plt)