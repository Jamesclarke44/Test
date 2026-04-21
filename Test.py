import streamlit as st
import pandas as pd
import yfinance as yf
import json
import os
import math
import numpy as np
from datetime import datetime, timedelta

from ta.trend import ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice

st.set_page_config(page_title="Options Engine V6 Stable", layout="centered")

TRADES_FILE = "trades.json"

# ----------------- GLOBAL SAFETY SWITCH -----------------
# Set to True if you want to actually hit Yahoo options endpoints.
# Default False to avoid YFRateLimitError and keep the app stable.
ENABLE_OPTIONS = False

# ----------------- SAFE STORAGE -----------------

def load_trades():
    if not os.path.exists(TRADES_FILE):
        return []
    try:
        with open(TRADES_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_trades(trades):
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2)

def add_trade(trade):
    trades = load_trades()
    trades.append(trade)
    save_trades(trades)

def remove_trade(index):
    trades = load_trades()
    if 0 <= index < len(trades):
        trades.pop(index)
        save_trades(trades)

# ----------------- DATA -----------------

@st.cache_data(ttl=3600)
def get_data(ticker):
    return yf.download(ticker, period="6mo", interval="1d", progress=False)

@st.cache_data
def load_universe():
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
    df = pd.read_csv(url)
    return df["Symbol"].tolist()

# ----------------- INDICATORS -----------------

def compute_indicators(df):
    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna()

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    df["RSI"] = RSIIndicator(close=close).rsi()
    df["ADX"] = ADXIndicator(high=high, low=low, close=close).adx()
    df["ATR"] = AverageTrueRange(high=high, low=low, close=close).average_true_range()

    bb = BollingerBands(close=close)
    df["BB_High"] = bb.bollinger_hband()
    df["BB_Low"] = bb.bollinger_lband()

    df["VWAP"] = VolumeWeightedAveragePrice(
        high=high, low=low, close=close, volume=volume
    ).volume_weighted_average_price()

    df["BB_Width"] = (df["BB_High"] - df["BB_Low"]) / df["Close"]

    df = compute_iv_proxy(df)

    return df

# ----------------- IV ENGINE -----------------

def compute_iv_proxy(df):
    df["ATR_PCT"] = df["ATR"] / df["Close"] * 100

    iv_min = df["ATR_PCT"].rolling(100).min()
    iv_max = df["ATR_PCT"].rolling(100).max()

    df["IV_Rank"] = ((df["ATR_PCT"] - iv_min) / (iv_max - iv_min)) * 100
    df["IV_Rank"] = df["IV_Rank"].fillna(50)

    return df

def volatility_regime(iv_rank):
    if iv_rank < 30:
        return "LOW"
    elif iv_rank > 70:
        return "HIGH"
    else:
        return "NORMAL"

def select_strategy(iv_rank, prob):
    regime = volatility_regime(iv_rank)

    if regime == "LOW" and prob >= 70:
        return "Calendar"
    elif regime == "HIGH" and prob >= 60:
        return "Credit Spread"
    elif regime == "NORMAL" and prob >= 75:
        return "Calendar"
    else:
        return "No Trade"

# ----------------- SCORING -----------------

def score_setup(rsi, adx, atr_pct, vwap_drift, bb_width):
    score = 0
    if 40 <= rsi <= 60: score += 1
    if adx < 20: score += 1
    if atr_pct < 2.5: score += 1
    if vwap_drift < 0.01: score += 1
    if bb_width < 0.05: score += 2
    return score

def probability(score):
    return int((score / 6) * 100)

# ----------------- OPTIONS ENGINE -----------------

def get_expirations(ticker):
    # Hard safety: if options are disabled, never hit Yahoo options endpoint.
    if not ENABLE_OPTIONS:
        return []
    try:
        tk = yf.Ticker(ticker)
        return tk.options or []
    except Exception:
        return []

def get_chain(ticker, expiry):
    if not ENABLE_OPTIONS:
        return None, None
    try:
        tk = yf.Ticker(ticker)
        chain = tk.option_chain(expiry)
        return chain.calls, chain.puts
    except Exception:
        return None, None

def find_atm(df, price):
    df = df.copy()
    df["dist"] = abs(df["strike"] - price)
    return df.sort_values("dist").iloc[0]["strike"]

def build_calendar(ticker, price):
    exps = get_expirations(ticker)
    if not exps or len(exps) < 2:
        return None

    front = exps[0]
    back = exps[min(3, len(exps)-1)]

    calls_f, _ = get_chain(ticker, front)
    calls_b, _ = get_chain(ticker, back)

    if calls_f is None or calls_f.empty:
        return None

    strike = find_atm(calls_f, price)

    return {
        "type": "Calendar Spread",
        "strike": float(strike),
        "front_exp": front,
        "back_exp": back
    }

def build_credit_spread(ticker, price):
    exps = get_expirations(ticker)
    if not exps:
        return None

    expiry = exps[0]

    calls, puts = get_chain(ticker, expiry)
    if calls is None or calls.empty:
        return None

    calls = calls.sort_values("strike")
    otm = calls[calls["strike"] > price]

    if len(otm) < 2:
        return None

    short = otm.iloc[0]["strike"]
    long = otm.iloc[1]["strike"]

    return {
        "type": "Call Credit Spread",
        "short_strike": float(short),
        "long_strike": float(long),
        "expiry": expiry
    }

