"""
STOCKal — Ichimoku Cloud Breakout Screener  (Design v2)
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
KST           = timezone(timedelta(hours=9))
PAGE_SIZE     = 15
IS_MOBILE     = False

INDICES = [
    {"label_en": "KOSPI",     "label_ko": "코스피",        "ticker": "^KS11",  "unit": ""},
    {"label_en": "KOSDAQ",    "label_ko": "코스닥",        "ticker": "^KQ11",  "unit": ""},
    {"label_en": "NASDAQ",    "label_ko": "나스닥",        "ticker": "^IXIC",  "unit": ""},
    {"label_en": "NQ100 FUT", "label_ko": "나스닥100선물", "ticker": "NQ=F",   "unit": ""},
    {"label_en": "S&P 500",   "label_ko": "S&P 500",       "ticker": "^GSPC",  "unit": ""},
    {"label_en": "DOW",       "label_ko": "다우존스",      "ticker": "^DJI",   "unit": ""},
    {"label_en": "WTI",       "label_ko": "WTI유가",       "ticker": "CL=F",   "unit": "$"},
    {"label_en": "GOLD",      "label_ko": "금",            "ticker": "GC=F",   "unit": "$"},
    {"label_en": "USD/KRW",   "label_ko": "달러/원",       "ticker": "KRW=X",  "unit": "₩"},
]

T = {
    "a1": {"en":"BREAKOUT",        "ko":"돌파 완료"},
    "a2": {"en":"APPROACHING 1%",  "ko":"돌파 임박 1%"},
    "c1": {"en":"ABOVE MA200 2%",  "ko":"200MA 위 2%"},
    "c2": {"en":"BELOW MA200 2%",  "ko":"200MA 아래 2%"},
    "ticker":      {"en":"TICKER",  "ko":"종목"},
    "price":       {"en":"PRICE",   "ko":"현재가"},
    "mktcap":      {"en":"MKTCAP",  "ko":"시총"},
    "ma20":        {"en":"MA20",    "ko":"MA20"},
    "ma200":       {"en":"MA200",   "ko":"MA200"},
    "dist":        {"en":"DIST%",   "ko":"거리%"},
    "chg1d":       {"en":"1D",      "ko":"1일"},
    "chg5d":       {"en":"5D",      "ko":"5일"},
    "no_signal":   {"en":"No signals found.", "ko":"해당 종목 없음"},
    "results":     {"en":"results", "ko":"종목"},
    "no_data":     {"en":"NO DATA", "ko":"데이터 없음"},
    "login":       {"en":"Log In",  "ko":"로그인"},
    "signup":      {"en":"Sign Up", "ko":"회원가입"},
    "logout":      {"en":"LOG OUT", "ko":"로그아웃"},
    "username":    {"en":"USERNAME","ko":"아이디"},
    "password":    {"en":"PASSWORD","ko":"비밀번호"},
    "watchlist":   {"en":"WATCHLIST","ko":"관심종목"},
    "entry_price": {"en":"ENTRY",   "ko":"진입가"},
    "current":     {"en":"NOW",     "ko":"현재가"},
    "added_at":    {"en":"ADDED",   "ko":"추가일"},
    "welcome":     {"en":"Welcome", "ko":"환영합니다"},
    "login_req":   {"en":"Log in to use watchlist.", "ko":"로그인 후 이용 가능합니다."},
    "no_watch":    {"en":"No stocks in watchlist.",  "ko":"관심종목이 없습니다."},
    "remove":      {"en":"✕",       "ko":"✕"},
    "err_pw":      {"en":"Wrong password",        "ko":"비밀번호 오류"},
    "err_user":    {"en":"Username not found",    "ko":"존재하지 않는 아이디"},
    "err_dup":     {"en":"Username already taken","ko":"이미 사용 중인 아이디"},
    "ok_signup":   {"en":"Account created! Please log in.", "ko":"가입 완료! 로그인해주세요."},
    "login_sub":   {"en":"Please log in to continue", "ko":"로그인 후 이용 가능합니다"},
}

def t(key: str) -> str:
    return T.get(key, {}).get(st.session_state.get("lang","en"), key)

# ── 페이지 설정 ───────────────────────────────────────────────
st.set_page_config(page_title="STOCKal", page_icon="▣", layout="wide")

# ── 모바일 감지 ───────────────────────────────────────────────
try:
    _ua = st.context.headers.get("user-agent", "")
    IS_MOBILE = any(x in _ua for x in ["iPhone","Android","Mobile","iPod"])
    if IS_MOBILE: PAGE_SIZE = 8
except Exception:
    pass


# ── 함수 정의 ─────────────────────────────────────────────────
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
        raw = yf.download(tickers, period="5d", auto_adjust=True,
                          progress=False, threads=True)
        for idx in INDICES:
            sym = idx["ticker"]
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    close = raw["Close"][sym].dropna()
                else:
                    close = raw["Close"].dropna()
                if len(close) < 2: raise ValueError
                val  = float(close.iloc[-1])
                prev = float(close.iloc[-2])
                chg  = (val - prev) / prev * 100
                out.append({**idx, "val": val, "chg": chg})
            except Exception:
                out.append({**idx, "val": None, "chg": None})
    except Exception:
        out = [{**i, "val": None, "chg": None} for i in INDICES]
    return out

@st.cache_data(ttl=300)
def fetch_current_prices(yf_syms: tuple) -> dict:
    if not yf_syms: return {}
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

def is_refreshing() -> bool:
    return os.path.exists(REFRESH_FLAG)

def start_background_refresh():
    if is_refreshing(): return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REFRESH_FLAG, "w") as f:
        f.write(datetime.now().isoformat())
    def _run():
        try:
            py   = sys.executable
            base = os.path.dirname(__file__)
            subprocess.run([py, os.path.join(base,"fetch_data.py"),"--market","all"],
                           capture_output=True, text=True)
            subprocess.run([py, os.path.join(base,"signals.py")],
                           capture_output=True, text=True)
        finally:
            if os.path.exists(REFRESH_FLAG): os.remove(REFRESH_FLAG)
    threading.Thread(target=_run, daemon=True).start()


# ── 세션 초기화 ───────────────────────────────────────────────
_defaults = {
    "lang": "en", "page": "main", "user": None, "watchlist": [],
    "menu": "MA20", "market": "KR", "sigtab": "A1",
    "page_a1": 0, "page_a2": 0,
    "page_c1": 0, "page_c2": 0,
    "page_watch": 0, "_prev_market": "BOOT",
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── 쿼리 파라미터 처리 ─────────────────────────────────────────
_qp = st.query_params
_rerun = False

if _qp.get("go") == "main":
    st.session_state["page"] = "main"
    _rerun = True

if _qp.get("menu") in ["MA20","MA200","WatchList"]:
    st.session_state["menu"] = _qp["menu"]
    st.session_state["page"] = "main"
    if _qp["menu"] == "MA20":      st.session_state["sigtab"] = "A1"
    elif _qp["menu"] == "MA200":   st.session_state["sigtab"] = "C1"
    _rerun = True

if _qp.get("mkt") in ["KR","US"]:
    st.session_state["market"] = _qp["mkt"]
    st.session_state["_prev_market"] = "RESET"
    _rerun = True

if _qp.get("lang") in ["en","ko"]:
    st.session_state["lang"] = _qp["lang"]
    _rerun = True

if _qp.get("page") in ["my","main"]:
    st.session_state["page"] = _qp["page"]
    _rerun = True

if _qp.get("sigtab") in ["A1","A2","C1","C2"]:
    st.session_state["sigtab"] = _qp["sigtab"]
    _rerun = True

# Page nav (prev/next)
for _pk in ["page_a1","page_a2","page_c1","page_c2","page_watch"]:
    if _qp.get(_pk) is not None:
        try: st.session_state[_pk] = int(_qp[_pk])
        except Exception: pass
        _rerun = True

if _qp.get("refresh") == "1":
    start_background_refresh()
    _rerun = True

if _rerun:
    st.query_params.clear()
    st.rerun()


# ── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --bg:     #0A0E1A;
  --bg2:    #111827;
  --bg3:    #1A2236;
  --bd:     rgba(255,255,255,0.07);
  --text:   #F0F2F7;
  --muted:  #8892A4;
  --accent: #C6F135;
  --red:    #FF4D4D;
  --green:  #22C55E;
  --fn:     'JetBrains Mono', monospace;
}

/* ── Global ── */
*, *::before, *::after { box-sizing: border-box; }
html, body { font-family: 'DM Sans', sans-serif !important; }
.stApp { background: var(--bg) !important; }
.stApp > header { display: none !important; }

/* Remove ALL Streamlit default padding */
.stMainBlockContainer, .block-container {
  padding-top: 0 !important;
  padding-bottom: 80px !important;
  max-width: 100% !important;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
  background: var(--bg) !important;
  border-right: 1px solid var(--bd) !important;
  width: 200px !important; min-width: 200px !important;
}
section[data-testid="stSidebar"] > div:first-child { padding: 0 !important; }
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"] { display: none !important; }

/* ── Nav ── */
.s-nav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; height: 56px;
  background: var(--bg); border-bottom: 1px solid var(--bd);
}
.s-nav-logo {
  font-size: 20px; font-weight: 700; letter-spacing: -0.03em;
  color: var(--text); text-decoration: none;
}
.s-nav-logo em { font-style: normal; color: var(--accent); }
.s-nav-right { display: flex; align-items: center; gap: 12px; }
.s-nav-update { font-size: 10px; color: #2a3347; letter-spacing: 0.04em; margin-left: 8px; }

/* Toggle group */
.tg {
  display: inline-flex; background: var(--bg3); border-radius: 8px;
  padding: 3px; gap: 2px;
}
.tb {
  padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 600;
  letter-spacing: 0.04em; border: none; cursor: pointer; transition: all 0.15s;
  color: var(--muted); background: none; font-family: 'DM Sans', sans-serif;
  text-decoration: none; display: inline-flex; align-items: center;
}
.tb.active { background: var(--accent) !important; color: #000 !important; }
.tb:hover:not(.active) { color: var(--text); background: rgba(255,255,255,0.06); }
.s-ctrl-label { font-size: 11px; color: var(--muted); font-weight: 600; letter-spacing: 0.05em; }
.s-avatar {
  width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
  background: linear-gradient(135deg, var(--accent), #00D4AA);
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: #000; cursor: pointer;
  text-decoration: none;
}
.s-refresh-btn {
  background: none; border: none; cursor: pointer;
  color: var(--muted); font-size: 18px; line-height: 1;
  padding: 4px; border-radius: 6px; transition: color 0.15s;
}
.s-refresh-btn:hover { color: var(--accent); }
@keyframes spin { to { transform: rotate(-360deg); } }
.spin { display: inline-block; animation: spin 1s linear infinite; color: var(--accent); }

/* ── Sidebar inner ── */
.sb-inner { padding: 12px; }
.sb-logo {
  display: block; font-size: 18px; font-weight: 700; letter-spacing: -0.03em;
  color: var(--text); text-decoration: none; padding: 4px 8px 2px;
}
.sb-logo em { font-style: normal; color: var(--accent); }
.sb-update { font-size: 10px; color: #2a3347; letter-spacing: 0.04em; padding: 0 8px 12px; }
.sb-section {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  color: var(--muted); padding: 10px 8px 4px; text-transform: uppercase;
}
.sb-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: 8px; margin-bottom: 2px;
  font-size: 13px; font-weight: 500; color: var(--muted);
  text-decoration: none; transition: all 0.15s; cursor: pointer;
}
.sb-item:hover { color: var(--text); background: var(--bg3); }
.sb-item.active { color: var(--text); background: var(--bg3); }
.sb-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: rgba(255,255,255,0.1); flex-shrink: 0;
}
.sb-item.active .sb-dot { background: var(--accent); }
.sb-idx {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.03);
}
.sb-idx-l { display: flex; flex-direction: column; gap: 1px; }
.sb-idx-name  { font-size: 9px; font-weight: 700; color: var(--muted); letter-spacing: 0.05em; }
.sb-idx-price { font-family: var(--fn); font-size: 12px; font-weight: 500; color: var(--text); }
.idx-up { font-family: var(--fn); font-size: 10px; font-weight: 600; color: var(--green); }
.idx-dn { font-family: var(--fn); font-size: 10px; font-weight: 600; color: var(--red); }

/* ── Mobile header ── */
.mob-hd {
  display: none; align-items: center; justify-content: space-between;
  padding: 12px 16px 8px;
}
.mob-logo { font-size: 18px; font-weight: 700; letter-spacing: -0.03em; color: var(--text); }
.mob-logo em { font-style: normal; color: var(--accent); }
.mob-avatar {
  width: 30px; height: 30px; border-radius: 50%;
  background: linear-gradient(135deg, var(--accent), #00D4AA);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: #000; text-decoration: none;
}

/* Mobile mkt+lang row */
.mob-row {
  display: none; align-items: center; justify-content: space-between;
  padding: 4px 16px 10px;
}

/* ── Ticker strip (mobile) ── */
.mob-strip {
  display: none; overflow-x: auto; scrollbar-width: none;
  background: var(--bg2); border-radius: 10px;
  margin: 0 16px 12px; border: 1px solid var(--bd);
}
.mob-strip::-webkit-scrollbar { display: none; }
.mob-tick-cell {
  display: flex; flex-direction: column; gap: 2px;
  padding: 10px 14px; border-right: 1px solid var(--bd);
  flex-shrink: 0; min-width: 88px;
}
.mob-tick-cell:last-child { border-right: none; }
.mob-tick-name  { font-size: 9px; font-weight: 700; color: var(--muted); letter-spacing: 0.05em; }
.mob-tick-price { font-family: var(--fn); font-size: 13px; font-weight: 500; color: var(--text); }

/* ── Main content wrapper ── */
.s-content { padding: 20px 24px 0; }

/* ── Panel ── */
.panel {
  background: var(--bg2); border: 1px solid var(--bd);
  border-radius: 12px; overflow: hidden; margin-bottom: 16px;
}
.panel-bc {
  padding: 12px 16px 0; display: flex; align-items: center; gap: 8px;
  font-size: 11px; color: var(--muted); font-weight: 600; letter-spacing: 0.05em;
}
.bc-dot   { font-size: 9px; color: var(--accent); }
.bc-label { color: var(--accent); }
.bc-sep   { opacity: 0.4; margin: 0 2px; }
.bc-sub   { opacity: 0.6; }

/* Signal tabs */
.sig-tabs {
  display: flex; border-bottom: 1px solid var(--bd);
  padding: 0; margin: 10px 0 0;
}
.sig-tab {
  padding: 8px 16px; font-size: 12px; font-weight: 600; letter-spacing: 0.04em;
  color: var(--muted); border: none; background: none; cursor: pointer;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
  transition: all 0.15s; text-transform: uppercase; text-decoration: none;
  font-family: 'DM Sans', sans-serif; display: inline-flex; align-items: center;
}
.sig-tab:hover { color: var(--text); }
.sig-tab.active { color: var(--accent) !important; border-bottom-color: var(--accent) !important; }

/* ── Table ── */
.tbl-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.stock-table { width: 100%; border-collapse: collapse; }
.stock-table-d { min-width: 680px; }
.stock-table-m { min-width: 320px; display: none; }
.stock-table th {
  padding: 8px 10px; font-size: 10px; font-weight: 600; letter-spacing: 0.07em;
  color: var(--muted); text-align: left; border-bottom: 1px solid var(--bd);
  white-space: nowrap; font-family: 'DM Sans', sans-serif;
}
.stock-table td {
  padding: 10px 10px; font-size: 13px; vertical-align: middle;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}
.stock-table tbody tr { cursor: default; transition: background 0.12s; }
.stock-table tbody tr:hover td { background: var(--bg3); }
.stock-table tbody tr:last-child td { border-bottom: none; }
.mkt-badge {
  font-size: 9px; font-weight: 700; padding: 2px 5px; border-radius: 3px;
  background: var(--bg3); color: var(--muted); letter-spacing: 0.05em;
  white-space: nowrap; font-family: 'DM Sans', sans-serif;
}
.tk-main { font-family: var(--fn); font-weight: 700; font-size: 14px; color: var(--text); }
.tk-sub  { font-family: var(--fn); font-size: 10px; color: var(--muted); margin-left: 6px; }
.num       { font-family: var(--fn); font-size: 13px; font-weight: 500; color: var(--text); }
.num-muted { font-family: var(--fn); font-size: 12px; color: var(--muted); }
a.toss-lnk {
  font-size: 10px; color: var(--muted); font-weight: 600; letter-spacing: 0.04em;
  opacity: 0.5; text-decoration: none; white-space: nowrap;
}
a.toss-lnk:hover { opacity: 1; color: var(--accent); }
.count-txt {
  font-family: 'DM Sans', sans-serif; color: var(--muted); font-size: 11px;
  letter-spacing: 0.04em; padding: 8px 16px 12px; opacity: 0.35;
}

/* Page nav */
.page-nav {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 12px 0;
}
.page-btn {
  width: 32px; height: 32px; border-radius: 6px; background: var(--bg3);
  border: 1px solid var(--bd); color: var(--text); font-size: 16px;
  display: flex; align-items: center; justify-content: center;
  text-decoration: none; cursor: pointer; transition: all 0.15s;
  font-family: 'DM Sans', sans-serif;
}
.page-btn:hover { border-color: var(--accent); color: var(--accent); }
.page-btn.disabled { opacity: 0.25; pointer-events: none; }
.page-info { font-family: var(--fn); font-size: 12px; color: var(--muted); min-width: 60px; text-align: center; }

/* ── Login ── */
.login-outer {
  min-height: 70vh; display: flex; align-items: center; justify-content: center;
  position: relative; padding: 32px 16px;
}
.login-glow {
  position: fixed; width: 600px; height: 600px; border-radius: 50%;
  background: radial-gradient(circle,rgba(198,241,53,0.06) 0%,transparent 70%);
  top: -100px; right: -100px; pointer-events: none; z-index: 0;
}
.login-grid {
  position: fixed; inset: 0; z-index: 0; opacity: 0.025; pointer-events: none;
  background-image:
    linear-gradient(rgba(255,255,255,.5) 1px,transparent 1px),
    linear-gradient(90deg,rgba(255,255,255,.5) 1px,transparent 1px);
  background-size: 40px 40px;
}
.login-card {
  width: 100%; max-width: 380px; background: var(--bg2);
  border: 1px solid var(--bd); border-radius: 16px;
  padding: 36px; position: relative; z-index: 1;
}
.login-logo { font-size: 24px; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 6px; color: var(--text); }
.login-logo em { font-style: normal; color: var(--accent); }
.login-sub { font-size: 13px; color: var(--muted); margin-bottom: 24px; }

/* Login Streamlit form styling */
.login-card [data-testid="stTextInput"] label,
.login-card [data-testid="stTextInput"] p {
  font-size: 11px !important; font-weight: 600 !important;
  letter-spacing: 0.06em !important; color: var(--muted) !important;
  text-transform: uppercase !important; font-family: 'DM Sans',sans-serif !important;
}
.login-card [data-testid="stTextInput"] input {
  background: var(--bg3) !important; border: 1px solid var(--bd) !important;
  border-radius: 8px !important; color: var(--text) !important;
  font-family: 'DM Sans',sans-serif !important; font-size: 14px !important;
  padding: 10px 14px !important;
}
.login-card [data-testid="stTextInput"] input:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 2px rgba(198,241,53,.12) !important;
}
.login-card [data-testid="stFormSubmitButton"] > button {
  background: var(--accent) !important; color: #000 !important;
  border: none !important; border-radius: 8px !important;
  font-size: 14px !important; font-weight: 700 !important;
  width: 100% !important; padding: 12px !important;
  font-family: 'DM Sans',sans-serif !important; letter-spacing: .02em !important;
}
.login-card [data-testid="stFormSubmitButton"] > button:hover {
  background: #d4f55a !important; transform: translateY(-1px) !important;
}

/* Login tab override */
div[data-baseweb="tab-list"] {
  background: var(--bg3) !important; border-radius: 8px !important; padding: 3px !important; gap: 2px !important;
}
button[data-baseweb="tab"] {
  background: none !important; border-radius: 6px !important;
  font-size: 13px !important; font-weight: 600 !important;
  color: var(--muted) !important; padding: 7px 20px !important;
  font-family: 'DM Sans',sans-serif !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
  background: var(--bg2) !important; color: var(--text) !important;
  box-shadow: 0 1px 3px rgba(0,0,0,.4) !important;
}
div[data-baseweb="tab-border"], div[data-baseweb="tab-highlight"] { display: none !important; }

/* Watchlist */
.wl-ticker { font-family: var(--fn); font-size: 13px; font-weight: 700; color: var(--text); }
.wl-sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
.ret-pos { font-family: var(--fn); font-size: 13px; font-weight: 600; color: var(--green); }
.ret-neg { font-family: var(--fn); font-size: 13px; font-weight: 600; color: var(--red); }
.my-welcome { font-size: 13px; color: var(--muted); padding: 4px 0 16px; }
.my-welcome em { font-style: normal; color: var(--accent); }

/* Watchlist delete button */
[data-testid="stButton"] > button {
  background: var(--bg3) !important; border: 1px solid var(--bd) !important;
  color: var(--muted) !important; font-size: 12px !important;
  padding: 4px 10px !important; border-radius: 6px !important;
  font-family: 'DM Sans',sans-serif !important; width: auto !important;
}
[data-testid="stButton"] > button:hover {
  border-color: var(--red) !important; color: var(--red) !important;
}

/* Misc */
.stAlert { background: var(--bg2) !important; border: 1px solid var(--bd) !important; border-radius: 8px !important; }
hr { border-color: rgba(255,255,255,.05) !important; margin: 8px 0 !important; }
::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-thumb { background: var(--bg3); border-radius: 2px; }

/* ── Mobile bottom nav ── */
.mob-bottom-nav {
  display: none; position: fixed; bottom: 0; left: 0; right: 0; z-index: 9999;
  background: var(--bg2); border-top: 1px solid var(--bd);
  padding: 8px 0 max(4px,env(safe-area-inset-bottom));
}
.mob-bottom-nav-inner { display: flex; justify-content: space-around; }
.mob-nav-item {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 4px 0; cursor: pointer; text-decoration: none;
}
.mob-nav-icon { font-size: 20px; line-height: 1; }
.mob-nav-label {
  font-size: 9px; font-weight: 600; letter-spacing: 0.04em;
  color: var(--muted); text-transform: uppercase; font-family: 'DM Sans',sans-serif;
}
.mob-nav-item.active .mob-nav-label { color: var(--accent); }

/* ── Responsive ── */
@media (max-width: 768px) {
  html, body, .stApp { overflow-x: hidden !important; max-width: 100vw !important; }

  .mob-hd       { display: flex !important; }
  .mob-row      { display: flex !important; }
  .mob-strip    { display: flex !important; }
  .mob-bottom-nav { display: block !important; }

  /* Hide desktop nav + sidebar */
  .s-nav { display: none !important; }
  section[data-testid="stSidebar"] { display: none !important; }

  /* Content padding */
  .s-content { padding: 0 0 0 !important; }
  .stMainBlockContainer, .block-container {
    padding-left: 0 !important; padding-right: 0 !important;
    padding-bottom: 90px !important;
  }

  .panel { border-radius: 8px; margin: 0 12px 12px; }
  .panel-bc { padding: 10px 12px 0; }
  .sig-tab { padding: 7px 12px; font-size: 11px; }

  .stock-table-d { display: none !important; }
  .stock-table-m { display: table !important; }

  .page-nav { padding: 8px 0; }
  .count-txt { padding: 6px 12px 10px; }
}
</style>
""", unsafe_allow_html=True)


