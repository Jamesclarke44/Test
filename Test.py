import math
import pandas as pd
import streamlit as st
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dt_time
import pytz

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockLatestTradeRequest,
    StockLatestBarRequest,
)

# =========================
# CONFIG
# =========================

ALPACA_API_KEY = ""
ALPACA_SECRET_KEY = ""

alpaca = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

# =========================
# LOAD TICKERS
# =========================

def load_universe_from_file(path="tickers.txt"):
    try:
        with open(path, "r") as f:
            return [
                line.strip().upper()
                for line in f
                if line.strip() and not line.startswith("#")
            ]
    except FileNotFoundError:
        return []

UNIVERSE = load_universe_from_file()

# =========================
# DATA HELPERS
# =========================

def fetch_alpaca_realtime(ticker: str):
    try:
        trade = alpaca.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=ticker)
        )[ticker]

        bar = alpaca.get_stock_latest_bar(
            StockLatestBarRequest(symbol_or_symbols=ticker)
        )[ticker]

        return float(trade.price), float(bar.close), int(bar.volume)

    except Exception:
        return None, None, None

def compute_gap_pct(price, prev_close):
    if not price or not prev_close:
        return None
    return (price - prev_close) / prev_close * 100

def compute_momentum(gap_pct, volume):
    if gap_pct is None or volume is None or volume <= 0:
        return None
    return gap_pct * math.log(volume + 1)

# =========================
# SYSTEM LOGIC
# =========================

def classify_setup(row):
    if row["Gap %"] > 5 and row["Volume"] > 1_000_000:
        return "A+"
    elif row["Gap %"] > 3 and row["Volume"] > 700_000:
        return "B"
    return "C"

def trade_signal(row):
    if row["Setup"] == "A+":
        return "Watch Breakout"
    elif row["Setup"] == "B":
        return "Continuation"
    return ""

def breakout_logic(row):
    price = row["Price"]
    pm_high = price * 1.02  # placeholder
    breakout = pm_high

    if price >= breakout:
        return pm_high, breakout, "BREAKOUT 🔥"
    elif price >= breakout * 0.98:
        return pm_high, breakout, "Near Breakout"
    return pm_high, breakout, ""

def risk_model(price):
    return price * 0.97, price * 1.06

# =========================
# MARKET SESSION FIX (KEY)
# =========================

def get_market_session():
    est = pytz.timezone("US/Eastern")
    now = datetime.now(est)
    current_time = now.time()
    current_day = now.weekday()

    if current_day >= 5:
        return "Closed"

    if dt_time(4, 0) <= current_time < dt_time(9, 30):
        return "Premarket"
    elif dt_time(9, 30) <= current_time < dt_time(16, 0):
        return "Open"
    elif dt_time(16, 0) <= current_time < dt_time(20, 0):
        return "After Hours"
    return "Closed"

# =========================
# PROCESS
# =========================

def process_ticker(t):
    price, prev_close, volume = fetch_alpaca_realtime(t)

    if price is None:
        return None

    gap = compute_gap_pct(price, prev_close)
    momentum = compute_momentum(gap, volume)

    return {
        "Ticker": t,
        "Price": price,
        "Gap %": round(gap, 2) if gap else None,
        "Momentum": round(momentum, 2) if momentum else None,
        "Volume": volume,
    }

# =========================
# SCAN
# =========================

def scan_universe(tickers):
    rows = []
    with ThreadPoolExecutor(max_workers=min(15, len(tickers))) as executor:
        futures = [executor.submit(process_ticker, t) for t in tickers]
        for f in as_completed(futures):
            r = f.result()
            if r:
                rows.append(r)

    return pd.DataFrame(rows)

# =========================
# UI
# =========================

def main():
    st.set_page_config(layout="wide")
    st.title("🚀 Momentum Trading System")

    # SESSION STATE
    if "df" not in st.session_state:
        st.session_state.df = None
    if "last_scan" not in st.session_state:
        st.session_state.last_scan = None

    # MARKET STATUS
    session = get_market_session()

    if session == "Premarket":
        st.info("📈 Premarket")
    elif session == "Open":
        st.success("🟢 Market Open")
    elif session == "After Hours":
        st.warning("🌙 After Hours")
    else:
        st.error("🔴 Market Closed")

    # SIDEBAR
    min_gap = st.sidebar.number_input("Min Gap %", 0.0, 20.0, 3.0)
    min_volume = st.sidebar.number_input("Min Volume", 0, 5000000, 500000)

    auto = st.sidebar.checkbox("Auto Refresh")
    refresh = st.sidebar.slider("Seconds", 10, 120, 30)

    # SCAN FUNCTION
    def run_scan():
        df = scan_universe(UNIVERSE)
        if df.empty:
            return None

        df = df[
            (df["Gap %"] >= min_gap) &
            (df["Volume"] >= min_volume)
        ]

        if df.empty:
            return None

        df["Setup"] = df.apply(classify_setup, axis=1)
        df["Signal"] = df.apply(trade_signal, axis=1)

        df[["PM High", "Breakout", "Entry"]] = df.apply(
            lambda r: pd.Series(breakout_logic(r)), axis=1
        )

        df[["Stop", "Target"]] = df.apply(
            lambda r: pd.Series(risk_model(r["Price"])), axis=1
        )

        df = df.sort_values("Momentum", ascending=False)

        # Only A+ trades
        df = df[df["Setup"] == "A+"]

        return df

    # BUTTON
    if st.button("Run Scan"):
        st.session_state.df = run_scan()
        st.session_state.last_scan = datetime.now()

    # AUTO
    if auto:
        time.sleep(refresh)
        st.session_state.df = run_scan()
        st.session_state.last_scan = datetime.now()
        st.rerun()

    # DISPLAY
    if st.session_state.df is not None:
        st.subheader("🔥 Trade Opportunities")

        if st.session_state.last_scan:
            st.caption(
                f"Last scan: {st.session_state.last_scan.strftime('%H:%M:%S')}"
            )

        st.dataframe(st.session_state.df, use_container_width=True)

        st.success(f"{len(st.session_state.df)} A+ setups found")

    else:
        st.info("Run scan to begin")

# =========================

if __name__ == "__main__":
    main()