import os
import math
import pandas as pd
import streamlit as st

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time
import pytz

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockLatestTradeRequest,
    StockLatestBarRequest,
)

# =========================
# CONFIG: INSERT YOUR KEYS
# =========================

ALPACA_API_KEY = "PKROA6C3OVWVE4ACLS7ZTSFZ2K"
ALPACA_SECRET_KEY = "CiMJpbtkkSedarodE3jsjyymAmpYPnh7UcZH2mnE8Y2j"

alpaca = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

# =========================
# LOAD TICKERS.TXT UNIVERSE
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
        print("tickers.txt not found.")
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

    except Exception as e:
        # Debug (optional)
        # print(f"{ticker} failed: {e}")
        return None, None, None

def compute_gap_pct(price, prev_close):
    if not price or not prev_close or prev_close == 0:
        return None
    return (price - prev_close) / prev_close * 100.0

# =========================
# MOMENTUM (FIXED)
# =========================

def compute_momentum(gap_pct, volume):
    if gap_pct is None or volume is None or volume <= 0:
        return None
    return gap_pct * math.log(volume + 1)

# =========================
# PREMARKET DETECTION
# =========================

def is_premarket():
    est = pytz.timezone("US/Eastern")
    now = datetime.now(est).time()
    return time(4, 0) <= now < time(9, 30)

# =========================
# HEATMAP COLORING
# =========================

def color_heatmap(val):
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        if val >= 20:
            return "background-color: #006400; color: white;"
        elif val >= 10:
            return "background-color: #00b300; color: white;"
        elif val >= 5:
            return "background-color: #66ff66;"
        elif val <= -10:
            return "background-color: #8b0000; color: white;"
        elif val <= -5:
            return "background-color: #ff4d4d;"
    return ""

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
        "Prev Close": prev_close,
        "Gap %": gap_pct,
        "Momentum": momentum,
        "Volume": volume,
    }

# =========================
# SCAN LOGIC
# =========================

def scan_universe(tickers):
    rows = []
    if not tickers:
        return pd.DataFrame()

    max_threads = min(15, len(tickers))  # safer for API

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = {executor.submit(process_ticker, t): t for t in tickers}

        for future in as_completed(futures):
            result = future.result()
            if result:
                rows.append(result)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    for col in ["Gap %", "Momentum"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

    return df

# =========================
# STREAMLIT UI
# =========================

def main():
    st.set_page_config(page_title="FAST Alpaca Scanner", layout="wide")
    st.title("⚡ FAST Alpaca Real-Time Scanner")

    if is_premarket():
        st.info("📈 Premarket Session (4:00–9:30 AM EST)")
    else:
        st.info("🕒 Regular Market Session")

    st.sidebar.header("Scan Settings")

    min_gap = st.sidebar.number_input("Min Gap %", value=3.0, step=0.5)
    min_volume = st.sidebar.number_input("Min Volume", value=500000, step=100000)

    top_mode = st.sidebar.selectbox(
        "Top Gappers Mode",
        ["Full Universe", "Top 10", "Top 20", "Top 50"]
    )

    st.sidebar.write("---")
    st.sidebar.write(f"Universe size: {len(UNIVERSE)} tickers")

    if st.button("Run Scan"):
        with st.spinner("Scanning FAST..."):
            df = scan_universe(UNIVERSE)

        if df.empty:
            st.warning("No data returned.")
            return

        # FILTERS (IMPROVED)
        df = df[
            (df["Gap %"].notna()) &
            (df["Gap %"] >= min_gap) &
            (df["Volume"] >= min_volume)
        ]

        if df.empty:
            st.warning("No tickers matched your filters.")
            return

        # TRADE READY FLAG
        df["Trade Ready"] = (
            (df["Gap %"] > 5) &
            (df["Volume"] > 1_000_000)
        )

        df = df.sort_values(by="Momentum", ascending=False)

        if top_mode == "Top 10":
            df = df.head(10)
        elif top_mode == "Top 20":
            df = df.head(20)
        elif top_mode == "Top 50":
            df = df.head(50)

        st.subheader("Scan Results")

        styled = df.style.applymap(
            color_heatmap,
            subset=["Gap %", "Momentum"]
        )

        st.dataframe(styled, use_container_width=True)
        st.success(f"Found {len(df)} matching tickers.")

    else:
        st.info("Set filters and click Run Scan")

if __name__ == "__main__":
    main()