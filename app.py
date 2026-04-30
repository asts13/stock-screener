"""
STOCKal — Ichimoku Cloud Breakout Screener
"""
import json, os, subprocess, sys
from datetime import datetime, timezone, timedelta

import yfinance as yf
import pandas as pd
import streamlit as st

# ── 상수 ─────────────────────────────────────────────────────
DATA_DIR     = os.path.join(os.path.dirname(__file__), "data")
RESULTS_PATH = os.path.join(DATA_DIR, "results.json")
KST          = timezone(timedelta(hours=9))

INDICES = [
    {"label_en": "KOSPI",        "label_ko": "코스피",       "ticker": "^KS11",  "unit": ""},
    {"label_en": "KOSDAQ",       "label_ko": "코스닥",       "ticker": "^KQ11",  "unit": ""},
    {"label_en": "NASDAQ",       "label_ko": "나스닥",       "ticker": "^IXIC",  "unit": ""},
    {"label_en": "NQ100 FUT",    "label_ko": "나스닥100선물", "ticker": "NQ=F",   "unit": ""},
    {"label_en": "S&P 500",      "label_ko": "S&P 500",      "ticker": "^GSPC",  "unit": ""},
    {"label_en": "DOW",          "label_ko": "다우존스",     "ticker": "^DJI",   "unit": ""},
    {"label_en": "WTI",          "label_ko": "WTI유가",      "ticker": "CL=F",   "unit": "$"},
    {"label_en": "GOLD",         "label_ko": "금",           "ticker": "GC=F",   "unit": "$"},
    {"label_en": "USD/KRW",      "label_ko": "달러/원",      "ticker": "KRW=X",  "unit": "₩"},
]

# ── i18n ─────────────────────────────────────────────────────
T = {
    "site":        {"en": "STOCKal",              "ko": "STOCKal"},
    "last_update": {"en": "LAST UPDATE",          "ko": "마지막 갱신"},
    "no_data":     {"en": "NO DATA",              "ko": "데이터 없음"},
    "refresh":     {"en": "REFRESH",              "ko": "새로고침"},
    "all":         {"en": "ALL",                  "ko": "전체"},
    "kr":          {"en": "KR",                   "ko": "한국"},
    "us":          {"en": "US",                   "ko": "미국"},
    "market":      {"en": "MARKET",               "ko": "시장"},
    "indices":     {"en": "MARKET INDICES",       "ko": "시장 지수"},
    "tab_a":       {"en": "MA20 · ICHIMOKU",      "ko": "MA20 · 일목"},
    "tab_b":       {"en": "PRICE BREAKOUT",       "ko": "종가 돌파"},
    "tab_c":       {"en": "MA200 PROXIMITY",      "ko": "200MA 근접"},
    "a1":          {"en": "BREAKOUT CONFIRMED",   "ko": "돌파 완료"},
    "a2":          {"en": "APPROACHING — WITHIN 1%", "ko": "돌파 임박 — 1% 이내"},
    "b1":          {"en": "BREAKOUT CONFIRMED",   "ko": "돌파 완료"},
    "b2":          {"en": "APPROACHING — WITHIN 1%", "ko": "돌파 임박 — 1% 이내"},
    "c1":          {"en": "ABOVE MA200 — WITHIN 2%", "ko": "200MA 위 2% 이내"},
    "c2":          {"en": "BELOW MA200 — WITHIN 2%", "ko": "200MA 아래 2% 이내"},
    "ticker":      {"en": "TICKER",               "ko": "종목"},
    "price":       {"en": "PRICE",                "ko": "현재가"},
    "mktcap":      {"en": "MKTCAP",               "ko": "시총"},
    "ma20":        {"en": "MA20",                 "ko": "MA20"},
    "ma200":       {"en": "MA200",                "ko": "MA200"},
    "cloud":       {"en": "CLOUD TOP",            "ko": "구름상단"},
    "dist":        {"en": "DIST%",                "ko": "거리%"},
    "chg1d":       {"en": "1D%",                  "ko": "1일%"},
    "chg5d":       {"en": "5D%",                  "ko": "5일%"},
    "no_signal":   {"en": "No signals found.",    "ko": "해당 종목 없음"},
    "results":     {"en": "RESULTS",              "ko": "종목"},
    "my":          {"en": "MY",                   "ko": "MY"},
    "login":       {"en": "LOG IN",               "ko": "로그인"},
    "signup":      {"en": "SIGN UP",              "ko": "회원가입"},
    "logout":      {"en": "LOG OUT",              "ko": "로그아웃"},
    "username":    {"en": "Username",             "ko": "아이디"},
    "password":    {"en": "Password",             "ko": "비밀번호"},
    "watchlist":   {"en": "WATCHLIST",            "ko": "관심종목"},
    "entry_price": {"en": "ENTRY PRICE",          "ko": "진입가"},
    "current":     {"en": "CURRENT",              "ko": "현재가"},
    "return":      {"en": "RETURN%",              "ko": "수익률%"},
    "add_watch":   {"en": "ADD TO WATCHLIST",     "ko": "관심종목 추가"},
    "added_at":    {"en": "ADDED",                "ko": "추가일"},
    "back":        {"en": "← BACK",              "ko": "← 돌아가기"},
    "main":        {"en": "SCREENER",             "ko": "스크리너"},
    "welcome":     {"en": "Welcome",              "ko": "환영합니다"},
    "login_req":   {"en": "Log in to use watchlist", "ko": "관심종목은 로그인 후 이용 가능합니다"},
    "no_watch":    {"en": "No stocks in your watchlist.", "ko": "관심종목이 없습니다."},
    "remove":      {"en": "REMOVE",               "ko": "삭제"},
    "err_pw":      {"en": "Wrong password",       "ko": "비밀번호 오류"},
    "err_user":    {"en": "Username not found",   "ko": "존재하지 않는 아이디"},
    "err_dup":     {"en": "Username already taken","ko": "이미 사용 중인 아이디"},
    "ok_signup":   {"en": "Account created! Please log in.", "ko": "가입 완료! 로그인해주세요."},
}

