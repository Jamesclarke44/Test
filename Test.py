"""
Test.py - Diagnostic Version - Robust MultiIndex Handling
"""

import streamlit as st
import pandas as pd
import yfinance as yf

st.set_page_config(page_title="Scanner Test", page_icon="🔍", layout="wide")

st.title("🔍 Scanner Diagnostic Test")

# ============================================================================
# ROBUST SAFE SCALAR - HANDLES ALL PANDAS TYPES
# ============================================================================

def robust_scalar(value):
    """Convert ANY pandas object to a scalar float"""
    if value is None:
        return 0.0
    
    # Handle pandas Series
    if isinstance(value, pd.Series):
        if len(value) == 0:
            return 0.0
        val = value.iloc[0]
        return float(val) if not pd.isna(val) else 0.0
    
    # Handle pandas DataFrame
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return 0.0
        # Get first column, first row
        val = value.iloc[0, 0]
        return float(val) if not pd.isna(val) else 0.0
    
    # Handle numpy arrays
    if hasattr(value, 'item'):
        val = value.item()
        return float(val) if val is not None else 0.0
    
    # Handle lists/tuples
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return 0.0
        return float(value[0])
    
    # Handle scalar values
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

# ============================================================================
# PROPER COLUMN EXTRACTION
# ============================================================================

def get_column(df, col_name):
    """Safely extract a column from DataFrame, handling MultiIndex"""
    if df.empty:
        return None
    
    # If MultiIndex, try to get the column
    if isinstance(df.columns, pd.MultiIndex):
        # Try to find the column at any level
        for level in range(df.columns.nlevels):
            if col_name in df.columns.get_level_values(level):
                # Get all columns where this level equals col_name
                mask = df.columns.get_level_values(level) == col_name
                col_idx = mask.argmax() if mask.any() else None
                if col_idx is not None:
                    return df.iloc[:, col_idx]
        return None
    
    # Regular single-level columns
    if col_name in df.columns:
        return df[col_name]
    
    # Try case-insensitive match
    for col in df.columns:
        if col.lower() == col_name.lower():
            return df[col]
    
    return None

# ============================================================================
# TESTS
# ============================================================================

st.markdown("### Test 1: Robust Data Fetch")

test_tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]

for ticker in test_tickers:
    try:
        # Download with auto_adjust=True for simpler columns
        df = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
        
        if df.empty:
            st.error(f"❌ {ticker}: Empty DataFrame")
            continue
        
        # Show raw data structure for debugging
        with st.expander(f"Debug: {ticker} DataFrame structure"):
            st.write(f"Columns type: {type(df.columns)}")
            st.write(f"Columns: {df.columns.tolist() if hasattr(df.columns, 'tolist') else df.columns}")
            st.write(f"Shape: {df.shape}")
            st.write(df.tail(2))
        
        # Get Close column using robust method
        close_col = get_column(df, 'Close')
        
        if close_col is None:
            st.error(f"❌ {ticker}: Could not find 'Close' column. Available: {df.columns.tolist()}")
            continue
        
        # Get the last value
        last_close = close_col.iloc[-1]
        price = robust_scalar(last_close)
        
        if price > 0:
            st.success(f"✅ {ticker}: ${price:.2f} - Data OK")
        else:
            st.error(f"❌ {ticker}: Price = {price}")
            
    except Exception as e:
        st.error(f"❌ {ticker}: Exception - {str(e)}")
        import traceback
        with st.expander(f"Full traceback for {ticker}"):
            st.code(traceback.format_exc())

st.divider()
st.markdown("### Test 2: Simple Scan (No Filters)")

if st.button("Run Simple Scan"):
    results = []
    
    progress = st.progress(0)
    
    for i, ticker in enumerate(test_tickers):
        progress.progress((i + 1) / len(test_tickers))
        
        try:
            df = yf.download(ticker, period="1mo", progress=False, auto_adjust=True)
            
            if df.empty or len(df) < 5:
                continue
            
            # Get columns
            close_col = get_column(df, 'Close')
            volume_col = get_column(df, 'Volume')
            
            if close_col is None:
                continue
            
            # Get current and previous values
            current = robust_scalar(close_col.iloc[-1])
            prev = robust_scalar(close_col.iloc[-2])
            
            if current <= 0:
                continue
            
            change = ((current - prev) / prev) * 100 if prev > 0 else 0
            volume = robust_scalar(volume_col.iloc[-1]) if volume_col is not None else 0
            
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
st.markdown("### 📋 Next Steps")

st.markdown("""
Run this diagnostic and:
1. Expand the **Debug** sections for each ticker
2. Tell me what the **Columns** look like

This will show exactly what yfinance is returning so I can fix the full scanner properly.
""")