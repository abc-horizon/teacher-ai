import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="BTEC AI Assessment Assistant")

st.caption(
    f"Environment: {os.getenv('APP_ENV', 'development').upper()} (local sample data)"
)
st.markdown("**اقتراح آلي — القرار للمدرّس**")

st.title("BTEC AI Assessment Assistant")

st.write(
    "استخدم القائمة الجانبية للتنقل بين الصفحات: ابدأ من صفحة **Units** لاختيار "
    "الوحدة، ثم **Assignments** لاختيار الواجب، ثم **Submissions** لعرض قائمة "
    "التسليمات، وأخيرًا **Submission Detail** لعرض النص المستخرج والمعايير "
    "لتسليم واحد."
)
