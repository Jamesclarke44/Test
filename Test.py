# app.py
# -----------------------------------------
# EOD Swing-Trade Scanner (Long Only)
# - Scans 1500+ U.S. stocks (S&P 500 + Russell 1000)
# - Uptrend + pullback + momentum turn
# - Ranks best "buy low, sell high" setups
# -----------------------------------------

import datetime as dt
import math
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# ------------------ CONFIG ------------------

START_DAYS_BACK = 250
MIN_PRICE = 10
MAX_PRICE = 200
MIN_AVG_VOLUME = 1_000_000


# ------------------ LOAD UNIVERSE ------------------

@st.cache_data(show_spinner=True)
def load_universe():
    # Load S&P 500
    sp500 = pd.read_csv(
        "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents_symbols.csv"
    )["Symbol"].dropna().tolist()

    # Load Russell 1000
    russell1000 = pd.read_csv(
        "https://raw.githubusercontent.com/datasets/russell-1000/master/data/russell1000.csv"
    )["Ticker"].dropna().tolist()

    tickers = pd.Series(sp500 + russell1000).dropna().unique().tolist()

    # Clean tickers for yfinance
    cleaned = [t.replace(".", "-").upper() for t in tickers]

    return sorted(list(set(cleaned)))


# ------------------ INDICATORS ------------------

def rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    gain_ema = pd.Series(gain, index=series.index).ewm(alpha=1/period, adjust=False).mean()
    loss_ema = pd.Series(loss, index=series.index).ewm(alpha=1/period, adjust=False).mean()

    rs = gain_ema / loss_ema
    return 100 - (100 / (1 + rs))


def atr(df, period=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.rolling(period).mean()


# ------------------ DATA LOADING ------------------

@st.cache_data(show_spinner=True)
def load_data_long_form(tickers, start, end, batch_size=200):
    all_records = []

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]

        raw = yf.download(
            tickers=batch,
            start=start,
            end=end,
            auto_adjust=False,
            progress=False,
            group_by="ticker"
        )

        # Multi-index case
        if isinstance(raw.columns, pd.MultiIndex):
            for t in batch:
                if t not in raw.columns.levels[0]:
                    continue
                df_t = raw[t].copy()
                df_t["Ticker"] = t
                df_t = df_t.reset_index().rename(columns={"Date": "Date"})
                all_records.append(df_t)
        else:
            # Single ticker fallback
            t = batch[0]
            df_t = raw.copy()
            df_t["Ticker"] = t
            df_t = df_t.reset_index().rename(columns={"Date": "Date"})
            all_records.append(df_t)

    if not all_records:
        return pd.DataFrame()

    return pd.concat(all_records, ignore_index=True)


# ------------------ INDICATOR ENGINE ------------------

def compute_indicators(df):
    df = df.sort_values(["Ticker", "Date"]).copy()
    frames = []

    for t, g in df.groupby("Ticker"):
        g = g.copy()
        g["SMA20"] = g["Close"].rolling(20).mean()
        g["SMA50"] = g["Close"].rolling(50).mean()
        g["SMA200"] = g["Close"].rolling(200).mean()
        g["EMA20"] = g["Close"].ewm(span=20, adjust=False).mean()
        g["RSI14"] = rsi(g["Close"])
        g["ATR14"] = atr(g)
        g["ATR_PCT"] = g["ATR14"] / g["Close"]
        g["Vol20"] = g["Volume"].rolling(20).mean()
        frames.append(g)

    return pd.concat(frames, ignore_index=True)


# ------------------ SIGNAL LOGIC ------------------

def evaluate_row(row, prev):
    needed = ["SMA20", "SMA50", "SMA200", "EMA20", "RSI14", "ATR14", "Vol20"]
    if any(math.isnan(row.get(col, np.nan)) for col in needed):
        return 0, False

    close = row["Close"]
    sma20, sma50, sma200 = row["SMA20"], row["SMA50"], row["SMA200"]
    ema20 = row["EMA20"]
    rsi14 = row["RSI14"]
    atr_pct = row["ATR_PCT"]
    vol, vol20 = row["Volume"], row["Vol20"]

    # Trend (incline)
    trend_ok = close > sma20 > sma50 > sma200

    # Pullback
    recent = prev.tail(5)
    pullback_ok = ((recent["Low"] <= recent["EMA20"]) | (recent["Low"] <= recent["SMA20"])).any()

    # Momentum turn
    momentum_ok = False
    if len(recent) >= 3:
        rsi_recent = recent["RSI14"].dropna()
        if len(rsi_recent) >= 3:
            rsi_min = rsi_recent.min()
            rsi_prev = rsi_recent.iloc[-1]
            momentum_ok = (35 <= rsi_min <= 50) and (rsi14 > 45) and (rsi14 > rsi_prev)

    # Volume confirmation
    vol_ok = vol20 > 0 and vol >= 1.2 * vol20

    # ATR sanity
    atr_ok = 0.01 <= atr_pct <= 0.05

    is_setup = trend_ok and pullback_ok and momentum_ok and vol_ok and atr_ok

    score = (
        0.4 * trend_ok +
        0.3 * pullback_ok +
        0.2 * momentum_ok +
        0.1 * vol_ok
    )

    return score, is_setup


def generate_signals(df):
    df = df.sort_values(["Ticker", "Date"]).copy()
    rows = []

    for t, g in df.groupby("Ticker"):
        if len(g) < 60:
            continue
        last = g.iloc[-1]
        prev = g.iloc[:-1]
        score, is_setup = evaluate_row(last, prev)
        last = last.copy()
        last["Score"] = score
        last["IsSetup"] = is_setup
        rows.append(last)

    out = pd.DataFrame(rows)
    return out[out["IsSetup"]].sort_values("Score", ascending=False)


# ------------------ STREAMLIT UI ------------------

def main():
    st.set_page_config(page_title="Swing Scanner", layout="wide")
    st.title("📈 EOD Swing Scanner — Long Only (Buy Low / Sell High)")

    st.write("Scans **1500+ U.S. stocks** for incline + pullback + momentum setups.")

    with st.spinner("Loading universe..."):
        universe_all = load_universe()

    st.sidebar.header("Settings")
    st.sidebar.write(f"Total tickers available: **{len(universe_all)}**")

    max_tickers = st.sidebar.slider(
        "Tickers to scan",
        min_value=100,
        max_value=len(universe_all),
        value=1000,
        step=50
    )

    universe = universe_all[:max_tickers]

    lookback_days = st.sidebar.slider("Lookback days", 120, 365, START_DAYS_BACK)
    start_date = dt.date.today() - dt.timedelta(days=lookback_days)
    end_date = dt.date.today()

    if st.sidebar.button("Run Scan"):
        with st.spinner("Downloading data..."):
            df = load_data_long_form(universe, start_date, end_date)

        if df.empty:
            st.error("No data returned.")
            return

        with st.spinner("Computing indicators..."):
            df_ind = compute_indicators(df)

        with st.spinner("Generating signals..."):
            signals = generate_signals(df_ind)

        st.subheader("Top Buy-Low / Sell-High Candidates")
        st.dataframe(signals[[
            "Ticker", "Date", "Close", "SMA20", "SMA50", "SMA200",
            "EMA20", "RSI14", "ATR_PCT", "Volume", "Vol20", "Score"
        ]], use_container_width=True)

    else:
        st.info("Set your options and click **Run Scan**.")


if __name__ == "__main__":
    main()
