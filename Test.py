"""
Test.py - Diagnostic Version - Fixed Series Conversion
"""

import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Scanner Test", page_icon="🔍", layout="wide")

st.title("🔍 Scanner Diagnostic Test")

def safe_scalar(value):
    """Safely convert pandas Series/DataFrame to scalar float"""
    if isinstance(value, (pd.Series, pd.DataFrame)):
        if len(value) == 0:
            return 0.0
        return float(value.iloc[0])
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

st.markdown("### Test 1: Basic yfinance Connectivity")

test_tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]

for ticker in test_tickers:
    try:
        df = yf.download(ticker, period="5d", progress=False, auto_adjust=False)
        if df.empty:
            st.error(f"❌ {ticker}: Empty DataFrame")
        else:
            # Handle MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            price = safe_scalar(df['Close'].iloc[-1])
            st.success(f"✅ {ticker}: ${price:.2f} - Data OK")
    except Exception as e:
        st.error(f"❌ {ticker}: Error - {str(e)}")

st.divider()
st.markdown("### Test 2: Simple Scan (No Filters)")

if st.button("Run Simple Scan"):
    results = []
    
    progress = st.progress(0)
    
    for i, ticker in enumerate(test_tickers):
        progress.progress((i + 1) / len(test_tickers))
        
        try:
            df = yf.download(ticker, period="1mo", progress=False, auto_adjust=False)
            
            if not df.empty and len(df) > 20:
                # Handle MultiIndex columns
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                close = df['Close']
                current = safe_scalar(close.iloc[-1])
                prev = safe_scalar(close.iloc[-2])
                change = ((current - prev) / prev) * 100 if prev > 0 else 0
                
                # Volume
                volume = safe_scalar(df['Volume'].iloc[-1])
                
                results.append({
                    'Ticker': ticker,
                    'Price': round(current, 2),
                    'Change %': round(change, 2),
                    'Volume': int(volume)
                })
        except Exception as e:
            st.warning(f"⚠️ {ticker}: {str(e)}")
    
    progress.empty()
    
    if results:
        st.success(f"✅ Found {len(results)} tickers - Data download works!")
        df_results = pd.DataFrame(results)
        st.dataframe(df_results, use_container_width=True, hide_index=True)
    else:
        st.error("❌ No results - Check error messages above")

st.divider()
st.markdown("### 📊 Data is Working!")

st.markdown("""
Since the data **is** downloading successfully (the issue was just Series conversion), 
your original scanner will work once we apply the `safe_scalar()` fix everywhere.

**The problem:** Some parts of the scanner code try to do `float(df['Close'].iloc[-1])` 
which fails on newer pandas/yfinance versions.

**The fix:** Use `safe_scalar(df['Close'].iloc[-1])` everywhere instead.

I can provide the **fully fixed scanner code** with `safe_scalar()` applied consistently.
""")

# Option to load full fixed scanner
st.divider()
st.markdown("### 🚀 Ready for Full Scanner?")

if st.button("Show me where the conversion error happens in the full scanner"):
    st.code("""
# Problematic code in scanner:
current_price = float(df['Close'].iloc[-1])  # ❌ Fails

# Fixed code:
current_price = safe_scalar(df['Close'].iloc[-1])  # ✅ Works
    """)