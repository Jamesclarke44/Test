import os
import math
import requests
import pandas as pd
import yfinance as yf
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
                if not line:
                    continue
                if line.startswith("#"):
                    continue
                tickers.append(line.upper())
    except FileNotFoundError:
        print("tickers.txt not found. Using empty universe.")
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

def compute_rvol(volume, avg_vol_10d):
    if not volume or not avg_vol_10d or avg_vol_10d == 0:
        return None
    return volume / avg_vol_10d

def compute_gap_pct(price, prev_close):
    if not price or not prev_close or prev_close == 0:
        return None
    return (price - prev_close) / prev_close * 100.0

# =========================
# MOMENTUM SCORE (A)
# =========================

def compute_momentum(gap_pct, rvol):
    if gap_pct is None or rvol is None:
        return None
    return (gap_pct * 1.0) + (rvol * 2.0)

# =========================
# PREMARKET DETECTION (C)
# =========================

def is_premarket():
    est = pytz.timezone("US/Eastern")
    now = datetime.now(est).time()
    return time(4, 0) <= now < time(9, 30)

# =========================
# HEATMAP COLORING (B)
# =========================

def color_heatmap(val):
    if val is None:
        return ""
    if isinstance(val, (int, float)):
        if val >= 5:
            return "background-color: #00b300; color: white;"
        elif val >= 2:
            return "background-color: #66ff66;"
        elif val <= -5:
            return "background-color: #ff4d4d; color: white;"
        elif val <= -2:
            return "background-color: #ff9999;"
    return ""

# =========================
# SCAN LOGIC (D)
# =========================

def process_ticker(t):
    price, prev_close, volume = fetch_alpaca_realtime(t)
    if price is None or prev_close is None or volume is None:
        return None

    # FAST MODE: No ATR, No NewsAPI, No Yahoo fundamentals
    avg_vol_10d = None  # remove slow Yahoo call
    rvol = None

    # RVOL requires avg_vol_10d; skip for speed
    # If you want RVOL back later, we re-enable Yahoo

    gap_pct = compute_gap_pct(price, prev_close)
    momentum = compute_momentum(gap_pct, 0)  # RVOL removed for speed

    return {
        "Ticker": t,
        "Price": price,
        "Prev Close": prev_close,
        "Gap %": gap_pct,
        "Momentum": momentum,
        "Volume": volume,
    }

def scan_universe(tickers):
    rows = []
    if not tickers:
        return pd.DataFrame()

    max_threads = min(40, len(tickers))

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
    st.title("FAST Alpaca Real‑Time Scanner")

    if is_premarket():
        st.info("📈 Premarket Session Detected (4:00–9:30 AM EST)")
    else:
        st.info("🕒 Regular Market Session")

    st.sidebar.header("Scan Settings")

    min_gap = st.sidebar.number_input("Min Gap %", value=3.0, step=0.5)

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

        df = df[df["Gap %"].notna() & (df["Gap %"] >= min_gap)]

        if df.empty:
            st.warning("No tickers matched your filters.")
            return

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
        st.info("Set your filters, then click **Run Scan**.")

if __name__ == "__main__":
    main()
