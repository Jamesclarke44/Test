import time
import yfinance as yf
import pandas as pd
import streamlit as st
import os

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
# FETCH DATA FOR A SINGLE TICKER
# ---------------------------------------------------------

def fetch_data_for_ticker(ticker):
    try:
        info = yf.Ticker(ticker).info
        return {
            "ticker": ticker,
            "price": info.get("regularMarketPrice"),
            "float": info.get("sharesOutstanding"),
            "has_catalyst": False,  # placeholder for your catalyst logic
        }
    except Exception:
        return None


# ---------------------------------------------------------
# APPLY ROSS FILTERS (CORRECTED)
# ---------------------------------------------------------

def apply_ross_filters(df, min_price=2.0, max_float=50_000_000, require_catalyst=False):

    # Normalize column names
    rename_map = {
        "price": "current_price",
        "close": "current_price",
        "last_price": "current_price",
        "regularMarketPrice": "current_price",
    }
    df = df.rename(columns=rename_map)

    # Safety checks
    required = ["current_price", "float"]
    missing = [c for c in required if c not in df.columns]

    if missing:
        st.error(f"Missing required columns: {missing}")
        return df.iloc[0:0]

    # Base filters
    filtered = df[
        (df["current_price"] >= min_price) &
        (df["float"] <= max_float)
    ]

    # Optional catalyst filter
    if require_catalyst and "has_catalyst" in filtered.columns:
        filtered = filtered[filtered["has_catalyst"] == True]

    return filtered


# ---------------------------------------------------------
# SCAN LOGIC WITH PROGRESS BAR
# ---------------------------------------------------------

def run_scan(tickers, min_price, max_float, require_catalyst):
    total = len(tickers)
    progress_bar = st.progress(0)
    status_text = st.empty()

    rows = []

    for i, t in enumerate(tickers):
        progress = int((i + 1) / total * 100)
        progress_bar.progress(progress)
        status_text.write(f"Scanning {i+1} of {total}: {t}")

        row = fetch_data_for_ticker(t)
        if row:
            rows.append(row)

        time.sleep(0.01)  # smooth animation

    status_text.write("Scan complete.")
    progress_bar.progress(100)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    filtered = apply_ross_filters(
        df,
        min_price=min_price,
        max_float=max_float,
        require_catalyst=require_catalyst,
    )
    return filtered


# ---------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------

def main():
    st.set_page_config(page_title="Ross-Style Scanner", layout="wide")
    st.title("Ross-Style Momentum Scanner")

    # Load tickers from file
    tickers = load_tickers_from_file("tickers.txt")
    st.sidebar.write(f"Loaded {len(tickers)} tickers from tickers.txt")

    # Sidebar settings
    min_price = st.sidebar.number_input("Min Price", value=2.0, step=0.5)
    max_float = st.sidebar.number_input("Max Float", value=50_000_000, step=1_000_000)
    require_catalyst = st.sidebar.checkbox("Require Catalyst", value=False)

    tab1, tab2 = st.tabs(["Main Scan", "Debug"])

    with tab1:
        st.subheader("Main Scan")

        if st.button("Run Scan"):
            with st.spinner("Running scan..."):
                results = run_scan(
                    tickers,
                    min_price=min_price,
                    max_float=max_float,
                    require_catalyst=require_catalyst,
                )

            if results.empty:
                st.warning("No tickers passed the filters.")
            else:
                st.success(f"{len(results)} tickers passed the filters.")
                st.dataframe(results)

    with tab2:
        st.subheader("Debug: Raw Data")
        if st.button("Fetch Raw Data Only"):
            with st.spinner("Fetching raw data..."):
                rows = [fetch_data_for_ticker(t) for t in tickers]
                df_raw = pd.DataFrame([r for r in rows if r])

            if df_raw.empty:
                st.warning("No data fetched.")
            else:
                st.write("Columns:", df_raw.columns.tolist())
                st.dataframe(df_raw)


if __name__ == "__main__":
    main()
