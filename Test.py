# app.py
# -----------------------------------------
# EOD Swing-Trade Scanner (Long Only)
# - U.S. stocks (S&P 500 + Russell 1000)
# - Uptrend + pullback + momentum turn
# - Ranks best "buy low, sell high" setups
# -----------------------------------------

import datetime as dt
import math

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


# ------------- CONFIG --------------------

START_DAYS_BACK = 250  # ~1 year of data
MIN_PRICE = 10
MAX_PRICE = 200
MIN_AVG_VOLUME = 1_000_000  # 1M shares


# ------------- UNIVERSE LOADING --------------------

@st.cache_data(show_spinner=True)
def load_universe():
    # S&P 500 symbols
    sp500 = pd.read_csv(
        "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents_symbols.csv"
    )
    sp500_symbols = sp500["Symbol"].dropna().tolist()

    # Russell 1000 symbols
    russell1000 = pd.read_csv(
        "https://raw.githubusercontent.com/datasets/russell-1000/master/data/russell1000.csv"
    )
    russell_symbols = russell1000["Ticker"].dropna().tolist()

    tickers = pd.Series(sp500_symbols + russell_symbols).dropna().unique().tolist()

    # Clean for yfinance (BRK.B -> BRK-B, etc.)
    cleaned = []
    for t in tickers:
        t = str(t).strip().upper()
        t = t.replace(".", "-")
        cleaned.append(t)

    return sorted(list(set(cleaned)))


# ------------- INDICATOR HELPERS --------------------

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    gain_ema = pd.Series(gain, index=series.index).ewm(alpha=1/period, adjust=False).mean()
    loss_ema = pd.Series(loss, index=series.index).ewm(alpha=1/period, adjust=False).mean()

    rs = gain_ema / loss_ema
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ------------- DATA LOADING --------------------

@st.cache_data(show_spinner=True)
def load_data_long_form(tickers, start, end, batch_size=200):
    """
    Downloads OHLCV for many tickers in batches and returns a long-form DataFrame:
    ['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
    """
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

        # If only one ticker, yfinance returns a single-level DF
        if isinstance(raw.columns, pd.MultiIndex):
            for t in batch:
                if t not in raw.columns.levels[0]:
                    continue
                df_t = raw[t].copy()
                df_t["Ticker"] = t
                df_t = df_t.reset_index().rename(columns={"Date": "Date"})
                all_records.append(df_t)
        else:
            # Single ticker case
            t = batch[0]
            df_t = raw.copy()
            df_t["Ticker"] = t
            df_t = df_t.reset_index().rename(columns={"Date": "Date"})
            all_records.append(df_t)

    if not all_records:
        return pd.DataFrame()

    out = pd.concat(all_records, ignore_index=True)
    return out


# ------------- INDICATOR ENGINE --------------------

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["Ticker", "Date"]).copy()

    out_frames = []
    for t, g in df.groupby("Ticker"):
        g = g.copy()
        g["SMA20"] = g["Close"].rolling(20).mean()
        g["SMA50"] = g["Close"].rolling(50).mean()
        g["SMA200"] = g["Close"].rolling(200).mean()
        g["EMA20"] = g["Close"].ewm(span=20, adjust=False).mean()
        g["RSI14"] = rsi(g["Close"], 14)
        g["ATR14"] = atr(g, 14)
        g["ATR_PCT"] = g["ATR14"] / g["Close"]
        g["Vol20"] = g["Volume"].rolling(20).mean()
        out_frames.append(g)

    out = pd.concat(out_frames, ignore_index=True)
    return out


# ------------- SIGNAL + SCORING --------------------

def evaluate_row(row, prev_rows):
    """
    Apply long-only, incline + pullback + momentum rules
    to the latest row for a ticker.
    """
    needed = ["SMA20", "SMA50", "SMA200", "EMA20", "RSI14", "ATR14", "Vol20"]
    if any(math.isnan(row.get(col, np.nan)) for col in needed):
        return 0.0, False

    close = row["Close"]
    sma20 = row["SMA20"]
    sma50 = row["SMA50"]
    sma200 = row["SMA200"]
    ema20 = row["EMA20"]
    rsi14 = row["RSI14"]
    atr_pct = row["ATR_PCT"]
    vol = row["Volume"]
    vol20 = row["Vol20"]

    # Trend filter: stock on the incline
    trend_ok = (close > sma20) and (sma20 > sma50) and (sma50 > sma200)

    # Pullback: touched EMA20/SMA20 in last 3–5 days
    recent = prev_rows.tail(5).copy()
    pullback_ok = False
    if not recent.empty:
        cond = (recent["Low"] <= recent["EMA20"]) | (recent["Low"] <= recent["SMA20"])
        pullback_ok = cond.any()

    # Momentum: RSI rising from 35–50 to >45
    momentum_ok = False
    if len(recent) >= 3:
        rsi_recent = recent["RSI14"].dropna()
        if len(rsi_recent) >= 3:
            rsi_min = rsi_recent.min()
            rsi_prev = rsi_recent.iloc[-1]
            momentum_ok = (35 <= rsi_min <= 50) and (rsi14 > 45) and (rsi14 > rsi_prev)

    # Volume confirmation
    vol_ok = (vol20 is not None) and (vol20 > 0) and (vol >= 1.2 * vol20)

    # ATR sanity: between 1% and 5%
    atr_ok = (atr_pct is not None) and (0.01 <= atr_pct <= 0.05)

    is_setup = trend_ok and pullback_ok and momentum_ok and vol_ok and atr_ok

    # Scoring
    trend_score = 1.0 if trend_ok else 0.0
    pullback_score = 1.0 if pullback_ok else 0.0
    momentum_score = 1.0 if momentum_ok else 0.0
    volume_score = 1.0 if vol_ok else 0.0

    score = 0.4 * trend_score + 0.3 * pullback_score + 0.2 * momentum_score + 0.1 * volume_score

    return score, is_setup


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["Ticker", "Date"]).copy()
    latest_rows = []

    for t, g in df.groupby("Ticker"):
        g = g.copy()
        if len(g) < 60:
            continue
        last = g.iloc[-1]
        prev = g.iloc[:-1]
        score, is_setup = evaluate_row(last, prev)
        last = last.copy()
        last["Score"] = score
        last["IsSetup"] = is_setup
        latest_rows.append(last)

    if not latest_rows:
        return pd.DataFrame()

    out = pd.DataFrame(latest_rows)
    out = out[out["IsSetup"]].sort_values("Score", ascending=False)
    return out


