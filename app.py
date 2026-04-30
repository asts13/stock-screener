"""
app.py  —  일목균형표 구름 돌파 스크리너
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
DATA_DIR     = os.path.join(os.path.dirname(__file__), "data")
RESULTS_PATH = os.path.join(DATA_DIR, "results.json")
KST          = timezone(timedelta(hours=9))


# ─────────────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="일목 구름 스크리너",
    page_icon="☁️",
    layout="wide",
)


# ─────────────────────────────────────────────
# 비밀번호 인증
# ─────────────────────────────────────────────
def check_password() -> bool:
    """비밀번호가 맞으면 True. 세션 내에서 1회만 입력."""
    if st.session_state.get("authenticated"):
        return True

    st.title("☁️ 일목 구름 스크리너")
    pw = st.text_input("비밀번호를 입력하세요", type="password", key="pw_input")
    if pw:
        correct = st.secrets.get("APP_PASSWORD", "changeme")
        if pw == correct:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")
    return False

if not check_password():
    st.stop()


# ─────────────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_results() -> dict:
    if not os.path.exists(RESULTS_PATH):
        return {}
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def manual_refresh():
    """수동 갱신: fetch_data.py → signals.py 순서로 실행."""
    with st.spinner("데이터 수집 중... (수 분 소요될 수 있습니다)"):
        python = sys.executable
        base   = os.path.dirname(__file__)
        try:
            subprocess.run(
                [python, os.path.join(base, "fetch_data.py"), "--market", "all"],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                [python, os.path.join(base, "signals.py")],
                check=True, capture_output=True, text=True,
            )
            st.cache_data.clear()
            st.success("갱신 완료!")
        except subprocess.CalledProcessError as e:
            st.error(f"갱신 실패: {e.stderr[-500:]}")


# ─────────────────────────────────────────────
# 헤더
# ─────────────────────────────────────────────
st.title("☁️ 일목 구름 돌파 스크리너")

results = load_results()

col_info, col_filter, col_btn = st.columns([3, 2, 1])

with col_info:
    if results:
        gen_at = results.get("generated_at", "")
        try:
            dt = datetime.fromisoformat(gen_at).astimezone(KST)
            st.caption(f"마지막 갱신: {dt.strftime('%Y-%m-%d %H:%M KST')}")
        except Exception:
            st.caption(f"마지막 갱신: {gen_at}")
    else:
        st.caption("데이터 없음 — 아래 '수동 갱신' 버튼을 눌러주세요.")

with col_filter:
    market_filter = st.radio(
        "시장 필터",
        ["전체", "한국만", "미국만"],
        horizontal=True,
        label_visibility="collapsed",
    )

with col_btn:
    if st.button("🔄 수동 갱신", use_container_width=True):
        manual_refresh()
        st.rerun()

st.divider()


# ─────────────────────────────────────────────
# 테이블 빌더
# ─────────────────────────────────────────────
MARKET_MAP = {"KR": "🇰🇷", "US": "🇺🇸"}

def chart_link(ticker: str, market: str) -> str:
    if market == "KR":
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    else:
        url = f"https://finance.yahoo.com/quote/{ticker}"
    return f"[차트]({url})"

def fmt_cap(row: dict) -> str:
    if row["market"] == "KR" and row.get("market_cap_krw"):
        return f"{row['market_cap_krw'] // 100_000_000:,}억원"
    if row["market"] == "US" and row.get("market_cap_usd"):
        return f"${row['market_cap_usd'] // 1_000_000:,}M"
    return "-"

def fmt_price(value: float, market: str) -> str:
    if market == "KR":
        return f"{value:,.0f}원"
    return f"${value:,.2f}"

def build_table(rows: list[dict], dist_col: str, ref_col: str,
                ref_label: str, market_filter: str) -> pd.DataFrame:
    """시그널 행 목록 → 표시용 DataFrame."""
    if market_filter == "한국만":
        rows = [r for r in rows if r["market"] == "KR"]
    elif market_filter == "미국만":
        rows = [r for r in rows if r["market"] == "US"]

    if not rows:
        return pd.DataFrame()

    records = []
    for r in rows:
        mkt    = r["market"]
        ticker = r["ticker"]
        name   = r.get("name", ticker)
        dist   = r.get(dist_col, 0)

        records.append({
            "시장":          MARKET_MAP.get(mkt, mkt),
            "종목명":        f"{name} ({ticker})",
            "현재가":        fmt_price(r["close"], mkt),
            "시총":          fmt_cap(r),
            ref_label:      fmt_price(r[ref_col], mkt),
            "구름 상단":     fmt_price(r["cloud_top"], mkt),
            "거리(%)":       f"{dist:+.2f}%",
            "차트":          chart_link(ticker, mkt),
        })

    return pd.DataFrame(records)


def show_section(title: str, rows: list[dict], dist_col: str,
                 ref_col: str, ref_label: str, market_filter: str):
    st.subheader(title)
    df = build_table(rows, dist_col, ref_col, ref_label, market_filter)
    if df.empty:
        st.info("해당 조건의 종목이 없습니다.")
        return
    st.markdown(
        df.to_markdown(index=False),
        unsafe_allow_html=True,
    )
    st.caption(f"총 {len(df)}종목")


# ─────────────────────────────────────────────
# 탭
# ─────────────────────────────────────────────
signals = results.get("signals", {})

tab_a, tab_b = st.tabs(["📈 탭 A — MA20 기준 돌파", "💹 탭 B — 종가 기준 돌파"])

with tab_a:
    show_section(
        "✅ A1 — MA20 돌파 완료 (오늘)",
        signals.get("A1", []),
        dist_col="dist_a_pct", ref_col="ma20", ref_label="MA20",
        market_filter=market_filter,
    )
    st.divider()
    show_section(
        "⏳ A2 — MA20 돌파 임박 (구름상단까지 1% 이내)",
        signals.get("A2", []),
        dist_col="dist_a_pct", ref_col="ma20", ref_label="MA20",
        market_filter=market_filter,
    )

with tab_b:
    show_section(
        "✅ B1 — 종가 돌파 완료 (오늘)",
        signals.get("B1", []),
        dist_col="dist_b_pct", ref_col="close", ref_label="종가",
        market_filter=market_filter,
    )
    st.divider()
    show_section(
        "⏳ B2 — 종가 돌파 임박 (구름상단까지 1% 이내)",
        signals.get("B2", []),
        dist_col="dist_b_pct", ref_col="close", ref_label="종가",
        market_filter=market_filter,
    )
