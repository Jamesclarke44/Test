import streamlit as st

st.title("Diagnostic Test App")

st.write("App loaded successfully.")

st.write("Python version OK.")
st.write("Streamlit version OK.")

try:
    import pandas as pd
    st.write("Pandas imported:", pd.__version__)
except Exception as e:
    st.error(f"Pandas import failed: {e}")

try:
    import numpy as np
    st.write("Numpy imported:", np.__version__)
except Exception as e:
    st.error(f"Numpy import failed: {e}")

try:
    import yfinance as yf
    st.write("yfinance imported:", yf.__version__)
except Exception as e:
    st.error(f"yfinance import failed: {e}")

st.success("If you see this message, the app is running.")
