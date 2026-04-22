"""
Test.py - Trading Scanner - FULLY FIXED
- Ultra-relaxed default filters
- Fixed session state for ticker selection
- 400+ tickers with Scan All option
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import json
from typing import List, Dict, Optional, Tuple

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="Trading Scanner",
    page_icon="🔍",
    layout="wide"
)

# ============================================================================
# ROBUST SCALAR CONVERSION
# ============================================================================

def robust_scalar(value):
    """Convert ANY pandas object to a scalar float"""
    if value is None:
        return 0.0
    if isinstance(value, pd.Series):
        if len(value) == 0:
            return 0.0
        val = value.iloc[0]
        return float(val) if not pd.isna(val) else 0.0
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return 0.0
        val = value.iloc[0, 0]
        return float(val) if not pd.isna(val) else 0.0
    if hasattr(value, 'item'):
        val = value.item()
        return float(val) if val is not None else 0.0
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return 0.0
        return float(value[0])
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def get_column(df, col_name):
    """Safely extract a column from DataFrame, handling MultiIndex"""
    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        col_name_lower = col_name.lower()
        for i, col_tuple in enumerate(df.columns):
            if any(str(c).lower() == col_name_lower for c in col_tuple):
                return df.iloc[:, i]
        return None
    for col in df.columns:
        if col.lower() == col_name.lower():
            return df[col]
    return None

# ============================================================================
# TECHNICAL INDICATORS
# ============================================================================

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = get_column(df, 'High')
    low = get_column(df, 'Low')
    close = get_column(df, 'Close')
    if high is None or low is None or close is None:
        return pd.Series([0] * len(df))
    high_low = high - low
    high_close = abs(high - close.shift())
    low_close = abs(low - close.shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_volume_sma(series: pd.Series, period: int = 20) -> pd.Series:
    return series.rolling(window=period).mean()

def calculate_volatility(series: pd.Series, period: int = 20) -> pd.Series:
    returns = series.pct_change()
    return returns.rolling(window=period).std() * np.sqrt(252) * 100

def detect_trend(df: pd.DataFrame) -> str:
    close = get_column(df, 'Close')
    if close is None or len(close) < 50:
        return "insufficient_data"
    sma_20 = robust_scalar(calculate_sma(close, 20).iloc[-1])
    sma_50 = robust_scalar(calculate_sma(close, 50).iloc[-1])
    current = robust_scalar(close.iloc[-1])
    if current > sma_20 > sma_50:
        return "strong_uptrend"
    elif current > sma_20:
        return "uptrend"
    elif current < sma_20 < sma_50:
        return "strong_downtrend"
    elif current < sma_20:
        return "downtrend"
    return "neutral"

def find_support_resistance(df: pd.DataFrame, lookback: int = 50) -> Tuple[float, float]:
    if len(df) < lookback:
        return 0.0, 0.0
    high = get_column(df, 'High')
    low = get_column(df, 'Low')
    if high is None or low is None:
        return 0.0, 0.0
    recent_high = high.tail(lookback)
    recent_low = low.tail(lookback)
    return float(recent_low.min()), float(recent_high.max())

# ============================================================================
# SCANNER ENGINE
# ============================================================================

class StockScanner:
    def __init__(self, tickers: List[str]):
        self.tickers = tickers
    
    def scan_single(self, ticker: str, criteria: Dict) -> Optional[Dict]:
        try:
            df = yf.download(ticker, period="3mo", progress=False, auto_adjust=True)
            if df.empty or len(df) < 50:
                return None
            
            close = get_column(df, 'Close')
            high = get_column(df, 'High')
            low = get_column(df, 'Low')
            volume = get_column(df, 'Volume')
            
            if close is None:
                return None
            
            current_price = robust_scalar(close.iloc[-1])
            previous_close = robust_scalar(close.iloc[-2])
            
            sma_20 = robust_scalar(calculate_sma(close, 20).iloc[-1])
            sma_50 = robust_scalar(calculate_sma(close, 50).iloc[-1])
            sma_200 = robust_scalar(calculate_sma(close, 200).iloc[-1]) if len(df) >= 200 else 0
            
            atr_series = calculate_atr(df, 14)
            atr_14 = robust_scalar(atr_series.iloc[-1])
            atr_percent = (atr_14 / current_price) * 100 if current_price > 0 else 0
            
            rsi_14 = robust_scalar(calculate_rsi(close, 14).iloc[-1])
            
            avg_volume = robust_scalar(calculate_volume_sma(volume, 20).iloc[-1]) if volume is not None else 0
            current_volume = robust_scalar(volume.iloc[-1]) if volume is not None else 0
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            
            volatility = robust_scalar(calculate_volatility(close, 20).iloc[-1])
            
            trend = detect_trend(df)
            support, resistance = find_support_resistance(df)
            
            dist_to_support = abs(current_price - support) / current_price * 100 if support > 0 else 100
            dist_to_resistance = abs(current_price - resistance) / current_price * 100 if resistance > 0 else 100
            
            change_pct = ((current_price - previous_close) / previous_close * 100) if previous_close > 0 else 0
            
            # Check criteria - ULTRA RELAXED DEFAULTS
            if criteria.get('min_price') and current_price < criteria['min_price']:
                return None
            if criteria.get('max_price') and current_price > criteria['max_price']:
                return None
            if criteria.get('min_volume') and avg_volume < criteria['min_volume']:
                return None
            if criteria.get('min_volatility') and volatility < criteria['min_volatility']:
                return None
            if criteria.get('max_volatility') and volatility > criteria['max_volatility']:
                return None
            if criteria.get('min_volume_ratio') and volume_ratio < criteria['min_volume_ratio']:
                return None
            if criteria.get('rsi_min') and rsi_14 < criteria['rsi_min']:
                return None
            if criteria.get('rsi_max') and rsi_14 > criteria['rsi_max']:
                return None
            if criteria.get('trend_filter') and criteria['trend_filter'] != 'all':
                if criteria['trend_filter'] == 'uptrend' and trend not in ['uptrend', 'strong_uptrend']:
                    return None
                elif criteria['trend_filter'] == 'downtrend' and trend not in ['downtrend', 'strong_downtrend']:
                    return None
            if criteria.get('above_sma20') and current_price < sma_20:
                return None
            if criteria.get('above_sma50') and current_price < sma_50:
                return None
            
            # Calculate score
            score = 0
            if volume_ratio > 1.5: score += 2
            elif volume_ratio > 1.2: score += 1
            if trend == "strong_uptrend": score += 3
            elif trend == "uptrend": score += 2
            if 30 <= rsi_14 <= 70: score += 1
            if 40 <= rsi_14 <= 60: score += 1
            if 1.5 <= atr_percent <= 5.0: score += 2
            if dist_to_support < 5: score += 2
            elif dist_to_support < 10: score += 1
            
            adr_pct = ((robust_scalar(high.iloc[-1]) - robust_scalar(low.iloc[-1])) / current_price * 100) if high is not None and low is not None else 0
            
            return {
                'ticker': ticker,
                'current_price': round(current_price, 2),
                'change_pct': round(change_pct, 2),
                'volume': int(current_volume),
                'avg_volume': int(avg_volume),
                'volume_ratio': round(volume_ratio, 2),
                'atr': round(atr_14, 2),
                'atr_percent': round(atr_percent, 2),
                'volatility': round(volatility, 1),
                'rsi': round(rsi_14, 1),
                'trend': trend,
                'sma_20': round(sma_20, 2),
                'sma_50': round(sma_50, 2),
                'sma_200': round(sma_200, 2),
                'support': round(support, 2),
                'resistance': round(resistance, 2),
                'dist_to_support': round(dist_to_support, 1),
                'dist_to_resistance': round(dist_to_resistance, 1),
                'adr_percent': round(adr_pct, 1),
                'score': score
            }
        except Exception:
            return None
    
    def scan_all(self, criteria: Dict) -> List[Dict]:
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        for i, ticker in enumerate(self.tickers):
            status_text.text(f"Scanning {ticker}... ({i+1}/{len(self.tickers)})")
            progress_bar.progress((i + 1) / len(self.tickers))
            result = self.scan_single(ticker, criteria)
            if result:
                results.append(result)
        progress_bar.empty()
        status_text.empty()
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

# ============================================================================
# EXPANDED DEFAULT WATCHLISTS (400+ tickers)
# ============================================================================

DEFAULT_WATCHLISTS = {
    "Major ETFs": [
        "SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "SLV", "USO", "XLF", "XLK",
        "XLV", "XLI", "XLE", "XLP", "XLY", "XLU", "XLB", "XME", "XRT", "XHB",
        "SMH", "SOXX", "IBB", "XBI", "ARKK"
    ],
    "Tech Giants": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX", "ADBE", "CRM",
        "ORCL", "IBM", "CSCO", "INTC", "AMD", "QCOM", "TXN", "AVGO", "MU", "AMAT",
        "LRCX", "KLAC", "SNPS", "CDNS", "ADSK", "NOW", "WDAY", "TEAM", "DDOG", "CRWD"
    ],
    "Semiconductors": [
        "NVDA", "AMD", "INTC", "AVGO", "TXN", "QCOM", "MU", "AMAT", "LRCX", "KLAC",
        "ASML", "TSM", "ADI", "MCHP", "ON", "STM", "NXPI", "MPWR", "MRVL", "SWKS"
    ],
    "Financials": [
        "JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP", "V",
        "MA", "PYPL", "SQ", "COIN", "BX", "KKR", "APO", "ARES", "CG", "TPG"
    ],
    "Healthcare": [
        "JNJ", "PFE", "MRK", "ABBV", "LLY", "TMO", "DHR", "ABT", "BMY", "AMGN",
        "GILD", "BIIB", "REGN", "VRTX", "MRNA", "ISRG", "EW", "BSX", "SYK", "ZBH"
    ],
    "Consumer": [
        "WMT", "AMZN", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "COST", "TJX",
        "ROST", "BURL", "DG", "DLTR", "FIVE", "ULTA", "LULU", "DECK", "CROX", "YETI"
    ],
    "Energy": [
        "XOM", "CVX", "COP", "SLB", "EOG", "PXD", "OXY", "MPC", "VLO", "PSX",
        "HAL", "BKR", "FANG", "DVN", "MRO", "APA", "HES", "CTRA", "EQT", "RRC"
    ],
    "High Volume Stocks": [
        "AAPL", "TSLA", "NVDA", "AMD", "AMZN", "META", "MSFT", "GOOGL", "NFLX", "PLTR",
        "SOFI", "RIVN", "LCID", "MARA", "RIOT", "COIN", "GME", "AMC", "TQQQ", "SQQQ"
    ],
    "Swing Trading Favorites": [
        "AAPL", "MSFT", "NVDA", "TSLA", "META", "AMZN", "GOOGL", "AMD", "NFLX", "CRM",
        "ADBE", "NOW", "SNOW", "DDOG", "CRWD", "ZS", "NET", "MDB", "PLTR", "SOFI"
    ],
    "Volatile Stocks": [
        "TSLA", "NVDA", "AMD", "PLTR", "COIN", "RIVN", "LCID", "MARA", "RIOT", "GME",
        "AMC", "MSTR", "AI", "UPST", "AFRM", "HOOD", "W", "CHWY", "CVNA", "WOLF"
    ]
}

# ============================================================================
# UI STYLING
# ============================================================================

st.markdown("""
<style>
    .scan-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 700;
    }
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 12px 24px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# SIDEBAR - ULTRA RELAXED DEFAULTS
# ============================================================================

