import streamlit as st

st.set_page_config(page_title="Test Lab", layout="centered")

st.title("🧪 Test App")
st.write("This is your testing environment.")

st.subheader("Status")
st.success("App is running successfully!")

# Simple input to confirm interactivity
test_input = st.text_input("Type something to test:")

if test_input:
    st.write(f"You entered: {test_input}")