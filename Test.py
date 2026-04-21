import streamlit as st

st.set_page_config(page_title="Options Strategy Engine", layout="wide")

st.title("Options Strategy Exit Engine")

tabs = st.tabs(["Bull Call Debit Spread", "Calendar Spread"])

# ============================================================
# ==================  BULL CALL EXIT ENGINE  ==================
# ============================================================

with tabs[0]:
    st.header("Bull Call Debit Spread – Exit Engine")

    col1, col2 = st.columns(2)
    with col1:
        price = st.number_input("Underlying Price", value=999.66, step=0.1, key="bc_price")
        rsi = st.number_input("RSI", value=56.36, step=0.1, key="bc_rsi")
        adx = st.number_input("ADX", value=20.60, step=0.1, key="bc_adx")
        ivr = st.number_input("IVR", value=23.0, step=0.1, key="bc_ivr")

    with col2:
        vwap = st.number_input("VWAP", value=997.99, step=0.1, key="bc_vwap")
        bbh = st.number_input("BB High", value=1008.88, step=0.1, key="bc_bbh")
        bbl = st.number_input("BB Low", value=980.90, step=0.1, key="bc_bbl")
        pnl_pct = st.number_input("Current P/L % on Spread", value=16.0, step=1.0, key="bc_pnl")

    # Compute BB position
    bb_pos = (price - bbl) / (bbh - bbl) if bbh != bbl else 0.5
    st.markdown(f"**BB Position (0–1):** `{bb_pos:.2f}`")

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

    if st.button("Evaluate Bull Call Exit"):
        decision = decide_bull_call_exit(price, rsi, adx, ivr, vwap, bb_pos, pnl_pct)
        st.subheader("Decision")
        st.success(decision)


# ============================================================
# ==================  CALENDAR EXIT ENGINE  ==================
# ============================================================

with tabs[1]:
    st.header("Calendar Spread – Exit Engine")

    col1, col2 = st.columns(2)
    with col1:
        c_price = st.number_input("Underlying Price", value=331.15, step=0.1, key="cal_price")
        c_rsi = st.number_input("RSI", value=53.91, step=0.1, key="cal_rsi")
        c_adx = st.number_input("ADX", value=20.0, step=0.1, key="cal_adx")
        c_ivr = st.number_input("IVR", value=62.0, step=0.1, key="cal_ivr")

    with col2:
        c_vwap = st.number_input("VWAP", value=330.50, step=0.1, key="cal_vwap")
        c_bbh = st.number_input("BB High", value=334.50, step=0.1, key="cal_bbh")
        c_bbl = st.number_input("BB Low", value=325.55, step=0.1, key="cal_bbl")
        c_pnl_pct = st.number_input("Current P/L % on Calendar", value=-5.0, step=1.0, key="cal_pnl")

    # Compute BB position
    c_bb_pos = (c_price - c_bbl) / (c_bbh - c_bbl) if c_bbh != c_bbl else 0.5
    st.markdown(f"**BB Position (0–1):** `{c_bb_pos:.2f}`")

    def decide_calendar_exit(price, rsi, adx, ivr, vwap, bb_pos, pnl_pct):
        # Stop loss
        if pnl_pct <= -30:
            return "EXIT: Stop loss hit (≤ -30%)"

        # Take profit
        if pnl_pct >= 25:
            return "EXIT: Take profit (≥ +25%)"

        # Early exit if environment breaks neutrality
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

        # Ideal hold zone
        if (45 <= rsi <= 55 and
            adx < 20 and
            0.3 <= bb_pos <= 0.7):
            return "HOLD: Ideal neutral environment for calendar – stay in the trade."

        # Default
        return "HOLD: No exit signal, but environment not ideal – monitor closely."

    if st.button("Evaluate Calendar Exit"):
        decision = decide_calendar_exit(c_price, c_rsi, c_adx, c_ivr, c_vwap, c_bb_pos, c_pnl_pct)
        st.subheader("Decision")
        st.success(decision)
