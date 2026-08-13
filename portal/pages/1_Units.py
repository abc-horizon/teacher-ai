import os
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from sqlmodel import Session, select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db import get_engine
from app.models import Unit

load_dotenv()

st.set_page_config(page_title="Units")

st.caption(
    f"Environment: {os.getenv('APP_ENV', 'development').upper()} (local sample data)"
)
st.markdown("**اقتراح آلي — القرار للمدرّس**")

st.header("Units")

engine = get_engine()
with Session(engine) as session:
    units = session.exec(select(Unit)).all()

if not units:
    st.info("No units found. Run scripts/seed_dev_db.py first.")
else:
    for unit in units:
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"**{unit.zoho_unit_id}** — {unit.name}")
        with col2:
            if st.button("Open", key=f"unit-{unit.id}"):
                st.session_state["selected_unit_id"] = unit.id
                st.switch_page("pages/2_Assignments.py")