# ── 자동새로고침 ─────────────────────────────────────────────
_refreshing = is_refreshing()
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=3_000 if _refreshing else 300_000, key="ar")
except ImportError:
    pass
if not _refreshing and st.session_state.get("_was_refreshing"):
    st.cache_data.clear()
st.session_state["_was_refreshing"] = _refreshing

# ── 데이터 ───────────────────────────────────────────────────
results      = load_results()
indices_data = fetch_indices()
lang         = st.session_state.lang
menu         = st.session_state.menu
mkt_code     = st.session_state.market
sigtab       = st.session_state.sigtab
signals      = results.get("signals", {})

gen_str = ""
if results:
    try:
        dt = datetime.fromisoformat(results["generated_at"]).astimezone(KST)
        gen_str = dt.strftime("%Y.%m.%d %H:%M KST")
    except Exception:
        pass

# 시장 변경 → 페이지 초기화
if st.session_state.get("_prev_market") != mkt_code:
    for pk in ("page_a1","page_a2","page_c1","page_c2","page_watch"):
        st.session_state[pk] = 0
    st.session_state["_prev_market"] = mkt_code


# ════════════════════════════════════════════════════════════
# HTML 빌더 함수들
# ════════════════════════════════════════════════════════════

def _a(v: bool) -> str:
    """Returns 'active' css class if True."""
    return " active" if v else ""


