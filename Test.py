# ============================================================
# PART 1 — IMPORTS & UNIVERSE
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import datetime as dt
from functools import lru_cache

# ---------- Universe from CSV ----------

UNIVERSE_CSV = "tickers.csv"   # <--- change if needed
UNIVERSE_COL = "Symbol"        # <--- change if needed

@st.cache_data
def load_universe():
    try:
        df = pd.read_csv(UNIVERSE_CSV)
        tickers = df[UNIVERSE_COL].dropna().astype(str).unique().tolist()
        # Basic cleaning: remove weird symbols
        tickers = [t.strip().upper() for t in tickers if t.strip().isalpha()]
        return tickers
    except Exception as e:
        st.error(f"Failed to load universe from {UNIVERSE_CSV}: {e}")
        return []

TICKERS = load_universe()
# ============================================================
# PART 2 — SETTINGS
# ============================================================

def init_settings():
    if "settings" not in st.session_state:
        st.session_state.settings = {
            "min_price": 2.0,
            "max_price": 20.0,
            "min_rvol": 1.2,
            "max_float_millions": 50.0,
            "gap_min_pct": 5.0,
            "require_catalyst": False,  # placeholder
        }

def settings_panel():
    settings = st.session_state.settings
    st.sidebar.header("Scanner Settings")

    settings["min_price"] = st.sidebar.number_input("Min Price", 0.5, 100.0, settings["min_price"], 0.5)
    settings["max_price"] = st.sidebar.number_input("Max Price", 1.0, 200.0, settings["max_price"], 0.5)
    settings["min_rvol"] = st.sidebar.number_input("Min RVOL", 1.0, 20.0, settings["min_rvol"], 0.5)
    settings["max_float_millions"] = st.sidebar.number_input("Max Float (M)", 1.0, 500.0, settings["max_float_millions"], 1.0)
    settings["gap_min_pct"] = st.sidebar.number_input("Min Gap %", 1.0, 100.0, settings["gap_min_pct"], 1.0)
    settings["require_catalyst"] = st.sidebar.checkbox("Require Catalyst (placeholder)", value=settings["require_catalyst"])
# ============================================================
# PART 3 — DATA LOADERS, FLOAT, RVOL
# ============================================================

# ---------- Float filter (placeholder: random-ish / demo) ----------

@lru_cache(maxsize=4096)
def get_float_millions(ticker: str) -> float:
    # In production, replace with real float API
    # For now, approximate using market cap / price if available
    try:
        info = yf.Ticker(ticker).info
        shares = info.get("sharesOutstanding", None)
        if shares is None:
            return 1000.0  # treat as large float
        return shares / 1_000_000.0
    except Exception:
        return 1000.0

def passes_float_filter(ticker: str, max_float_millions: float) -> bool:
    f = get_float_millions(ticker)
    return f <= max_float_millions

# ---------- Daily data & RVOL ----------

@st.cache_data
def download_daily_data(tickers, period="1mo"):
    try:
        data = yf.download(
            tickers=tickers,
            period=period,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False
        )
        return data
    except Exception:
        return None

def compute_rvol(today_volume, avg20_volume):
    if avg20_volume is None or avg20_volume == 0:
        return 0.0
    return today_volume / avg20_volume

# ---------- Intraday batch loader ----------
@st.cache_data
def download_intraday_batches(tickers, interval="1m", period="1d"):
    try:
        data = yf.download(
            tickers=tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False
        )

        result = {}

        # MULTI-TICKER CASE
        if isinstance(data.columns, pd.MultiIndex):
            for t in tickers:
                if t in data.columns.get_level_values(0):

                    df_t = data[t].copy()

                    # Only require Close (DON'T drop everything)
                    df_t = df_t[df_t["Close"].notna()]

                    if df_t.empty:
                        continue

                    df_t.index = df_t.index.tz_localize(None)
                    result[t] = df_t

        # SINGLE TICKER CASE
        else:
            df_t = data.copy()
            df_t = df_t[df_t["Close"].notna()]

            if not df_t.empty and len(tickers) == 1:
                df_t.index = df_t.index.tz_localize(None)
                result[tickers[0]] = df_t

        return result

    except Exception as e:
        st.write("Intraday download error:", e)
        