def build_trade(row):
    if row["Strategy"] == "Calendar":
        return build_calendar(row["Ticker"], row["Price"])
    elif row["Strategy"] == "Credit Spread":
        return build_credit_spread(row["Ticker"], row["Price"])
    return None

# ----------------- GREEKS -----------------

def estimate_delta(price, strike, iv_rank):
    m = (price - strike) / price
    return round(np.tanh(m * 5) * (1 + iv_rank / 100), 2)

def estimate_theta(dte, iv_rank):
    if dte <= 0:
        return -1
    return round(-(1 / math.sqrt(dte)) * (1 + iv_rank / 100), 2)

def estimate_vega(price, atr_pct, iv_rank):
    return round((atr_pct * 0.5) * (iv_rank / 50), 2)

# ----------------- SCAN -----------------

def scan_universe(tickers):
    results = []

    for t in tickers[:50]:
        try:
            df = get_data(t)
            if df.empty:
                continue

            df = compute_indicators(df)
            last = df.iloc[-1]

            price = last["Close"]
            rsi = last["RSI"]
            adx = last["ADX"]
            atr = last["ATR"]
            vwap = last["VWAP"]
            bb_width = last["BB_Width"]
            iv_rank = last["IV_Rank"]

            atr_pct = (atr / price) * 100
            vwap_drift = abs(price - vwap) / price

            score = score_setup(rsi, adx, atr_pct, vwap_drift, bb_width)
            prob = probability(score)

            regime = volatility_regime(iv_rank)
            strategy = select_strategy(iv_rank, prob)

            if strategy != "No Trade":
                results.append({
                    "Ticker": t,
                    "Price": round(price, 2),
                    "Probability %": prob,
                    "IV Rank": round(iv_rank, 1),
                    "Regime": regime,
                    "Strategy": strategy
                })

        except:
            continue

    return pd.DataFrame(results)

# ----------------- SAFE REPORT (FIXED CRASH) -----------------

def trade_report(trade):
    df = get_data(trade["ticker"])
    if df.empty:
        return {}

    df = compute_indicators(df)
    last = df.iloc[-1]

    price = last["Close"]
    atr = last["ATR"]
    iv_rank = last["IV_Rank"]

    entry = trade.get("price_at_entry", price)
    pnl = ((price - entry) / entry) * 100 if entry else 0

    strike = trade.get("strike")
    strike = float(strike) if strike is not None else price

    expiry = trade.get("front_exp") or trade.get("expiry")

    if expiry:
        try:
            dte = (datetime.strptime(expiry, "%Y-%m-%d").date()
                   - datetime.today().date()).days
        except:
            dte = 0
    else:
        dte = 0

    delta = estimate_delta(price, strike, iv_rank)
    theta = estimate_theta(dte, iv_rank)
    vega = estimate_vega(price, (atr / price) * 100, iv_rank)

    return {
        "Price": round(price, 2),
        "PnL %": round(pnl, 2),
        "IV Rank": round(iv_rank, 1),
        "Delta": delta,
        "Theta": theta,
        "Vega": vega,
        "DTE": dte
    }

# ----------------- EXIT -----------------

def evaluate_exit(trade):
    report = trade_report(trade)
    if not report:
        return "UNKNOWN"

    score = 0
    if report["DTE"] <= 3:
        score += 2
    if abs(report["Delta"]) > 0.85:
        score += 2

    if score >= 3:
        return "EXIT"
    elif score == 2:
        return "WATCH"
    else:
        return "HOLD"

# ----------------- UI -----------------

st.title("🧠 Options Engine V6 Stable")

tab1, tab2, tab3 = st.tabs(["Scan", "Trades", "Exit"])

# ---------- SCAN ----------
with tab1:

    if st.button("Run Scan"):
        df = scan_universe(load_universe())
        st.session_state["scan"] = df

    if "scan" in st.session_state:
        df = st.session_state["scan"]

        st.dataframe(df.sort_values("Probability %", ascending=False))

        st.subheader("🔥 Build Trades")

        for i, row in df.head(5).iterrows():

            if st.button(f"Build {row['Ticker']}", key=f"b{i}"):

                trade_plan = build_trade(row)

                if trade_plan:
                    st.success("Trade Built")

                    for k, v in trade_plan.items():
                        st.write(f"{k}: {v}")

                    trade = {
                        "ticker": row["Ticker"],
                        "price_at_entry": row["Price"],
                        **trade_plan
                    }

                    add_trade(trade)

# ---------- TRADES ----------
with tab2:

    trades = load_trades()

    if not trades:
        st.info("No trades yet")
    else:
        for i, t in enumerate(trades):
            st.markdown(f"## {t['ticker']}")

            report = trade_report(t)
            for k, v in report.items():
                st.write(f"{k}: {v}")

            if st.button("Remove", key=f"r{i}"):
                remove_trade(i)
                st.rerun()

# ---------- EXIT ----------
with tab3:

    trades = load_trades()

    for t in trades:
        decision = evaluate_exit(t)

        if decision == "EXIT":
            st.error(f"{t['ticker']} → EXIT")
        elif decision == "WATCH":
            st.warning(f"{t['ticker']} → WATCH")
        else:
            st.success(f"{t['ticker']} → HOLD")
