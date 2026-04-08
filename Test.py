import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator
from ta.volatility import BollingerBands
from ta.volume import VolumeWeightedAveragePrice

st.set_page_config(page_title="Options Trading System", layout="wide")

st.title("🧠 Options Trading System (Scanner + Analyzer + Exit Engine)")

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
        df = yf.download(symbol, period="6mo", interval="1d", progress=False, auto_adjust=True)
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
    volume = df["Volume"]

    df["RSI"] = RSIIndicator(close=close).rsi()
    df["ADX"] = ADXIndicator(high=high, low=low, close=close).adx()

    bb = BollingerBands(close=close)
    df["BB_High"] = bb.bollinger_hband()
    df["BB_Low"] = bb.bollinger_lband()

    vwap = VolumeWeightedAveragePrice(
        high=high, low=low, close=close, volume=volume
    )
    df["VWAP"] = vwap.volume_weighted_average_price()

    return df.dropna()

# ---------------- ENTRY MODEL ----------------
def is_A_plus_setup(price, rsi, adx, vwap, bb_low, bb_high):

    vwap_drift = abs(price - vwap) / price

    if bb_high - bb_low == 0:
        bb_position = 0.5
    else:
        bb_position = (price - bb_low) / (bb_high - bb_low)

    if (
        40 <= rsi <= 60 and
        adx < 25 and
        vwap_drift <= 0.01 and
        0.4 <= bb_position <= 0.6
    ):
        return True, bb_position, vwap_drift

    return False, bb_position, vwap_drift

# ---------------- EXIT ENGINE ----------------
def exit_engine(rsi, adx, bb_position, vwap_drift):

    # PRIORITY ORDER (real trading logic)

    if adx >= 25:
        return "⚠️ EXIT — Trend forming (edge gone)"

    if vwap_drift > 0.01:
        return "⚠️ EXIT — Price leaving fair value"

    if rsi < 40 or rsi > 60:
        return "⚠️ EXIT — Lost neutrality"

    if bb_position < 0.3 or bb_position > 0.7:
        return "⚠️ EXIT — Range breaking"

    return "✅ HOLD — Conditions intact"

# ---------------- EXIT CONFIDENCE ----------------
def exit_confidence(rsi, adx, bb_position, vwap_drift):

    score = 0

    if adx >= 25:
        score += 2
    if vwap_drift > 0.01:
        score += 3
    if rsi < 40 or rsi > 60:
        score += 2
    if bb_position < 0.3 or bb_position > 0.7:
        score += 2

    return score  # out of 9

# ---------------- UI ----------------
tab1, tab2 = st.tabs(["🔍 Scanner", "📈 Analyzer"])

# ================= SCANNER =================
with tab1:

    if st.button("Run Scan"):

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
            vwap = safe_float(last["VWAP"])

            bb_low = last["BB_Low"]
            bb_high = last["BB_High"]

            if None in [price, rsi, adx, vwap]:
                continue

            valid, bb_pos, vwap_drift = is_A_plus_setup(
                price, rsi, adx, vwap, bb_low, bb_high
            )

            if valid:
                results.append({
                    "Ticker": ticker,
                    "RSI": round(rsi,1),
                    "ADX": round(adx,1),
                    "BB Pos": round(bb_pos,2),
                    "VWAP Drift %": round(vwap_drift*100,2)
                })

            progress.progress((i+1)/len(tickers))

        if results:
            df_results = pd.DataFrame(results)
            st.session_state["scan"] = df_results

            st.success(f"Found {len(df_results)} A+ setups")
            st.dataframe(df_results)

            # SELECT TICKER
            selected = st.selectbox("Select Ticker", df_results["Ticker"])

            if st.button("Analyze Selected"):
                st.session_state["selected"] = selected

        else:
            st.warning("No A+ setups found")

# ================= ANALYZER =================
with tab2:

    symbol = st.text_input(
        "Ticker",
        value=st.session_state.get("selected", "SPY")
    )

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
            vwap = safe_float(last["VWAP"])

            bb_low = last["BB_Low"]
            bb_high = last["BB_High"]

            bb_range = bb_high - bb_low
            bb_position = (price - bb_low) / bb_range if bb_range != 0 else 0.5

            vwap_drift = abs(price - vwap) / price

            # DISPLAY
            st.subheader(f"{symbol} — {price:.2f}")

            st.write(f"RSI: {rsi:.1f}")
            st.write(f"ADX: {adx:.1f}")
            st.write(f"BB Position: {bb_position:.2f}")
            st.write(f"VWAP Drift: {vwap_drift*100:.2f}%")

            # EXIT
            exit_signal = exit_engine(rsi, adx, bb_position, vwap_drift)
            confidence = exit_confidence(rsi, adx, bb_position, vwap_drift)

            st.subheader("🚦 Exit Decision")
            st.warning(exit_signal)
            st.write(f"Confidence: {confidence}/9")

            # ---------------- TRADE TRACKER ----------------
            st.subheader("📒 Track Trade")

            if "trades" not in st.session_state:
                st.session_state["trades"] = []

            entry = st.number_input("Entry Price", value=3.0)
            current = st.number_input("Current Price", value=3.2)

            if st.button("Add Trade"):
                st.session_state["trades"].append({
                    "Ticker": symbol,
                    "Entry": entry,
                    "Current": current
                })
                st.success("Trade added")

            # SHOW TRADES
            st.subheader("📊 Active Trades")

            for trade in st.session_state["trades"]:

                pnl = ((trade["Current"] - trade["Entry"]) / trade["Entry"]) * 100

                st.write(f"{trade['Ticker']} → P&L: {pnl:.2f}%")

            # ---------------- CHART ----------------
            fig, ax = plt.subplots()
            ax.plot(df["Close"], label="Price")
            ax.plot(df["BB_High"], linestyle="--", label="BB High")
            ax.plot(df["BB_Low"], linestyle="--", label="BB Low")
            ax.plot(df["VWAP"], linestyle=":", label="VWAP")

            ax.set_title(symbol)
            ax.legend()

            st.pyplot(fig)
            plt.close(fig)