def t(key: str) -> str:
    lang = st.session_state.get("lang", "en")
    return T.get(key, {}).get(lang, key)

# ── 페이지 설정 ───────────────────────────────────────────────
st.set_page_config(page_title="STOCKal", page_icon="▣", layout="wide")

# ── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=DM+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
.stApp { background-color: #1A1A1A; }

/* 최상단 바 */
.topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 18px 0 14px 0;
    border-bottom: 1px solid #2A2A2A;
    margin-bottom: 20px;
}
.site-logo { font-size: 1.4rem; font-weight: 700; letter-spacing: 0.2em; color: #D1FF00; }
.topbar-right { display: flex; align-items: center; gap: 16px; }
.lang-btn {
    font-size: 0.7rem; letter-spacing: 0.12em; color: #555; cursor: pointer;
    background: none; border: none; padding: 4px 8px;
}
.lang-btn:hover { color: #D1FF00; }
.my-btn {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.15em;
    color: #1A1A1A; background: #D1FF00; border: none;
    padding: 6px 16px; border-radius: 2px; cursor: pointer;
}
.updated-txt { font-size: 0.68rem; color: #3a3a3a; letter-spacing: 0.06em; }

/* 버튼 공통 */
div[data-testid="stButton"] > button {
    background: transparent; border: 1px solid #D1FF00; color: #D1FF00;
    font-weight: 600; letter-spacing: 0.1em; font-size: 0.76rem;
    padding: 7px 18px; border-radius: 2px; transition: all 0.18s;
}
div[data-testid="stButton"] > button:hover { background: #D1FF00; color: #1A1A1A; }

/* 시장 필터 라디오 */
div[data-testid="stRadio"] > div { gap: 6px; }
div[data-testid="stRadio"] label {
    font-size: 0.76rem; letter-spacing: 0.1em;
    color: #444; padding: 5px 14px !important;
    border: 1px solid #2a2a2a; border-radius: 2px;
}
div[data-testid="stRadio"] label:has(input:checked) {
    color: #1A1A1A !important; background: #D1FF00 !important; border-color: #D1FF00 !important;
}

/* 헤더 지수 가로띠 */
.hdr-idx-strip {
    display: flex; align-items: center;
    overflow-x: auto; padding: 4px 0;
    scrollbar-width: none; height: 52px;
}
.hdr-idx-strip::-webkit-scrollbar { display: none; }
.hdr-idx {
    display: flex; flex-direction: column; align-items: flex-start;
    padding: 2px 14px 2px 0; margin-right: 14px;
    border-right: 1px solid #2a2a2a;
    white-space: nowrap;
}
.hdr-idx:last-child { border-right: none; }
.hdr-idx-name { font-size: 0.62rem; letter-spacing: 0.08em; color: #777; text-transform: uppercase; }
.hdr-idx-val  { font-size: 0.80rem; font-family: 'DM Mono', monospace; color: #C8C8C8; }
.hdr-chg-pos  { font-size: 0.65rem; font-family: 'DM Mono', monospace; color: #D1FF00; }
.hdr-chg-neg  { font-size: 0.65rem; font-family: 'DM Mono', monospace; color: #ff5555; }

/* 지수 위젯 (메인 그리드용) */
.indices-grid {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
    background: #242424; border: 1px solid #242424; border-radius: 3px;
    margin-bottom: 4px;
}
.idx-cell {
    background: #1A1A1A; padding: 10px 14px;
    display: flex; justify-content: space-between; align-items: center;
}
.idx-name { font-size: 0.72rem; letter-spacing: 0.08em; color: #777; }
.idx-val  { font-size: 0.82rem; font-family: 'DM Mono', monospace; color: #C8C8C8; }
.idx-chg-pos { font-size: 0.72rem; font-family: 'DM Mono', monospace; color: #D1FF00; }
.idx-chg-neg { font-size: 0.72rem; font-family: 'DM Mono', monospace; color: #ff5555; }

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
.auth-box { max-width:360px; margin:0 auto; }
.watch-row { display:flex; align-items:center; justify-content:space-between; padding:12px 0; border-bottom:1px solid #1f1f1f; }
.watch-name { font-family:'DM Mono',monospace; font-size:0.82rem; color:#E0E0E0; }
.ret-pos { color:#D1FF00; font-family:'DM Mono',monospace; font-size:0.8rem; }
.ret-neg { color:#ff5555; font-family:'DM Mono',monospace; font-size:0.8rem; }

hr { border-color:#1f1f1f !important; margin:14px 0 !important; }
.stAlert { background:#1e1e1e !important; border:1px solid #2a2a2a !important; border-radius:2px !important; }
::-webkit-scrollbar { width:3px; height:3px; }
::-webkit-scrollbar-thumb { background:#2a2a2a; }
</style>
""", unsafe_allow_html=True)

# ── 세션 초기화 ───────────────────────────────────────────────
if "lang"     not in st.session_state: st.session_state.lang     = "en"
if "page"     not in st.session_state: st.session_state.page     = "main"
if "user"     not in st.session_state: st.session_state.user     = None
if "watchlist" not in st.session_state: st.session_state.watchlist = []
if "auth_tab" not in st.session_state: st.session_state.auth_tab = "login"


# ── 간이 유저 DB (로컬 JSON) ─────────────────────────────────
USERS_PATH = os.path.join(DATA_DIR, "users.json")

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
    users = load_users()
    return users.get(username, {}).get("watchlist", [])

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
        raw = yf.download(tickers, period="2d", auto_adjust=True,
                          progress=False, threads=True)
        for idx in INDICES:
            t_sym = idx["ticker"]
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    close = raw["Close"][t_sym].dropna()
                else:
                    close = raw["Close"].dropna()
                if len(close) < 2:
                    raise ValueError("data short")
                val  = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                chg  = (val - prev) / prev * 100
                out.append({**idx, "val": val, "chg": chg})
            except Exception:
                out.append({**idx, "val": None, "chg": None})
    except Exception:
        out = [{**i, "val": None, "chg": None} for i in INDICES]
    return out

def _pill(val: float, mode: str = "dist") -> str:
    if val is None: return '<span class="pill pill-neu">—</span>'
    sign = "+" if val > 0 else ""
    if mode == "chg":
        cls = "pill-near" if val > 0 else "pill-neg"
    else:
        cls = "pill-near" if 0 <= val <= 2 else ("pill-over" if val < 0 else "pill-neu")
    return f'<span class="pill {cls}">{sign}{val:.2f}%</span>'

def _render_table(rows: list, dist_key: str, ref_key: str,
                  ref_label: str, mf_code, tab_id: str):
    if mf_code:
        rows = [r for r in rows if r["market"] == mf_code]
    if not rows:
        st.markdown(f'<div style="color:#2e2e2e;font-size:0.8rem;padding:12px 0">{t("no_signal")}</div>',
                    unsafe_allow_html=True)
        return

    cur_prices = {}
    if st.session_state.user:
        wl_tickers = {w["ticker"] for w in st.session_state.watchlist}
    else:
        wl_tickers = set()

    tbody = ""
    for r in rows:
        mkt   = r["market"]
        flag  = "🇰🇷" if mkt == "KR" else "🇺🇸"
        tk    = r["ticker"]
        name  = r.get("name", tk)
        is_kr = mkt == "KR"
        price_fmt = lambda v: f"{v:,.0f}" if is_kr else f"{v:,.2f}"
        cur   = price_fmt(r["close"])
        ref   = price_fmt(r.get(ref_key, r["close"]))
        cloud = price_fmt(r["cloud_top"]) if r.get("cloud_top") else "—"
        dist  = _pill(r.get(dist_key))
        c1d   = _pill(r.get("chg1d"), "chg")
        c5d   = _pill(r.get("chg5d"), "chg")
        cap   = f"{r['market_cap_krw']//100_000_000:,}억" if is_kr and r.get("market_cap_krw") else (f"${r['market_cap_usd']//1_000_000:,}M" if r.get("market_cap_usd") else "—")
        url   = f"https://tossinvest.com/stocks/{tk}"

        # 관심종목 추가 버튼 (로그인 시)
        watch_col = ""
        if st.session_state.user and tk not in wl_tickers:
            watch_col = f'<a href="#" onclick="return false" style="color:#2a2a2a;font-size:0.68rem;letter-spacing:0.06em">＋</a>'

        tbody += f"""
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

    html = f"""
    <table class="stock-table">
      <thead><tr>
        <th></th><th>{t('ticker')}</th><th>{t('price')}</th><th>{t('mktcap')}</th>
        <th>{ref_label}</th><th>{t('dist')}</th><th>{t('chg1d')}</th><th>{t('chg5d')}</th><th></th>
      </tr></thead>
      <tbody>{tbody}</tbody>
    </table>
    <div class="count-txt">{len(rows)} {t('results')}</div>
    """
    st.markdown(html, unsafe_allow_html=True)

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


# ── 5분마다 증시 지수 자동 새로고침 ────────────────────────
st_autorefresh = None
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=300_000, key="idx_refresh")   # 300,000ms = 5분
except ImportError:
    pass   # 미설치 시 무시

# ── 데이터 로드 ───────────────────────────────────────────────
results = load_results()
indices_data = fetch_indices()
lang = st.session_state.lang

gen_str = ""
if results:
    try:
        dt = datetime.fromisoformat(results["generated_at"]).astimezone(KST)
        gen_str = dt.strftime("%Y.%m.%d %H:%M KST")
    except Exception:
        pass

# ── 헤더: [STOCKal] [지수 가로띠] [KO|REFRESH|MY] ──────────
def _idx_strip(data: list) -> str:
    items = ""
    for d in data:
        name = d["label_en"] if lang == "en" else d["label_ko"]
        if d["val"] is None:
            items += f'<div class="hdr-idx"><span class="hdr-idx-name">{name}</span><span class="hdr-idx-val" style="color:#2e2e2e">—</span></div>'
            continue
        val, chg, unit = d["val"], d["chg"], d["unit"]
        val_str = f'{unit}{val:,.2f}' if unit in ("$","₩") else f'{val:,.2f}'
        sign    = "+" if chg >= 0 else ""
        chg_cls = "hdr-chg-pos" if chg >= 0 else "hdr-chg-neg"
        items += (f'<div class="hdr-idx">'
                  f'<span class="hdr-idx-name">{name}</span>'
                  f'<span class="hdr-idx-val">{val_str}</span>'
                  f'<span class="{chg_cls}">{sign}{chg:.2f}%</span>'
                  f'</div>')
    return f'<div class="hdr-idx-strip">{items}</div>'

col_logo, col_idx, col_btns = st.columns([2, 7, 3])

with col_logo:
    st.markdown(
        f'<div class="site-logo" style="padding-top:10px">STOCKal</div>'
        f'<div class="updated-txt">{gen_str or t("no_data")}</div>',
        unsafe_allow_html=True,
    )

with col_idx:
    st.markdown(_idx_strip(indices_data), unsafe_allow_html=True)
    st.markdown('<div class="updated-txt" style="text-align:center;margin-top:2px">~15min delayed</div>',
                unsafe_allow_html=True)

with col_btns:
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("KO" if lang == "en" else "EN", key="lang_toggle"):
            st.session_state.lang = "ko" if lang == "en" else "en"
            st.rerun()
    with b2:
        if st.button("↺", key="refresh_btn"):
            with st.spinner(""):
                manual_refresh()
            st.rerun()
    with b3:
        if st.session_state.page == "main":
            my_label = f"MY·{st.session_state.user}" if st.session_state.user else "MY"
            if st.button(my_label, key="my_btn"):
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
# MY 페이지
# ════════════════════════════════════════════════════
if st.session_state.page == "my":

    st.markdown(f'<div class="my-header">{t("my")}</div>', unsafe_allow_html=True)

    # ── 로그인/가입 영역 ─────────────────────────────
    if not st.session_state.user:
        tab_login, tab_signup = st.tabs([t("login"), t("signup")])

        with tab_login:
            with st.form("login_form"):
                uname = st.text_input(t("username"), placeholder="username")
                pw    = st.text_input(t("password"), type="password", placeholder="••••••••")
                if st.form_submit_button(t("login")):
                    users = load_users()
                    import hashlib
                    hw = hashlib.sha256(pw.encode()).hexdigest()
                    if uname not in users:
                        st.error(t("err_user"))
                    elif users[uname].get("pw") != hw:
                        st.error(t("err_pw"))
                    else:
                        st.session_state.user = uname
                        st.session_state.watchlist = load_watchlist(uname)
                        st.rerun()

        with tab_signup:
            with st.form("signup_form"):
                new_u = st.text_input(t("username"), placeholder="username", key="su_u")
                new_p = st.text_input(t("password"), type="password", placeholder="••••••••", key="su_p")
                if st.form_submit_button(t("signup")):
                    import hashlib
                    users = load_users()
                    if new_u in users:
                        st.error(t("err_dup"))
                    elif len(new_u) < 2 or len(new_p) < 4:
                        st.error("아이디 2자 이상, 비밀번호 4자 이상")
                    else:
                        hw = hashlib.sha256(new_p.encode()).hexdigest()
                        users[new_u] = {"pw": hw, "watchlist": []}
                        save_users(users)
                        st.success(t("ok_signup"))

    else:
        # ── 로그인 상태 ──────────────────────────────
        col_w, col_out = st.columns([8, 1])
        with col_w:
            st.markdown(f'<div style="color:#555;font-size:0.78rem;letter-spacing:0.1em">'
                        f'{t("welcome")},  <span style="color:#D1FF00">{st.session_state.user}</span></div>',
                        unsafe_allow_html=True)
        with col_out:
            if st.button(t("logout")):
                st.session_state.user = None
                st.session_state.watchlist = []
                st.rerun()

        st.markdown("<hr>", unsafe_allow_html=True)
        st.markdown(f'<div class="section-label"><span>◈</span>{t("watchlist")}</div>',
                    unsafe_allow_html=True)

        wl = st.session_state.watchlist

        # 현재가 일괄 조회
        current_prices = {}
        if wl:
            us_tickers = [w["ticker"] + (".KS" if w["market"] == "KR" else "") for w in wl
                          if w["market"] == "KR"]
            us_tickers += [w["ticker"] for w in wl if w["market"] == "US"]
            try:
                raw = yf.download(us_tickers, period="2d", auto_adjust=True,
                                  progress=False, threads=True)
                for w in wl:
                    sym = w["ticker"] + ".KS" if w["market"] == "KR" else w["ticker"]
                    try:
                        if isinstance(raw.columns, pd.MultiIndex):
                            cp = float(raw["Close"][sym].dropna().iloc[-1])
                        else:
                            cp = float(raw["Close"].dropna().iloc[-1])
                        current_prices[w["ticker"]] = cp
                    except Exception:
                        current_prices[w["ticker"]] = None
            except Exception:
                pass

        if not wl:
            st.markdown(f'<div style="color:#333;font-size:0.82rem;padding:16px 0">{t("no_watch")}</div>',
                        unsafe_allow_html=True)
        else:
            to_remove = None
            for idx, w in enumerate(wl):
                cur = current_prices.get(w["ticker"])
                entry = w.get("entry_price", 0)
                ret_str = "—"
                ret_cls = "ret-pos"
                if cur and entry:
                    ret = (cur - entry) / entry * 100
                    sign = "+" if ret >= 0 else ""
                    ret_str = f"{sign}{ret:.2f}%"
                    ret_cls = "ret-pos" if ret >= 0 else "ret-neg"

                is_kr = w["market"] == "KR"
                cur_str   = f"{cur:,.0f}원" if is_kr and cur else (f"${cur:,.2f}" if cur else "—")
                entry_str = f"{entry:,.0f}원" if is_kr else f"${entry:,.2f}"

                col_info, col_ret, col_del = st.columns([6, 2, 1])
                with col_info:
                    flag = "🇰🇷" if is_kr else "🇺🇸"
                    st.markdown(
                        f'{flag} <span class="watch-name">{w.get("name", w["ticker"])}</span>'
                        f' <span style="color:#333;font-family:DM Mono,monospace;font-size:0.7rem">{w["ticker"]}</span>'
                        f'<br><span style="color:#333;font-size:0.7rem">'
                        f'{t("entry_price")}: {entry_str} &nbsp;→&nbsp; {t("current")}: {cur_str}'
                        f'&nbsp; | &nbsp;{t("added_at")}: {w.get("added_at","")}</span>',
                        unsafe_allow_html=True,
                    )
                with col_ret:
                    st.markdown(f'<div class="{ret_cls}" style="padding-top:8px">{ret_str}</div>',
                                unsafe_allow_html=True)
                with col_del:
                    if st.button(t("remove"), key=f"del_{idx}"):
                        to_remove = idx

                st.markdown("<hr>", unsafe_allow_html=True)

            if to_remove is not None:
                wl.pop(to_remove)
                save_watchlist(st.session_state.user, wl)
                st.session_state.watchlist = wl
                st.rerun()

    st.stop()


# ════════════════════════════════════════════════════
# 메인 화면 (4분할)
# ════════════════════════════════════════════════════
signals = results.get("signals", {})

# ── 시장 필터 ────────────────────────────────────────
filt_col, _ = st.columns([4, 6])
with filt_col:
    mf = st.radio("", [t("all"), t("kr"), t("us")], horizontal=True,
                  label_visibility="collapsed")
mf_code = {"ALL": None, t("all"): None, t("kr"): "KR", t("us"): "US"}.get(mf)

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ── 4분할 레이아웃 ────────────────────────────────────
left_col, right_col = st.columns(2, gap="medium")


# ┌── 좌상단: MA20 일목균형표 돌파 ──────────────────┐
with left_col:
    st.markdown(f'<div class="section-label"><span>◈</span>{t("tab_a")}</div>',
                unsafe_allow_html=True)
    sub_a1, sub_a2 = st.tabs([f"▲ {t('a1')}", f"◎ {t('a2')}"])
    with sub_a1:
        _render_table(signals.get("A1", []), "dist_a_pct", "ma20", t("ma20"), mf_code, "a1")
    with sub_a2:
        _render_table(signals.get("A2", []), "dist_a_pct", "ma20", t("ma20"), mf_code, "a2")


# ┌── 우상단: MA200 근접 ─────────────────────────────┐
with right_col:
    st.markdown(f'<div class="section-label"><span>◈</span>{t("tab_c")}</div>',
                unsafe_allow_html=True)
    sub_c1, sub_c2 = st.tabs([f"▲ {t('c1')}", f"▼ {t('c2')}"])
    with sub_c1:
        _render_table(signals.get("C1", []), "dist_200_pct", "ma200", t("ma200"), mf_code, "c1")
    with sub_c2:
        _render_table(signals.get("C2", []), "dist_200_pct", "ma200", t("ma200"), mf_code, "c2")

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
left_col2, right_col2 = st.columns(2, gap="medium")


# ┌── 좌하단: 종가 구름대 돌파 ──────────────────────┐
with left_col2:
    st.markdown(f'<div class="section-label"><span>◈</span>{t("tab_b")}</div>',
                unsafe_allow_html=True)
    sub_b1, sub_b2 = st.tabs([f"▲ {t('b1')}", f"◎ {t('b2')}"])
    with sub_b1:
        _render_table(signals.get("B1", []), "dist_b_pct", "close", t("price"), mf_code, "b1")
    with sub_b2:
        _render_table(signals.get("B2", []), "dist_b_pct", "close", t("price"), mf_code, "b2")


# ┌── 우하단: 증시 지수 (상세) ───────────────────────┐
with right_col2:
    st.markdown(f'<div class="section-label"><span>◈</span>{t("indices")}</div>',
                unsafe_allow_html=True)
    cells = ""
    for d in indices_data:
        name = d["label_en"] if lang == "en" else d["label_ko"]
        if d["val"] is None:
            cells += f'<div class="idx-cell"><span class="idx-name">{name}</span><span class="idx-val" style="color:#333">—</span></div>'
            continue
        val  = d["val"]
        chg  = d["chg"]
        unit = d["unit"]
        val_str = f'{unit}{val:,.2f}' if unit in ("$", "₩") else f'{val:,.2f}'
        sign    = "+" if chg >= 0 else ""
        chg_cls = "idx-chg-pos" if chg >= 0 else "idx-chg-neg"
        cells += (f'<div class="idx-cell">'
                  f'<span class="idx-name">{name}</span>'
                  f'<div style="text-align:right">'
                  f'<span class="idx-val">{val_str}</span>&nbsp;'
                  f'<span class="{chg_cls}">{sign}{chg:.2f}%</span>'
                  f'</div></div>')
    st.markdown(f'<div class="indices-grid">{cells}</div>', unsafe_allow_html=True)
    st.markdown('<div class="updated-txt" style="margin-top:4px">~15min delayed · auto-refresh 5min</div>',
                unsafe_allow_html=True)