# ------------- STREAMLIT UI --------------------

def main():
    st.set_page_config(page_title="Swing Scanner - Long Only", layout="wide")
    st.title("📈 EOD Swing Scanner (Long Only, Buy Low / Sell High)")

    st.markdown(
        "Scans U.S. stocks (S&P 500 + Russell 1000) for **uptrends with pullbacks and momentum turning up**.\n\n"
        "**Educational use only — not financial advice.**"
    )

    with st.spinner("Loading universe..."):
        universe_all = load_universe()

    st.sidebar.header("Settings")
    max_tickers = st.sidebar.slider(
        "Max tickers to scan",
        min_value=100,
        max_value=len(universe_all),
        value=min(1000, len(universe_all)),
        step=50,
    )
    universe = universe_all[:max_tickers]

    lookback_days = st.sidebar.slider("Lookback days", 120, 365, START_DAYS_BACK, step=10)
    start_date = dt.date.today() - dt.timedelta(days=lookback_days)
    end_date = dt.date.today()

    st.sidebar.write(f"Scanning **{len(universe)}** tickers from {start_date} to {end_date}")

    if st.sidebar.button("Run Scan"):
        with st.spinner("Downloading data in batches..."):
            df = load_data_long_form(universe, start_date, end_date, batch_size=200)
            if df.empty:
                st.error("No data returned. Check tickers or date range.")
                return

        # Basic price + volume filter using latest data
        with st.spinner("Filtering universe by price and volume..."):
            df = df.sort_values(["Ticker", "Date"])
            latest = df.groupby("Ticker").tail(1)

            price_mask = (latest["Close"] >= MIN_PRICE) & (latest["Close"] <= MAX_PRICE)

            # 20d average volume
            vol20 = (
                df.groupby("Ticker")["Volume"]
                .rolling(20)
                .mean()
                .reset_index()
                .rename(columns={"Volume": "Vol20"})
            )
            df = df.reset_index(drop=True)
            df = df.merge(vol20, on=["Ticker", "level_1"], how="left") if "level_1" in vol20.columns else df

            # Recompute latest with Vol20 if merged
            latest = df.sort_values(["Ticker", "Date"]).groupby("Ticker").tail(1)
            if "Vol20" in latest.columns:
                vol_mask = latest["Vol20"] >= MIN_AVG_VOLUME
            else:
                # Fallback: use raw volume
                vol_mask = latest["Volume"].rolling(20).mean() >= MIN_AVG_VOLUME

            keep_tickers = latest[price_mask & vol_mask]["Ticker"].unique()
            df = df[df["Ticker"].isin(keep_tickers)].copy()

        with st.spinner("Computing indicators..."):
            df_ind = compute_indicators(df)

        with st.spinner("Generating signals..."):
            signals = generate_signals(df_ind)

        st.subheader("Top Buy-Low / Sell-High Candidates (Today)")
        if signals.empty:
            st.info("No setups found today with current rules.")
        else:
            show_cols = [
                "Ticker", "Date", "Close", "SMA20", "SMA50", "SMA200",
                "EMA20", "RSI14", "ATR_PCT", "Volume", "Vol20", "Score"
            ]
            st.dataframe(
                signals[show_cols].sort_values("Score", ascending=False).reset_index(drop=True),
                use_container_width=True
            )

            st.subheader("Chart View")
            selected = st.selectbox("Select ticker to view chart", signals["Ticker"].unique())
            if selected:
                g = df_ind[df_ind["Ticker"] == selected].sort_values("Date").copy()
                g["ATR_PCT"] = g["ATR_PCT"] * 100

                c1, c2 = st.columns(2)

                with c1:
                    st.markdown(f"**Price & Moving Averages — {selected}**")
                    price_df = g[["Date", "Close", "SMA20", "SMA50", "SMA200"]].set_index("Date")
                    st.line_chart(price_df)

                with c2:
                    st.markdown("**RSI(14) & ATR%**")
                    rsi_df = g[["Date", "RSI14"]].set_index("Date")
                    st.line_chart(rsi_df)
                    atr_df = g[["Date", "ATR_PCT"]].set_index("Date")
                    st.line_chart(atr_df)
    else:
        st.info("Set your options in the sidebar and click **Run Scan** to start.")


if __name__ == "__main__":
    main()
