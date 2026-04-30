import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st

DATA_DIR     = os.path.join(os.path.dirname(__file__), "data")
RESULTS_PATH = os.path.join(DATA_DIR, "results.json")
KST          = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="SCREENER",
    page_icon="▣",
    layout="wide",
)

# ── 글로벌 CSS ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Space Grotesk', monospace;
}

/* 전체 배경 */
.stApp { background-color: #1A1A1A; }

/* 헤더 */
.header-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 28px 0 20px 0;
    border-bottom: 1px solid #2E2E2E;
    margin-bottom: 24px;
}
.site-title {
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    color: #D1FF00;
    text-transform: uppercase;
}
.updated-badge {
    font-size: 0.72rem;
    color: #555;
    letter-spacing: 0.05em;
    margin-top: 4px;
}

/* 수동 갱신 버튼 */
div[data-testid="stButton"] > button {
    background: transparent;
    border: 1px solid #D1FF00;
    color: #D1FF00;
    font-weight: 600;
    letter-spacing: 0.1em;
    font-size: 0.78rem;
    padding: 8px 20px;
    border-radius: 2px;
    transition: all 0.2s ease;
}
div[data-testid="stButton"] > button:hover {
    background: #D1FF00;
    color: #1A1A1A;
}

/* 시장 필터 라디오 */
div[data-testid="stRadio"] label {
    font-size: 0.8rem;
    letter-spacing: 0.08em;
    color: #888;
}
div[data-testid="stRadio"] label[data-selected="true"] {
    color: #D1FF00 !important;
}

/* 탭 */
button[data-baseweb="tab"] {
    font-size: 0.82rem;
    letter-spacing: 0.1em;
    font-weight: 600;
    color: #555 !important;
    border-bottom: 2px solid transparent;
    text-transform: uppercase;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #D1FF00 !important;
    border-bottom: 2px solid #D1FF00 !important;
}

/* 섹션 제목 */
.section-label {
    font-size: 0.72rem;
    letter-spacing: 0.2em;
    color: #555;
    text-transform: uppercase;
    margin: 28px 0 12px 0;
}
.section-label span {
    color: #D1FF00;
    margin-right: 8px;
}