# ============================================================
# PART 4 — SCANNERS (CLEAN + ENTRY / EXIT SYSTEM)
# ============================================================

# ---------- ACTIVE STOCKS ----------
def get_active_stocks():
    try:
        data = yf.download(
            tickers=TICKERS[:1000],
            period="2d",
            interval="1d",
            group_by="ticker",
            progress=False
        )

        movers = []

        for t in TICKERS[:1000]:
            try:
                d = data[t]
                if d is None or d.empty or len(d) < 2:
                    continue

                change_pct = (d["Close"].iloc[-1] - d["Close"].iloc[-2]) / d["Close"].iloc[-2] * 100
                vol = d["Volume"].iloc[-1]

                if change_pct > 1 and vol > 300000:
                    movers.append(t)

            except:
                continue

        return movers

    except:
        return []


# ---------- INDICATORS ----------
def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def vwap(df):
    return (df["Close"] * df["Volume"]).cumsum() / df["Volume"].cumsum()

def compute_trend_metrics(df):
    if df is None or df.empty:
        return None

    df = df.copy()
    df["EMA9"] = ema(df["Close"], 9)
    df["EMA20"] = ema(df["Close"], 20)
    df["VWAP"] = vwap(df)
    return df


# ============================================================
# 🔥 ENTRY / EXIT SIGNAL ENGINE
# ============================================================

def entry_exit_signals(df):
    last = df.iloc[-1]

    entry = False
    exit_signal = False

    # ENTRY CONDITIONS
    if (
        last["EMA9"] > last["EMA20"] and
        last["Close"] > last["VWAP"] and
        df["Volume"].iloc[-1] > df["Volume"].rolling(10).mean().iloc[-1]
    ):
        entry = True

    # EXIT CONDITIONS
    if (
        last["EMA9"] < last["EMA20"] or
        last["Close"] < last["VWAP"]
    ):
        exit_signal = True

    return entry, exit_signal


# ============================================================
# 🚀 PRO SCANNER
# ============================================================

def run_pro_scanner(interval="1m"):
    st.write(f"🚀 Running PRO Scanner ({interval})…")
    settings = st.session_state.settings

    active = get_active_stocks()
    if not active:
        return pd.DataFrame()

    daily = download_daily_data(active, period="1mo")
    intraday = download_intraday_batches(active, interval=interval, period="1d")

    if daily is None or not intraday:
        return pd.DataFrame()

    results = []

    for ticker in active:
        try:
            d = daily[ticker]
            df = intraday.get(ticker)
        except:
            continue

        if d is None or df is None or df.empty or len(df) < 20:
            continue

        price = df["Close"].iloc[-1]

        if price < settings["min_price"] or price > settings["max_price"]:
            continue

        # RVOL
        today_vol = d["Volume"].iloc[-1]
        avg_vol = d["Volume"].iloc[-21:-1].mean() if len(d) > 21 else d["Volume"].mean()
        rvol = today_vol / avg_vol if avg_vol else 0

        if rvol < 0.5:
            continue

        df = compute_trend_metrics(df)
        if df is None:
            continue

        entry, exit_signal = entry_exit_signals(df)

        last = df.iloc[-1]

        score = 0
        if last["EMA9"] > last["EMA20"]:
            score += 2
        if last["Close"] > last["VWAP"]:
            score += 2

        near_hod = last["Close"] >= df["High"].max() * 0.95
        if near_hod:
            score += 2

        vol_spike = df["Volume"].iloc[-1] > df["Volume"].rolling(10).mean().iloc[-1]
        if vol_spike:
            score += 2

        if score < 4:
            continue

        results.append({
            "Ticker": ticker,
            "Price": round(price, 2),
            "RVOL": round(rvol, 2),
            "Score": score,
            "ENTRY": "YES" if entry else "—",
            "EXIT": "YES" if exit_signal else "—",
            "Trend": "Bullish" if last["EMA9"] > last["EMA20"] else "Bearish"
        })

    return pd.DataFrame(results)