def _nav_html() -> str:
    en_a  = _a(lang == "en");   ko_a  = _a(lang == "ko")
    kr_a  = _a(mkt_code == "KR"); us_a  = _a(mkt_code == "US")
    avatar_label = (st.session_state.user or "?")[:2].upper()
    ref_btn = (f'<span class="spin">↺</span>' if _refreshing
               else f'<a href="?refresh=1" class="s-refresh-btn" title="Refresh">↺</a>')
    return f"""
<div class="s-nav">
  <div style="display:flex;align-items:center">
    <a class="s-nav-logo" href="?go=main">STOCK<em>al</em></a>
    <span class="s-nav-update">{gen_str or t("no_data")}</span>
  </div>
  <div class="s-nav-right">
    <div style="display:flex;align-items:center;gap:6px">
      <span class="s-ctrl-label">LANGUAGE</span>
      <div class="tg">
        <a class="tb{en_a}" href="?lang=en">EN</a>
        <a class="tb{ko_a}" href="?lang=ko">KO</a>
      </div>
    </div>
    <div class="tg">
      <a class="tb{kr_a}" href="?mkt=KR">KR</a>
      <a class="tb{us_a}" href="?mkt=US">US</a>
    </div>
    {ref_btn}
    <a href="?page=my" class="s-avatar">{avatar_label}</a>
  </div>
</div>"""