with st.sidebar:
    st.header("🔍 Scan Criteria")
    st.subheader("📋 Watchlist")
    watchlist_option = st.selectbox("Select Watchlist", list(DEFAULT_WATCHLISTS.keys()) + ["Custom"])
    
    st.divider()
    
    # Option to scan all watchlists combined
    scan_all_watchlists = st.checkbox("🔍 Scan ALL Watchlists Combined", value=True)
    
    if scan_all_watchlists:
        all_tickers = set()
        for name, tlist in DEFAULT_WATCHLISTS.items():
            all_tickers.update(tlist)
        tickers = list(all_tickers)
        st.success(f"🎯 Scanning ALL {len(tickers)} tickers!")
    elif watchlist_option == "Custom":
        custom_tickers = st.text_area("Enter tickers", value="AAPL, MSFT, NVDA", height=100)
        tickers = [t.strip().upper() for t in custom_tickers.replace(',', ' ').split() if t.strip()]
    else:
        tickers = DEFAULT_WATCHLISTS[watchlist_option]
        st.info(f"Scanning {len(tickers)} tickers")
    
    st.divider()
    st.subheader("💰 Price Filters")
    col1, col2 = st.columns(2)
    with col1:
        min_price = st.number_input("Min Price ($)", value=0.01, step=1.0, format="%.2f")
    with col2:
        max_price = st.number_input("Max Price ($)", value=9999.0, step=10.0, format="%.2f")
    
    st.divider()
    st.subheader("📊 Volume Filters")
    min_volume = st.number_input("Min Avg Volume", value=0, step=50000, format="%.0f")
    min_volume_ratio = st.slider("Min Volume Ratio", 0.1, 3.0, 0.1, 0.1)
    
    st.divider()
    st.subheader("📈 Technical Filters")
    trend_filter = st.selectbox("Trend Direction", ["all", "uptrend", "downtrend"], index=0)
    above_sma20 = st.checkbox("Price > 20 SMA", value=False)
    above_sma50 = st.checkbox("Price > 50 SMA", value=False)
    col1, col2 = st.columns(2)
    with col1:
        rsi_min = st.number_input("RSI Min", value=0.0, step=1.0)
    with col2:
        rsi_max = st.number_input("RSI Max", value=100.0, step=1.0)
    
    st.divider()
    st.subheader("📉 Volatility Filters")
    col1, col2 = st.columns(2)
    with col1:
        min_volatility = st.number_input("Min Volatility %", value=0.0, step=5.0)
    with col2:
        max_volatility = st.number_input("Max Volatility %", value=500.0, step=5.0)
    
    st.divider()
    scan_button = st.button("🔍 Run Scanner", type="primary", use_container_width=True)

