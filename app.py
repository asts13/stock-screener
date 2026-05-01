"""
STOCKal — Ichimoku Cloud Breakout Screener
"""
import hashlib, json, os, subprocess, sys, threading
from datetime import datetime, timezone, timedelta

import yfinance as yf
import pandas as pd
import streamlit as st

# ── 상수 ─────────────────────────────────────────────────────
DATA_DIR      = os.path.join(os.path.dirname(__file__), "data")
RESULTS_PATH  = os.path.join(DATA_DIR, "results.json")
USERS_PATH    = os.path.join(DATA_DIR, "users.json")
REFRESH_FLAG  = os.path.join(DATA_DIR, ".refreshing")
KST          = timezone(timedelta(hours=9))
PAGE_SIZE    = 15   # 모바일에서는 set_page_config 이후 8로 덮어씀
IS_MOBILE    = False

INDICES = [
    {"label_en": "KOSPI",     "label_ko": "코스피",       "ticker": "^KS11", "unit": ""},
    {"label_en": "KOSDAQ",    "label_ko": "코스닥",       "ticker": "^KQ11", "unit": ""},
    {"label_en": "NASDAQ",    "label_ko": "나스닥",       "ticker": "^IXIC", "unit": ""},
    {"label_en": "NQ100 FUT", "label_ko": "나스닥100선물", "ticker": "NQ=F",  "unit": ""},
    {"label_en": "S&P 500",   "label_ko": "S&P 500",      "ticker": "^GSPC", "unit": ""},
    {"label_en": "DOW",       "label_ko": "다우존스",     "ticker": "^DJI",  "unit": ""},
    {"label_en": "WTI",       "label_ko": "WTI유가",      "ticker": "CL=F",  "unit": "$"},
    {"label_en": "GOLD",      "label_ko": "금",           "ticker": "GC=F",  "unit": "$"},
    {"label_en": "USD/KRW",   "label_ko": "달러/원",      "ticker": "KRW=X", "unit": "₩"},
]

# ── i18n ─────────────────────────────────────────────────────
T = {
    "site":        {"en": "STOCKal",                  "ko": "STOCKal"},
    "last_update": {"en": "LAST UPDATE",              "ko": "마지막 갱신"},
    "no_data":     {"en": "NO DATA",                  "ko": "데이터 없음"},
    "refresh":     {"en": "REFRESH",                  "ko": "새로고침"},
    "all":         {"en": "ALL",                      "ko": "전체"},
    "kr":          {"en": "KR",                       "ko": "한국"},
    "us":          {"en": "US",                       "ko": "미국"},
    "market":      {"en": "MARKET",                   "ko": "시장"},
    "indices":     {"en": "MARKET INDICES",           "ko": "시장 지수"},
    "tab_a":       {"en": "MA20 · ICHIMOKU",          "ko": "MA20 · 일목"},
    "tab_b":       {"en": "PRICE BREAKOUT",           "ko": "종가 돌파"},
    "tab_c":       {"en": "MA200 PROXIMITY",          "ko": "200MA 근접"},
    "a1":          {"en": "BREAKOUT",                 "ko": "돌파 완료"},
    "a2":          {"en": "APPROACHING 1%",           "ko": "돌파 임박 1%"},
    "b1":          {"en": "BREAKOUT",                 "ko": "돌파 완료"},
    "b2":          {"en": "APPROACHING 1%",           "ko": "돌파 임박 1%"},
    "c1":          {"en": "ABOVE MA200 2%",           "ko": "200MA 위 2%"},
    "c2":          {"en": "BELOW MA200 2%",           "ko": "200MA 아래 2%"},
    "ticker":      {"en": "TICKER",                   "ko": "종목"},
    "price":       {"en": "PRICE",                    "ko": "현재가"},
    "mktcap":      {"en": "MKTCAP",                   "ko": "시총"},
    "ma20":        {"en": "MA20",                     "ko": "MA20"},
    "ma200":       {"en": "MA200",                    "ko": "MA200"},
    "cloud":       {"en": "CLOUD TOP",                "ko": "구름상단"},
    "dist":        {"en": "DIST%",                    "ko": "거리%"},
    "chg1d":       {"en": "1D",                       "ko": "1일"},
    "chg5d":       {"en": "5D",                       "ko": "5일"},
    "no_signal":   {"en": "No signals found.",        "ko": "해당 종목 없음"},
    "results":     {"en": "results",                  "ko": "종목"},
    "my":          {"en": "MY",                       "ko": "MY"},
    "login":       {"en": "LOG IN",                   "ko": "로그인"},
    "signup":      {"en": "SIGN UP",                  "ko": "회원가입"},
    "logout":      {"en": "LOG OUT",                  "ko": "로그아웃"},
    "username":    {"en": "Username",                 "ko": "아이디"},
    "password":    {"en": "Password",                 "ko": "비밀번호"},
    "watchlist":   {"en": "WATCHLIST",                "ko": "관심종목"},
    "entry_price": {"en": "ENTRY",                    "ko": "진입가"},
    "current":     {"en": "NOW",                      "ko": "현재가"},
    "return_pct":  {"en": "RETURN",                   "ko": "수익률"},
    "add_watch":   {"en": "ADD TO WATCHLIST",         "ko": "관심종목 추가"},
    "added_at":    {"en": "ADDED",                    "ko": "추가일"},
    "back":        {"en": "← BACK",                  "ko": "← 돌아가기"},
    "welcome":     {"en": "Welcome",                  "ko": "환영합니다"},
    "login_req":   {"en": "Log in to use watchlist.", "ko": "로그인 후 이용 가능합니다."},
    "no_watch":    {"en": "No stocks in watchlist.",  "ko": "관심종목이 없습니다."},
    "remove":      {"en": "✕",                        "ko": "✕"},
    "err_pw":      {"en": "Wrong password",           "ko": "비밀번호 오류"},
    "err_user":    {"en": "Username not found",       "ko": "존재하지 않는 아이디"},
    "err_dup":     {"en": "Username already taken",   "ko": "이미 사용 중인 아이디"},
    "ok_signup":   {"en": "Account created! Please log in.", "ko": "가입 완료! 로그인해주세요."},
}

