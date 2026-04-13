# app.py
# -----------------------------------------
# Simple EOD swing-trade scanner:
# - U.S. stocks
# - Long-only
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

# TODO: Replace this with your full universe:
# e.g., S&P 500 + mid-caps + Russell 1000 tickers from a file or API.
UNIVERSE_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "UNH", "XOM",
    "HD", "PG", "V", "MA", "AVGO", "LLY", "PEP", "COST", "ABBV", "MRK"
]

START_DAYS_BACK = 250  # ~1 year of data
MIN_PRICE = 10
MAX_PRICE = 200
MIN_AVG_VOLUME = 1_000_000
MIN_MARKET_CAP = 2_000_000_000  # 2B


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
def load_data(tickers, start, end):
    data = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        group_by="ticker"
    )
    return data


def flatten_yf_data(raw, tickers):
    """
    yfinance returns a multi-index DataFrame when multiple tickers are used.
    This flattens it into a long DataFrame with columns:
    ['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']
    """
    records = []
    for t in tickers:
        if t not in raw.columns.levels[0]:
            continue
        df_t = raw[t].copy()
        df_t["Ticker"] = t
        df_t = df_t.reset_index().rename(columns={"Date": "Date"})
        records.append(df_t)
    if not records:
        return pd.DataFrame()
    out = pd.concat(records, ignore_index=True)
    return out


# ------------- UNIVERSE FILTERS --------------------

def filter_universe(df: pd.DataFrame) -> pd.DataFrame:
    # Use last row per ticker to filter by price, volume, etc.
    latest = df.sort_values("Date").groupby("Ticker").tail(1)

    # Price filter
    price_mask = (latest["Close"] >= MIN_PRICE) & (latest["Close"] <= MAX_PRICE)

    # Volume filter (20d avg)
    vol_20 = (
        df.sort_values("Date")
        .groupby("Ticker")["Volume"]
        .rolling(20)
        .mean()
        .reset_index()
        .rename(columns={"Volume": "Vol20"})
    )
    df = df.merge(vol_20, on=["Ticker", "level_1"], how="left") if "level_1" in vol_20.columns else df

    # Recompute latest with Vol20 if needed
    latest = df.sort_values("Date").groupby("Ticker").tail(1)
    vol_mask = latest["Volume"].rolling(20).mean() >= MIN_AVG_VOLUME if "Vol20" not in latest.columns else latest["Vol20"] >= MIN_AVG_VOLUME

    # Market cap filter (approx via yfinance info)
    # For simplicity, we skip strict market cap filtering here.
    # You can pre-filter your universe externally by market cap.

    keep_tickers = latest[price_mask & vol_mask]["Ticker"].unique()
    return df[df["Ticker"].isin(keep_tickers)].copy()


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
    Apply your long-only, incline + pullback + momentum rules
    to the latest row for a ticker.
    """
    # Require enough history
    if any(math.isnan(row.get(col, np.nan)) for col in ["SMA20", "SMA50", "SMA200", "RSI14", "ATR14", "Vol20"]):
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

    # Trend filter: incline
    trend_ok = (close > sma20) and (sma20 > sma50) and (sma50 > sma200)

    # Pullback: touched EMA20/SMA20 in last 3–5 days
    recent = prev_rows.tail(5).copy()
    pullback_ok = False
    if not recent.empty:
        # price dipped to or below EMA20/SMA20
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

    # Final "is setup" flag
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
        "Scans U.S. stocks for **uptrends with pullbacks and momentum turning up**. "
        "Educational use only — not financial advice."
    )

    # Sidebar controls
    st.sidebar.header("Settings")
    max_tickers = st.sidebar.slider("Max tickers to scan", 10, len(UNIVERSE_TICKERS), len(UNIVERSE_TICKERS), step=10)
    universe = UNIVERSE_TICKERS[:max_tickers]

    lookback_days = st.sidebar.slider("Lookback days", 120, 365, START_DAYS_BACK, step=10)
    start_date = dt.date.today() - dt.timedelta(days=lookback_days)
    end_date = dt.date.today()

    st.sidebar.write(f"Scanning {len(universe)} tickers from {start_date} to {end_date}")

    if st.sidebar.button("Run Scan"):
        with st.spinner("Downloading data..."):
            raw = load_data(universe, start_date, end_date)
            if raw.empty:
                st.error("No data returned. Check tickers or date range.")
                return

        df = flatten_yf_data(raw, universe)
        if df.empty:
            st.error("No usable data after flattening.")
            return

        with st.spinner("Filtering universe..."):
            # Simple filter by price/volume using latest data
            df = df.sort_values(["Ticker", "Date"])
            latest = df.groupby("Ticker").tail(1)
            price_mask = (latest["Close"] >= MIN_PRICE) & (latest["Close"] <= MAX_PRICE)
            keep_tickers = latest[price_mask]["Ticker"].unique()
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

            # Chart viewer
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