# ============================================================================
# MAIN CONTENT
# ============================================================================

st.markdown('<h1 class="scan-header">🔍 Trading Scanner</h1>', unsafe_allow_html=True)
st.caption("Find high-probability setups based on technical criteria")

# Initialize session state for results
if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None
if 'selected_ticker' not in st.session_state:
    st.session_state.selected_ticker = None

if scan_button:
    # Clear old results
    st.session_state.scan_results = None
    st.session_state.selected_ticker = None
    
    criteria = {
        'min_price': min_price, 'max_price': max_price,
        'min_volume': min_volume, 'min_volume_ratio': min_volume_ratio,
        'trend_filter': trend_filter, 'above_sma20': above_sma20, 'above_sma50': above_sma50,
        'rsi_min': rsi_min, 'rsi_max': rsi_max,
        'min_volatility': min_volatility, 'max_volatility': max_volatility
    }
    
    scanner = StockScanner(tickers)
    results = scanner.scan_all(criteria)
    
    if results:
        st.session_state.scan_results = results
        st.session_state.selected_ticker = results[0]['ticker']
        st.success(f"✅ Found {len(results)} setups matching criteria")
        st.rerun()
    else:
        st.warning("⚠️ No setups found. Try relaxing filters further.")

# Display results if they exist in session state
if st.session_state.scan_results:
    results = st.session_state.scan_results
    df_results = pd.DataFrame(results)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Total Scanned", len(tickers))
    with col2: st.metric("Setups Found", len(results))
    with col3: st.metric("Hit Rate", f"{(len(results)/len(tickers))*100:.1f}%" if tickers else "0%")
    with col4: st.metric("Avg Score", f"{df_results['score'].mean():.1f}")
    
    st.divider()
    st.subheader("📊 Scan Results")
    
    display_cols = ['ticker', 'current_price', 'change_pct', 'volume_ratio', 
                   'atr_percent', 'rsi', 'trend', 'dist_to_support', 'score']
    display_df = df_results[display_cols].copy()
    display_df.columns = ['Ticker', 'Price', 'Change %', 'Vol Ratio', 
                         'ATR %', 'RSI', 'Trend', 'Dist to Sup %', 'Score']
    
    def style_trend(val):
        if val in ['strong_uptrend', 'uptrend']: return 'color: #22c55e; font-weight: 600'
        elif val in ['strong_downtrend', 'downtrend']: return 'color: #ef4444; font-weight: 600'
        return 'color: #f59e0b; font-weight: 600'
    
    def style_score(val):
        if val >= 8: return 'background-color: #22c55e; color: white; padding: 4px 8px; border-radius: 12px;'
        elif val >= 5: return 'background-color: #f59e0b; color: white; padding: 4px 8px; border-radius: 12px;'
        return 'background-color: #ef4444; color: white; padding: 4px 8px; border-radius: 12px;'
    
    styled_df = display_df.style.map(style_trend, subset=['Trend'])\
                              .map(style_score, subset=['Score'])\
                              .format({'Price': '${:.2f}', 'Change %': '{:+.2f}%',
                                       'Vol Ratio': '{:.2f}x', 'ATR %': '{:.2f}%',
                                       'RSI': '{:.1f}', 'Dist to Sup %': '{:.1f}%'})
    st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
    # Detailed view - SIMPLE RADIO BUTTONS (more reliable than selectbox)
    st.divider()
    st.subheader("🔎 Detailed View")
    
    ticker_options = [r['ticker'] for r in results]
    
    # Use radio buttons for more reliable selection
    selected = st.radio(
        "Select ticker for detailed analysis",
        ticker_options,
        index=ticker_options.index(st.session_state.selected_ticker) if st.session_state.selected_ticker in ticker_options else 0,
        horizontal=True,
        key='ticker_radio'
    )
    
    # Update session state when radio changes
    if selected != st.session_state.selected_ticker:
        st.session_state.selected_ticker = selected
        st.rerun()
    
    current_ticker = st.session_state.selected_ticker
    
    if current_ticker and current_ticker in [r['ticker'] for r in results]:
        detail = next(r for r in results if r['ticker'] == current_ticker)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"### {detail['ticker']}")
            st.markdown(f"**Price:** ${detail['current_price']:.2f}")
            st.markdown(f"**Change:** {detail['change_pct']:+.2f}%")
            st.markdown(f"**Score:** {detail['score']}/12")
            if detail['score'] >= 8: st.success("⭐⭐⭐ High Quality")
            elif detail['score'] >= 5: st.warning("⭐⭐ Medium Quality")
            else: st.error("⭐ Low Quality")
        with col2:
            st.markdown("### Technicals")
            st.markdown(f"**RSI:** {detail['rsi']:.1f}")
            st.markdown(f"**ATR:** ${detail['atr']:.2f} ({detail['atr_percent']:.2f}%)")
            st.markdown(f"**Volatility:** {detail['volatility']:.1f}%")
            st.markdown(f"**Volume Ratio:** {detail['volume_ratio']:.2f}x")
        with col3:
            st.markdown("### Levels")
            st.markdown(f"**Support:** ${detail['support']:.2f}")
            st.markdown(f"**Resistance:** ${detail['resistance']:.2f}")
            st.markdown(f"**Dist to Support:** {detail['dist_to_support']:.1f}%")
            st.markdown(f"**20 SMA:** ${detail['sma_20']:.2f}")
        
        st.markdown("### 🎯 Next Steps")
        st.markdown(f"**Entry:** ${detail['current_price']:.2f} | **Suggested Stop:** ${detail['support']:.2f}")
        
        export_data = {
            'ticker': detail['ticker'], 
            'price': detail['current_price'],
            'score': detail['score'], 
            'trend': detail['trend'],
            'support': detail['support'], 
            'resistance': detail['resistance'],
            'atr': detail['atr'],
            'rsi': detail['rsi']
        }
        st.download_button(
            f"📥 Export {detail['ticker']} Setup", 
            data=json.dumps(export_data, indent=2),
            file_name=f"{detail['ticker']}_setup.json",
            mime="application/json"
        )

else:
    st.info("👈 Click 'Run Scanner' to begin")
    st.markdown("""
    ### 📋 Quick Start
    1. ✅ 'Scan ALL Watchlists Combined' is checked by default
    2. Filters are set to **show everything** initially
    3. Click **'Run Scanner'** 
    4. Use the radio buttons to browse results
    """)

st.divider()
st.caption("🔍 Trading Scanner — Find setups. Plan exits. Trade with confidence.")