def t(key: str) -> str:
    lang = st.session_state.get("lang", "en")
    return T.get(key, {}).get(lang, key)

# ── 페이지 설정 ───────────────────────────────────────────────
st.set_page_config(page_title="STOCKal", page_icon="▣", layout="wide")

# ── 모바일 감지 ───────────────────────────────────────────────
try:
    _ua = st.context.headers.get("user-agent", "")
    IS_MOBILE = any(x in _ua for x in ["iPhone", "Android", "Mobile", "iPod"])
    if IS_MOBILE:
        PAGE_SIZE = 8
except Exception:
    pass

# ── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
.stApp { background-color: #1A1A1A; }

.site-logo { font-size: 1.4rem; font-weight: 700; letter-spacing: 0.2em; color: #D1FF00; }
.updated-txt { font-size: 0.68rem; color: #3a3a3a; letter-spacing: 0.06em; }

/* 버튼 공통 */
div[data-testid="stButton"] > button {
    background: transparent; border: 1px solid #2a2a2a; color: #666;
    font-weight: 600; letter-spacing: 0.1em; font-size: 0.76rem;
    padding: 6px 10px; border-radius: 2px; transition: all 0.18s;
    width: 100%;
}
div[data-testid="stButton"] > button:hover { border-color: #D1FF00; color: #D1FF00; }

/* 시장 필터 라디오 */
div[data-testid="stRadio"] > div { gap: 6px; }
div[data-testid="stRadio"] label {
    font-size: 0.76rem; letter-spacing: 0.1em;
    color: #888; padding: 5px 18px !important;
    border: 1px solid #2a2a2a; border-radius: 2px;
}
div[data-testid="stRadio"] label:has(input:checked) {
    color: #000000 !important; background: #D1FF00 !important;
    border-color: #D1FF00 !important; font-weight: 700 !important;
}


/* 헤더 지수 가로띠 */
.hdr-idx-strip {
    display: flex; align-items: center;
    overflow: hidden; padding: 4px 0; height: 52px;
}
.hdr-idx {
    display: flex; flex-direction: column; align-items: flex-start; justify-content: center;
    flex: 1; min-width: 0;
    padding: 0 6px 0 0;
    border-right: 1px solid #2a2a2a; white-space: nowrap;
}
.hdr-idx:last-child { border-right: none; padding-right: 0; }
.hdr-idx-name { font-size: 0.58rem; letter-spacing: 0.06em; color: #888; text-transform: uppercase; }
.hdr-idx-val  { font-size: 0.78rem; font-family: 'DM Mono', monospace; color: #D0D0D0; font-weight: 500; }
.hdr-chg-pos  { font-size: 0.62rem; font-family: 'DM Mono', monospace; color: #D1FF00; }
.hdr-chg-neg  { font-size: 0.62rem; font-family: 'DM Mono', monospace; color: #ff5555; }

/* 섹션 레이블 */
.section-label {
    font-size: 0.66rem; letter-spacing: 0.22em; color: #3a3a3a;
    text-transform: uppercase; margin: 16px 0 10px 0;
}
.section-label span { color: #D1FF00; margin-right: 6px; }

/* 탭 */
button[data-baseweb="tab"] {
    font-size: 0.76rem; letter-spacing: 0.12em; font-weight: 600;
    color: #444 !important; text-transform: uppercase;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #D1FF00 !important; border-bottom: 2px solid #D1FF00 !important;
}

/* 종목 테이블 */
.stock-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.stock-table th {
    text-align: left; padding: 8px 12px;
    font-size: 0.64rem; letter-spacing: 0.16em; color: #383838;
    text-transform: uppercase; border-bottom: 1px solid #222;
}
.stock-table td { padding: 10px 12px; border-bottom: 1px solid #1f1f1f; color: #B0B0B0; }
.stock-table tr:hover td { background: #1f1f1f; }
.stock-table tr:last-child td { border-bottom: none; }
.tk-name { font-family: 'DM Mono', monospace; font-weight: 500; color: #E0E0E0; font-size: 0.82rem; }
.tk-code { font-family: 'DM Mono', monospace; font-size: 0.68rem; color: #404040; margin-left: 5px; }
.pill { display:inline-block; padding:2px 7px; border-radius:2px; font-family:'DM Mono',monospace; font-size:0.74rem; font-weight:500; }
.pill-near { background:#1a2800; color:#D1FF00; }
.pill-over { background:#0f1f00; color:#7acc00; }
.pill-neg  { background:#2a0000; color:#ff5555; }
.pill-neu  { background:#1e1e1e; color:#555; border:1px solid #2a2a2a; }
.toss-link a { color:#333; font-size:0.7rem; text-decoration:none; letter-spacing:0.06em; }
.toss-link a:hover { color:#D1FF00; }
.count-txt { color:#2e2e2e; font-size:0.66rem; letter-spacing:0.12em; margin-top:6px; }

/* MY 페이지 */
.my-header { font-size:1.1rem; font-weight:700; letter-spacing:0.18em; color:#D1FF00; margin-bottom:24px; }

/* 관심종목 (우하단) */
.ret-pos { color:#D1FF00; font-family:'DM Mono',monospace; font-size:0.8rem; }
.ret-neg { color:#ff5555; font-family:'DM Mono',monospace; font-size:0.8rem; }
.watch-name { font-family:'DM Mono',monospace; font-size:0.82rem; color:#E0E0E0; }
.watch-sub  { font-size:0.68rem; color:#383838; letter-spacing:0.04em; margin-top:2px; }

/* 새로고침 스피닝 아이콘 */
@keyframes spin { to { transform: rotate(-360deg); } }
.spin-icon {
    display: inline-block;
    animation: spin 1s linear infinite;
    color: #D1FF00; font-size: 1rem; line-height: 1;
}
.spin-wrap {
    text-align: center; padding: 6px 0;
    border: 1px solid #2a2a2a; border-radius: 2px;
}

hr { border-color:#1f1f1f !important; margin:14px 0 !important; }
.stAlert { background:#1e1e1e !important; border:1px solid #2a2a2a !important; border-radius:2px !important; }
::-webkit-scrollbar { width:3px; height:3px; }
::-webkit-scrollbar-thumb { background:#2a2a2a; }

/* ── 테이블 래퍼 ─────────────────────────── */
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }

/* 데스크탑: 모바일 테이블 숨김 */
.stock-table-m { display: none; }

/* ── 모바일 반응형 (iPhone 12 Pro 기준 390px) ── */
@media (max-width: 768px) {

    /* ① 헤더·콘텐츠 컬럼 세로 스택 */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }
    [data-testid="column"] {
        min-width: 100% !important;
        width: 100% !important;
        flex: 1 1 100% !important;
    }
    /* 중첩 컬럼(페이지 네비·관심종목행)은 가로 유지 */
    [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
    }
    [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] [data-testid="column"] {
        min-width: 0 !important;
        width: auto !important;
        flex: 1 1 0 !important;
    }

    /* ② 헤더 버튼 영역: 우측 정렬·compact */
    [data-testid="column"]:has(.btn-area-marker) [data-testid="stHorizontalBlock"] {
        justify-content: flex-end !important;
        gap: 4px !important;
        flex-wrap: nowrap !important;
    }
    [data-testid="column"]:has(.btn-area-marker) [data-testid="stHorizontalBlock"] [data-testid="column"] {
        flex: 0 0 52px !important;
        max-width: 52px !important;
        min-width: 0 !important;
        width: 52px !important;
    }
    /* 빈 첫 번째 스페이서 컬럼 숨김 */
    [data-testid="column"]:has(.btn-area-marker) [data-testid="stHorizontalBlock"] [data-testid="column"]:first-child {
        display: none !important;
    }

    /* ③ 지수 띠: 가로 스크롤 */
    .hdr-idx-strip {
        overflow-x: auto !important;
        overflow-y: hidden !important;
        height: auto !important;
        padding-bottom: 6px !important;
        -webkit-overflow-scrolling: touch;
    }
    .hdr-idx {
        flex: 0 0 auto !important;
        min-width: 70px !important;
    }

    /* ④ 테이블: 모바일 버전 표시 */
    .stock-table-d { display: none !important; }
    .stock-table-m { display: table !important; min-width: 400px; font-size: 0.74rem; }
    .stock-table-m th, .stock-table-m td { padding: 7px 8px; }

    /* ⑤ 버튼 패딩 축소 */
    div[data-testid="stButton"] > button {
        padding: 6px 4px !important;
        font-size: 0.74rem !important;
    }

    /* ⑥ 간격·크기 조정 */
    .section-label { margin: 8px 0 6px 0; }
    .site-logo { font-size: 1.15rem; }
}
</style>
""", unsafe_allow_html=True)

# ── 세션 초기화 ───────────────────────────────────────────────
_defaults = {
    "lang": "en", "page": "main", "user": None, "watchlist": [],
    "auth_tab": "login",
    "page_a1": 0, "page_a2": 0,
    "page_b1": 0, "page_b2": 0,
    "page_c1": 0, "page_c2": 0,
    "page_watch": 0, "_prev_mf": "BOOT",
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── 간이 유저 DB ─────────────────────────────────────────────
def load_users() -> dict:
    if os.path.exists(USERS_PATH):
        with open(USERS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_watchlist(username: str) -> list:
    return load_users().get(username, {}).get("watchlist", [])

def save_watchlist(username: str, wl: list):
    users = load_users()
    if username not in users:
        users[username] = {}
    users[username]["watchlist"] = wl
    save_users(users)


# ── 데이터 로드 ───────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_results() -> dict:
    if not os.path.exists(RESULTS_PATH):
        return {}
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)

@st.cache_data(ttl=300)
def fetch_indices() -> list:
    out = []
    tickers = [i["ticker"] for i in INDICES]
    try:
        # 5d: 휴장일·마감 후에도 최근 거래일 데이터 확보
        raw = yf.download(tickers, period="5d", auto_adjust=True,
                          progress=False, threads=True)
        for idx in INDICES:
            t_sym = idx["ticker"]
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    close = raw["Close"][t_sym].dropna()
                else:
                    close = raw["Close"].dropna()
                if len(close) < 2:
                    raise ValueError("short")
                val  = float(close.iloc[-1])   # 마지막 거래가
                prev = float(close.iloc[-2])   # 직전 거래가
                chg  = (val - prev) / prev * 100
                out.append({**idx, "val": val, "chg": chg})
            except Exception:
                out.append({**idx, "val": None, "chg": None})
    except Exception:
        out = [{**i, "val": None, "chg": None} for i in INDICES]
    return out

@st.cache_data(ttl=300)
def fetch_current_prices(yf_syms: tuple) -> dict:
    if not yf_syms:
        return {}
    try:
        raw = yf.download(list(yf_syms), period="2d", auto_adjust=True,
                          progress=False, threads=True)
        result = {}
        for sym in yf_syms:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    cp = float(raw["Close"][sym].dropna().iloc[-1])
                else:
                    cp = float(raw["Close"].dropna().iloc[-1])
                result[sym] = cp
            except Exception:
                result[sym] = None
        return result
    except Exception:
        return {}


# ── UI 헬퍼 ──────────────────────────────────────────────────
def _pill(val, mode: str = "dist") -> str:
    if val is None:
        return '<span class="pill pill-neu">—</span>'
    sign = "+" if val > 0 else ""
    if mode == "chg":
        cls = "pill-near" if val > 0 else "pill-neg"
    else:
        cls = "pill-near" if 0 <= val <= 2 else ("pill-over" if val < 0 else "pill-neu")
    return f'<span class="pill {cls}">{sign}{val:.2f}%</span>'


def _render_table(rows: list, dist_key: str, ref_key: str,
                  ref_label: str, tab_id: str, total: int = None):
    """이미 필터·페이지네이션된 rows 렌더링 (데스크탑·모바일 테이블 각각 생성)."""
    if not rows:
        st.markdown(
            f'<div style="color:#2e2e2e;font-size:0.8rem;padding:12px 0">{t("no_signal")}</div>',
            unsafe_allow_html=True)
        return

    tbody_d = ""   # 데스크탑 행
    tbody_m = ""   # 모바일 행 (컬럼 순서 다름)

    for r in rows:
        mkt   = r["market"]
        flag  = "🇰🇷" if mkt == "KR" else "🇺🇸"
        tk    = r["ticker"]
        name  = r.get("name", tk)
        is_kr = mkt == "KR"
        fmt   = (lambda v: f"{v:,.0f}") if is_kr else (lambda v: f"{v:,.2f}")
        cur   = fmt(r["close"])
        ref_v = r.get(ref_key)
        ref   = fmt(ref_v) if ref_v is not None else "—"
        dist  = _pill(r.get(dist_key))
        c1d   = _pill(r.get("chg1d"), "chg")
        c5d   = _pill(r.get("chg5d"), "chg")
        cap   = (f"{r['market_cap_krw']//100_000_000:,}억"
                 if is_kr and r.get("market_cap_krw")
                 else (f"${r['market_cap_usd']//1_000_000:,}M"
                       if r.get("market_cap_usd") else "—"))
        url   = f"https://tossinvest.com/stocks/{tk}"

        # 데스크탑: 기존 순서 (flag / ticker / price / mktcap / ref / dist / 1d / 5d / link)
        tbody_d += f"""
        <tr>
          <td>{flag}</td>
          <td><span class="tk-name">{name}</span><span class="tk-code">{tk}</span></td>
          <td style="font-family:'DM Mono',monospace;font-size:0.8rem">{cur}</td>
          <td style="color:#333;font-size:0.76rem">{cap}</td>
          <td style="font-family:'DM Mono',monospace;color:#555;font-size:0.78rem">{ref}</td>
          <td>{dist}</td>
          <td>{c1d}</td>
          <td>{c5d}</td>
          <td class="toss-link"><a href="{url}" target="_blank">TOSS ↗</a></td>
        </tr>"""

        # 모바일: TICKER / PRICE / ref / DIST% / 1D / 5D / MKTCAP / link
        tbody_m += f"""
        <tr>
          <td><span class="tk-name">{flag}&nbsp;{name}</span><br><span class="tk-code">{tk}</span></td>
          <td style="font-family:'DM Mono',monospace;font-size:0.78rem">{cur}</td>
          <td style="font-family:'DM Mono',monospace;color:#555;font-size:0.74rem">{ref}</td>
          <td>{dist}</td>
          <td>{c1d}</td>
          <td>{c5d}</td>
          <td style="color:#333;font-size:0.72rem">{cap}</td>
          <td class="toss-link"><a href="{url}" target="_blank">↗</a></td>
        </tr>"""

    count_label = f"{total if total is not None else len(rows)} {t('results')}"
    st.markdown(f"""
    <div class="table-wrap">
      <table class="stock-table stock-table-d">
        <thead><tr>
          <th></th><th>{t('ticker')}</th><th>{t('price')}</th><th>{t('mktcap')}</th>
          <th>{ref_label}</th><th>{t('dist')}</th><th>{t('chg1d')}</th><th>{t('chg5d')}</th><th></th>
        </tr></thead>
        <tbody>{tbody_d}</tbody>
      </table>
      <table class="stock-table stock-table-m">
        <thead><tr>
          <th>{t('ticker')}</th><th>{t('price')}</th><th>{ref_label}</th>
          <th>{t('dist')}</th><th>{t('chg1d')}</th><th>{t('chg5d')}</th>
          <th>{t('mktcap')}</th><th></th>
        </tr></thead>
        <tbody>{tbody_m}</tbody>
      </table>
    </div>
    <div class="count-txt">{count_label}</div>
    """, unsafe_allow_html=True)


def _page_nav(page: int, n_pages: int, page_key: str):
    """이전/다음 페이지 네비게이션 버튼 (중앙 압축)."""
    if n_pages <= 1:
        return
    # 좌우 여백으로 가운데 압축
    _, nav_area, _ = st.columns([3, 2, 3])
    with nav_area:
        c_prev, c_info, c_next = st.columns([1, 2, 1])
        with c_prev:
            if st.button("‹", key=f"{page_key}_prev", disabled=(page == 0)):
                st.session_state[page_key] = page - 1
                st.rerun()
        with c_info:
            st.markdown(
                f'<div style="text-align:center;color:#444;font-size:0.7rem;'
                f'padding-top:8px;letter-spacing:0.08em">{page + 1}&thinsp;/&thinsp;{n_pages}</div>',
                unsafe_allow_html=True)
        with c_next:
            if st.button("›", key=f"{page_key}_next", disabled=(page == n_pages - 1)):
                st.session_state[page_key] = page + 1
                st.rerun()


def _get_page(signal_key: str, page_key: str, mf: str):
    """시그널 rows 필터 + 페이지 슬라이스 반환 → (display, page, n_pages, total)."""
    rows = signals.get(signal_key, [])
    if mf:
        rows = [r for r in rows if r["market"] == mf]
    total   = len(rows)
    n_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page    = min(st.session_state.get(page_key, 0), n_pages - 1)
    st.session_state[page_key] = page
    display = rows[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]
    return display, page, n_pages, total


def is_refreshing() -> bool:
    return os.path.exists(REFRESH_FLAG)

def start_background_refresh():
    """백그라운드 스레드로 데이터 갱신 시작. 이미 실행 중이면 무시."""
    if is_refreshing():
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REFRESH_FLAG, "w") as f:
        f.write(datetime.now().isoformat())

    def _run():
        try:
            python = sys.executable
            base   = os.path.dirname(__file__)
            subprocess.run([python, os.path.join(base, "fetch_data.py"), "--market", "all"],
                           capture_output=True, text=True)
            subprocess.run([python, os.path.join(base, "signals.py")],
                           capture_output=True, text=True)
        finally:
            if os.path.exists(REFRESH_FLAG):
                os.remove(REFRESH_FLAG)

    threading.Thread(target=_run, daemon=True).start()


# ── 로고 클릭 → 메인 화면 리디렉션 ─────────────────────────
if st.query_params.get("go") == "main":
    st.session_state.page = "main"
    st.query_params.clear()
    st.rerun()

# ── 자동 새로고침 (갱신 중 3초, 평상시 5분) ─────────────────
_refreshing = is_refreshing()
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=3_000 if _refreshing else 300_000, key="idx_refresh")
except ImportError:
    pass

# 갱신 완료 감지 → 캐시 비워서 새 데이터 즉시 반영
if not _refreshing and st.session_state.get("_was_refreshing"):
    st.cache_data.clear()
st.session_state["_was_refreshing"] = _refreshing

# ── 데이터 로드 ───────────────────────────────────────────────
results      = load_results()
indices_data = fetch_indices()
lang         = st.session_state.lang

gen_str = ""
if results:
    try:
        dt = datetime.fromisoformat(results["generated_at"]).astimezone(KST)
        gen_str = dt.strftime("%Y.%m.%d %H:%M KST")
    except Exception:
        pass

# ── 헤더: [STOCKal+시간] [지수 가로띠] [KO|↺|◉] ─────────────
def _idx_strip(data: list) -> str:
    items = ""
    for d in data:
        name = d["label_en"] if lang == "en" else d["label_ko"]
        if d["val"] is None:
            items += (f'<div class="hdr-idx">'
                      f'<span class="hdr-idx-name">{name}</span>'
                      f'<span class="hdr-idx-val" style="color:#2e2e2e">—</span>'
                      f'</div>')
            continue
        val, chg, unit = d["val"], d["chg"], d["unit"]
        val_str = f'{unit}{val:,.2f}' if unit in ("$", "₩") else f'{val:,.2f}'
        sign    = "+" if chg >= 0 else ""
        chg_cls = "hdr-chg-pos" if chg >= 0 else "hdr-chg-neg"
        items += (f'<div class="hdr-idx">'
                  f'<span class="hdr-idx-name">{name}</span>'
                  f'<span class="hdr-idx-val">{val_str}</span>'
                  f'<span class="{chg_cls}">{sign}{chg:.2f}%</span>'
                  f'</div>')
    return f'<div class="hdr-idx-strip">{items}</div>'

col_logo, col_idx, col_btns = st.columns([2, 8, 2])

with col_logo:
    st.markdown(
        f'<div class="site-logo" style="padding-top:6px;cursor:pointer"'
        f'     onclick="window.location.href=window.location.pathname+\'?go=main\'">'
        f'STOCKal</div>'
        f'<div class="updated-txt">{gen_str or t("no_data")}</div>',
        unsafe_allow_html=True)

with col_idx:
    st.markdown(_idx_strip(indices_data), unsafe_allow_html=True)
    st.markdown('<div class="updated-txt" style="text-align:center;margin-top:2px">~15min delayed</div>',
                unsafe_allow_html=True)

with col_btns:
    st.markdown('<span class="btn-area-marker"></span>', unsafe_allow_html=True)
    _, bn1, bn2, bn3 = st.columns([1, 1, 1, 1])
    with bn1:
        if st.button("KO" if lang == "en" else "EN", key="lang_toggle"):
            st.session_state.lang = "ko" if lang == "en" else "en"
            st.rerun()
    with bn2:
        if _refreshing:
            st.markdown('<div class="spin-wrap"><span class="spin-icon">↺</span></div>',
                        unsafe_allow_html=True)
        else:
            if st.button("↺", key="refresh_btn"):
                start_background_refresh()
                st.rerun()
    with bn3:
        # 프로필 아이콘: 로그인 여부에 따라 색감 표현
        if st.session_state.page == "main":
            if st.button("◉", key="my_btn"):
                if st.session_state.user:
                    st.session_state.watchlist = load_watchlist(st.session_state.user)
                st.session_state.page = "my"
                st.rerun()
        else:
            if st.button("←", key="back_btn"):
                st.session_state.page = "main"
                st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════
# MY 페이지 (로그인 / 회원가입만)
# ════════════════════════════════════════════════════
if st.session_state.page == "my":

    st.markdown(f'<div class="my-header">{t("my")}</div>', unsafe_allow_html=True)

    if not st.session_state.user:
        tab_login, tab_signup = st.tabs([t("login"), t("signup")])

        with tab_login:
            with st.form("login_form"):
                uname = st.text_input(t("username"), placeholder="username")
                pw    = st.text_input(t("password"), type="password", placeholder="••••••••")
                if st.form_submit_button(t("login")):
                    users = load_users()
                    hw = hashlib.sha256(pw.encode()).hexdigest()
                    if uname not in users:
                        st.error(t("err_user"))
                    elif users[uname].get("pw") != hw:
                        st.error(t("err_pw"))
                    else:
                        st.session_state.user      = uname
                        st.session_state.watchlist = load_watchlist(uname)
                        st.session_state.page      = "main"
                        st.rerun()

        with tab_signup:
            with st.form("signup_form"):
                new_u = st.text_input(t("username"), placeholder="username", key="su_u")
                new_p = st.text_input(t("password"), type="password",
                                      placeholder="••••••••", key="su_p")
                if st.form_submit_button(t("signup")):
                    users = load_users()
                    if new_u in users:
                        st.error(t("err_dup"))
                    elif len(new_u) < 2 or len(new_p) < 4:
                        st.error("아이디 2자 이상, 비밀번호 4자 이상")
                    else:
                        users[new_u] = {
                            "pw": hashlib.sha256(new_p.encode()).hexdigest(),
                            "watchlist": [],
                        }
                        save_users(users)
                        st.success(t("ok_signup"))
    else:
        col_w, col_out = st.columns([8, 1])
        with col_w:
            st.markdown(
                f'<div style="color:#555;font-size:0.78rem;letter-spacing:0.1em">'
                f'{t("welcome")}, <span style="color:#D1FF00">{st.session_state.user}</span></div>',
                unsafe_allow_html=True)
        with col_out:
            if st.button(t("logout")):
                st.session_state.user      = None
                st.session_state.watchlist = []
                st.session_state.page      = "main"
                st.rerun()

        st.markdown(
            '<div style="color:#333;font-size:0.8rem;padding:28px 0 8px">'
            '관심종목은 메인 화면 우하단에서 확인할 수 있습니다.</div>',
            unsafe_allow_html=True)

    st.stop()


# ════════════════════════════════════════════════════
# 메인 화면 (4분할)
# ════════════════════════════════════════════════════
signals = results.get("signals", {})

# ── 시장 필터 ────────────────────────────────────────
filt_col, _ = st.columns([3, 7])
with filt_col:
    mf = st.radio("", [t("kr"), t("us")], horizontal=True,
                  label_visibility="collapsed")
mf_code = {t("kr"): "KR", t("us"): "US"}.get(mf, "KR")

# 필터 변경 시 모든 페이지 초기화
if st.session_state["_prev_mf"] != str(mf_code):
    for _pk in ("page_a1", "page_a2", "page_b1", "page_b2",
                "page_c1", "page_c2", "page_watch"):
        st.session_state[_pk] = 0
    st.session_state["_prev_mf"] = str(mf_code)

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ── 4분할 레이아웃 ────────────────────────────────────
left_col, right_col = st.columns(2, gap="medium")


# ┌── 좌상단: MA20 · 일목균형표 ─────────────────────┐
with left_col:
    st.markdown(f'<div class="section-label"><span>◈</span>{t("tab_a")}</div>',
                unsafe_allow_html=True)
    sub_a1, sub_a2 = st.tabs([f"▲ {t('a1')}", f"◎ {t('a2')}"])
    with sub_a1:
        rows, pg, np_, tot = _get_page("A1", "page_a1", mf_code)
        _render_table(rows, "dist_a_pct", "ma20", t("ma20"), "a1", total=tot)
        _page_nav(pg, np_, "page_a1")
    with sub_a2:
        rows, pg, np_, tot = _get_page("A2", "page_a2", mf_code)
        _render_table(rows, "dist_a_pct", "ma20", t("ma20"), "a2", total=tot)
        _page_nav(pg, np_, "page_a2")


# ┌── 우상단: MA200 근접 ─────────────────────────────┐
with right_col:
    st.markdown(f'<div class="section-label"><span>◈</span>{t("tab_c")}</div>',
                unsafe_allow_html=True)
    sub_c1, sub_c2 = st.tabs([f"▲ {t('c1')}", f"▼ {t('c2')}"])
    with sub_c1:
        rows, pg, np_, tot = _get_page("C1", "page_c1", mf_code)
        _render_table(rows, "dist_200_pct", "ma200", t("ma200"), "c1", total=tot)
        _page_nav(pg, np_, "page_c1")
    with sub_c2:
        rows, pg, np_, tot = _get_page("C2", "page_c2", mf_code)
        _render_table(rows, "dist_200_pct", "ma200", t("ma200"), "c2", total=tot)
        _page_nav(pg, np_, "page_c2")

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
left_col2, right_col2 = st.columns(2, gap="medium")


# ┌── 좌하단: 종가 구름대 돌파 ──────────────────────┐
with left_col2:
    st.markdown(f'<div class="section-label"><span>◈</span>{t("tab_b")}</div>',
                unsafe_allow_html=True)
    sub_b1, sub_b2 = st.tabs([f"▲ {t('b1')}", f"◎ {t('b2')}"])
    with sub_b1:
        rows, pg, np_, tot = _get_page("B1", "page_b1", mf_code)
        _render_table(rows, "dist_b_pct", "close", t("price"), "b1", total=tot)
        _page_nav(pg, np_, "page_b1")
    with sub_b2:
        rows, pg, np_, tot = _get_page("B2", "page_b2", mf_code)
        _render_table(rows, "dist_b_pct", "close", t("price"), "b2", total=tot)
        _page_nav(pg, np_, "page_b2")


# ┌── 우하단: 관심종목 (WATCHLIST) ──────────────────┐
with right_col2:
    st.markdown(f'<div class="section-label"><span>◈</span>{t("watchlist")}</div>',
                unsafe_allow_html=True)

    if not st.session_state.user:
        st.markdown(
            f'<div style="color:#2e2e2e;font-size:0.82rem;padding:16px 0">'
            f'{t("login_req")}</div>',
            unsafe_allow_html=True)
    else:
        wl = st.session_state.watchlist

        # 현재가 일괄 조회 (캐시 활용)
        yf_syms = tuple(
            (w["ticker"] + ".KS" if w["market"] == "KR" else w["ticker"])
            for w in wl
        )
        raw_prices = fetch_current_prices(yf_syms) if yf_syms else {}
        current_prices = {}
        for w in wl:
            sym = w["ticker"] + ".KS" if w["market"] == "KR" else w["ticker"]
            current_prices[w["ticker"]] = raw_prices.get(sym)

        if not wl:
            st.markdown(
                f'<div style="color:#2e2e2e;font-size:0.82rem;padding:16px 0">'
                f'{t("no_watch")}</div>',
                unsafe_allow_html=True)
        else:
            wl_total   = len(wl)
            wl_pages   = max(1, (wl_total + PAGE_SIZE - 1) // PAGE_SIZE)
            wl_page    = min(st.session_state.get("page_watch", 0), wl_pages - 1)
            st.session_state["page_watch"] = wl_page
            wl_display = wl[wl_page * PAGE_SIZE: (wl_page + 1) * PAGE_SIZE]

            to_remove = None
            for idx_w, w in enumerate(wl_display):
                real_idx = wl_page * PAGE_SIZE + idx_w
                cur   = current_prices.get(w["ticker"])
                entry = w.get("entry_price", 0)
                is_kr = w["market"] == "KR"
                flag  = "🇰🇷" if is_kr else "🇺🇸"

                cur_str   = (f"{cur:,.0f}원" if is_kr else f"${cur:,.2f}") if cur else "—"
                entry_str = (f"{entry:,.0f}원" if is_kr else f"${entry:,.2f}") if entry else "—"

                ret_str = "—"
                ret_cls = "ret-pos"
                if cur and entry:
                    ret     = (cur - entry) / entry * 100
                    sign    = "+" if ret >= 0 else ""
                    ret_str = f"{sign}{ret:.2f}%"
                    ret_cls = "ret-pos" if ret >= 0 else "ret-neg"

                c_info, c_ret, c_del = st.columns([5, 2, 1])
                with c_info:
                    st.markdown(
                        f'{flag} <span class="watch-name">{w.get("name", w["ticker"])}</span>'
                        f' <span style="color:#333;font-family:DM Mono,monospace;'
                        f'font-size:0.7rem">{w["ticker"]}</span>'
                        f'<br><span class="watch-sub">'
                        f'{t("entry_price")}: {entry_str} → {t("current")}: {cur_str}'
                        f'&nbsp;|&nbsp;{t("added_at")}: {w.get("added_at","")}</span>',
                        unsafe_allow_html=True)
                with c_ret:
                    st.markdown(
                        f'<div class="{ret_cls}" style="padding-top:8px">{ret_str}</div>',
                        unsafe_allow_html=True)
                with c_del:
                    if st.button(t("remove"), key=f"del_{real_idx}"):
                        to_remove = real_idx
                st.markdown("<hr>", unsafe_allow_html=True)

            if to_remove is not None:
                wl.pop(to_remove)
                save_watchlist(st.session_state.user, wl)
                st.session_state.watchlist = wl
                st.rerun()

            _page_nav(wl_page, wl_pages, "page_watch")
