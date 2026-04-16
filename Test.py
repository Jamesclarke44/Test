import time
import os
import yfinance as yf
import pandas as pd
import streamlit as st

# ---------------------------------------------------------
# LOAD TICKERS FROM tickers.txt
# ---------------------------------------------------------

def load_tickers_from_file(path="tickers.txt"):
    if not os.path.exists(path):
        st.error(f"File not found: {path}")
        return []
    with open(path, "r") as f:
        tickers = [line.strip().upper() for line in f.readlines() if line.strip()]
    return tickers


# ---------------------------------------------------------
# FETCH DATA FOR A SINGLE TICKER (Ross-style fields)
# ---------------------------------------------------------

def fetch_data_for_ticker(ticker):
    try:
        info = yf.Ticker(ticker).info or {}

        # Extract raw fields
        price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("lastPrice")
        prev_close = info.get("previousClose")
        vol = info.get("regularMarketVolume")
        avg_vol = info.get("averageDailyVolume10Day")
        shares_out = (
            info.get("sharesOutstanding")
            or info.get("floatShares")
            or info.get("impliedSharesOutstanding")
        )

        # % Change
        pct_change = None
        if price not in (None, 0) and prev_close not in (None, 0):
            pct_change = ((price - prev_close) / prev_close) * 100

        # RVOL
        rvol = None
        if vol not in (None, 0) and avg_vol not in (None, 0):
            rvol = vol / avg_vol

        # Halt detector
        halted = info.get("tradeable", True) is False

        return {
            "ticker": ticker,
            "regularMarketPrice": price,
            "previousClose": prev_close,
            "pct_change": pct_change,
            "volume": vol,
            "avg_volume_10d": avg_vol,
            "rvol": rvol,
            "sharesOutstanding": shares_out,
            "halted": halted,
            "has_catalyst": False,  # placeholder
        }
    except Exception:
        return None


# ---------------------------------------------------------
# BATCH FETCH WITH OPTIONAL PROGRESS BAR
# ---------------------------------------------------------

def fetch_batch(tickers, show_progress=False, label="Scanning"):
    rows = []
    total = len(tickers)

    if show_progress:
        progress_bar = st.progress(0)
        status_text = st.empty()
    else:
        progress_bar = None
        status_text = None

    for i, t in enumerate(tickers):
        if show_progress:
            progress = int((i + 1) / total * 100)
            progress_bar.progress(progress)
            status_text.write(f"{label} {i+1} of {total}: {t}")

        row = fetch_data_for_ticker(t)

        # Skip tickers with missing or invalid price
        if row and row.get("regularMarketPrice") not in (None, 0):
            rows.append(row)

        if show_progress:
            time.sleep(0.01)

    if show_progress:
        status_text.write(f"{label} complete.")
        progress_bar.progress(100)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


# ---------------------------------------------------------
# MOMENTUM SCORING (Ross A-Setup Logic)
# ---------------------------------------------------------

def momentum_score(row):
    score = 0

    # Gap size
    if row.get("pct_change"):
        score += row["pct_change"] * 1.0

    # RVOL
    if row.get("rvol"):
        score += row["rvol"] * 10

    # Float bonus
    if row.get("float"):
        if row["float"] < 10_000_000:
            score += 20
        elif row["float"] < 20_000_000:
            score += 10

    # Catalyst bonus
    if row.get("has_catalyst"):
        score += 25

    return score


# ---------------------------------------------------------
# CORE ROSS FILTERS (A–D integrated)
# ---------------------------------------------------------

def apply_ross_filters(df, min_price, max_float, min_gap, min_rvol, min_premarket_vol, require_catalyst):

    # Safety: empty DF
    if df is None or df.empty:
        return df

    # ---------------------------------------------------------
    # NORMALIZE PRICE + FLOAT FIELDS (bulletproof)
    # ---------------------------------------------------------

    # Normalize price fields
    price_fields = [
        "regularMarketPrice",
        "currentPrice",
        "lastPrice",
        "price",
        "close",
        "previousClose",
    ]

    df["current_price"] = None
    for field in price_fields:
        if field in df.columns:
            df["current_price"] = df["current_price"].fillna(df[field])

    # Normalize float fields
    float_fields = [
        "sharesOutstanding",
        "floatShares",
        "impliedSharesOutstanding",
    ]

    df["float"] = None
    for field in float_fields:
        if field in df.columns:
            df["float"] = df["float"].fillna(df[field])

    # Drop rows missing critical data
    df = df.dropna(subset=["current_price", "float"])

    # Price + float filters
    filtered = df[
        (df["current_price"] >= min_price) &
        (df["float"] <= max_float)
    ]

    # Gap filter
    if "pct_change" in filtered.columns:
        filtered = filtered[filtered["pct_change"] >= min_gap]

    # Premarket volume filter
    if "volume" in filtered.columns:
        filtered = filtered[filtered["volume"] >= min_premarket_vol]

    # RVOL filter
    if "rvol" in filtered.columns:
        filtered = filtered[filtered["rvol"] >= min_rvol]

    # Catalyst filter
    if require_catalyst and "has_catalyst" in filtered.columns:
        filtered = filtered[filtered["has_catalyst"] == True]

    return filtered