/* 테이블 */
.stock-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
    margin-bottom: 8px;
}
.stock-table th {
    text-align: left;
    padding: 10px 14px;
    font-size: 0.68rem;
    letter-spacing: 0.14em;
    color: #444;
    text-transform: uppercase;
    border-bottom: 1px solid #2A2A2A;
}
.stock-table td {
    padding: 11px 14px;
    border-bottom: 1px solid #222;
    color: #C8C8C8;
    vertical-align: middle;
}
.stock-table tr:hover td { background: #202020; }
.stock-table tr:last-child td { border-bottom: none; }

.dist-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 2px;
    font-weight: 600;
    font-size: 0.78rem;
}
.dist-near  { background: #1e2a00; color: #D1FF00; }
.dist-ok    { background: #1a1a1a; color: #888; border: 1px solid #2e2e2e; }
.dist-over  { background: #0d1f00; color: #6aad00; }

.ticker-name { font-weight: 600; color: #E8E8E8; font-family: 'DM Mono', monospace; letter-spacing: 0.04em; }
.ticker-code { font-size: 0.7rem; color: #444; margin-left: 6px; font-family: 'DM Mono', monospace; }
.flag        { font-size: 1rem; }

.chart-link a { color: #444; font-size: 0.75rem; text-decoration: none; letter-spacing: 0.05em; }
.chart-link a:hover { color: #D1FF00; }

.count-badge {
    display: inline-block;
    background: #242424;
    color: #555;
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    padding: 2px 8px;
    border-radius: 2px;
    margin-left: 8px;
}

/* info/warning 박스 제거하고 미니멀하게 */
.stAlert { background: #242424 !important; border: 1px solid #2E2E2E !important; border-radius: 2px !important; }

/* 구분선 */
hr { border-color: #242424 !important; margin: 20px 0 !important; }

/* 스크롤바 */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #1A1A1A; }
::-webkit-scrollbar-thumb { background: #333; border-radius: 2px; }
</style>
""", unsafe_allow_html=True)


# ── 비밀번호 인증 ────────────────────────────────────────────
def check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True
    st.markdown('<div style="max-width:320px;margin:120px auto;">', unsafe_allow_html=True)
    st.markdown('<div class="site-title" style="margin-bottom:32px;">SCREENER</div>', unsafe_allow_html=True)
    pw = st.text_input("", type="password", placeholder="PASSWORD", key="pw_input")
    if pw:
        if pw == st.secrets.get("APP_PASSWORD", "changeme"):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.markdown('<div style="color:#ff4444;font-size:0.8rem;margin-top:8px;">incorrect password</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    return False

if not check_password():
    st.stop()


# ── 데이터 로드 ──────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_results() -> dict:
    if not os.path.exists(RESULTS_PATH):
        return {}
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)

def manual_refresh():
    python = sys.executable
    base   = os.path.dirname(__file__)
    try:
        subprocess.run([python, os.path.join(base, "fetch_data.py"), "--market", "all"],
                       check=True, capture_output=True, text=True)
        subprocess.run([python, os.path.join(base, "signals.py")],
                       check=True, capture_output=True, text=True)
        st.cache_data.clear()
    except subprocess.CalledProcessError as e:
        st.error(e.stderr[-400:] if e.stderr else "갱신 실패")


# ── 헤더 ─────────────────────────────────────────────────────
results = load_results()

gen_str = ""
if results:
    try:
        dt = datetime.fromisoformat(results["generated_at"]).astimezone(KST)
        gen_str = dt.strftime("LAST UPDATE  %Y.%m.%d  %H:%M KST")
    except Exception:
        pass

col_title, col_filter, col_btn = st.columns([4, 3, 1])

with col_title:
    st.markdown(f"""
        <div class="site-title">SCREENER</div>
        <div class="updated-badge">{gen_str or "NO DATA — CLICK REFRESH"}</div>
    """, unsafe_allow_html=True)

with col_filter:
    st.markdown("<div style='padding-top:14px'>", unsafe_allow_html=True)
    market_filter = st.radio("", ["ALL", "KR", "US"], horizontal=True,
                             label_visibility="collapsed")
    st.markdown("</div>", unsafe_allow_html=True)

with col_btn:
    st.markdown("<div style='padding-top:12px'>", unsafe_allow_html=True)
    if st.button("REFRESH", use_container_width=True):
        with st.spinner(""):
            manual_refresh()
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)


# ── 테이블 렌더 ──────────────────────────────────────────────
MARKET_FLAG = {"KR": "🇰🇷", "US": "🇺🇸"}

def chart_url(ticker: str, market: str) -> str:
    # 한국·미국 모두 토스증권 — 모바일에서 앱 설치 시 자동으로 앱 오픈
    return f"https://tossinvest.com/stocks/{ticker}"

def fmt_price(v: float, market: str) -> str:
    return f"{v:,.0f}" if market == "KR" else f"{v:,.2f}"

def fmt_cap(row: dict) -> str:
    if row["market"] == "KR" and row.get("market_cap_krw"):
        return f"{row['market_cap_krw'] // 100_000_000:,}억"
    if row["market"] == "US" and row.get("market_cap_usd"):
        return f"${row['market_cap_usd'] // 1_000_000:,}M"
    return "—"

def dist_pill(val: float) -> str:
    cls = "dist-near" if 0 <= val <= 1 else ("dist-over" if val < 0 else "dist-ok")
    sign = "+" if val > 0 else ""
    return f'<span class="dist-pill {cls}">{sign}{val:.2f}%</span>'

def render_table(rows: list, dist_key: str, ref_key: str, ref_label: str, mkt_filter: str):
    mkt_map = {"KR": "KR", "US": "US", "ALL": None}
    filt = mkt_map[mkt_filter]
    if filt:
        rows = [r for r in rows if r["market"] == filt]
    if not rows:
        st.markdown('<div style="color:#444;font-size:0.82rem;padding:16px 0;">No signals found.</div>',
                    unsafe_allow_html=True)
        return

    currency = {"KR": "KRW", "US": "USD"}
    rows_html = ""
    for r in rows:
        mkt    = r["market"]
        flag   = MARKET_FLAG.get(mkt, mkt)
        ticker = r["ticker"]
        name   = r.get("name", ticker)
        cur    = currency.get(mkt, "")
        price  = fmt_price(r["close"], mkt)
        ref    = fmt_price(r[ref_key], mkt)
        top    = fmt_price(r["cloud_top"], mkt)
        cap    = fmt_cap(r)
        dist   = dist_pill(r[dist_key])
        url    = chart_url(ticker, mkt)

        rows_html += f"""
        <tr>
          <td class="flag">{flag}</td>
          <td><span class="ticker-name">{name}</span><span class="ticker-code">{ticker}</span></td>
          <td>{price} <span style="color:#3a3a3a;font-size:0.7rem">{cur}</span></td>
          <td style="color:#555">{cap}</td>
          <td style="color:#aaa">{ref}</td>
          <td style="color:#666">{top}</td>
          <td>{dist}</td>
          <td class="chart-link"><a href="{url}" target="_blank">TOSS ↗</a></td>
        </tr>"""

    table_html = f"""
    <table class="stock-table">
      <thead><tr>
        <th></th><th>TICKER</th><th>PRICE</th><th>MKTCAP</th>
        <th>{ref_label}</th><th>CLOUD TOP</th><th>DIST%</th><th></th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
    <div style="color:#333;font-size:0.7rem;letter-spacing:0.1em;margin-top:6px">{len(rows)} RESULTS</div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


def section(label: str, icon: str, rows: list, dist_key: str,
            ref_key: str, ref_label: str, mkt_filter: str):
    st.markdown(f'<div class="section-label"><span>{icon}</span>{label}</div>',
                unsafe_allow_html=True)
    render_table(rows, dist_key, ref_key, ref_label, mkt_filter)


# ── 탭 ───────────────────────────────────────────────────────
signals = results.get("signals", {})
tab_a, tab_b = st.tabs(["MA20  BREAKOUT", "PRICE  BREAKOUT"])

with tab_a:
    section("BREAKOUT  CONFIRMED", "▲", signals.get("A1", []),
            "dist_a_pct", "ma20", "MA20", market_filter)
    st.markdown("<hr>", unsafe_allow_html=True)
    section("APPROACHING  CLOUD  TOP  — WITHIN 1%", "◎", signals.get("A2", []),
            "dist_a_pct", "ma20", "MA20", market_filter)

with tab_b:
    section("BREAKOUT  CONFIRMED", "▲", signals.get("B1", []),
            "dist_b_pct", "close", "CLOSE", market_filter)
    st.markdown("<hr>", unsafe_allow_html=True)
    section("APPROACHING  CLOUD  TOP  — WITHIN 1%", "◎", signals.get("B2", []),
            "dist_b_pct", "close", "CLOSE", market_filter)
