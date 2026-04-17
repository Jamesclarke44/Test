import os
import math
import requests
import pandas as pd
import yfinance as yf
import streamlit as st

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
    StockLatestBarRequest,
)
from alpaca.data.timeframe import TimeFrame

# =========================
# CONFIG: INSERT YOUR KEYS
# =========================

ALPACA_API_KEY = "PKROA6C3OVWVE4ACLS7ZTSFZ2K"
ALPACA_SECRET_KEY = "CiMJpbtkkSedarodE3jsjyymAmpYPnh7UcZH2mnE8Y2j"
NEWSAPI_KEY = "YOUR_NEWSAPI_KEY"

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

                # Skip empty lines
                if not line:
                    continue

                # Skip header lines (anything starting with #)
                if line.startswith("#"):
                    continue

                # Add ticker (uppercase, clean)
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
    """
    Get latest trade, quote, and bar from Alpaca.
    Returns price, prev_close, volume.
    """
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
    """
    Use yfinance for float + 10-day avg volume.
    """
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
# CATALYST DETECTION
# =========================

CATALYST_KEYWORDS = [
    "earnings", "guidance", "upgrade", "downgrade", "beats", "misses",
    "FDA", "approval", "trial", "phase", "contract", "partnership",
    "acquisition", "merger", "record", "revenue", "outlook",
]

def check_catalyst_newsapi(ticker: str):
    """
    Simple catalyst detector using NewsAPI headlines.
    Returns (has_catalyst: bool, first_match_title: str or None)
    """
    if not NEWSAPI_KEY or NEWSAPI_KEY == "YOUR_NEWSAPI_KEY":
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
# SCAN LOGIC
# =========================

def scan_universe(tickers):
    rows = []

    for t in tickers:
        price, prev_close, volume = fetch_alpaca_realtime(t)
        if price is None or prev_close is None or volume is None:
            continue

        avg_vol_10d, float_shares = fetch_yahoo_fundamentals(t)

        gap_pct = compute_gap_pct(price, prev_close)
        rvol = compute_rvol(volume, avg_vol_10d)

        has_catalyst, catalyst_title = check_catalyst_newsapi(t)

        rows.append(
            {
                "Ticker": t,
                "Price": price,
                "Prev Close": prev_close,
                "Gap %": gap_pct,
                "Volume": volume,
                "Avg Vol 10D": avg_vol_10d,
                "RVOL": rvol,
                "Float": float_shares,
                "Has Catalyst": has_catalyst,
                "Catalyst Headline": catalyst_title,
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Clean formatting
    if "Gap %" in df.columns:
        df["Gap %"] = df["Gap %"].round(2)
    if "RVOL" in df.columns:
        df["RVOL"] = df["RVOL"].round(2)

    return df


# =========================
# STREAMLIT UI
# =========================

def main():
    st.set_page_config(page_title="Alpaca + Catalyst Scanner", layout="wide")
    st.title("Alpaca Real‑Time + Catalyst Scanner")

    st.markdown(
        "Real‑time price/volume from **Alpaca**, float/avg volume from **Yahoo**, "
        "and catalyst detection via **NewsAPI**."
    )

    st.sidebar.header("Scan Settings")

    min_gap = st.sidebar.number_input("Min Gap %", value=3.0, step=0.5)
    min_rvol = st.sidebar.number_input("Min RVOL", value=1.5, step=0.1)
    require_catalyst = st.sidebar.checkbox("Require Catalyst", value=False)

    st.sidebar.write("---")
    st.sidebar.write(f"Universe size: {len(UNIVERSE)} tickers")

    if st.button("Run Scan"):
        with st.spinner("Scanning universe with Alpaca + NewsAPI..."):
            df = scan_universe(UNIVERSE)

        if df.empty:
            st.warning("No data returned. Check keys, market hours, or universe.")
            return

        # Apply filters
        if "Gap %" in df.columns:
            df = df[df["Gap %"].notna() & (df["Gap %"] >= min_gap)]
        if "RVOL" in df.columns:
            df = df[df["RVOL"].notna() & (df["RVOL"] >= min_rvol)]
        if require_catalyst and "Has Catalyst" in df.columns:
            df = df[df["Has Catalyst"] == True]

        if df.empty:
            st.warning("No tickers matched your filters.")
            return

        # Sort by Gap % descending
        df = df.sort_values(by="Gap %", ascending=False)

        st.subheader("Scan Results")
        st.dataframe(
            df[
                [
                    "Ticker",
                    "Price",
                    "Gap %",
                    "RVOL",
                    "Volume",
                    "Float",
                    "Has Catalyst",
                    "Catalyst Headline",
                ]
            ],
            use_container_width=True,
        )

        st.success(f"Found {len(df)} matching tickers.")

    else:
        st.info("Set your filters, then click **Run Scan**.")


if __name__ == "__main__":
    main()