def _sidebar_html() -> str:
    # Indices
    idx_rows = ""
    for d in indices_data:
        name = d["label_en"] if lang == "en" else d["label_ko"]
        if d["val"] is None:
            idx_rows += (f'<div class="sb-idx">'
                         f'<div class="sb-idx-l"><span class="sb-idx-name">{name}</span>'
                         f'<span class="sb-idx-price" style="color:#2a3347">—</span></div></div>')
            continue
        val, chg, unit = d["val"], d["chg"], d["unit"]
        val_str = (f'{unit}{val:,.2f}' if unit in ("$","₩") else f'{val:,.2f}')
        sign    = "+" if chg >= 0 else ""
        cls     = "idx-up" if chg >= 0 else "idx-dn"
        idx_rows += (f'<div class="sb-idx">'
                     f'<div class="sb-idx-l"><span class="sb-idx-name">{name}</span>'
                     f'<span class="sb-idx-price">{val_str}</span></div>'
                     f'<span class="{cls}">{sign}{chg:.2f}%</span></div>')

    menu_items = [("MA20","MA20"), ("MA200","MA200"), ("WatchList","WatchList")]
    nav_rows   = "".join(
        f'<a class="sb-item{_a(menu==k)}" href="?menu={k}">'
        f'<span class="sb-dot"></span>{label}</a>'
        for k, label in menu_items
    )
    return f"""
<div class="sb-inner">
  <a class="sb-logo" href="?go=main">STOCK<em>al</em></a>
  <div class="sb-update">{gen_str or "—"}</div>
  <div class="sb-section">MENU</div>
  {nav_rows}
  <div class="sb-section" style="margin-top:14px">MARKET</div>
  {idx_rows}
</div>"""


