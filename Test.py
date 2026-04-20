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

ALPACA_API_KEY = "PKROA6C3OVWVE4ACLS7ZTSFZ2K"
ALPACA_SECRET_KEY = "CiMJpbtkkSedarodE3jsjyymAmpYPnh7UcZH2mnE8Y2j"

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
    except:
        return []

UNIVERSE = load_universe_from_file()

# =========================
# MARKET SESSION (FIXED)
# =========================

def get_market_session():
    est = pytz.timezone("US/Eastern")
    now = datetime.now(est)

    t = now.time()
    d = now.weekday()

    if d >= 5:
        return "Closed"

    if dt_time(4, 0) <= t < dt_time(9, 30):
        return "Premarket"
    elif dt_time(9, 30) <= t < dt_time(16, 0):
        return "Open"
    elif dt_time(16, 0) <= t < dt_time(20, 0):
        return "After Hours"
    else:
        return "Closed"

# =========================
# DATA FETCH (RETRY SAFE)
# =========================

def fetch_alpaca_realtime(ticker: str, retries=2):
    for _ in range(retries):
        try:
            trade = alpaca.get_stock_latest_trade(
                StockLatestTradeRequest(symbol_or_symbols=ticker)
            )[ticker]

            bar = alpaca.get_stock_latest_bar(
                StockLatestBarRequest(symbol_or_symbols=ticker)
            )[ticker]

            return float(trade.price), float(bar.close), int(bar.volume)

        except Exception:
            time.sleep(0.2)

    return None, None, None

# =========================
# CALCULATIONS
# =========================

def compute_gap(price, prev):
    if not price or not prev:
        return None
    return (price - prev) / prev * 100

def compute_momentum(gap, vol):
    if gap is None or vol is None:
        return None
    return gap * math.log(vol + 1)

# =========================
# PROCESS
# =========================

def process_ticker(t):
    price, prev, vol = fetch_alpaca_realtime(t)

    if price is None:
        return None

    gap = compute_gap(price, prev)
    momentum = compute_momentum(gap, vol)

    return {
        "Ticker": t,
        "Price": price,
        "Gap %": round(gap, 2) if gap else None,
        "Momentum": round(momentum, 2) if momentum else None,
        "Volume": vol,
    }

# =========================
# SCANNER (STABLE)
# =========================

def scan_universe(tickers):
    rows = []

    max_threads = min(10, len(tickers))  # lower = more stable

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(process_ticker, t): t for t in tickers}

        for future in as_completed(futures):
            try:
                result = future.result(timeout=5)
                if result:
                    rows.append(result)
            except:
                continue

    return pd.DataFrame(rows)

# =========================
# UI
# =========================

def main():
    st.set_page_config(layout="wide")
    st.title("🚀 Stable Momentum Scanner")

    # SESSION DISPLAY
    session = get_market_session()

    st.write(f"**Session:** {session}")

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
    min_vol = st.sidebar.number_input("Min Volume", 0, 5000000, 500000)

    # BUTTON
    if st.button("Run Scan"):

        st.write("Scanning...")

        df = scan_universe(UNIVERSE)

        if df.empty:
            st.warning("No data returned (likely API or rate limit issue)")
            return

        df = df[
            (df["Gap %"] >= min_gap) &
            (df["Volume"] >= min_vol)
        ]

        if df.empty:
            st.warning("No tickers matched filters")
            return

        df = df.sort_values("Momentum", ascending=False)

        st.dataframe(df, use_container_width=True)
        st.success(f"{len(df)} results")

# =========================

if __name__ == "__main__":
    main()