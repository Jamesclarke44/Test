import streamlit as st

st.set_page_config(page_title="Options Strategy Engine", layout="wide")
st.title("Options Strategy Engine")

tabs = st.tabs(["Strategy Entry Engine", "Bull Call Exit Engine", "Calendar Exit Engine"])

# ============================================================
# ===============  SHARED: STRATEGY CLASSIFIER  ==============
# ============================================================

def classify_strategy(price, rsi, adx, ivr, vwap, bb_pos, atr):
    # 1. Calendar Spread
    if (45 <= rsi <= 55 and
        adx < 20 and
        30 <= ivr <= 60 and
        0.30 <= bb_pos <= 0.70 and
        abs(price - vwap) <= atr):
        return "CALENDAR SPREAD", "Neutral: RSI 45–55, ADX < 20, IVR medium, price near VWAP."

    # 2. Bull Call Debit Spread
    if (55 <= rsi <= 65 and
        18 <= adx <= 25 and
        ivr <= 35 and
        price > vwap and
        0.55 <= bb_pos <= 0.75):
        return "BULL CALL DEBIT SPREAD", "Mild bullish: RSI 55–65, ADX 18–25, low IVR, price above VWAP."

    # 3. Bear Put Debit Spread
    if (35 <= rsi <= 45 and
        18 <= adx <= 25 and
        ivr <= 40 and
        price < vwap and
        0.25 <= bb_pos <= 0.45):
        return "BEAR PUT DEBIT SPREAD", "Mild bearish: RSI 35–45, ADX 18–25, low IVR, price below VWAP."

    # 4. Diagonal Spread
    if (50 <= rsi <= 60 and
        15 <= adx <= 25 and
        ivr <= 35 and
        0.45 <= bb_pos <= 0.65):
        return "DIAGONAL SPREAD", "Slight trend with low IV: RSI 50–60, ADX 15–25, low IVR."

    # 5. No Trade
    return "NO TRADE", "Environment does not match any high‑probability setup."

# ============================================================
# ==================  TAB 1: ENTRY ENGINE  ===================
# ============================================================

with tabs[0]:
    st.header("Strategy Entry Engine")

    col1, col2 = st.columns(2)
    with col1:
        e_price = st.number_input("Underlying Price", value=999.66, step=0.1, key="e_price")
        e_rsi = st.number_input("RSI", value=56.36, step=0.1, key="e_rsi")
        e_adx = st.number_input("ADX", value=20.60, step=0.1, key="e_adx")
        e_ivr = st.number_input("IVR", value=23.0, step=0.1, key="e_ivr")
    with col2:
        e_vwap = st.number_input("VWAP", value=997.99, step=0.1, key="e_vwap")
        e_bbh = st.number_input("BB High", value=1008.88, step=0.1, key="e_bbh")
        e_bbl = st.number_input("BB Low", value=980.90, step=0.1, key="e_bbl")
        e_atr = st.number_input("ATR", value=5.78, step=0.1, key="e_atr")

    if e_bbh != e_bbl:
        e_bb_pos = (e_price - e_bbl) / (e_bbh - e_bbl)
    else:
        e_bb_pos = 0.5

    st.markdown(f"**BB Position (0–1):** `{e_bb_pos:.2f}`")

    if st.button("Classify Strategy", key="classify_btn"):
        strat, reason = classify_strategy(e_price, e_rsi, e_adx, e_ivr, e_vwap, e_bb_pos, e_atr)
        st.subheader("Recommended Strategy")
        st.success(strat)
        st.subheader("Reason")
        st.write(reason)

# ============================================================
# ============  TAB 2: BULL CALL EXIT ENGINE  ================
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
        return "HOLD: Environment ideal for bull call spread – stay in the trade."
    return "HOLD: No exit signal, but environment not ideal – monitor closely."

