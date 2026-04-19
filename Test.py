import os
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
    tickers = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tickers.append(line.upper())
    except FileNotFoundError:
        return []
    return tickers

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

        price = float(trade.price)
        prev_close = float(bar.close)
        volume = int(bar.volume)

        return price, prev_close, volume

    except Exception:
        return None, None, None

def compute_gap_pct(price, prev_close):
    if not price or not prev_close or prev_close == 0:
        return None
    return (price - prev_close) / prev_close * 100.0

def compute_momentum(gap_pct, volume):
    if gap_pct is None or volume is None or volume <= 0:
        return None
    return gap_pct * math.log(volume + 1)

# =========================
# SYSTEM LOGIC
# =========================

def classify_setup(row):
    if row["Gap %"] > 5 and row["Volume"] > 1_000_000:
        return "A+ Momentum"
    elif row["Gap %"] > 3 and row["Volume"] > 700_000:
        return "B Setup"
    else:
        return "C (Ignore)"

def trade_signal(row):
    if row["Setup"] == "A+ Momentum":
        return "Watch Breakout"
    elif row["Setup"] == "B Setup":
        return "Possible Continuation"
    return ""

def risk_model(price):
    stop = price * 0.97
    target = price * 1.06
    return stop, target

# =========================
# PROCESS TICKER
# =========================

def process_ticker(t):
    price, prev_close, volume = fetch_alpaca_realtime(t)

    if price is None or prev_close is None or volume is None:
        return None

    gap_pct = compute_gap_pct(price, prev_close)
    momentum = compute_momentum(gap_pct, volume)

    return {
        "Ticker": t,
        "Price": price,
        "Gap %": gap_pct,
        "Momentum": momentum,
        "Volume": volume,
    }

# =========================
# SCAN
# =========================

def scan_universe(tickers):
    rows = []
    if not tickers:
        return pd.DataFrame()

    max_threads = min(15, len(tickers))

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(process_ticker, t): t for t in tickers}

        for future in as_completed(futures):
            result = future.result()
            if result:
                rows.append(result)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    df["Gap %"] = pd.to_numeric(df["Gap %"], errors="coerce").round(2)
    df["Momentum"] = pd.to_numeric(df["Momentum"], errors="coerce").round(2)

    return df

# =========================
# UI
# =========================

def is_premarket():
    est = pytz.timezone("US/Eastern")
    now = datetime.now(est).time()
    return dt_time(4, 0) <= now < dt_time(9, 30)

def main():
    st.set_page_config(page_title="Trading System", layout="wide")
    st.title("🚀 Momentum Trading System")

    if "df" not in st.session_state:
        st.session_state.df = None
    if "last_scan" not in st.session_state:
        st.session_state.last_scan = None

    if is_premarket():
        st.info("📈 Premarket Session")
    else:
        st.info("🕒 Market Open")

    # SIDEBAR
    st.sidebar.header("Settings")

    min_gap = st.sidebar.number_input("Min Gap %", value=3.0)
    min_volume = st.sidebar.number_input("Min Volume", value=500000)

    auto_refresh = st.sidebar.checkbox("Auto Refresh")
    refresh_time = st.sidebar.slider("Refresh Seconds", 10, 120, 30)

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

        # ADD SYSTEM LOGIC
        df["Setup"] = df.apply(classify_setup, axis=1)
        df["Signal"] = df.apply(trade_signal, axis=1)

        df[["Stop", "Target"]] = df.apply(
            lambda row: pd.Series(risk_model(row["Price"])),
            axis=1
        )

        df = df.sort_values(by="Momentum", ascending=False)

        # ONLY A+ TRADES
        df = df[df["Setup"] == "A+ Momentum"]

        return df

    # MANUAL RUN
    if st.button("Run Scan"):
        with st.spinner("Scanning..."):
            st.session_state.df = run_scan()
            st.session_state.last_scan = datetime.now()

    # AUTO REFRESH
    if auto_refresh:
        time.sleep(refresh_time)
        st.session_state.df = run_scan()
        st.session_state.last_scan = datetime.now()
        st.rerun()

    # DISPLAY
    if st.session_state.df is not None:
        st.subheader("Trade Opportunities")

        if st.session_state.last_scan:
            st.caption(f"Last scan: {st.session_state.last_scan.strftime('%H:%M:%S')}")

        st.dataframe(st.session_state.df, use_container_width=True)

        st.success(f"{len(st.session_state.df)} A+ setups found")

    else:
        st.info("Run scan to find trades")

if __name__ == "__main__":
    main()