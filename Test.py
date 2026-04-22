"""
Teat.py - Trading Scanner for Finding High-Probability Setups
Run with: streamlit run Test.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
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
# SAFE SCALAR HELPER
# ============================================================================

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

# ============================================================================
# TECHNICAL INDICATORS
# ============================================================================

def calculate_sma(data: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average"""
    return data.rolling(window=period).mean()

def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average"""
    return data.ewm(span=period, adjust=False).mean()

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range"""
    high_low = high - low
    high_close = abs(high - close.shift())
    low_close = abs(low - close.shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    """Volume Simple Moving Average"""
    return volume.rolling(window=period).mean()

def calculate_adr_percent(high: pd.Series, low: pd.Series, period: int = 20) -> pd.Series:
    """Average Daily Range as percentage"""
    daily_range = (high - low) / low * 100
    return daily_range.rolling(window=period).mean()

def calculate_volatility(close: pd.Series, period: int = 20) -> pd.Series:
    """Historical Volatility (annualized)"""
    returns = close.pct_change()
    return returns.rolling(window=period).std() * np.sqrt(252) * 100

def detect_trend(df: pd.DataFrame, short_ma: int = 20, long_ma: int = 50) -> str:
    """Detect trend direction based on moving averages"""
    if len(df) < long_ma:
        return "insufficient_data"
    
    close = df['Close']
    sma_short = calculate_sma(close, short_ma).iloc[-1]
    sma_long = calculate_sma(close, long_ma).iloc[-1]
    current_price = safe_scalar(close.iloc[-1])
    
    if current_price > sma_short > sma_long:
        return "strong_uptrend"
    elif current_price > sma_short:
        return "uptrend"
    elif current_price < sma_short < sma_long:
        return "strong_downtrend"
    elif current_price < sma_short:
        return "downtrend"
    else:
        return "neutral"

def find_support_resistance(df: pd.DataFrame, lookback: int = 50) -> Tuple[float, float]:
    """Find nearest support and resistance levels"""
    if len(df) < lookback:
        return 0.0, 0.0
    
    recent = df.tail(lookback)
    support = float(recent['Low'].min())
    resistance = float(recent['High'].max())
    
    return support, resistance

def calculate_distance_to_level(current_price: float, level: float) -> float:
    """Calculate percentage distance to a price level"""
    if level == 0:
        return 0.0
    return abs(current_price - level) / current_price * 100

# ============================================================================
# SCANNER ENGINE
# ============================================================================

class StockScanner:
    """Main scanner class for finding trade setups"""
    
    def __init__(self, tickers: List[str]):
        self.tickers = tickers
        self.results = []
    
    def scan_single(self, ticker: str, criteria: Dict) -> Optional[Dict]:
        """Scan a single ticker against criteria"""
        try:
            # Download data
            df = yf.download(ticker, period="3mo", progress=False, auto_adjust=False)
            
            if df.empty or len(df) < 50:
                return None
            
            # Handle MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Calculate all indicators
            close = df['Close']
            high = df['High']
            low = df['Low']
            volume = df['Volume']
            
            current_price = safe_scalar(close.iloc[-1])
            previous_close = safe_scalar(close.iloc[-2])
            
            # Moving Averages
            sma_20 = safe_scalar(calculate_sma(close, 20).iloc[-1])
            sma_50 = safe_scalar(calculate_sma(close, 50).iloc[-1])
            sma_200 = safe_scalar(calculate_sma(close, 200).iloc[-1]) if len(df) >= 200 else 0
            
            # ATR and Volatility
            atr_14 = safe_scalar(calculate_atr(high, low, close, 14).iloc[-1])
            atr_percent = (atr_14 / current_price) * 100 if current_price > 0 else 0
            
            # RSI
            rsi_14 = safe_scalar(calculate_rsi(close, 14).iloc[-1])
            
            # Volume
            avg_volume_20 = safe_scalar(calculate_volume_sma(volume, 20).iloc[-1])
            volume_ratio = safe_scalar(volume.iloc[-1]) / avg_volume_20 if avg_volume_20 > 0 else 0
            
            # ADR %
            adr_percent = safe_scalar(calculate_adr_percent(high, low, 20).iloc[-1])
            
            # Volatility
            volatility = safe_scalar(calculate_volatility(close, 20).iloc[-1])
            
            # Trend
            trend = detect_trend(df)
            
            # Support/Resistance
            support, resistance = find_support_resistance(df)
            distance_to_support = calculate_distance_to_level(current_price, support)
            distance_to_resistance = calculate_distance_to_level(current_price, resistance)
            
            # Price change
            change_pct = ((current_price - previous_close) / previous_close * 100) if previous_close > 0 else 0
            
            # Check criteria
            passes = True
            reasons = []
            
            if criteria.get('min_price') and current_price < criteria['min_price']:
                passes = False
                reasons.append(f"Price below min: ${current_price:.2f} < ${criteria['min_price']}")
            
            if criteria.get('max_price') and current_price > criteria['max_price']:
                passes = False
                reasons.append(f"Price above max: ${current_price:.2f} > ${criteria['max_price']}")
            
            if criteria.get('min_volume') and avg_volume_20 < criteria['min_volume']:
                passes = False
                reasons.append(f"Volume too low: {avg_volume_20:,.0f} < {criteria['min_volume']:,.0f}")
            
            if criteria.get('min_volatility') and volatility < criteria['min_volatility']:
                passes = False
                reasons.append(f"Volatility too low: {volatility:.1f}% < {criteria['min_volatility']}%")
            
            if criteria.get('max_volatility') and volatility > criteria['max_volatility']:
                passes = False
                reasons.append(f"Volatility too high: {volatility:.1f}% > {criteria['max_volatility']}%")
            
            if criteria.get('min_volume_ratio') and volume_ratio < criteria['min_volume_ratio']:
                passes = False
                reasons.append(f"Volume ratio too low: {volume_ratio:.2f}x < {criteria['min_volume_ratio']}x")
            
            if criteria.get('rsi_min') and rsi_14 < criteria['rsi_min']:
                passes = False
                reasons.append(f"RSI too low: {rsi_14:.1f} < {criteria['rsi_min']}")
            
            if criteria.get('rsi_max') and rsi_14 > criteria['rsi_max']:
                passes = False
                reasons.append(f"RSI too high: {rsi_14:.1f} > {criteria['rsi_max']}")
            
            if criteria.get('trend_filter') and criteria['trend_filter'] != 'all':
                if criteria['trend_filter'] == 'uptrend' and trend not in ['uptrend', 'strong_uptrend']:
                    passes = False
                    reasons.append(f"Not in uptrend: {trend}")
                elif criteria['trend_filter'] == 'downtrend' and trend not in ['downtrend', 'strong_downtrend']:
                    passes = False
                    reasons.append(f"Not in downtrend: {trend}")
            
            if criteria.get('above_sma20') and current_price < sma_20:
                passes = False
                reasons.append(f"Below 20 SMA: ${current_price:.2f} < ${sma_20:.2f}")
            
            if criteria.get('above_sma50') and current_price < sma_50:
                passes = False
                reasons.append(f"Below 50 SMA: ${current_price:.2f} < ${sma_50:.2f}")
            
            if not passes:
                return None
            
            # Calculate score (higher = better setup)
            score = 0
            
            # Volume bonus
            if volume_ratio > 1.5:
                score += 2
            elif volume_ratio > 1.2:
                score += 1
            
            # Trend bonus
            if trend == "strong_uptrend":
                score += 3
            elif trend == "uptrend":
                score += 2
            elif trend == "neutral":
                score += 1
            
            # RSI optimal range
            if 30 <= rsi_14 <= 70:
                score += 1
            if 40 <= rsi_14 <= 60:
                score += 1
            
            # ATR % range (good for day/swing trading)
            if 1.5 <= atr_percent <= 5.0:
                score += 2
            
            # Distance to support (for long setups)
            if distance_to_support < 5.0:
                score += 2
            elif distance_to_support < 10.0:
                score += 1
            
            return {
                'ticker': ticker,
                'current_price': round(current_price, 2),
                'change_pct': round(change_pct, 2),
                'volume': int(volume.iloc[-1]),
                'avg_volume': int(avg_volume_20),
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
                'dist_to_support': round(distance_to_support, 1),
                'dist_to_resistance': round(distance_to_resistance, 1),
                'adr_percent': round(adr_percent, 1),
                'score': score
            }
            
        except Exception as e:
            return None
    
    def scan_all(self, criteria: Dict) -> List[Dict]:
        """Scan all tickers and return results"""
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
        
        # Sort by score (highest first)
        results.sort(key=lambda x: x['score'], reverse=True)
        
        return results


# ============================================================================
# DEFAULT WATCHLISTS
# ============================================================================

DEFAULT_WATCHLISTS = {
    "Major ETFs": ["SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "SLV", "USO", "XLF", "XLK"],
    "Tech Giants": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX", "ADBE", "CRM"],
    "Semiconductors": ["NVDA", "AMD", "INTC", "AVGO", "TXN", "QCOM", "MU", "AMAT", "LRCX", "KLAC"],
    "Financials": ["JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP", "V"],
    "Healthcare": ["JNJ", "PFE", "MRK", "ABBV", "LLY", "TMO", "DHR", "ABT", "BMY", "AMGN"],
    "Consumer": ["WMT", "AMZN", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "COST", "TJX"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "PXD", "OXY", "MPC", "VLO", "PSX"],
    "High Volume Stocks": ["AAPL", "TSLA", "NVDA", "AMD", "AMZN", "META", "MSFT", "GOOGL", "NFLX", "PLTR"],
    "Swing Trading": ["AAPL", "MSFT", "NVDA", "TSLA", "META", "AMZN", "GOOGL", "AMD", "NFLX", "CRM"],
    "Volatile Stocks": ["TSLA", "NVDA", "AMD", "PLTR", "COIN", "RIVN", "LCID", "MARA", "RIOT", "GME"]
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
    .metric-good { color: #22c55e; }
    .metric-warning { color: #f59e0b; }
    .metric-bad { color: #ef4444; }
    .trend-up { color: #22c55e; font-weight: 600; }
    .trend-down { color: #ef4444; font-weight: 600; }
    .trend-neutral { color: #f59e0b; font-weight: 600; }
    .score-high { background: #22c55e; color: white; padding: 2px 8px; border-radius: 20px; }
    .score-medium { background: #f59e0b; color: white; padding: 2px 8px; border-radius: 20px; }
    .score-low { background: #ef4444; color: white; padding: 2px 8px; border-radius: 20px; }
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
# SIDEBAR - SCAN CRITERIA
# ============================================================================

with st.sidebar:
    st.header("🔍 Scan Criteria")
    
    # Watchlist selection
    st.subheader("📋 Watchlist")
    watchlist_option = st.selectbox(
        "Select Watchlist",
        list(DEFAULT_WATCHLISTS.keys()) + ["Custom"]
    )
    
    if watchlist_option == "Custom":
        custom_tickers = st.text_area(
            "Enter tickers (comma or space separated)",
            value="AAPL, MSFT, NVDA, TSLA, AMZN, GOOGL, META",
            height=100
        )
        # Parse tickers
        tickers = [t.strip().upper() for t in custom_tickers.replace(',', ' ').split() if t.strip()]
    else:
        tickers = DEFAULT_WATCHLISTS[watchlist_option]
        st.info(f"Scanning {len(tickers)} tickers")
    
    st.divider()
    
    # Price filters
    st.subheader("💰 Price Filters")
    col1, col2 = st.columns(2)
    with col1:
        min_price = st.number_input("Min Price ($)", value=10.0, step=1.0, format="%.2f")
    with col2:
        max_price = st.number_input("Max Price ($)", value=1000.0, step=10.0, format="%.2f")
    
    st.divider()
    
    # Volume filters
    st.subheader("📊 Volume Filters")
    min_volume = st.number_input("Min Avg Volume", value=1000000, step=100000, format="%.0f")
    min_volume_ratio = st.slider("Min Volume Ratio (vs 20-day avg)", 0.5, 3.0, 1.0, 0.1)
    
    st.divider()
    
    # Technical filters
    st.subheader("📈 Technical Filters")
    
    trend_filter = st.selectbox(
        "Trend Direction",
        ["all", "uptrend", "downtrend"],
        format_func=lambda x: {
            "all": "All",
            "uptrend": "Uptrend Only",
            "downtrend": "Downtrend Only"
        }[x]
    )
    
    above_sma20 = st.checkbox("Price > 20 SMA", value=False)
    above_sma50 = st.checkbox("Price > 50 SMA", value=False)
    
    col1, col2 = st.columns(2)
    with col1:
        rsi_min = st.number_input("RSI Min", value=30.0, step=1.0, format="%.1f")
    with col2:
        rsi_max = st.number_input("RSI Max", value=70.0, step=1.0, format="%.1f")
    
    st.divider()
    
    # Volatility filters
    st.subheader("📉 Volatility Filters")
    col1, col2 = st.columns(2)
    with col1:
        min_volatility = st.number_input("Min Volatility %", value=20.0, step=5.0, format="%.1f")
    with col2:
        max_volatility = st.number_input("Max Volatility %", value=100.0, step=5.0, format="%.1f")
    
    st.divider()
    
    # Scan button
    scan_button = st.button("🔍 Run Scanner", type="primary", use_container_width=True)

# ============================================================================
# MAIN CONTENT
# ============================================================================

st.markdown('<h1 class="scan-header">🔍 Trading Scanner</h1>', unsafe_allow_html=True)
st.caption("Find high-probability setups based on technical criteria")

if scan_button:
    # Build criteria dict
    criteria = {
        'min_price': min_price,
        'max_price': max_price,
        'min_volume': min_volume,
        'min_volume_ratio': min_volume_ratio,
        'trend_filter': trend_filter,
        'above_sma20': above_sma20,
        'above_sma50': above_sma50,
        'rsi_min': rsi_min,
        'rsi_max': rsi_max,
        'min_volatility': min_volatility,
        'max_volatility': max_volatility
    }
    
    # Run scanner
    scanner = StockScanner(tickers)
    results = scanner.scan_all(criteria)
    
    if results:
        st.success(f"✅ Found {len(results)} setups matching criteria")
        
        # Convert to DataFrame for display
        df_results = pd.DataFrame(results)
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Scanned", len(tickers))
        with col2:
            st.metric("Setups Found", len(results))
        with col3:
            hit_rate = (len(results) / len(tickers)) * 100 if tickers else 0
            st.metric("Hit Rate", f"{hit_rate:.1f}%")
        with col4:
            avg_score = df_results['score'].mean() if len(df_results) > 0 else 0
            st.metric("Avg Score", f"{avg_score:.1f}")
        
        st.divider()
        
        # Display results table
        st.subheader("📊 Scan Results")
        
        # Format for display
        display_cols = ['ticker', 'current_price', 'change_pct', 'volume_ratio', 
                       'atr_percent', 'rsi', 'trend', 'dist_to_support', 'score']
        
        display_df = df_results[display_cols].copy()
        display_df.columns = ['Ticker', 'Price', 'Change %', 'Vol Ratio', 
                             'ATR %', 'RSI', 'Trend', 'Dist to Sup %', 'Score']
        
        # Apply styling
        def style_trend(val):
            if val in ['strong_uptrend', 'uptrend']:
                return 'color: #22c55e; font-weight: 600'
            elif val in ['strong_downtrend', 'downtrend']:
                return 'color: #ef4444; font-weight: 600'
            return 'color: #f59e0b'
        
        def style_score(val):
            if val >= 8:
                return 'background-color: #22c55e; color: white; padding: 4px 8px; border-radius: 12px;'
            elif val >= 5:
                return 'background-color: #f59e0b; color: white; padding: 4px 8px; border-radius: 12px;'
            return 'background-color: #ef4444; color: white; padding: 4px 8px; border-radius: 12px;'
        
        styled_df = display_df.style.applymap(style_trend, subset=['Trend'])\
                                  .applymap(style_score, subset=['Score'])\
                                  .format({
                                      'Price': '${:.2f}',
                                      'Change %': '{:+.2f}%',
                                      'Vol Ratio': '{:.2f}x',
                                      'ATR %': '{:.2f}%',
                                      'RSI': '{:.1f}',
                                      'Dist to Sup %': '{:.1f}%'
                                  })
        
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
        
        # Detailed view for selected ticker
        st.divider()
        st.subheader("🔎 Detailed View")
        
        selected_ticker = st.selectbox(
            "Select ticker for detailed analysis",
            [r['ticker'] for r in results]
        )
        
        if selected_ticker:
            detail = next(r for r in results if r['ticker'] == selected_ticker)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(f"""
                ### {detail['ticker']}
                **Price:** ${detail['current_price']:.2f}  
                **Change:** {detail['change_pct']:+.2f}%  
                **Score:** {detail['score']}/12
                """)
                
                # Score badge
                if detail['score'] >= 8:
                    st.success("⭐⭐⭐ High Quality Setup")
                elif detail['score'] >= 5:
                    st.warning("⭐⭐ Medium Quality Setup")
                else:
                    st.error("⭐ Low Quality Setup")
            
            with col2:
                st.markdown(f"""
                ### Technicals
                **RSI (14):** {detail['rsi']:.1f}  
                **ATR:** ${detail['atr']:.2f} ({detail['atr_percent']:.2f}%)  
                **Volatility:** {detail['volatility']:.1f}%
                """)
            
            with col3:
                st.markdown(f"""
                ### Levels
                **Support:** ${detail['support']:.2f} ({detail['dist_to_support']:.1f}% away)  
                **Resistance:** ${detail['resistance']:.2f} ({detail['dist_to_resistance']:.1f}% away)  
                **ADR %:** {detail['adr_percent']:.1f}%
                """)
            
            # Moving Averages
            st.markdown("### 📈 Moving Averages")
            ma_col1, ma_col2, ma_col3 = st.columns(3)
            
            with ma_col1:
                price = detail['current_price']
                sma20 = detail['sma_20']
                above20 = price > sma20
                st.metric(
                    "20 SMA",
                    f"${sma20:.2f}",
                    delta=f"{'Above' if above20 else 'Below'} by ${abs(price - sma20):.2f}"
                )
            
            with ma_col2:
                sma50 = detail['sma_50']
                above50 = price > sma50
                st.metric(
                    "50 SMA",
                    f"${sma50:.2f}",
                    delta=f"{'Above' if above50 else 'Below'} by ${abs(price - sma50):.2f}"
                )
            
            with ma_col3:
                sma200 = detail['sma_200']
                if sma200 > 0:
                    above200 = price > sma200
                    st.metric(
                        "200 SMA",
                        f"${sma200:.2f}",
                        delta=f"{'Above' if above200 else 'Below'} by ${abs(price - sma200):.2f}"
                    )
            
            # Volume Analysis
            st.markdown("### 📊 Volume Analysis")
            st.markdown(f"""
            - **Current Volume:** {detail['volume']:,} shares
            - **20-Day Avg Volume:** {detail['avg_volume']:,} shares
            - **Volume Ratio:** {detail['volume_ratio']:.2f}x average
            """)
            
            if detail['volume_ratio'] >= 2.0:
                st.success("🔥 High relative volume - increased interest")
            elif detail['volume_ratio'] >= 1.5:
                st.info("📈 Above average volume")
            elif detail['volume_ratio'] >= 1.0:
                st.warning("📊 Average volume")
            else:
                st.error("📉 Below average volume")
            
            # Trade Setup Notes
            st.markdown("### 📝 Trade Setup Notes")
            
            notes = []
            
            if detail['trend'] in ['strong_uptrend', 'uptrend']:
                notes.append("✅ Stock is in an uptrend - favors long positions")
            elif detail['trend'] in ['strong_downtrend', 'downtrend']:
                notes.append("⚠️ Stock is in a downtrend - consider short or wait")
            
            if detail['dist_to_support'] < 5:
                notes.append(f"✅ Near support (${detail['support']:.2f}) - potential bounce area")
            elif detail['dist_to_resistance'] < 5:
                notes.append(f"⚠️ Near resistance (${detail['resistance']:.2f}) - potential reversal area")
            
            if 30 <= detail['rsi'] <= 70:
                notes.append("✅ RSI in neutral range")
            elif detail['rsi'] < 30:
                notes.append("🟢 RSI oversold - potential bounce")
            elif detail['rsi'] > 70:
                notes.append("🔴 RSI overbought - potential pullback")
            
            if 1.5 <= detail['atr_percent'] <= 5.0:
                notes.append(f"✅ ATR {detail['atr_percent']:.1f}% - good for day/swing trading")
            elif detail['atr_percent'] > 5.0:
                notes.append(f"⚠️ High volatility (ATR {detail['atr_percent']:.1f}%) - use wider stops")
            
            for note in notes:
                st.markdown(f"- {note}")
            
            # Link to Exit Planner
            st.divider()
            st.markdown("### 🎯 Next Steps")
            st.markdown(f"""
            Ready to plan your exit for **{detail['ticker']}**?
            
            1. Use the **Exit Strategy Command Center** to calculate stops and targets
            2. Suggested entry: **${detail['current_price']:.2f}**
            3. Suggested stop: **${detail['support']:.2f}** (support level)
            """)
            
            # Export
            export_data = {
                'ticker': detail['ticker'],
                'scan_date': datetime.now().isoformat(),
                'price': detail['current_price'],
                'score': detail['score'],
                'trend': detail['trend'],
                'support': detail['support'],
                'resistance': detail['resistance'],
                'atr': detail['atr'],
                'rsi': detail['rsi']
            }
            
            st.download_button(
                label=f"📥 Export {detail['ticker']} Setup",
                data=json.dumps(export_data, indent=2),
                file_name=f"{detail['ticker']}_setup_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )
    
    else:
        st.warning("⚠️ No setups found matching your criteria. Try relaxing filters.")

else:
    # Show instructions when no scan has been run
    st.info("👈 Configure scan criteria in the sidebar and click 'Run Scanner' to begin")
    
    st.markdown("""
    ### 📋 How to Use This Scanner
    
    1. **Select a watchlist** from the sidebar or enter custom tickers
    2. **Set your filters**:
       - Price range
       - Minimum volume
       - Trend direction
       - Technical indicators (RSI, moving averages)
       - Volatility parameters
    3. **Click 'Run Scanner'** to find matching setups
    4. **Review results** sorted by quality score
    5. **Click any ticker** for detailed analysis
    6. **Export setups** for further analysis in the Exit Strategy Command Center
    
    ### 🎯 What Makes a Good Setup?
    
    | Criteria | Ideal Range | Why |
    |---|---|---|
    | **Volume Ratio** | > 1.5x | Shows increased interest |
    | **ATR %** | 1.5% - 5% | Enough movement for profit |
    | **RSI** | 30 - 70 | Not overextended |
    | **Distance to Support** | < 5% | Clear stop loss level |
    | **Trend** | Strong Uptrend | Momentum on your side |
    
    ### ⭐ Scoring System
    
    - **8-12 points:** High quality setup - strong consideration
    - **5-7 points:** Medium quality - review carefully
    - **0-4 points:** Low quality - consider passing
    """)

# Footer
st.divider()
st.caption("🔍 Trading Scanner — Find setups. Plan exits. Trade with confidence.")