# ============================================================
# ⚡ GAP SCANNER
# ============================================================

def run_gap_scanner():
    st.write("⚡ Running Gap Scanner…")

    daily = download_daily_data(TICKERS, period="5d")
    if daily is None:
        return pd.DataFrame()

    results = []

    for ticker in TICKERS:
        try:
            d = daily[ticker]
        except:
            continue

        if d is None or len(d) < 2:
            continue

        gap_pct = (d["Close"].iloc[-1] - d["Close"].iloc[-2]) / d["Close"].iloc[-2] * 100

        if gap_pct < st.session_state.settings["gap_min_pct"]:
            continue

        results.append({
            "Ticker": ticker,
            "Price": round(d["Close"].iloc[-1], 2),
            "Gap %": round(gap_pct, 2),
            "ENTRY": "YES" if gap_pct > 5 else "WATCH"
        })

    return pd.DataFrame(results)


# ============================================================
# 🔁PULLBACK SCANNER
# ============================================================

def run_pullback_scanner(interval="1m"):
    st.write(f"⚡ Running Pullback Scanner ({interval})…")

    active = get_active_stocks()
    if not active:
        return pd.DataFrame()

    intraday = download_intraday_batches(active[:300], interval=interval, period="1d")

    results = []

    for ticker, df in intraday.items():

        if df is None or len(df) < 20:
            continue

        df = compute_trend_metrics(df)
        if df is None:
            continue

        entry, exit_signal = entry_exit_signals(df)

        last = df.iloc[-1]

        pullback = (
            last["EMA9"] * 0.98 <= last["Close"] <= last["EMA9"] * 1.02
        )

        if last["EMA9"] > last["EMA20"] and pullback:
            results.append({
                "Ticker": ticker,
                "Price": round(last["Close"], 2),
                "ENTRY": "YES" if entry else "—",
                "EXIT": "YES" if exit_signal else "—"
            })

    return pd.DataFrame(results)


def run_pullback_1m():
    return run_pullback_scanner("1m")

def run_pullback_5m():
    return run_pullback_scanner("5m")
# ============================================================
# PART 5 — UI HELPERS
# ============================================================

def render_results_table(df, title: str):
    st.subheader(title)
    if df is None or df.empty:
        st.info("No setups found.")
        return
    st.dataframe(df, use_container_width=True)

def render_summary(df, label: str):
    if df is None or df.empty:
        st.write(f"{label}: 0 results")
    else:
        st.write(f"{label}: {len(df)} results")
# ============================================================
# PART 6 — MAIN UI
# ============================================================

def main():
    st.set_page_config(page_title="Full Market Scanner", layout="wide")
    init_settings()
    settings_panel()

    st.title("Full U.S. Market Scanner")
    st.caption("Momentum • Gap • Pullback — batch-based, Ross-style logic")

    tab1, tab2, tab3, tab4 = st.tabs(["Momentum", "Gap", "Pullback", "Debug"])

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Run Momentum 1m"):
                df = run_pro_scanner("1m")
                render_summary(df, "Momentum 1m")
                render_results_table(df, "Momentum 1m Results")
        with col2:
            if st.button("Run Momentum 5m"):
                df = run_pro_scanner("5m")
                render_summary(df, "Momentum 5m")
                render_results_table(df, "Momentum 5m Results")

    with tab2:
        if st.button("Run Gap Scanner"):
            df = run_gap_scanner()
            render_summary(df, "Gap Scanner")
            render_results_table(df, "Gap Scanner Results")

    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Run Pullback 1m"):
                df = run_pullback_1m()
                render_summary(df, "Pullback 1m")
                render_results_table(df, "Pullback 1m Results")
        with col2:
            if st.button("Run Pullback 5m"):
                df = run_pullback_5m()
                render_summary(df, "Pullback 5m")
                render_results_table(df, "Pullback 5m Results")

    with tab4:
        st.write("Universe size:", len(TICKERS))
        st.write("Universe sample:", TICKERS[:50])

if __name__ == "__main__":
    main()
    