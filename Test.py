import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator
from ta.volatility import BollingerBands

st.set_page_config(page_title="Options Strategy Dashboard", layout="wide")

st.title("📊 Options Strategy Dashboard (Scanner + Exit Engine)")

# ---------------- SAFE FLOAT ----------------

def safe_float(val):
    try:
        if isinstance(val, pd.Series):
            return float(val.iloc[0])
        return float(val)
    except:
        return None

# ---------------- DATA ----------------

@st.cache_data
def get_data(symbol):
    df = yf.download(symbol, period="6mo", interval="1d", progress=False)
    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()
    return df

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

# ---------------- STRATEGY LOGIC ----------------

def exit_engine(price, rsi, adx, bb_low, bb_high, profit_pct, days_to_expiry):

    if bb_high - bb_low == 0:
        bb_position = 0.5
    else:
        bb_position = (price - bb_low) / (bb_high - bb_low)

    action = "MONITOR"

    if profit_pct >= 25:
        action = "✅ EXIT — Target Hit"

    elif profit_pct <= -40:
        action = "⛔ EXIT — Loss Limit"

    elif adx > 25:
        action = "⚠️ EXIT — Trend Forming"

    elif rsi < 40 or rsi > 60:
        action = "⚠️ EXIT — Momentum Shift"

    elif bb_position < 0.3 or bb_position > 0.7:
        action = "⚠️ EXIT — Range Break"

    elif days_to_expiry <= 5:
        action = "⏳ EXIT — Time Decay"

    elif 0.4 <= bb_position <= 0.6:
        action = "🎯 HOLD — Ideal Zone"

    return action, bb_position

# ---------------- CHART ----------------

def plot_chart(df, symbol, entry_price=None, strike=None):

    plt.figure()

    plt.plot(df["Close"], label="Close")
    plt.plot(df["BB_High"], linestyle="--")
    plt.plot(df["BB_Low"], linestyle="--")

    if entry_price:
        plt.axhline(entry_price)

    if strike:
        plt.axhline(strike)

    plt.title(symbol)
    plt.legend()

    st.pyplot(plt)

# ---------------- UI ----------------

mode = st.radio("Mode", ["Scan Universe", "Single Analysis"])

# ---------------- SCAN MODE ----------------

if mode == "Scan Universe":

    if st.button("Run Scan"):

        tickers = ["SPY","QQQ","IWM","DIA","AAPL","MSFT","TSLA","NVDA","AMZN"]

        results = []

        for ticker in tickers:

            df = get_data(ticker)
            if df is None:
                continue

            df = add_indicators(df)
            last = df.iloc[-1]

            price = safe_float(last["Close"])
            rsi = safe_float(last["RSI"])
            adx = safe_float(last["ADX"])
            bb_low = safe_float(last["BB_Low"])
            bb_high = safe_float(last["BB_High"])

            if None in [price, rsi, adx, bb_low, bb_high]:
                continue

            if 40 <= rsi <= 60 and adx < 25:
                results.append({
                    "Ticker": ticker,
                    "Price": round(price, 2),
                    "RSI": round(rsi, 1),
                    "ADX": round(adx, 1)
                })

        if results:
            df_results = pd.DataFrame(results)
            st.dataframe(df_results)

            st.session_state["results"] = df_results

# ---------------- SINGLE ANALYSIS ----------------

if mode == "Single Analysis":

    symbol = st.text_input("Symbol", value="AAPL")

    entry_price = st.number_input("Entry Price", value=3.40)
    current_spread = st.number_input("Current Spread", value=3.70)
    strike_price = st.number_input("Strike Price", value=100.0)
    days_to_expiry = st.number_input("Days to Expiry", value=10)

    if st.button("Analyze"):

        df = get_data(symbol)

        if df is None:
            st.error("No data")
            st.stop()

        df = add_indicators(df)
        last = df.iloc[-1]

        price = safe_float(last["Close"])
        rsi = safe_float(last["RSI"])
        adx = safe_float(last["ADX"])
        bb_low = safe_float(last["BB_Low"])
        bb_high = safe_float(last["BB_High"])

        profit_pct = ((current_spread - entry_price) / entry_price) * 100

        action, bb_position = exit_engine(
            price, rsi, adx, bb_low, bb_high, profit_pct, days_to_expiry
        )

        st.subheader("📊 Metrics")
        st.write(f"Price: {price}")
        st.write(f"RSI: {rsi}")
        st.write(f"ADX: {adx}")
        st.write(f"BB Position: {bb_position:.2f}")
        st.write(f"Profit %: {profit_pct:.2f}")

        st.subheader("🚦 Exit Decision")
        st.success(action)

        st.subheader("📈 Chart")
        plot_chart(df, symbol, entry_price, strike_price)