def _mob_ticker_strip_html() -> str:
    cells = ""
    for d in indices_data:
        name = d["label_en"] if lang == "en" else d["label_ko"]
        if d["val"] is None:
            cells += (f'<div class="mob-tick-cell">'
                      f'<span class="mob-tick-name">{name}</span>'
                      f'<span class="mob-tick-price" style="color:#2a3347">—</span>'
                      f'<span class="idx-dn" style="font-size:10px">—</span></div>')
            continue
        val, chg, unit = d["val"], d["chg"], d["unit"]
        val_str = (f'{unit}{val:,.2f}' if unit in ("$","₩") else f'{val:,.2f}')
        sign    = "+" if chg >= 0 else ""
        cls     = "idx-up" if chg >= 0 else "idx-dn"
        cells += (f'<div class="mob-tick-cell">'
                  f'<span class="mob-tick-name">{name}</span>'
                  f'<span class="mob-tick-price">{val_str}</span>'
                  f'<span class="{cls}" style="font-size:10px">{sign}{chg:.2f}%</span></div>')
    return f'<div class="mob-strip">{cells}</div>'


def _breadcrumb_html(label: str, subtitle: str = "") -> str:
    sub = (f'<span class="bc-sep">→</span><span class="bc-sub">{subtitle}</span>'
           if subtitle else "")
    return (f'<div class="panel-bc">'
            f'<span class="bc-dot">◆</span>'
            f'<span class="bc-label">{label}</span>{sub}</div>')


