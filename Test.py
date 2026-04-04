import streamlit as st
import pandas as pd
import yfinance as yf

from ta.trend import ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands, AverageTrueRange

st.set_page_config(page_title="Strategy Finder Pro", layout="centered")

# ----------------- DATA -----------------

@st.cache_data
def load_universe():
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
    df = pd.read_csv(url)

    sp500 = df["Symbol"].tolist()

    etfs = [
        "SPY","QQQ","IWM","DIA","VTI","VOO","IVV",
        "XLF","XLK","XLE","XLV","XLI","XLP","XLU","XLY","XLB","XLRE","XLC",
        "ARKK","ARKG","SMH","SOXX","XBI","EEM","GLD","SLV","TLT"
    ]

    return list(set(sp500 + etfs))


@st.cache_data
def get_data(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        print(f"{ticker} download error: {e}")
        return None


# ----------------- INDICATORS -----------------

def compute_indicators(df):

    if df is None or df.empty or len(df) < 50:
        return None

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    df["RSI"] = RSIIndicator(close=close).rsi()
    df["ADX"] = ADXIndicator(high=high, low=low, close=close).adx()
    df["ATR"] = AverageTrueRange(high=high, low=low, close=close).average_true_range()

    bb = BollingerBands(close=close)
    df["BB_High"] = bb.bollinger_hband()
    df["BB_Low"] = bb.bollinger_lband()

    # Moving averages (better than VWAP on daily)
    df["SMA20"] = close.rolling(20).mean()
    df["SMA50"] = close.rolling(50).mean()

    return df.dropna()


# ----------------- STRATEGY ENGINE -----------------

def classify_market(price, rsi, adx, atr, sma20, sma50, bb_low, bb_high):

    atr_pct = (atr / price) * 100
    sma_drift = abs(price - sma20) / price

    # BB position
    if bb_high - bb_low == 0:
        bb_pos = 0.5
    else:
        bb_pos = (price - bb_low) / (bb_high - bb_low)

    # -------- BIAS --------
    if price > sma20 > sma50:
        bias = "STRONG BULLISH"
    elif price > sma20:
        bias = "BULLISH"
    elif price < sma20 < sma50:
        bias = "STRONG BEARISH"
    elif price < sma20:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    # -------- REGIME --------
    if adx < 20:
        regime = "RANGE"
    elif adx > 25:
        regime = "TREND"
    else:
        regime = "MIXED"

    # -------- STRATEGIES --------
    strategies = []
    risk = None
    score = 0

    # 🎯 LOW RISK RANGE (A+)
    if (
        40 <= rsi <= 60 and
        adx < 25 and
        sma_drift <= 0.01 and
        0.4 <= bb_pos <= 0.6 and
        atr_pct <= 2.5
    ):
        strategies = ["Calendars", "Iron Condor", "Butterfly"]
        risk = "LOW RISK"
        score = 3

    # ⚖️ MODERATE RANGE
    elif adx < 30:
        strategies = ["Wide Iron Condor", "Credit Spreads", "Jade Lizard"]
        risk = "MODERATE"
        score = 2

    # 🔥 TREND PLAYS
    if regime == "TREND":
        if "BULLISH" in bias:
            strategies += ["Bull Put Spread", "Call Debit Spread"]
        elif "BEARISH" in bias:
            strategies += ["Bear Call Spread", "Put Debit Spread"]

        risk = "TREND TRADE"
        score = max(score, 2)

    strategies = list(set(strategies))

    # -------- CONFIDENCE --------
    if score == 3:
        confidence = "A+"
    elif score == 2:
        confidence = "B"
    else:
        confidence = "C"

    return {
        "risk": risk,
        "strategies": strategies,
        "bb_pos": bb_pos,
        "atr_pct": atr_pct,
        "sma_drift": sma_drift,
        "bias": bias,
        "regime": regime,
        "confidence": confidence
    }


# ----------------- SCANNER -----------------

def scan_universe(tickers, progress_bar, status_text, counter_text):

    results = []
    total = len(tickers)

    for i, ticker in enumerate(tickers):

        counter_text.markdown(f"### Scanned: {i+1} / {total}")
        status_text.text(f"Scanning {ticker}")

        try:
            df = get_data(ticker)
            df = compute_indicators(df)

            if df is None:
                continue

            last = df.iloc[-1]

            data = classify_market(
                last["Close"],
                last["RSI"],
                last["ADX"],
                last["ATR"],
                last["SMA20"],
                last["SMA50"],
                last["BB_Low"],
                last["BB_High"]
            )

            if data["risk"]:
                results.append({
                    "Ticker": ticker,
                    "Price": round(last["Close"], 2),
                    "RSI": round(last["RSI"], 1),
                    "ADX": round(last["ADX"], 1),
                    "ATR %": round(data["atr_pct"], 2),
                    "BB Pos": round(data["bb_pos"], 2),
                    "Bias": data["bias"],
                    "Regime": data["regime"],
                    "Confidence": data["confidence"],
                    "Risk": data["risk"],
                    "Strategies": ", ".join(data["strategies"])
                })

        except Exception as e:
            print(f"{ticker} failed: {e}")

        progress_bar.progress((i + 1) / total)

    status_text.text("Scan complete ✅")
    return pd.DataFrame(results)


# ----------------- UI -----------------

st.title("🧠 Strategy Finder PRO")

mode = st.radio("Mode", ["Scan Universe", "Single Ticker"])

# ----------------- SCAN -----------------

if mode == "Scan Universe":

    if st.button("Run Scan"):

        tickers = load_universe()

        progress_bar = st.progress(0)
        status_text = st.empty()
        counter_text = st.empty()

        with st.spinner("Scanning market..."):
            df_results = scan_universe(tickers, progress_bar, status_text, counter_text)

        if df_results.empty:
            st.warning("❌ No setups found")
        else:
            df_results = df_results.sort_values(by=["Confidence", "ATR %"], ascending=[True, True])

            st.subheader("📊 Opportunities")
            st.dataframe(df_results, use_container_width=True)

            st.session_state["results"] = df_results

# ----------------- SINGLE -----------------

if mode == "Single Ticker":

    ticker = st.text_input("Enter Ticker", value="SPY").upper()

    if st.button("Analyze"):

        df = compute_indicators(get_data(ticker))

        if df is None:
            st.error("No data found")
        else:
            last = df.iloc[-1]

            data = classify_market(
                last["Close"],
                last["RSI"],
                last["ADX"],
                last["ATR"],
                last["SMA20"],
                last["SMA50"],
                last["BB_Low"],
                last["BB_High"]
            )

            st.subheader(f"{ticker} — {last['Close']:.2f}")

            st.write(f"**Bias:** {data['bias']}")
            st.write(f"**Regime:** {data['regime']}")
            st.write(f"**Confidence:** {data['confidence']}")

            st.write(f"RSI: {last['RSI']:.1f}")
            st.write(f"ADX: {last['ADX']:.1f}")
            st.write(f"ATR %: {data['atr_pct']:.2f}%")

            st.subheader("Strategies")

            for s in data["strategies"]:
                st.write(f"• {s}")