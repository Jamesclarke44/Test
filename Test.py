"""
Test.py - Diagnostic Version - Tests yfinance connectivity
"""

import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Scanner Test", page_icon="🔍", layout="wide")

st.title("🔍 Scanner Diagnostic Test")

st.markdown("### Test 1: Basic yfinance Connectivity")

test_tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]

for ticker in test_tickers:
    try:
        df = yf.download(ticker, period="5d", progress=False, auto_adjust=False)
        if df.empty:
            st.error(f"❌ {ticker}: Empty DataFrame")
        else:
            price = float(df['Close'].iloc[-1])
            st.success(f"✅ {ticker}: ${price:.2f} - Data OK")
    except Exception as e:
        st.error(f"❌ {ticker}: Error - {str(e)}")

st.divider()
st.markdown("### Test 2: Simple Scan (No Filters)")

if st.button("Run Simple Scan"):
    results = []
    for ticker in test_tickers:
        try:
            df = yf.download(ticker, period="1mo", progress=False, auto_adjust=False)
            if not df.empty and len(df) > 20:
                close = df['Close']
                current = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                change = ((current - prev) / prev) * 100
                
                results.append({
                    'Ticker': ticker,
                    'Price': current,
                    'Change %': round(change, 2)
                })
        except:
            pass
    
    if results:
        st.success(f"Found {len(results)} tickers")
        st.dataframe(pd.DataFrame(results))
    else:
        st.error("No results - yfinance may be blocked")

st.divider()
st.markdown("### 🔧 If Nothing Works...")

st.markdown("""
**yfinance is likely blocked on Streamlit Cloud.** Try these fixes:

1. **Add a User-Agent header** (requires modifying code)
2. **Use an alternative data source** like Alpha Vantage (free API key required)
3. **Deploy locally** where yfinance isn't restricted

Would you like me to provide a version with:
- Alpha Vantage API instead?
- Cached data fallback?
""")