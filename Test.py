import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import pandas_ta as ta

st.set_page_config(page_title="Options Strategy Engine", layout="wide")
st.title("Options Strategy Engine – Semi‑Automated (Level 1)")

# ============================================================
# ===============  DATA FETCH & INDICATOR ENGINE  ============
# ============================================================

def fetch_metrics(ticker: str):
    try:
        data = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if data.empty:
            return None, "No data returned for this ticker."

        df = data.copy()

        # Price
        price = float(df["Close"].iloc[-1])

        # ATR(14)
        atr_series = ta.atr(high=df["High"], low=df["Low"], close=df["Close"], length=14)
        atr = float(atr_series.iloc[-1])

        # RSI(14)
        rsi_series = ta.rsi(df["Close"], length=14)
        rsi = float(rsi_series.iloc[-1])

        # ADX(14)
        adx_series = ta.adx(high=df["High"], low=df["Low"], close=df["Close"], length=14)["ADX_14"]
        adx = float(adx_series.iloc[-1])

        # Bollinger Bands (20, 2)
        bb = ta.bbands(df["Close"], length=20, std=2)
        bbl = float(bb["BBL_20_2.0"].iloc[-1])
        bbh = float(bb["BBU_20_2.0"].iloc[-1])

        # Approx VWAP (daily)
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        vwap = float((tp * df["Volume"]).cumsum() / df["Volume"].cumsum()).iloc[-1]

        # BB position
        if bbh != bbl:
            bb_pos = (price - bbl) / (bbh - bbl)
        else:
            bb_pos = 0.5

        metrics = {
            "price": price,
            "rsi": rsi,
            "adx": adx,
            "atr": atr,
            "vwap": vwap,
            "bbh": bbh,
            "bbl": bbl,
            "bb_pos": bb_pos,
        }
        return metrics, None
    except Exception as e:
        return None, str(e)
# ============================================================
# ===============  STRATEGY CLASSIFIER (ENTRY)  ==============
# ============================================================

def classify_strategy(price, rsi, adx, ivr, vwap, bb_pos, atr):
    if (45 <= rsi <= 55 and
        adx < 20 and
        30 <= ivr <= 60 and
        0.30 <= bb_pos <= 0.70 and
        abs(price - vwap) <= atr):
        return "CALENDAR SPREAD", "Neutral: RSI 45–55, ADX < 20, IVR medium, price near VWAP."

    if (55 <= rsi <= 65 and
        18 <= adx <= 25 and
        ivr <= 35 and
        price > vwap and
        0.55 <= bb_pos <= 0.75):
        return "BULL CALL DEBIT SPREAD", "Mild bullish: RSI 55–65, ADX 18–25, low IVR, price above VWAP."

    if (35 <= rsi <= 45 and
        18 <= adx <= 25 and
        ivr <= 40 and
        price < vwap and
        0.25 <= bb_pos <= 0.45):
        return "BEAR PUT DEBIT SPREAD", "Mild bearish: RSI 35–45, ADX 18–25, low IVR, price below VWAP."

    if (50 <= rsi <= 60 and
        15 <= adx <= 25 and
        ivr <= 35 and
        0.45 <= bb_pos <= 0.65):
        return "DIAGONAL SPREAD", "Slight trend with low IV: RSI 50–60, ADX 15–25, low IVR."

    return "NO TRADE", "Environment does not match any high‑probability setup."

# ============================================================
# ==================  EXIT ENGINES  ==========================
# ============================================================

def decide_bull_call_exit(price, rsi, adx, ivr, vwap, bb_pos, pnl_pct):
    if pnl_pct <= -30:
        return "EXIT: Stop loss hit (≤ -30%)"
    if pnl_pct >= 25:
        return "EXIT: Take profit (≥ +25%)"
    if pnl_pct > 0:
        if rsi > 65:
            return "EXIT: Take profit early (RSI > 65)"
        if adx > 25:
            return "EXIT: Take profit early (ADX > 25)"
        if price < vwap:
            return "EXIT: Take profit early (price < VWAP)"
        if bb_pos >= 0.9:
            return "EXIT: Take profit early (near upper Bollinger Band)"
    if (50 <= rsi <= 60 and
        18 <= adx <= 23 and
        price > vwap and
        0.55 <= bb_pos <= 0.75):
        return "HOLD: Ideal environment for bull call spread."
    return "HOLD: No exit signal, but environment not ideal."

