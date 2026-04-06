import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator
from ta.volatility import BollingerBands

st.set_page_config(page_title="Options Strategy Engine", layout="wide")

st.title("🧠 Options Strategy Engine (AI Regime + Scoring)")

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

    df = df.dropna()
    return df

# ---------------- REGIME ----------------
def detect_regime(adx, bb_position, rsi):
    if adx > 25:
        return "TREND"
    elif 0.4 <= bb_position <= 0.6 and 40 <= rsi <= 60:
        return "RANGE"
    else:
        return "TRANSITION"

# ---------------- SCORING ----------------
def calculate_score(rsi, adx, bb_position):
    score = 0

    if 40 <= rsi <= 60:
        score += 2
    elif 35 <= rsi <= 65:
        score += 1

    if adx < 20:
        score += 3
    elif adx < 25:
        score += 1

    if 0.4 <= bb_position <= 0.6:
        score += 2
    elif 0.3 <= bb_position <= 0.7:
        score += 1

    return score

# ---------------- BIAS ----------------
def get_bias(rsi, adx):
    if adx > 25:
        if rsi > 55:
            return "BULLISH"
        elif rsi < 45:
            return "BEARISH"
    return "NEUTRAL"

# ---------------- STRATEGY ENGINE ----------------
def recommend_strategy(score, regime, rsi, bb_position):

    if regime == "RANGE" and score >= 6:
        return "Iron Condor", "LOW RISK"

    if regime == "RANGE" and score >= 5:
        return "Double Calendar", "LOW RISK"

    if regime == "RANGE":
        return "Broken Wing Butterfly", "LOW-MODERATE"

    if regime == "TREND":
        if rsi > 55:
            return "Bull Put Spread", "TREND"
        elif rsi < 45:
            return "Bear Call Spread", "TREND"
        else:
            return "Credit Spread", "TREND"

    return "No Trade / Wait", "NO EDGE"

# ---------------- EXIT ENGINE ----------------
def exit_engine(rsi, adx, bb_position):

    if adx > 30:
        return "⚠️ Exit - Strong trend forming"

    if rsi < 35 or rsi > 65:
        return "⚠️ Exit - Momentum extreme"

    if bb_position < 0.25 or bb_position > 0.75:
        return "⚠️ Exit - Range broken"

    return "✅ Hold"

# ---------------- UI ----------------
tab1, tab2 = st.tabs(["🔍 Scanner", "📈 Analyzer"])

# ================= SCANNER =================
with tab1:

    auto = st.checkbox("Auto Refresh")

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

            if bb_range and bb_range > 0:
                bb_position = (price - last["BB_Low"]) / bb_range
            else:
                bb_position = 0.5

            if rsi is None or adx is None:
                continue

            score = calculate_score(rsi, adx, bb_position)
            regime = detect_regime(adx, bb_position, rsi)

            if score >= 4 and regime in ["RANGE", "TRANSITION"]:

                strategy, risk = recommend_strategy(score, regime, rsi, bb_position)
                bias = get_bias(rsi, adx)

                results.append({
                    "Ticker": ticker,
                    "RSI": round(rsi,1),
                    "ADX": round(adx,1),
                    "Regime": regime,
                    "Bias": bias,
                    "Score": score,
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
        st.autorefresh(interval=60000, key="refresh")

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

            if bb_range and bb_range > 0:
                bb_position = (price - last["BB_Low"]) / bb_range
            else:
                bb_position = 0.5

            score = calculate_score(rsi, adx, bb_position)
            regime = detect_regime(adx, bb_position, rsi)
            bias = get_bias(rsi, adx)

            strategy, risk = recommend_strategy(score, regime, rsi, bb_position)
            exit_signal = exit_engine(rsi, adx, bb_position)

            st.subheader(f"{symbol} — {price:.2f}")

            st.write(f"RSI: {rsi:.1f}")
            st.write(f"ADX: {adx:.1f}")
            st.write(f"BB Position: {bb_position:.2f}")
            st.write(f"Regime: {regime}")
            st.write(f"Bias: {bias}")
            st.write(f"Score: {score}")

            st.subheader("Strategy")
            st.success(f"{strategy} ({risk})")

            st.subheader("Exit Signal")
            st.warning(exit_signal)

            # Chart
            fig, ax = plt.subplots()
            ax.plot(df["Close"])
            ax.plot(df["BB_High"], linestyle="--")
            ax.plot(df["BB_Low"], linestyle="--")
            ax.set_title(symbol)

            st.pyplot(fig)
            plt.close(fig)