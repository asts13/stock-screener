"""
STOCKal — 한·미 주식 스크리너
MA20 구름대 돌파 / MA200 근접 신호 탐지
"""
import streamlit as st

st.set_page_config(
    page_title="STOCKal",
    page_icon="▣",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif !important; }
.stApp { background: #0A0E1A !important; }
</style>
""", unsafe_allow_html=True)

st.markdown(
    '<h1 style="color:#C6F135;font-size:2rem;font-weight:700;letter-spacing:-0.03em">'
    'STOCK<em style="font-style:normal">al</em></h1>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="color:#8892A4;font-size:0.9rem">Phase 1 완료 — 개발 진행 중</p>',
    unsafe_allow_html=True,
)
