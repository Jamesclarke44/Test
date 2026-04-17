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
from alpaca.data.timeframe import TimeFrame

# =========================
# CONFIG: INSERT YOUR KEYS
# =========================

ALPACA_API_KEY = "PKROA6C3OVWVE4ACLS7ZTSFZ2K"
ALPACA_SECRET_KEY = "CiMJpbtkkSedarodE3jsjyymAmpYPnh7UcZH2mnE8Y2j"
NEWSAPI_KEY = "08d9db0ed13a4bddb15a589db72a501b"

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


def fetch_yahoo_fundamentals(ticker: str):
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}

    avg_vol_10d = info.get("averageDailyVolume10Day")
    float_shares = (
        info.get("floatShares")
        or info.get("sharesOutstanding")
        or info.get("impliedSharesOutstanding")
    )

    return avg_vol_10d, float_shares


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
# CATALYST DETECTION
# =========================

CATALYST_KEYWORDS = [
    "earnings", "guidance", "upgrade", "downgrade", "beats", "misses",
    "FDA", "approval", "trial", "phase", "contract", "partnership",
    "acquisition", "merger", "record", "revenue", "outlook",
]

def check_catalyst_newsapi(ticker: str):
    if not NEWSAPI_KEY:
        return False, None

    try:
        url = (
            "https://newsapi.org/v2/everything"
            f"?q={ticker}&language=en&sortBy=publishedAt&pageSize=10&apiKey={NEWSAPI_KEY}"
        )
        r = requests.get(url, timeout=5)
        data = r.json()
    except Exception:
        return False, None

    articles = data.get("articles", [])
    for a in articles:
        title = (a.get("title") or "").lower()
        if not title:
            continue
        for kw in CATALYST_KEYWORDS:
            if kw.lower() in title:
                return True, a.get("title")
    return False, None


# =========================
# VWAP DEVIATION (E)
# =========================

def fetch_vwap(ticker):
    try:
        bar = alpaca.get_stock_latest_bar(
            StockLatestBarRequest(symbol_or_symbols=ticker)
        )[ticker]
        return bar.vwap if hasattr(bar, "vwap") else None
    except:
        return None


# =========================
# ATR FILTER (F)
# =========================

def fetch_atr(ticker, period=14):
    try:
        data = yf.download(ticker, period="30d", interval="1d", progress=False)
        if len(data) < period:
            return None

        data["H-L"] = data["High"] - data["Low"]
        data["H-PC"] = abs(data["High"] - data["Close"].shift(1))
        data["L-PC"] = abs(data["Low"] - data["Close"].shift(1))
        data["TR"] = data[["H-L", "H-PC", "L-PC"]].max(axis=1)
        atr = data["TR"].rolling(period).mean().iloc[-1]
        return atr
    except:
        return None


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

    avg_vol_10d, float_shares = fetch_yahoo_fundamentals(t)

    gap_pct = compute_gap_pct(price, prev_close)
    rvol = compute_rvol(volume, avg_vol_10d)
    momentum = compute_momentum(gap_pct, rvol)

    has_catalyst, catalyst_title = check_catalyst_newsapi(t)

    vwap = fetch_vwap(t)
    vwap_dev = ((price - vwap) / vwap * 100) if vwap else None

    atr = fetch_atr(t)

    return {
        "Ticker": t,
        "Price": price,
        "Prev Close": prev_close,
        "Gap %": gap_pct,
        "Volume": volume,
        "Avg Vol 10D": avg_vol_10d,
        "RVOL": rvol,
        "Momentum": momentum,
        "Float": float_shares,
        "Has Catalyst": has_catalyst,
        "Catalyst Headline": catalyst_title,
        "VWAP": vwap,
        "VWAP Dev %": vwap_dev,
        "ATR": atr,
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

    for col in ["Gap %", "RVOL", "Momentum", "VWAP Dev %", "ATR"]:
        if col in df.columns:
            df[col] = df[col].round(2)

    return df


# =========================
# STREAMLIT UI
# =========================

def main():
    st.set_page_config(page_title="Alpaca + Catalyst Scanner", layout="wide")
    st.title("Alpaca Real‑Time + Catalyst Scanner")

    if is_premarket():
        st.info("📈 Premarket Session Detected (4:00–9:30 AM EST)")
    else:
        st.info("🕒 Regular Market Session")

    st.sidebar.header("Scan Settings")

    min_gap = st.sidebar.number_input("Min Gap %", value=3.0, step=0.5)
    min_rvol = st.sidebar.number_input("Min RVOL", value=1.5, step=0.1)
    min_atr = st.sidebar.number_input("Min ATR", value=0.5, step=0.1)
    require_catalyst = st.sidebar.checkbox("Require Catalyst", value=False)

    top_mode = st.sidebar.selectbox(
        "Top Gappers Mode",
        ["Full Universe", "Top 10", "Top 20", "Top 50"]
    )

    st.sidebar.write("---")
    st.sidebar.write(f"Universe size: {len(UNIVERSE)} tickers")

    if st.button("Run Scan"):
        with st.spinner("Scanning universe..."):
            df = scan_universe(UNIVERSE)

        if df.empty:
            st.warning("No data returned.")
            return

        df = df[df["Gap %"].notna() & (df["Gap %"] >= min_gap)]
        df = df[df["RVOL"].notna() & (df["RVOL"] >= min_rvol)]
        df = df[df["ATR"].notna() & (df["ATR"] >= min_atr)]

        if require_catalyst:
            df = df[df["Has Catalyst"] == True]

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
            subset=["Gap %", "RVOL", "Momentum"]
        )

        st.dataframe(styled, use_container_width=True)
        st.success(f"Found {len(df)} matching tickers.")

    else:
        st.info("Set your filters, then click **Run Scan**.")


if __name__ == "__main__":
    main()