def decide_calendar_exit(price, rsi, adx, ivr, vwap, bb_pos, pnl_pct):
    if pnl_pct <= -30:
        return "EXIT: Stop loss hit (≤ -30%)"
    if pnl_pct >= 25:
        return "EXIT: Take profit (≥ +25%)"
    if rsi > 60:
        return "EXIT: RSI > 60 (trend forming)"
    if rsi < 40:
        return "EXIT: RSI < 40 (trend forming)"
    if adx > 25:
        return "EXIT: ADX > 25 (trend forming)"
    if price > vwap + 2:
        return "EXIT: Price breaking above VWAP"
    if price < vwap - 2:
        return "EXIT: Price breaking below VWAP"
    if (45 <= rsi <= 55 and
        adx < 20 and
        0.30 <= bb_pos <= 0.70):
        return "HOLD: Ideal neutral environment for calendar."
    return "HOLD: No exit signal, but environment not ideal."
# ============================================================
# ==================  SIDEBAR: TICKER & FETCH  ===============
# ============================================================

st.sidebar.header("Data Source")
ticker = st.sidebar.text_input("Ticker", value="COST")
auto_fetch = st.sidebar.button("Fetch latest metrics")

if "metrics" not in st.session_state:
    st.session_state.metrics = None
if "fetch_error" not in st.session_state:
    st.session_state.fetch_error = None

if auto_fetch:
    metrics, err = fetch_metrics(ticker)
    st.session_state.metrics = metrics
    st.session_state.fetch_error = err

if st.session_state.fetch_error:
    st.sidebar.error(f"Fetch error: {st.session_state.fetch_error}")
elif st.session_state.metrics:
    m = st.session_state.metrics
    st.sidebar.success("Metrics fetched")
    st.sidebar.write(
        f"Price: {m['price']:.2f}\n\n"
        f"RSI: {m['rsi']:.2f}\n\n"
        f"ADX: {m['adx']:.2f}\n\n"
        f"ATR: {m['atr']:.2f}\n\n"
        f"VWAP: {m['vwap']:.2f}\n\n"
        f"BBL: {m['bbl']:.2f}\n\n"
        f"BBH: {m['bbh']:.2f}\n\n"
        f"BB Pos: {m['bb_pos']:.2f}"
    )

tabs = st.tabs(["Strategy Entry Engine", "Bull Call Exit Engine", "Calendar Exit Engine"])

# ============================================================
# ==================  TAB 1: ENTRY ENGINE  ===================
# ============================================================

with tabs[0]:
    st.header("Strategy Entry Engine")

    base = st.session_state.metrics or {
        "price": 999.66,
        "rsi": 56.36,
        "adx": 20.60,
        "atr": 5.78,
        "vwap": 997.99,
        "bbh": 1008.88,
        "bbl": 980.90,
        "bb_pos": 0.6,
    }

    col1, col2 = st.columns(2)
    with col1:
        e_price = st.number_input("Underlying Price", value=float(base["price"]), step=0.1)
        e_rsi = st.number_input("RSI", value=float(base["rsi"]), step=0.1)
        e_adx = st.number_input("ADX", value=float(base["adx"]), step=0.1)
        e_ivr = st.number_input("IVR (manual)", value=30.0, step=1.0)
    with col2:
        e_vwap = st.number_input("VWAP", value=float(base["vwap"]), step=0.1)
        e_bbh = st.number_input("BB High", value=float(base["bbh"]), step=0.1)
        e_bbl = st.number_input("BB Low", value=float(base["bbl"]), step=0.1)
        e_atr = st.number_input("ATR", value=float(base["atr"]), step=0.1)

    if e_bbh != e_bbl:
        e_bb_pos = (e_price - e_bbl) / (e_bbh - e_bbl)
    else:
        e_bb_pos = 0.5

    st.markdown(f"**BB Position (0–1):** `{e_bb_pos:.2f}`")

    if st.button("Classify Strategy"):
        strat, reason = classify_strategy(e_price, e_rsi, e_adx, e_ivr, e_vwap, e_bb_pos, e_atr)
        st.subheader("Recommended Strategy")
        st.success(strat)
        st.subheader("Reason")
        st.write(reason)

