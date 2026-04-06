import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator
from ta.volatility import BollingerBands

st.set_page_config(page_title="Options Strategy Dashboard", layout="wide")

st.title("📊 Options Strategy Dashboard (Scanner + Analyzer + Tracker)")

# ---------------- SAFE FLOAT ----------------

def safe_float(val):
    try:
        if isinstance(val, pd.Series):
            return float(val.iloc[0])
        return float(val)
    except:
        return None

# ---------------- LOAD S&P 500 ----------------

@st.cache_data
def load_sp500_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = pd.read_html(url)
    df = tables[0]
    return df["Symbol"].tolist()

# ---------------- GET DATA ----------------

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

# ---------------- EXIT ENGINE ----------------

def exit_engine(price, rsi, adx, bb_low, bb_high, profit_pct, days_to_expiry):

    if bb_high - bb_low == 0:
        bb_position = 0.5
    else:
        bb_position = (price - bb_low) / (bb_high - bb_low)

    action = "MONITOR"

    if profit_pct >= 25:
        action = "✅ EXIT — Target Hit"

    elif profit_pct <= -40:
        action = "⛔ EXIT — Max Loss"

    elif adx > 25:
        action = "⚠️ EXIT — Trend Forming"

    elif rsi < 40 or rsi > 60:
        action = "⚠️ EXIT — Momentum Shift"

    elif bb_position < 0.3 or bb_position > 0.7:
        action = "⚠️ EXIT — Range Break"

    elif days_to_expiry <= 5:
        action = "⏳ EXIT — Theta Decay"

    elif 0.4 <= bb_position <= 0.6:
        action = "🎯 HOLD — Ideal Zone"

    return action, bb_position

# ---------------- CHART ----------------

def plot_chart(df, symbol):
    plt.figure()
    plt.plot(df["Close"], label="Close")
    plt.plot(df["BB_High"], linestyle="--")
    plt.plot(df["BB_Low"], linestyle="--")
    plt.title(symbol)
    plt.legend()
    st.pyplot(plt)

# ---------------- SESSION STATE ----------------

if "trades" not in st.session_state:
    st.session_state["trades"] = []

if "scan_results" not in st.session_state:
    st.session_state["scan_results"] = pd.DataFrame()

# ---------------- TABS ----------------

tab1, tab2, tab3 = st.tabs(["🔍 Scanner", "📈 Analyzer", "📌 Trades"])

# ================= SCANNER =================

with tab1:

    st.subheader("S&P 500 Scanner")

    if st.button("Run Scan"):

        tickers = load_sp500_tickers()

        progress_bar = st.progress(0)
        status_text = st.empty()

        results = []

        for i, ticker in enumerate(tickers):

            status_text.write(f"Scanning {ticker} ({i+1}/{len(tickers)})")

            df = get_data(ticker)
            if df is None:
                continue

            df = add_indicators(df)
            last = df.iloc[-1]

            price = safe_float(last["Close"])
            rsi = safe_float(last["RSI"])
            adx = safe_float(last["ADX"])

            if None in [price, rsi, adx]:
                continue

            # Low risk filter
            if 40 <= rsi <= 60 and adx < 25:
                results.append({
                    "Ticker": ticker,
                    "Price": round(price, 2),
                    "RSI": round(rsi, 1),
                    "ADX": round(adx, 1)
                })

            progress_bar.progress((i + 1) / len(tickers))

        if results:
            df_results = pd.DataFrame(results)
            st.session_state["scan_results"] = df_results
            st.dataframe(df_results)

    # Select ticker from results
    if not st.session_state["scan_results"].empty:
        selected = st.selectbox(
            "Select ticker for analysis",
            st.session_state["scan_results"]["Ticker"]
        )

        if st.button("Analyze Selected"):
            st.session_state["selected_ticker"] = selected
            st.success(f"{selected} loaded into Analyzer tab")

    # Top 5 auto analyze
    if st.button("Analyze Top 5") and not st.session_state["scan_results"].empty:
        top5 = st.session_state["scan_results"].head(5)

        for ticker in top5["Ticker"]:
            st.subheader(f"🔍 {ticker}")

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

            action, _ = exit_engine(price, rsi, adx, bb_low, bb_high, 0, 10)

            st.write(f"Price: {price}")
            st.write(f"RSI: {rsi}")
            st.write(f"ADX: {adx}")
            st.success(action)

# ================= ANALYZER =================

with tab2:

    st.subheader("Single Trade Analyzer")

    symbol = st.text_input("Symbol", value=st.session_state.get("selected_ticker", "AAPL"))

    entry_price = st.number_input("Entry Price", value=3.40)
    current_spread = st.number_input("Current Spread", value=3.70)
    strike_price = st.number_input("Strike Price", value=100.0)
    days_to_expiry = st.number_input("Days to Expiry", value=10)

    if st.button("Analyze Trade"):

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

        if action.startswith("⚠️") or action.startswith("⛔"):
            st.error(action)
        else:
            st.success(action)

        st.subheader("📈 Chart")
        plot_chart(df, symbol)

# ================= TRADES =================

with tab3:

    st.subheader("📌 Trade Tracker")

    trade_symbol = st.text_input("Ticker")
    entry = st.number_input("Entry Price", value=0.0)

    if st.button("Add Trade"):
        st.session_state["trades"].append({
            "Ticker": trade_symbol,
            "Entry": entry
        })

    if st.session_state["trades"]:
        for trade in st.session_state["trades"]:
            df = get_data(trade["Ticker"])
            if df is None:
                continue

            current_price = float(df["Close"].iloc[-1])
            pnl = ((current_price - trade["Entry"]) / trade["Entry"]) * 100

            st.write(f"{trade['Ticker']} | Entry: {trade['Entry']} | P&L: {pnl:.2f}%")

            if pnl < -40:
                st.error("⚠️ Risk alert")