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
        return {}
        
# ============================================================
# PART 4 — SCANNERS & ENGINES (PATCHED)
# ============================================================
def get_active_stocks():
    try:
        data = yf.download(
            tickers=TICKERS[:3000],  # scan more here
            period="2d",
            interval="1d",
            group_by="ticker",
            progress=False
        )

        movers = []

        for t in TICKERS[:1500]:
            try:
                d = data[t]
                if d is None or d.empty or len(d) < 2:
                    continue

                prev_close = d["Close"].iloc[-2]
                last_close = d["Close"].iloc[-1]
                change_pct = (last_close - prev_close) / prev_close * 100
                volume = d["Volume"].iloc[-1]

                # 🔥 KEY: loosen criteria
                if change_pct > 2 and volume > 500000:
                    movers.append(t)

            except:
                continue

        return movers

    except:
        return []
# ---------- Trend Engine (EMA9, EMA20, VWAP) ----------

def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def vwap(df):
    pv = (df["Close"] * df["Volume"]).cumsum()
    vol = df["Volume"].cumsum()
    return pv / vol

def compute_trend_metrics(df):
    if df is None or df.empty:
        return None
    df = df.copy()
    df["EMA9"] = ema(df["Close"], 9)
    df["EMA20"] = ema(df["Close"], 20)
    df["VWAP"] = vwap(df)
    df["TrendStrong"] = (df["EMA9"] > df["EMA20"]) & (df["Close"] > df["VWAP"])
    return df

# ---------- Momentum Score ----------

def compute_momentum_score(df):
    if df is None or df.empty:
        return 0
    last = df.iloc[-1]
    score = 0
    if last["EMA9"] > last["EMA20"]:
        score += 2
    if last["Close"] > last["VWAP"]:
        score += 2
    if len(df) > 3:
        if df["High"].iloc[-1] > df["High"].iloc[-2]:
            score += 1
        if df["High"].iloc[-2] > df["High"].iloc[-3]:
            score += 1
    if len(df) > 5:
        if df["Volume"].iloc[-1] > df["Volume"].iloc[-2]:
            score += 1
    return score

# ---------- New High of Day ----------

def is_new_hod(df):
    if df is None or df.empty:
        return False
    return df["High"].iloc[-1] >= df["High"].max()

# ---------- Core Momentum Scanner (PATCHED) ----------
def run_pro_scanner(interval="1m"):
    st.write(f"🚀 Running PRO Scanner ({interval})…")
    settings = st.session_state.settings

    # ---------------------------
    # STEP 1 — GET ACTIVE STOCKS
    # ---------------------------
    active = get_active_stocks()

    if not active:
        st.warning("No active stocks found")
        return pd.DataFrame()

    st.write(f"Active stocks: {len(active)}")

    # ---------------------------
    # STEP 2 — LOAD DATA
    # ---------------------------
    daily = download_daily_data(active, period="1mo")
    intraday = download_intraday_batches(active, interval=interval, period="1d")

    if daily is None or not intraday:
        return pd.DataFrame()

    st.write(f"Intraday loaded: {len(intraday)}")

    results = []

    # ---------------------------
    # STEP 3 — LOOP
    # ---------------------------
    for ticker in active:

        try:
            d = daily[ticker]
            df = intraday.get(ticker)
        except:
            continue

        if d is None or df is None or df.empty or len(df) < 20:
            continue

        # ---------------------------
        # PRICE FILTER
        # ---------------------------
        price = df["Close"].iloc[-1]
        if price < settings["min_price"] or price > settings["max_price"]:
            continue

        # ---------------------------
        # RVOL
        # ---------------------------
        today_vol = d["Volume"].iloc[-1]
        avg_vol = d["Volume"].iloc[-21:-1].mean() if len(d) > 21 else d["Volume"].mean()
        rvol = compute_rvol(today_vol, avg_vol)

        # 🔥 loosened
        if rvol < 0.8:
            continue

        # ---------------------------
        # INDICATORS
        # ---------------------------
        df = compute_trend_metrics(df)
        if df is None:
            continue

        last = df.iloc[-1]

        # ---------------------------
        # CORE SIGNALS
        # ---------------------------
        ema_trend = last["EMA9"] > last["EMA20"]
        above_vwap = last["Close"] > last["VWAP"]

        # HOD breakout
        hod = df["High"].max()
        near_hod = last["Close"] >= hod * 0.97

        # MICRO PULLBACK (KEY EDGE)
        micro_pullback = (
            last["EMA9"] * 0.995 <= last["Close"] <= last["EMA9"] * 1.02
        )

        # VOLUME SURGE
        vol_spike = df["Volume"].iloc[-1] > df["Volume"].rolling(10).mean().iloc[-1]

        # ---------------------------
        # SCORING SYSTEM (🔥 CORE)
        # ---------------------------
        score = 0

        if ema_trend:
            score += 2
        if above_vwap:
            score += 2
        if near_hod:
            score += 2
        if micro_pullback:
            score += 2
        if vol_spike:
            score += 2

        # ---------------------------
        # FILTER MIN SCORE
        # ---------------------------
        if score < 4:
            continue

        results.append({
            "Ticker": ticker,
            "Price": round(price, 2),
            "RVOL": round(rvol, 2),
            "Score": score,
            "Trend": "Yes" if ema_trend else "No",
            "VWAP Hold": "Yes" if above_vwap else "No",
            "Near HOD": "Yes" if near_hod else "No",
            "Pullback": "Yes" if micro_pullback else "No",
            "Vol Spike": "Yes" if vol_spike else "No",
        })

    if not results:
        return pd.DataFrame()

    df_out = pd.DataFrame(results)
    df_out = df_out.sort_values("Score", ascending=False)
    df_out.reset_index(drop=True, inplace=True)

    return df_out

# ---------- Pullback Scanner (PATCHED) ----------

def run_pullback_scanner(interval="1m"):
    st.write(f"⚡ Running Pullback Scanner ({interval})…")
    settings = st.session_state.settings

    float_pass = [
        t for t in TICKERS
        if passes_float_filter(t, settings["max_float_millions"])
    ]
    if not float_pass:
        return pd.DataFrame()

    intraday = download_intraday_batches(float_pass, interval=interval, period="1d")
    results = []

    for ticker in float_pass:
        df = intraday.get(ticker)
        if df is None or df.empty:
            continue

        last_price = df["Close"].iloc[-1]
        if last_price < settings["min_price"] or last_price > settings["max_price"]:
            continue

        df = compute_trend_metrics(df)
        if df is None:
            continue

        last = df.iloc[-1]

        # Pullback logic
        if last["TrendStrong"] and last["EMA9"] * 0.995 <= last["Close"] <= last["EMA9"] * 1.01:
            results.append({
                "Ticker": ticker,
                "Price": round(last_price, 2),
                "EMA9": round(last["EMA9"], 2),
                "EMA20": round(last["EMA20"], 2),
            })

    if not results:
        return pd.DataFrame()

    out = pd.DataFrame(results)
    out.reset_index(drop=True, inplace=True)
    return out

def run_pullback_1m():
    return run_pullback_scanner(interval="1m")

def run_pullback_5m():
    return run_pullback_scanner(interval="5m")
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
                df = run_momentum_5m()
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
    