# ============================================================
# ============  TAB 2: BULL CALL EXIT ENGINE  ================
# ============================================================

with tabs[1]:
    st.header("Bull Call Debit Spread – Exit Engine")

    base = st.session_state.metrics or {
        "price": 999.66,
        "rsi": 56.36,
        "adx": 20.60,
        "atr": 5.78,
        "vwap": 997.99,
        "bbh": 1008.88,
        "bbl": 980.90,
        "bb_pos": 0.6,
    }

    col1, col2 = st.columns(2)
    with col1:
        bc_price = st.number_input("Underlying Price", value=float(base["price"]), step=0.1)
        bc_rsi = st.number_input("RSI", value=float(base["rsi"]), step=0.1)
        bc_adx = st.number_input("ADX", value=float(base["adx"]), step=0.1)
        bc_ivr = st.number_input("IVR (manual)", value=23.0, step=1.0)
    with col2:
        bc_vwap = st.number_input("VWAP", value=float(base["vwap"]), step=0.1)
        bc_bbh = st.number_input("BB High", value=float(base["bbh"]), step=0.1)
        bc_bbl = st.number_input("BB Low", value=float(base["bbl"]), step=0.1)
        bc_pnl = st.number_input("Current P/L % on Spread", value=16.0, step=1.0)

    if bc_bbh != bc_bbl:
        bc_bb_pos = (bc_price - bc_bbl) / (bc_bbh - bc_bbl)
    else:
        bc_bb_pos = 0.5

    st.markdown(f"**BB Position (0–1):** `{bc_bb_pos:.2f}`")

    if st.button("Evaluate Bull Call Exit"):
        decision = decide_bull_call_exit(bc_price, bc_rsi, bc_adx, bc_ivr, bc_vwap, bc_bb_pos, bc_pnl)
        st.subheader("Decision")
        st.success(decision)

# ============================================================
# ============  TAB 3: CALENDAR EXIT ENGINE  =================
# ============================================================

with tabs[2]:
    st.header("Calendar Spread – Exit Engine")

    base = st.session_state.metrics or {
        "price": 331.15,
        "rsi": 53.91,
        "adx": 20.0,
        "atr": 4.0,
        "vwap": 330.50,
        "bbh": 334.50,
        "bbl": 325.55,
        "bb_pos": 0.5,
    }

    col1, col2 = st.columns(2)
    with col1:
        cal_price = st.number_input("Underlying Price", value=float(base["price"]), step=0.1)
        cal_rsi = st.number_input("RSI", value=float(base["rsi"]), step=0.1)
        cal_adx = st.number_input("ADX", value=float(base["adx"]), step=0.1)
        cal_ivr = st.number_input("IVR (manual)", value=62.0, step=1.0)
    with col2:
        cal_vwap = st.number_input("VWAP", value=float(base["vwap"]), step=0.1)
        cal_bbh = st.number_input("BB High", value=float(base["bbh"]), step=0.1)
        cal_bbl = st.number_input("BB Low", value=float(base["bbl"]), step=0.1)
        cal_pnl = st.number_input("Current P/L % on Calendar", value=-5.0, step=1.0)

    if cal_bbh != cal_bbl:
        cal_bb_pos = (cal_price - cal_bbl) / (cal_bbh - cal_bbl)
    else:
        cal_bb_pos = 0.5

    st.markdown(f"**BB Position (0–1):** `{cal_bb_pos:.2f}`")

    if st.button("Evaluate Calendar Exit"):
        decision = decide_calendar_exit(cal_price, cal_rsi, cal_adx, cal_ivr, cal_vwap, cal_bb_pos, cal_pnl)
        st.subheader("Decision")
        st.success(decision)