with tabs[1]:
    st.header("Bull Call Debit Spread – Exit Engine")

    col1, col2 = st.columns(2)
    with col1:
        bc_price = st.number_input("Underlying Price", value=999.66, step=0.1, key="bc_price")
        bc_rsi = st.number_input("RSI", value=56.36, step=0.1, key="bc_rsi")
        bc_adx = st.number_input("ADX", value=20.60, step=0.1, key="bc_adx")
        bc_ivr = st.number_input("IVR", value=23.0, step=0.1, key="bc_ivr")
    with col2:
        bc_vwap = st.number_input("VWAP", value=997.99, step=0.1, key="bc_vwap")
        bc_bbh = st.number_input("BB High", value=1008.88, step=0.1, key="bc_bbh")
        bc_bbl = st.number_input("BB Low", value=980.90, step=0.1, key="bc_bbl")
        bc_pnl = st.number_input("Current P/L % on Spread", value=16.0, step=1.0, key="bc_pnl")

    if bc_bbh != bc_bbl:
        bc_bb_pos = (bc_price - bc_bbl) / (bc_bbh - bc_bbl)
    else:
        bc_bb_pos = 0.5

    st.markdown(f"**BB Position (0–1):** `{bc_bb_pos:.2f}`")

    if st.button("Evaluate Bull Call Exit", key="bc_btn"):
        decision = decide_bull_call_exit(bc_price, bc_rsi, bc_adx, bc_ivr, bc_vwap, bc_bb_pos, bc_pnl)
        st.subheader("Decision")
        st.success(decision)

# ============================================================
# ============  TAB 3: CALENDAR EXIT ENGINE  =================
# ============================================================

def decide_calendar_exit(price, rsi, adx, ivr, vwap, bb_pos, pnl_pct):
    if pnl_pct <= -30:
        return "EXIT: Stop loss hit (≤ -30%)"
    if pnl_pct >= 25:
        return "EXIT: Take profit (≥ +25%)"
    if rsi > 60:
        return "EXIT: RSI > 60 (momentum breaking neutrality)"
    if rsi < 40:
        return "EXIT: RSI < 40 (momentum breaking neutrality)"
    if adx > 25:
        return "EXIT: ADX > 25 (trend forming – bad for calendars)"
    if price > vwap + 2:
        return "EXIT: Price breaking above VWAP (trend forming)"
    if price < vwap - 2:
        return "EXIT: Price breaking below VWAP (trend forming)"
    if (45 <= rsi <= 55 and
        adx < 20 and
        0.30 <= bb_pos <= 0.70):
        return "HOLD: Ideal neutral environment for calendar – stay in the trade."
    return "HOLD: No exit signal, but environment not ideal – monitor closely."

with tabs[2]:
    st.header("Calendar Spread – Exit Engine")

    col1, col2 = st.columns(2)
    with col1:
        cal_price = st.number_input("Underlying Price", value=331.15, step=0.1, key="cal_price")
        cal_rsi = st.number_input("RSI", value=53.91, step=0.1, key="cal_rsi")
        cal_adx = st.number_input("ADX", value=20.0, step=0.1, key="cal_adx")
        cal_ivr = st.number_input("IVR", value=62.0, step=0.1, key="cal_ivr")
    with col2:
        cal_vwap = st.number_input("VWAP", value=330.50, step=0.1, key="cal_vwap")
        cal_bbh = st.number_input("BB High", value=334.50, step=0.1, key="cal_bbh")
        cal_bbl = st.number_input("BB Low", value=325.55, step=0.1, key="cal_bbl")
        cal_pnl = st.number_input("Current P/L % on Calendar", value=-5.0, step=1.0, key="cal_pnl")

    if cal_bbh != cal_bbl:
        cal_bb_pos = (cal_price - cal_bbl) / (cal_bbh - cal_bbl)
    else:
        cal_bb_pos = 0.5

    st.markdown(f"**BB Position (0–1):** `{cal_bb_pos:.2f}`")

    if st.button("Evaluate Calendar Exit", key="cal_btn"):
        decision = decide_calendar_exit(cal_price, cal_rsi, cal_adx, cal_ivr, cal_vwap, cal_bb_pos, cal_pnl)
        st.subheader("Decision")
        st.success(decision)