def _signal_tabs_html(current: str, tabs: list[tuple[str,str,str]]) -> str:
    """tabs: list of (key, icon+label, href)"""
    items = "".join(
        f'<a class="sig-tab{_a(current==key)}" href="{href}">{label}</a>'
        for key, label, href in tabs
    )
    return f'<div class="sig-tabs">{items}</div>'


def _dist_badge(val) -> str:
    if val is None:
        return ('<span style="display:inline-block;min-width:52px;padding:3px 8px;'
                'border-radius:4px;background:#1A2236;color:#8892A4;'
                'font-family:JetBrains Mono,monospace;font-size:12px;'
                'font-weight:600;text-align:center">—</span>')
    n = float(val)
    if n >= 3:      color = '#22C55E'
    elif n >= 0:    color = '#86efac'
    elif n >= -3:   color = '#fca5a5'
    else:           color = '#FF4D4D'
    sign = "+" if n > 0 else ""
    bg   = color + "22"
    return (f'<span style="display:inline-block;min-width:52px;padding:3px 8px;'
            f'border-radius:4px;background:{bg};color:{color};'
            f'font-family:JetBrains Mono,monospace;font-size:12px;'
            f'font-weight:600;text-align:center">{sign}{n:.2f}%</span>')


def _chg_html(val) -> str:
    if val is None:
        return '<span style="font-family:JetBrains Mono,monospace;font-size:12px;color:#8892A4">—</span>'
    color = '#22C55E' if val >= 0 else '#FF4D4D'
    sign  = "+" if val > 0 else ""
    return (f'<span style="font-family:JetBrains Mono,monospace;font-size:12px;'
            f'font-weight:600;color:{color}">{sign}{val:.2f}%</span>')


def _fmt_cap(r) -> str:
    is_kr = r["market"] == "KR"
    if is_kr and r.get("market_cap_krw"):
        v = r["market_cap_krw"]
        return f"₩{v//1_000_000_000_000:.0f}T" if v >= 1_000_000_000_000 else f"₩{v//100_000_000:,}억"
    elif r.get("market_cap_usd"):
        return f"${r['market_cap_usd']//1_000_000:,}M"
    return "—"


def _render_panel(rows: list, dist_key: str, ref_key: str,
                  ref_label: str, total: int = None):
    """테이블 + 카운트 렌더링."""
    if not rows:
        st.markdown(
            '<div style="color:#8892A4;font-size:13px;padding:20px 16px;opacity:.6">'
            + t("no_signal") + '</div>',
            unsafe_allow_html=True)
        return

    td_d = ""
    td_m = ""

    for r in rows:
        mkt   = r["market"]
        flag  = "🇰🇷" if mkt == "KR" else "🇺🇸"
        tk    = r["ticker"]
        name  = r.get("name", tk)
        is_kr = mkt == "KR"
        fmt   = (lambda v: f"{v:,.0f}") if is_kr else (lambda v: f"{v:,.2f}")
        price = fmt(r["close"])
        ref_v = r.get(ref_key)
        ref   = fmt(ref_v) if ref_v is not None else "—"
        dist  = _dist_badge(r.get(dist_key))
        c1d   = _chg_html(r.get("chg1d"))
        c5d   = _chg_html(r.get("chg5d"))
        cap   = _fmt_cap(r)
        url   = f"https://tossinvest.com/stocks/{tk}"

        td_d += f"""<tr>
<td style="padding-left:14px;width:40px"><span class="mkt-badge">{mkt}</span></td>
<td><span class="tk-main">{flag} {name}</span><span class="tk-sub">{tk}</span></td>
<td class="num">{price}</td>
<td class="num-muted">{ref}</td>
<td>{dist}</td>
<td>{c1d}</td>
<td>{c5d}</td>
<td class="num-muted" style="font-size:12px">{cap}</td>
<td style="text-align:right;padding-right:14px"><a href="{url}" target="_blank" class="toss-lnk">TOSS →</a></td>
</tr>"""

        td_m += f"""<tr>
<td style="padding-left:12px">
  <div style="display:flex;align-items:center;gap:5px">
    <span class="mkt-badge">{mkt}</span>
    <span class="tk-main" style="font-size:13px">{flag} {name}</span>
  </div>
  <div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#8892A4;margin-top:2px">{tk} · {ref_label}: {ref} · {cap}</div>
</td>
<td class="num" style="font-size:12px;text-align:right;padding-right:6px">{price}</td>
<td style="text-align:right;padding-right:6px">{dist}</td>
<td style="text-align:right;padding-right:6px">{c1d}</td>
<td style="text-align:right;padding-right:12px">{c5d}</td>
</tr>"""

    count_label = f"{total if total is not None else len(rows)} {t('results')}"
    st.markdown(f"""
<div class="tbl-wrap">
<table class="stock-table stock-table-d">
<thead><tr>
<th></th><th>{t('ticker')}</th><th>{t('price')}</th>
<th>{ref_label}</th><th>{t('dist')}</th>
<th>{t('chg1d')}</th><th>{t('chg5d')}</th>
<th>{t('mktcap')}</th><th></th>
</tr></thead>
<tbody>{td_d}</tbody>
</table>
<table class="stock-table stock-table-m">
<thead><tr>
<th style="padding-left:12px">{t('ticker')}</th>
<th style="text-align:right">{t('price')}</th>
<th style="text-align:right">{t('dist')}</th>
<th style="text-align:right">{t('chg1d')}</th>
<th style="text-align:right;padding-right:12px">{t('chg5d')}</th>
</tr></thead>
<tbody>{td_m}</tbody>
</table>
</div>
<div class="count-txt">{count_label}</div>
""", unsafe_allow_html=True)


