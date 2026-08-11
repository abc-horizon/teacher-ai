import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.title("BTEC AI Assessment Assistant")
st.write(f"Environment: {os.getenv('APP_ENV', 'unknown')}")