# ---------------------------------------------------------
# GAP VIEW / MOMENTUM VIEW / HOT LIST
# ---------------------------------------------------------

def build_gap_view(df):
    return df.sort_values("pct_change", ascending=False)


def build_momentum_view(df):
    return df.sort_values("rvol", ascending=False)


def build_hot_list(df, top_n=10):
    df = df.copy()
    df["momentum_score"] = df.apply(momentum_score, axis=1)
    return df.sort_values("momentum_score", ascending=False).head(top_n)


# ---------------------------------------------------------
# MAIN APP (Ross MAX)
# ---------------------------------------------------------

def main():
    st.set_page_config(page_title="Ross MAX Scanner", layout="wide")
    st.title("Ross MAX Momentum Scanner")

    tickers = load_tickers_from_file("tickers.txt")
    st.sidebar.write(f"Loaded {len(tickers)} tickers")

    # Sidebar filters
    st.sidebar.header("Ross Filters")
    min_price = st.sidebar.number_input("Min Price", value=2.0)
    max_float = st.sidebar.number_input("Max Float", value=50_000_000)
    min_gap = st.sidebar.number_input("Min Gap %", value=4.0)
    min_rvol = st.sidebar.number_input("Min RVOL", value=2.0)
    min_premarket_vol = st.sidebar.number_input("Min Premarket Volume", value=100_000)
    require_catalyst = st.sidebar.checkbox("Require Catalyst", value=False)

    tab_gap, tab_momo, tab_hot, tab_halts, tab_universe, tab_debug = st.tabs(
        ["Gap Scanner", "Momentum", "Hot List", "Halts", "Universe Scan", "Debug"]
    )

    # ---------------- GAP SCANNER ----------------
    with tab_gap:
        st.subheader("Gap Scanner")
        if st.button("Run Gap Scan"):
            with st.spinner("Scanning gappers..."):
                df = fetch_batch(tickers)
                df = apply_ross_filters(df, min_price, max_float, min_gap, min_rvol, min_premarket_vol, require_catalyst)
                gappers = build_gap_view(df)

            st.dataframe(gappers)

    # ---------------- MOMENTUM ----------------
    with tab_momo:
        st.subheader("Momentum Scanner")
        if st.button("Run Momentum Scan"):
            with st.spinner("Scanning momentum..."):
                df = fetch_batch(tickers)
                df = apply_ross_filters(df, min_price, max_float, min_gap, min_rvol, min_premarket_vol, require_catalyst)
                movers = build_momentum_view(df)

            st.dataframe(movers)

    # ---------------- HOT LIST ----------------
    with tab_hot:
        st.subheader("Hot List (Top Momentum Scores)")
        if st.button("Build Hot List"):
            with st.spinner("Building hot list..."):
                df = fetch_batch(tickers)
                df = apply_ross_filters(df, min_price, max_float, min_gap, min_rvol, min_premarket_vol, require_catalyst)
                hot = build_hot_list(df)

            st.dataframe(hot)

    # ---------------- HALTS ----------------
    with tab_halts:
        st.subheader("Halt Detector")
        if st.button("Scan for Halts"):
            with st.spinner("Checking halts..."):
                df = fetch_batch(tickers)
                halted = df[df["halted"] == True]

            st.dataframe(halted)

    # ---------------- UNIVERSE SCAN ----------------
    with tab_universe:
        st.subheader("Full Universe Scan (with progress bar)")
        if st.button("Run Full Scan"):
            with st.spinner("Scanning full universe..."):
                df = fetch_batch(tickers, show_progress=True)
                results = apply_ross_filters(df, min_price, max_float, min_gap, min_rvol, min_premarket_vol, require_catalyst)

            st.dataframe(results)

    # ---------------- DEBUG ----------------
    with tab_debug:
        st.subheader("Debug: Raw Data")
        if st.button("Fetch Raw Data"):
            df_raw = fetch_batch(tickers)
            st.write(df_raw.columns.tolist())
            st.dataframe(df_raw)


if __name__ == "__main__":
    main()