def _page_nav_html(page: int, n_pages: int, page_key: str):
    if n_pages <= 1:
        return
    prev_href = f"?{page_key}={page-1}"
    next_href = f"?{page_key}={page+1}"
    prev_dis  = " disabled" if page == 0 else ""
    next_dis  = " disabled" if page == n_pages - 1 else ""
    p_link    = f'href="{prev_href}"' if not prev_dis else ""
    n_link    = f'href="{next_href}"' if not next_dis else ""
    st.markdown(f"""
<div class="page-nav">
  <a class="page-btn{prev_dis}" {p_link}>‹</a>
  <span class="page-info">{page+1} / {n_pages}</span>
  <a class="page-btn{next_dis}" {n_link}>›</a>
</div>""", unsafe_allow_html=True)


def _get_page(signal_key: str, page_key: str, mf: str):
    rows    = signals.get(signal_key, [])
    if mf:
        rows = [r for r in rows if r["market"] == mf]
    total   = len(rows)
    n_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page    = min(st.session_state.get(page_key, 0), n_pages - 1)
    st.session_state[page_key] = page
    display = rows[page * PAGE_SIZE: (page + 1) * PAGE_SIZE]
    return display, page, n_pages, total


def _mob_bottom_nav_html() -> str:
    page = st.session_state.page
    nav = [
        ("MA20",      "📈", "MA20",  "?menu=MA20"),
        ("MA200",     "📊", "MA200", "?menu=MA200"),
        ("WatchList", "⭐", "Watch", "?menu=WatchList"),
        ("my",        "👤", "Login", "?page=my"),
    ]
    items = ""
    for key, icon, label, href in nav:
        is_active = (key == page) or (page == "main" and key == menu and key != "my")
        items += (f'<a class="mob-nav-item{_a(is_active)}" href="{href}">'
                  f'<span class="mob-nav-icon">{icon}</span>'
                  f'<span class="mob-nav-label">{label}</span></a>')
    return f'<div class="mob-bottom-nav"><div class="mob-bottom-nav-inner">{items}</div></div>'


# ════════════════════════════════════════════════════════════
# RENDER
# ════════════════════════════════════════════════════════════

# ── Sidebar ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown(_sidebar_html(), unsafe_allow_html=True)

# ── Desktop nav bar (HTML) ────────────────────────────────────
st.markdown(_nav_html(), unsafe_allow_html=True)

