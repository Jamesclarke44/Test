import streamlit as st
import yfinance as yf
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import ADXIndicator
from ta.volatility import BollingerBands

st.title("📊 Options Exit Strategy Engine (Pro)")

# ---------------- INPUTS ----------------

symbol = st.text_input("Stock Symbol", value="AAPL")

entry_price = st.number_input("Entry Price (Spread Cost)", value=3.40)
current_spread = st.number_input("Current Spread Value", value=3.70)

strike_price = st.number_input("Strike Price", value=100.0)
days_to_expiry = st.number_input("Days to Short Expiry", value=10)

target_profit = st.number_input("Target Profit %", value=25)

# ---------------- DATA ----------------

def safe_float(val):
    try:
        if isinstance(val, pd.Series):
            return float(val.iloc[0])
        return float(val)
    except:
        return None

try:
    data = yf.download(symbol, period="3mo", interval="1d")

    if data is None or data.empty or len(data) < 50:
        st.error("Not enough data.")
        st.stop()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    data = data.dropna()

    close = data["Close"]
    high = data["High"]
    low = data["Low"]

    # ---------------- INDICATORS ----------------

    data["RSI"] = RSIIndicator(close=close).rsi()
    data["ADX"] = ADXIndicator(high=high, low=low, close=close).adx()

    bb = BollingerBands(close=close)
    data["BB_High"] = bb.bollinger_hband()
    data["BB_Low"] = bb.bollinger_lband()

    # ---------------- LAST VALUES ----------------

    last = data.iloc[-1]

    current_price = safe_float(last["Close"])
    rsi = safe_float(last["RSI"])
    adx = safe_float(last["ADX"])
    bb_low = safe_float(last["BB_Low"])
    bb_high = safe_float(last["BB_High"])

    # ---------------- CALCULATIONS ----------------

    profit_pct = ((current_spread - entry_price) / entry_price) * 100
    distance = abs(current_price - strike_price)

    if bb_high - bb_low == 0:
        bb_position = 0.5
    else:
        bb_position = (current_price - bb_low) / (bb_high - bb_low)

    # ---------------- EXIT ENGINE ----------------

    action = "MONITOR"

    # 1️⃣ PROFIT FIRST (priority)
    if profit_pct >= target_profit:
        action = "✅ EXIT — Target Hit"

    # 2️⃣ HARD RISK CONTROL
    elif profit_pct <= -40:
        action = "⛔ EXIT — Max Loss Hit"

    # 3️⃣ TREND BREAK (VERY IMPORTANT)
    elif adx > 25:
        action = "⚠️ EXIT — Trend Forming (ADX)"

    # 4️⃣ MOMENTUM SHIFT
    elif rsi < 40 or rsi > 60:
        action = "⚠️ EXIT — Momentum Break (RSI)"

    # 5️⃣ RANGE BREAK
    elif bb_position < 0.3 or bb_position > 0.7:
        action = "⚠️ EXIT — Range Breakdown (BB)"

    # 6️⃣ TIME DECAY
    elif days_to_expiry <= 5:
        action = "⏳ EXIT — Theta Captured"

    # 7️⃣ IDEAL HOLD ZONE
    elif 10 <= profit_pct < target_profit and 0.4 <= bb_position <= 0.6:
        action = "🎯 HOLD — Ideal Zone"

    # 8️⃣ ROLL LOGIC
    elif days_to_expiry <= 7 and 0.4 <= bb_position <= 0.6:
        action = "🔄 ROLL — Maintain Position"

    # ---------------- DISPLAY ----------------

    st.subheader("📈 Market State")
    st.write(f"Price: {current_price:.2f}")
    st.write(f"RSI: {rsi:.1f}")
    st.write(f"ADX: {adx:.1f}")
    st.write(f"BB Position: {bb_position:.2f}")

    st.subheader("📊 Trade Metrics")
    st.write(f"Profit: {profit_pct:.2f}%")
    st.write(f"Distance from Strike: {distance:.2f}")
    st.write(f"Days to Expiry: {days_to_expiry}")

    st.subheader("🚦 Recommended Action")
    st.success(action)

except Exception as e:
    st.error(f"Error fetching data: {e}")