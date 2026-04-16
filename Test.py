import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# -----------------------------
# Real data fetcher (free)
# -----------------------------
def generate_realtime_data(tickers):
    data = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            current_price = info.get("regularMarketPrice")
            prior_close = info.get("previousClose")
            volume = info.get("volume")

            if current_price is None or prior_close is None:
                continue

            gap_pct = ((current_price - prior_close) / prior_close) * 100

            float_shares = info.get("floatShares")
            if float_shares:
                float_millions = float_shares / 1_000_000
            else:
                float_millions = 50  # fallback placeholder

            data.append({
                "ticker": ticker,
                "prior_close": prior_close,
                "current_price": current_price,
                "premarket_volume": volume,  # placeholder
                "float_millions": float_millions,
                "rvol": 1.0,  # placeholder
                "has_catalyst": False,  # placeholder
                "gap_pct": gap_pct,
            })

        except Exception:
            continue

    return pd.DataFrame(data)


# -----------------------------
# Ross-style filter logic
# -----------------------------
def apply_ross_filters(
    df,
    min_price=2.0,
    max_price=20.0,
    min_gap_pct=4.0,
    min_premarket_volume=100_000,
    max_float_millions=50.0,
    min_rvol=3.0,
    require_catalyst=True,
):
    filtered = df.copy()

    filtered = filtered[
        (filtered["current_price"] >= min_price)
        & (filtered["current_price"] <= max_price)
    ]

    filtered = filtered[filtered["gap_pct"] >= min_gap_pct]
    filtered = filtered[filtered["premarket_volume"] >= min_premarket_volume]
    filtered = filtered[filtered["float_millions"] <= max_float_millions]
    filtered = filtered[filtered["rvol"] >= min_rvol]

    if require_catalyst:
        filtered = filtered[filtered["has_catalyst"] == True]

    filtered = filtered.sort_values(by=["gap_pct"], ascending=False)
    return filtered


# -----------------------------
# Streamlit UI
# -----------------------------
def main():
    st.set_page_config(page_title="Ross Gap Scanner v1", layout="wide")
    st.title("Ross-Style Gap Scanner v1 (Free Data Version)")

    st.markdown(
        """
        This scanner uses **free Yahoo Finance data** to simulate a Ross Cameron–style
        **gap scanner**.

        **Filters included:**
        - Price between **$2 and $20**
        - Gap **> 4%**
        - Volume (placeholder for premarket)
        - Float **< 50M**
        - RVOL (placeholder)
        - Optional: **must have catalyst**
        """
    )

    # Editable ticker list
    tickers = [AAPL, TSLA, NVDA, AMD, PLTR, SOFI, RIOT, MARA, GME, AMC, BBBY, BILI, NIO, XPEV, LCID, SNAP, PINS, UBER, LYFT, AFRM, UPST, RBLX, HOOD, FSR, NKLA, DNA, WISH, SNDL, CGC, TLRY, BB, NOK, F, GM, T, VZ, BABA, JD, BIDU, COIN, SQ, PYPL, SHOP, NET, CRWD, ZM, DOCU, ROKU, DKNG, PENN, CCL, NCLH, AAL, DAL, UAL, JBLU, SAVE, RUN, ENPH, FSLR, SPWR, CHPT, BLNK, QS, RIVN, ENVX, IONQ, AI, PATH, MDB, DDOG, ZS, OKTA, TEAM, HUBS, ETSY, W, DASH, ABNB, EXPE, BKNG, MRNA, PFE, BNTX, NVAX, CVNA, OPEN, Z, RDFN, TOST, CELH, MNST, BYND, SBUX, CMG, WMT, COST, TGT, HD, LOW, DIS, PARA, WBD, NFLX, META, GOOG, MSFT, INTC, MU, SMCI, ARM, AVGO, LRCX, AMAT, TXN, ON, AEHR, ASML, CRSR, LOGI, JBL, HPQ, DELL, IBM, ORCL, SAP, CRM, NOW, INTU, ADP, V, MA, JPM, BAC, WFC, C, GS, MS, SCHW, USB, TD, BMO, RY, BNS, ENB, SU, CNQ, CVE, DVN, MRO, OXY, XOM, CVX, HAL, SLB, RIG, WTI, VTNR, INDO, IMPP, HUSA, BOIL, KOLD, LABU, LABD, TNA, TZA, SQQQ, TQQQ, UVXY, SVXY, SPY, QQQ, IWM, DIA, VIXY, VXX, BITF, HUT, CLSK, CORZ, WULF, BTBT, ATER, MULN, AERC, AEMD, ACRX, ACRS, ADIL, AEZS, AGLE, AGRX, AHT, AITX, AKBA, AKRO, ALDX, ALZN, AMAM, AMRS, ANIX, APDN, APGN, APRN, ARDX, ARQQ, ASNS, ATHE, ATNF, ATOS, AURA, AVCT, AVXL, AXLA, AYLA, BBIG, BCTX, BDRX, BFRI, BGLC, BIVI, BLBX, BLIN, BLRX, BNGO, BNOX, BOLT, BPTS, BRSH, BRQS, BRTX, BSFC, BTCS, BTDR, BTTX, BURU, BYSI]


    st.sidebar.header("Data Settings")
    user_tickers = st.sidebar.text_area(
        "Tickers (comma separated)",
        value=",".join(tickers)
    )
    tickers = [t.strip().upper() for t in user_tickers.split(",") if t.strip()]

    st.sidebar.write("Fetching real data...")
    df = generate_realtime_data(tickers)

    with st.expander("Raw Data (from Yahoo Finance)", expanded=False):
        st.dataframe(df, use_container_width=True)

    st.sidebar.header("Ross Filter Settings")

    min_price = st.sidebar.number_input("Min price", value=2.0, step=0.5)
    max_price = st.sidebar.number_input("Max price", value=20.0, step=0.5)
    min_gap_pct = st.sidebar.number_input("Min gap %", value=4.0, step=0.5)
    min_premarket_volume = st.sidebar.number_input(
        "Min volume", value=100_000, step=10_000
    )
    max_float_millions = st.sidebar.number_input(
        "Max float (millions)", value=50.0, step=5.0
    )
    min_rvol = st.sidebar.number_input("Min RVOL", value=3.0, step=0.5)
    require_catalyst = st.sidebar.checkbox("Require catalyst (news)", value=False)

    filtered = apply_ross_filters(
        df,
        min_price=min_price,
        max_price=max_price,
        min_gap_pct=min_gap_pct,
        min_premarket_volume=min_premarket_volume,
        max_float_millions=max_float_millions,
        min_rvol=min_rvol,
        require_catalyst=require_catalyst,
    )

    st.subheader("Scanner Results")
    st.write(f"Matches: **{len(filtered)}**")
    st.dataframe(filtered, use_container_width=True)


if __name__ == "__main__":
    main()