# ── Mobile header ─────────────────────────────────────────────
avatar_label = (st.session_state.user or "?")[:2].upper()
en_a = _a(lang=="en"); ko_a = _a(lang=="ko")
kr_a = _a(mkt_code=="KR"); us_a = _a(mkt_code=="US")
st.markdown(f"""
<div class="mob-hd">
  <div class="mob-logo">STOCK<em>al</em></div>
  <a href="?page=my" class="mob-avatar">{avatar_label}</a>
</div>
<div class="mob-row">
  <div style="display:flex;gap:6px">
    <a class="tb{kr_a}" href="?mkt=KR" style="border-radius:20px;padding:5px 14px">KR</a>
    <a class="tb{us_a}" href="?mkt=US" style="border-radius:20px;padding:5px 14px">US</a>
  </div>
  <div style="display:flex;align-items:center;gap:6px">
    <span style="font-size:10px;color:var(--muted);font-weight:600;letter-spacing:.05em">LANG</span>
    <div class="tg">
      <a class="tb{en_a}" href="?lang=en">EN</a>
      <a class="tb{ko_a}" href="?lang=ko">KO</a>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Mobile ticker strip ───────────────────────────────────────
st.markdown(_mob_ticker_strip_html(), unsafe_allow_html=True)

# ── Content wrapper open ──────────────────────────────────────
st.markdown('<div class="s-content">', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# MY / LOGIN PAGE
# ════════════════════════════════════════════════════════════
if st.session_state.page == "my":

    st.markdown(
        '<div class="login-glow"></div><div class="login-grid"></div>'
        '<div class="login-outer"><div class="login-card">',
        unsafe_allow_html=True)
    st.markdown(
        '<div class="login-logo">STOCK<em>al</em></div>'
        f'<div class="login-sub">{t("login_sub")}</div>',
        unsafe_allow_html=True)

    if not st.session_state.user:
        tab_l, tab_s = st.tabs([t("login"), t("signup")])

        with tab_l:
            with st.form("login_form"):
                uname = st.text_input(t("username"), placeholder="Enter your username")
                pw    = st.text_input(t("password"), type="password", placeholder="Enter your password")
                if st.form_submit_button(t("login")):
                    users = load_users(); hw = hashlib.sha256(pw.encode()).hexdigest()
                    if uname not in users:         st.error(t("err_user"))
                    elif users[uname].get("pw") != hw: st.error(t("err_pw"))
                    else:
                        st.session_state.user      = uname
                        st.session_state.watchlist = load_watchlist(uname)
                        st.session_state.page      = "main"
                        st.rerun()

        with tab_s:
            with st.form("signup_form"):
                new_u = st.text_input(t("username"), placeholder="Choose a username", key="su_u")
                new_p = st.text_input(t("password"), type="password", placeholder="8+ characters", key="su_p")
                if st.form_submit_button(t("signup")):
                    users = load_users()
                    if new_u in users:                    st.error(t("err_dup"))
                    elif len(new_u) < 2 or len(new_p) < 4: st.error("아이디 2자 이상, 비밀번호 4자 이상")
                    else:
                        users[new_u] = {"pw": hashlib.sha256(new_p.encode()).hexdigest(), "watchlist": []}
                        save_users(users)
                        st.success(t("ok_signup"))
    else:
        st.markdown(f'<div class="my-welcome">Welcome, <em>{st.session_state.user}</em></div>',
                    unsafe_allow_html=True)
        c1, _ = st.columns([2, 5])
        with c1:
            if st.button(t("logout")):
                st.session_state.user      = None
                st.session_state.watchlist = []
                st.session_state.page      = "main"
                st.rerun()

    st.markdown('</div></div>', unsafe_allow_html=True)
    st.markdown(_mob_bottom_nav_html(), unsafe_allow_html=True)
    st.stop()


# ════════════════════════════════════════════════════════════
# MAIN CONTENT
# ════════════════════════════════════════════════════════════

# ── MA20 ─────────────────────────────────────────────────────
if menu == "MA20":
    tabs = [
        ("A1", f"▲ {t('a1')}", "?sigtab=A1"),
        ("A2", f"▼ {t('a2')}", "?sigtab=A2"),
    ]
    st.markdown(
        '<div class="panel">'
        + _breadcrumb_html("MA20", "ICHIMOKU")
        + _signal_tabs_html(sigtab, tabs),
        unsafe_allow_html=True)
    st.markdown('<div style="padding:0 16px 16px">', unsafe_allow_html=True)

    if sigtab == "A1":
        rows, pg, np_, tot = _get_page("A1", "page_a1", mkt_code)
        _render_panel(rows, "dist_a_pct", "ma20", t("ma20"), total=tot)
        _page_nav_html(pg, np_, "page_a1")
    else:
        rows, pg, np_, tot = _get_page("A2", "page_a2", mkt_code)
        _render_panel(rows, "dist_a_pct", "ma20", t("ma20"), total=tot)
        _page_nav_html(pg, np_, "page_a2")

    st.markdown('</div></div>', unsafe_allow_html=True)


# ── MA200 ────────────────────────────────────────────────────
elif menu == "MA200":
    tabs = [
        ("C1", f"▲ {t('c1')}", "?sigtab=C1"),
        ("C2", f"▼ {t('c2')}", "?sigtab=C2"),
    ]
    st.markdown(
        '<div class="panel">'
        + _breadcrumb_html("MA200")
        + _signal_tabs_html(sigtab, tabs),
        unsafe_allow_html=True)
    st.markdown('<div style="padding:0 16px 16px">', unsafe_allow_html=True)

    if sigtab == "C1":
        rows, pg, np_, tot = _get_page("C1", "page_c1", mkt_code)
        _render_panel(rows, "dist_200_pct", "ma200", t("ma200"), total=tot)
        _page_nav_html(pg, np_, "page_c1")
    else:
        rows, pg, np_, tot = _get_page("C2", "page_c2", mkt_code)
        _render_panel(rows, "dist_200_pct", "ma200", t("ma200"), total=tot)
        _page_nav_html(pg, np_, "page_c2")

    st.markdown('</div></div>', unsafe_allow_html=True)


# ── WatchList ────────────────────────────────────────────────
elif menu == "WatchList":
    st.markdown(
        '<div class="panel">' + _breadcrumb_html("WatchList"),
        unsafe_allow_html=True)
    st.markdown('<div style="padding:8px 16px 16px">', unsafe_allow_html=True)

    if not st.session_state.user:
        st.markdown(
            f'<div style="color:#8892A4;font-size:13px;padding:12px 0;opacity:.7">'
            f'{t("login_req")}</div>',
            unsafe_allow_html=True)
    else:
        wl      = st.session_state.watchlist
        yf_syms = tuple(
            (w["ticker"]+".KS" if w["market"]=="KR" else w["ticker"]) for w in wl
        )
        raw_prices    = fetch_current_prices(yf_syms) if yf_syms else {}
        current_prices = {
            w["ticker"]: raw_prices.get(
                w["ticker"]+".KS" if w["market"]=="KR" else w["ticker"]
            ) for w in wl
        }

        if not wl:
            st.markdown(
                f'<div style="color:#8892A4;font-size:13px;padding:12px 0;opacity:.7">'
                f'{t("no_watch")}</div>',
                unsafe_allow_html=True)
        else:
            wl_pages = max(1, (len(wl) + PAGE_SIZE - 1) // PAGE_SIZE)
            wl_page  = min(st.session_state.get("page_watch",0), wl_pages-1)
            st.session_state["page_watch"] = wl_page
            wl_disp  = wl[wl_page*PAGE_SIZE: (wl_page+1)*PAGE_SIZE]

            to_remove = None
            for idx_w, w in enumerate(wl_disp):
                real_idx = wl_page * PAGE_SIZE + idx_w
                cur   = current_prices.get(w["ticker"])
                entry = w.get("entry_price", 0)
                is_kr = w["market"] == "KR"
                flag  = "🇰🇷" if is_kr else "🇺🇸"
                cur_s   = (f"{cur:,.0f}" if is_kr else f"${cur:,.2f}") if cur else "—"
                entry_s = (f"{entry:,.0f}" if is_kr else f"${entry:,.2f}") if entry else "—"
                ret_s, ret_cls = "—", "ret-pos"
                if cur and entry:
                    ret   = (cur - entry) / entry * 100
                    sign  = "+" if ret >= 0 else ""
                    ret_s = f"{sign}{ret:.2f}%"
                    ret_cls = "ret-pos" if ret >= 0 else "ret-neg"

                ci, cr, cd = st.columns([5, 2, 1])
                with ci:
                    st.markdown(
                        f'<div style="padding:6px 0">{flag} <span class="wl-ticker">'
                        f'{w.get("name",w["ticker"])}</span>'
                        f' <span style="font-family:JetBrains Mono,monospace;font-size:10px;color:#2a3347">'
                        f'{w["ticker"]}</span><br>'
                        f'<span class="wl-sub">{t("entry_price")}: {entry_s} → {t("current")}: {cur_s}'
                        f' · {t("added_at")}: {w.get("added_at","")}</span></div>',
                        unsafe_allow_html=True)
                with cr:
                    st.markdown(
                        f'<div class="{ret_cls}" style="padding-top:10px">{ret_s}</div>',
                        unsafe_allow_html=True)
                with cd:
                    if st.button(t("remove"), key=f"del_{real_idx}"):
                        to_remove = real_idx
                st.markdown("<hr>", unsafe_allow_html=True)

            if to_remove is not None:
                wl.pop(to_remove)
                save_watchlist(st.session_state.user, wl)
                st.session_state.watchlist = wl
                st.rerun()

            _page_nav_html(wl_page, wl_pages, "page_watch")

    st.markdown('</div></div>', unsafe_allow_html=True)


# ── Content wrapper close + mobile bottom nav ────────────────
st.markdown('</div>', unsafe_allow_html=True)
st.markdown(_mob_bottom_nav_html(), unsafe_allow_html=True)
