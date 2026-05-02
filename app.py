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
KST          = timezone(timedelta(hours=9))
PAGE_SIZE    = 15
IS_MOBILE    = False

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

# ── i18n ─────────────────────────────────────────────────────
T = {
    "site":        {"en": "STOCKal",                       "ko": "STOCKal"},
    "last_update": {"en": "LAST UPDATE",                   "ko": "마지막 갱신"},
    "no_data":     {"en": "NO DATA",                       "ko": "데이터 없음"},
    "refresh":     {"en": "REFRESH",                       "ko": "새로고침"},
    "kr":          {"en": "KR",                            "ko": "한국"},
    "us":          {"en": "US",                            "ko": "미국"},
    "a1":          {"en": "BREAKOUT",                      "ko": "돌파 완료"},
    "a2":          {"en": "APPROACHING 1%",                "ko": "돌파 임박 1%"},
    "c1":          {"en": "ABOVE MA200 2%",                "ko": "200MA 위 2%"},
    "c2":          {"en": "BELOW MA200 2%",                "ko": "200MA 아래 2%"},
    "ticker":      {"en": "TICKER",                        "ko": "종목"},
    "price":       {"en": "PRICE",                         "ko": "현재가"},
    "mktcap":      {"en": "MKTCAP",                        "ko": "시총"},
    "ma20":        {"en": "MA20",                          "ko": "MA20"},
    "ma200":       {"en": "MA200",                         "ko": "MA200"},
    "dist":        {"en": "DIST%",                         "ko": "거리%"},
    "chg1d":       {"en": "1D",                            "ko": "1일"},
    "chg5d":       {"en": "5D",                            "ko": "5일"},
    "no_signal":   {"en": "No signals found.",             "ko": "해당 종목 없음"},
    "results":     {"en": "results",                       "ko": "종목"},
    "my":          {"en": "MY",                            "ko": "MY"},
    "login":       {"en": "Log In",                        "ko": "로그인"},
    "signup":      {"en": "Sign Up",                       "ko": "회원가입"},
    "logout":      {"en": "LOG OUT",                       "ko": "로그아웃"},
    "username":    {"en": "USERNAME",                      "ko": "아이디"},
    "password":    {"en": "PASSWORD",                      "ko": "비밀번호"},
    "watchlist":   {"en": "WATCHLIST",                     "ko": "관심종목"},
    "entry_price": {"en": "ENTRY",                         "ko": "진입가"},
    "current":     {"en": "NOW",                           "ko": "현재가"},
    "return_pct":  {"en": "RETURN",                        "ko": "수익률"},
    "added_at":    {"en": "ADDED",                         "ko": "추가일"},
    "welcome":     {"en": "Welcome",                       "ko": "환영합니다"},
    "login_req":   {"en": "Log in to use watchlist.",      "ko": "로그인 후 이용 가능합니다."},
    "no_watch":    {"en": "No stocks in watchlist.",       "ko": "관심종목이 없습니다."},
    "remove":      {"en": "✕",                             "ko": "✕"},
    "err_pw":      {"en": "Wrong password",                "ko": "비밀번호 오류"},
    "err_user":    {"en": "Username not found",            "ko": "존재하지 않는 아이디"},
    "err_dup":     {"en": "Username already taken",        "ko": "이미 사용 중인 아이디"},
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

# ── 쿼리 파라미터 처리 ─────────────────────────────────────────
_qp = st.query_params
if _qp.get("go") == "main":
    st.session_state["page"] = "main"
    st.session_state["menu"] = st.session_state.get("menu", "MA20")
    st.query_params.clear()
    st.rerun()
if _qp.get("menu") in ["MA20", "MA200", "WatchList"]:
    st.session_state["menu"] = _qp.get("menu")
    st.session_state["page"] = "main"
    st.query_params.clear()
    st.rerun()
if _qp.get("page") == "my":
    st.session_state["page"] = "my"
    st.query_params.clear()
    st.rerun()

# ── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg:      #0A0E1A;
    --bg2:     #111827;
    --bg3:     #1A2236;
    --border:  rgba(255,255,255,0.07);
    --text:    #F0F2F7;
    --muted:   #8892A4;
    --accent:  #C6F135;
    --red:     #FF4D4D;
    --green:   #22C55E;
    --fn:      'JetBrains Mono', monospace;
}

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: var(--bg) !important; }
.stMainBlockContainer { padding-top: 16px !important; padding-bottom: 80px !important; }

/* ── Sidebar ─────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: var(--bg) !important;
    border-right: 1px solid var(--border) !important;
    min-width: 200px !important; max-width: 200px !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 12px !important; }

/* Hide sidebar toggle button */
[data-testid="stSidebarNavLink"], button[kind="header"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stSidebarCollapseButton"] { display: none !important; }

.sb-logo {
    font-size: 18px; font-weight: 700; letter-spacing: -0.03em;
    color: var(--text); padding: 4px 8px 4px; cursor: pointer;
    display: block; text-decoration: none;
}
.sb-logo em { font-style: normal; color: var(--accent); }
.sb-update { font-size: 10px; color: #2a3347; letter-spacing: 0.04em; padding: 0 8px 12px; }
.sb-section {
    font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
    color: var(--muted); padding: 12px 8px 4px; text-transform: uppercase;
}

/* Sidebar nav anchor links */
.sb-item {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 10px; border-radius: 8px;
    font-size: 13px; font-weight: 500; color: var(--muted);
    cursor: pointer; transition: all 0.15s;
    text-decoration: none; margin-bottom: 2px;
}
.sb-item:hover { color: var(--text); background: var(--bg3); }
.sb-item.active { color: var(--text); background: var(--bg3); }
.sb-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: rgba(255,255,255,0.1); flex-shrink: 0;
}
.sb-item.active .sb-dot { background: var(--accent); }

/* Sidebar indices */
.sb-idx-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.03);
    border-radius: 4px;
}
.sb-idx-left { display: flex; flex-direction: column; gap: 1px; }
.sb-idx-name  { font-size: 9px; font-weight: 700; color: var(--muted); letter-spacing: 0.05em; }
.sb-idx-price { font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 500; color: var(--text); }
.sb-idx-up  { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; color: var(--green); }
.sb-idx-dn  { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; color: var(--red); }

/* ── Top controls bar ────────────────────────────────── */
.top-ctrl-bar {
    display: flex; align-items: center; justify-content: flex-end;
    gap: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--border);
    margin-bottom: 16px; flex-wrap: wrap;
}
.ctrl-label { font-size: 10px; font-weight: 600; letter-spacing: 0.06em; color: var(--muted); }
.toggle-group {
    display: inline-flex; background: var(--bg3); border-radius: 8px; padding: 3px; gap: 2px;
}
.t-btn {
    padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 600;
    letter-spacing: 0.04em; border: none; cursor: pointer; transition: all 0.15s;
    color: var(--muted); background: none; font-family: 'DM Sans', sans-serif;
}
.t-btn.active { background: var(--accent); color: #000; }
.t-btn:hover:not(.active) { color: var(--text); background: rgba(255,255,255,0.05); }

/* Streamlit buttons (top controls) */
div[data-testid="stButton"] > button {
    background: var(--bg3) !important; border: 1px solid var(--border) !important;
    color: var(--muted) !important; font-family: 'DM Sans', sans-serif !important;
    font-size: 12px !important; font-weight: 600 !important;
    padding: 5px 14px !important; border-radius: 8px !important;
    letter-spacing: 0.04em !important; transition: all 0.15s !important;
    width: auto !important;
}
div[data-testid="stButton"] > button:hover {
    color: var(--text) !important; border-color: rgba(255,255,255,0.2) !important;
}

/* ── Mobile header ───────────────────────────────────── */
.mob-header {
    display: none;
    align-items: center; justify-content: space-between;
    padding: 12px 4px 8px;
}
.mob-logo { font-size: 18px; font-weight: 700; letter-spacing: -0.03em; color: var(--text); }
.mob-logo em { font-style: normal; color: var(--accent); }
.mob-avatar {
    width: 30px; height: 30px; border-radius: 50%;
    background: linear-gradient(135deg, var(--accent), #00D4AA);
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; color: #000; cursor: pointer;
    text-decoration: none;
}

/* Mobile market+lang row */
.mob-mkt-row {
    display: none;
    align-items: center; justify-content: space-between;
    padding: 4px 4px 8px;
}

/* ── Ticker strip (mobile) ───────────────────────────── */
.mob-ticker-strip {
    display: none; overflow-x: auto; scrollbar-width: none;
    background: var(--bg2); border-radius: 10px; margin-bottom: 12px;
    border: 1px solid var(--border);
}
.mob-ticker-strip::-webkit-scrollbar { display: none; }
.mob-ticker-cell {
    display: flex; flex-direction: column; gap: 2px;
    padding: 10px 14px; border-right: 1px solid var(--border);
    flex-shrink: 0; min-width: 90px;
}
.mob-ticker-cell:last-child { border-right: none; }
.mob-ticker-name  { font-size: 9px; font-weight: 700; color: var(--muted); letter-spacing: 0.05em; }
.mob-ticker-price { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 500; color: var(--text); }
.mob-ticker-up    { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; color: var(--green); }
.mob-ticker-dn    { font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; color: var(--red); }

/* ── Panel / breadcrumb ──────────────────────────────── */
.panel {
    background: var(--bg2); border: 1px solid var(--border);
    border-radius: 12px; overflow: hidden; margin-bottom: 16px;
}
.panel-bc {
    padding: 12px 16px 0; display: flex; align-items: center; gap: 8px;
    font-size: 11px; color: var(--muted); font-weight: 600; letter-spacing: 0.05em;
}
.bc-dot    { font-size: 9px; color: var(--accent); }
.bc-label  { color: var(--accent); }
.bc-sep    { opacity: 0.4; }
.bc-sub    { opacity: 0.6; }

/* ── Signal tab radio ────────────────────────────────── */
div[data-testid="stRadio"][data-role="signal-tabs"] > div {
    gap: 0 !important; flex-direction: row !important;
    border-bottom: 1px solid var(--border);
    padding: 0 4px;
}
div[data-testid="stRadio"][data-role="signal-tabs"] label {
    padding: 8px 16px !important; font-size: 12px !important;
    font-weight: 600 !important; letter-spacing: 0.04em !important;
    color: var(--muted) !important; background: none !important;
    border: none !important; border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    text-transform: uppercase !important; cursor: pointer !important;
    margin-bottom: -1px !important;
}
div[data-testid="stRadio"][data-role="signal-tabs"] label:has(input:checked) {
    color: var(--accent) !important;
    border-bottom-color: var(--accent) !important;
    background: none !important;
}

/* Market radio (top bar) */
div[data-testid="stRadio"][data-role="market-filter"] > div {
    gap: 4px !important; flex-direction: row !important;
}
div[data-testid="stRadio"][data-role="market-filter"] label {
    padding: 4px 12px !important; font-size: 12px !important; font-weight: 600 !important;
    letter-spacing: 0.04em !important; color: var(--muted) !important;
    background: var(--bg3) !important; border: none !important;
    border-radius: 20px !important; cursor: pointer !important;
}
div[data-testid="stRadio"][data-role="market-filter"] label:has(input:checked) {
    color: #000 !important; background: var(--accent) !important; font-weight: 700 !important;
}

/* ── Stock table ─────────────────────────────────────── */
.tbl-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.stock-table { width: 100%; border-collapse: collapse; }
.stock-table-d { min-width: 680px; }
.stock-table-m { min-width: 340px; display: none; }
.stock-table th {
    padding: 8px 10px; font-size: 10px; font-weight: 600; letter-spacing: 0.07em;
    color: var(--muted); text-align: left; border-bottom: 1px solid var(--border);
    white-space: nowrap; background: transparent;
}
.stock-table td { padding: 10px 10px; font-size: 13px; vertical-align: middle; border-bottom: 1px solid rgba(255,255,255,0.04); }
.stock-table tbody tr:hover td { background: var(--bg3); }
.stock-table tbody tr:last-child td { border-bottom: none; }
.mkt-badge {
    font-size: 9px; font-weight: 700; padding: 2px 5px; border-radius: 3px;
    background: var(--bg3); color: var(--muted); letter-spacing: 0.05em; white-space: nowrap;
}
.tk-main { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 14px; color: var(--text); }
.tk-sub  { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--muted); margin-left: 6px; }
.num { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 500; color: var(--text); }
.num-muted { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--muted); }
a.toss-lnk {
    font-size: 10px; color: var(--muted); font-weight: 600; letter-spacing: 0.04em;
    opacity: 0.6; text-decoration: none; white-space: nowrap;
}
a.toss-lnk:hover { opacity: 1; color: var(--accent); }
.count-txt {
    color: var(--muted); font-size: 11px; letter-spacing: 0.05em;
    padding: 8px 16px 12px; opacity: 0.35;
}

/* ── Page nav ────────────────────────────────────────── */
.nav-wrap { padding: 6px 0 4px; }

/* ── Spin ─────────────────────────────────────────────── */
@keyframes spin { to { transform: rotate(-360deg); } }
.spin-icon { display: inline-block; animation: spin 1s linear infinite; color: var(--accent); }

/* ── Login card ──────────────────────────────────────── */
.login-outer {
    min-height: 60vh; background: var(--bg);
    display: flex; align-items: center; justify-content: center;
    position: relative; overflow: hidden; padding: 32px 16px;
}
.login-glow {
    position: fixed; width: 500px; height: 500px; border-radius: 50%;
    background: radial-gradient(circle, rgba(198,241,53,0.06) 0%, transparent 70%);
    top: -100px; right: -100px; pointer-events: none; z-index: 0;
}
.login-grid {
    position: fixed; inset: 0; z-index: 0; opacity: 0.03; pointer-events: none;
    background-image:
        linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px);
    background-size: 40px 40px;
}
.login-card {
    width: 100%; max-width: 380px; background: var(--bg2);
    border: 1px solid var(--border); border-radius: 16px;
    padding: 36px; position: relative; z-index: 1;
}
.login-logo { font-size: 24px; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 6px; color: var(--text); }
.login-logo em { font-style: normal; color: var(--accent); }
.login-sub { font-size: 13px; color: var(--muted); margin-bottom: 24px; }

/* Form fields inside login card */
.login-card div[data-testid="stTextInput"] input,
.mob-login-form div[data-testid="stTextInput"] input {
    background: var(--bg3) !important; border: 1px solid var(--border) !important;
    border-radius: 8px !important; color: var(--text) !important;
    font-family: 'DM Sans', sans-serif !important; font-size: 14px !important;
}
.login-card div[data-testid="stTextInput"] input:focus,
.mob-login-form div[data-testid="stTextInput"] input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(198,241,53,0.12) !important;
}
.login-card div[data-testid="stTextInput"] label,
.mob-login-form div[data-testid="stTextInput"] label {
    font-size: 11px !important; font-weight: 600 !important;
    letter-spacing: 0.06em !important; color: var(--muted) !important;
    text-transform: uppercase !important;
}
.login-card div[data-testid="stFormSubmitButton"] > button,
.mob-login-form div[data-testid="stFormSubmitButton"] > button {
    background: var(--accent) !important; color: #000 !important;
    border: none !important; border-radius: 8px !important;
    font-size: 14px !important; font-weight: 700 !important;
    width: 100% !important; padding: 12px !important;
    letter-spacing: 0.02em !important;
}
.login-card div[data-testid="stFormSubmitButton"] > button:hover,
.mob-login-form div[data-testid="stFormSubmitButton"] > button:hover {
    background: #d4f55a !important;
}

/* Tab styles in login */
div[data-baseweb="tab-list"] { background: var(--bg3) !important; border-radius: 8px !important; padding: 3px !important; gap: 2px !important; }
button[data-baseweb="tab"] {
    background: none !important; border-radius: 6px !important;
    font-size: 13px !important; font-weight: 600 !important;
    color: var(--muted) !important; padding: 7px 16px !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    background: var(--bg2) !important; color: var(--text) !important;
    border-bottom: none !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.4) !important;
}
div[data-baseweb="tab-border"] { display: none !important; }

/* Watchlist */
.wl-ticker { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700; color: var(--text); }
.wl-sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
.ret-pos { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 600; color: var(--green); }
.ret-neg { font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 600; color: var(--red); }

/* Welcome / My page */
.my-welcome { font-size: 13px; color: var(--muted); letter-spacing: 0.04em; padding: 8px 0 16px; }
.my-welcome em { font-style: normal; color: var(--accent); }

/* Misc */
hr { border-color: rgba(255,255,255,0.06) !important; margin: 10px 0 !important; }
.stAlert { background: var(--bg2) !important; border: 1px solid var(--border) !important; border-radius: 8px !important; }
::-webkit-scrollbar { width: 3px; height: 3px; }
::-webkit-scrollbar-thumb { background: var(--bg3); border-radius: 2px; }

/* ── Mobile bottom nav ───────────────────────────────── */
.mob-bottom-nav {
    display: none;
    position: fixed; bottom: 0; left: 0; right: 0; z-index: 9999;
    background: var(--bg2); border-top: 1px solid var(--border);
    padding: 8px 0 max(4px, env(safe-area-inset-bottom));
    justify-content: space-around; align-items: stretch;
}
.mob-nav-item {
    display: flex; flex-direction: column; align-items: center; gap: 3px;
    padding: 4px 8px; cursor: pointer; text-decoration: none; flex: 1;
}
.mob-nav-icon { font-size: 18px; line-height: 1; }
.mob-nav-label {
    font-size: 9px; font-weight: 600; letter-spacing: 0.04em;
    color: var(--muted); text-transform: uppercase;
}
.mob-nav-item.active .mob-nav-label { color: var(--accent); }

/* ── Responsive breakpoint ───────────────────────────── */
@media (max-width: 768px) {
    html, body, .stApp { overflow-x: hidden !important; max-width: 100vw !important; }

    /* Show mobile elements */
    .mob-header       { display: flex !important; }
    .mob-mkt-row      { display: flex !important; }
    .mob-ticker-strip { display: flex !important; }
    .mob-bottom-nav   { display: flex !important; }

    /* Hide desktop sidebar & top controls */
    [data-testid="stSidebar"]  { display: none !important; }
    .desktop-ctrl-bar          { display: none !important; }

    /* Content padding for bottom nav */
    .stMainBlockContainer { padding-bottom: 90px !important; padding-left: 12px !important; padding-right: 12px !important; }

    /* Table: hide desktop, show mobile */
    .stock-table-d { display: none !important; }
    .stock-table-m { display: table !important; }

    /* Sidebar occupy full width when toggled (mobile) */
    [data-testid="stSidebar"] { width: 100% !important; }
}
</style>
""", unsafe_allow_html=True)

# ── 세션 초기화 ───────────────────────────────────────────────
_defaults = {
    "lang": "en", "page": "main", "user": None, "watchlist": [],
    "menu": "MA20", "market": "KR",
    "page_a1": 0, "page_a2": 0,
    "page_c1": 0, "page_c2": 0,
    "page_watch": 0, "_prev_market": "BOOT",
}
for _k, _v in _defaults.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── 유저 DB ──────────────────────────────────────────────────
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
        raw = yf.download(tickers, period="5d", auto_adjust=True,
                          progress=False, threads=True)
        for idx in INDICES:
            sym = idx["ticker"]
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    close = raw["Close"][sym].dropna()
                else:
                    close = raw["Close"].dropna()
                if len(close) < 2:
                    raise ValueError
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
def _dist_badge(val) -> str:
    """DIST% colored badge (transparent background)."""
    if val is None:
        return ('<span style="display:inline-block;min-width:52px;padding:3px 8px;'
                'border-radius:4px;background:#1A2236;color:#8892A4;'
                'font-family:JetBrains Mono,monospace;font-size:12px;'
                'font-weight:600;text-align:center">—</span>')
    n = float(val)
    if n >= 3:     color = '#22C55E'
    elif n >= 0:   color = '#86efac'
    elif n >= -3:  color = '#fca5a5'
    else:          color = '#FF4D4D'
    sign = "+" if n > 0 else ""
    bg   = color + "22"   # ~13% opacity
    return (f'<span style="display:inline-block;min-width:52px;padding:3px 8px;'
            f'border-radius:4px;background:{bg};color:{color};'
            f'font-family:JetBrains Mono,monospace;font-size:12px;'
            f'font-weight:600;text-align:center">{sign}{n:.2f}%</span>')

def _chg_html(val) -> str:
    """1D / 5D change with green/red color."""
    if val is None:
        return '<span style="font-family:JetBrains Mono,monospace;font-size:12px;color:#8892A4">—</span>'
    color = '#22C55E' if val >= 0 else '#FF4D4D'
    sign  = "+" if val > 0 else ""
    return (f'<span style="font-family:JetBrains Mono,monospace;font-size:12px;'
            f'font-weight:600;color:{color}">{sign}{val:.2f}%</span>')


def _render_table(rows: list, dist_key: str, ref_key: str, ref_label: str,
                  total: int = None):
    """데스크탑·모바일 이중 테이블 렌더링."""
    if not rows:
        st.markdown(
            '<div style="color:#8892A4;font-size:13px;padding:20px 16px;opacity:0.5">'
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
        if is_kr and r.get("market_cap_krw"):
            cap = f"₩{r['market_cap_krw']//1_000_000_000_000:.0f}T" if r['market_cap_krw'] >= 1_000_000_000_000 else f"₩{r['market_cap_krw']//100_000_000:,}억"
        elif r.get("market_cap_usd"):
            cap = f"${r['market_cap_usd']//1_000_000:,}M"
        else:
            cap = "—"
        url = f"https://tossinvest.com/stocks/{tk}"

        # Desktop row
        td_d += f"""<tr>
  <td style="padding-left:14px"><span class="mkt-badge">{mkt}</span></td>
  <td><span class="tk-main">{flag}&nbsp;{name}</span><span class="tk-sub">{tk}</span></td>
  <td class="num">{price}</td>
  <td class="num-muted">{ref}</td>
  <td>{dist}</td>
  <td>{c1d}</td>
  <td>{c5d}</td>
  <td class="num-muted" style="font-size:12px">{cap}</td>
  <td style="text-align:right;padding-right:14px"><a href="{url}" target="_blank" class="toss-lnk">TOSS →</a></td>
</tr>"""

        # Mobile row (TICKER+sub | PRICE | DIST% | 1D | 5D)
        ma_sub = f"{ref_label}: {ref}"
        td_m += f"""<tr>
  <td style="padding-left:12px">
    <div style="display:flex;align-items:center;gap:5px">
      <span class="mkt-badge">{mkt}</span>
      <span class="tk-main" style="font-size:13px">{flag}&nbsp;{name}</span>
    </div>
    <div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#8892A4;margin-top:2px">{tk} · {ma_sub} · {cap}</div>
  </td>
  <td class="num" style="font-size:12px;text-align:right">{price}</td>
  <td style="text-align:right">{dist}</td>
  <td style="text-align:right">{c1d}</td>
  <td style="text-align:right">{c5d}</td>
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
      <th style="text-align:right">{t('chg5d')}</th>
    </tr></thead>
    <tbody>{td_m}</tbody>
  </table>
</div>
<div class="count-txt">{count_label}</div>
""", unsafe_allow_html=True)


def _page_nav(page: int, n_pages: int, page_key: str):
    if n_pages <= 1:
        return
    _, nav_c, _ = st.columns([3, 2, 3])
    with nav_c:
        cl, cm, cr = st.columns([1, 2, 1])
        with cl:
            if st.button("‹", key=f"{page_key}_p", disabled=(page == 0)):
                st.session_state[page_key] = page - 1; st.rerun()
        with cm:
            st.markdown(
                f'<div style="text-align:center;color:#8892A4;font-size:11px;padding-top:8px">'
                f'{page+1} / {n_pages}</div>', unsafe_allow_html=True)
        with cr:
            if st.button("›", key=f"{page_key}_n", disabled=(page == n_pages - 1)):
                st.session_state[page_key] = page + 1; st.rerun()


def _get_page(signal_key: str, page_key: str, mf: str):
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
    if is_refreshing():
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(REFRESH_FLAG, "w") as f:
        f.write(datetime.now().isoformat())
    def _run():
        try:
            py   = sys.executable
            base = os.path.dirname(__file__)
            subprocess.run([py, os.path.join(base, "fetch_data.py"), "--market", "all"],
                           capture_output=True, text=True)
            subprocess.run([py, os.path.join(base, "signals.py")],
                           capture_output=True, text=True)
        finally:
            if os.path.exists(REFRESH_FLAG):
                os.remove(REFRESH_FLAG)
    threading.Thread(target=_run, daemon=True).start()


# ── 자동 새로고침 ────────────────────────────────────────────
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
mkt_code     = st.session_state.market      # "KR" or "US"
signals      = results.get("signals", {})

gen_str = ""
if results:
    try:
        dt = datetime.fromisoformat(results["generated_at"]).astimezone(KST)
        gen_str = dt.strftime("%Y.%m.%d %H:%M KST")
    except Exception:
        pass

# Market filter 변경 → 페이지 초기화
if st.session_state.get("_prev_market") != mkt_code:
    for pk in ("page_a1","page_a2","page_c1","page_c2","page_watch"):
        st.session_state[pk] = 0
    st.session_state["_prev_market"] = mkt_code


# ── 사이드바 (데스크탑) ──────────────────────────────────────
def _sb_indices_html(data: list) -> str:
    items = ""
    for d in data:
        name = d["label_en"] if lang == "en" else d["label_ko"]
        if d["val"] is None:
            items += (f'<div class="sb-idx-item">'
                      f'<div class="sb-idx-left"><span class="sb-idx-name">{name}</span>'
                      f'<span class="sb-idx-price" style="color:#2a3347">—</span></div></div>')
            continue
        val, chg, unit = d["val"], d["chg"], d["unit"]
        val_str = f'{unit}{val:,.2f}' if unit in ("$","₩") else f'{val:,.2f}'
        sign    = "+" if chg >= 0 else ""
        cls     = "sb-idx-up" if chg >= 0 else "sb-idx-dn"
        items += (f'<div class="sb-idx-item">'
                  f'<div class="sb-idx-left"><span class="sb-idx-name">{name}</span>'
                  f'<span class="sb-idx-price">{val_str}</span></div>'
                  f'<span class="{cls}">{sign}{chg:.2f}%</span></div>')
    return items

with st.sidebar:
    # Logo
    st.markdown(
        f'<a class="sb-logo" href="?go=main">STOCK<em>al</em></a>'
        f'<div class="sb-update">{gen_str or t("no_data")}</div>',
        unsafe_allow_html=True)

    # MENU nav
    menu_items = [("MA20", "📈"), ("MA200", "📊"), ("WatchList", "⭐")]
    st.markdown('<div class="sb-section">MENU</div>', unsafe_allow_html=True)
    for item, icon in menu_items:
        active_cls = " active" if menu == item else ""
        st.markdown(
            f'<a class="sb-item{active_cls}" href="?menu={item}">'
            f'<span class="sb-dot"></span>{item}</a>',
            unsafe_allow_html=True)

    # MARKET indices
    st.markdown('<div class="sb-section" style="margin-top:16px">MARKET</div>',
                unsafe_allow_html=True)
    st.markdown(_sb_indices_html(indices_data), unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# MOBILE header / ticker strip / mkt-lang row
# (CSS hides these on desktop, shows on mobile)
# ════════════════════════════════════════════════════════════

# Mobile: logo + avatar
user_initials = (st.session_state.user or "?")[:2].upper()
st.markdown(
    f'<div class="mob-header">'
    f'  <div class="mob-logo">STOCK<em>al</em></div>'
    f'  <a class="mob-avatar" href="?page=my">{user_initials}</a>'
    f'</div>',
    unsafe_allow_html=True)

# Mobile: KR/US + LANG row (HTML with JS onclick → query param)
_m_kr_active = "active" if mkt_code == "KR" else ""
_m_us_active = "active" if mkt_code == "US" else ""
_l_en_active = "active" if lang == "en" else ""
_l_ko_active = "active" if lang == "ko" else ""
st.markdown(f"""
<div class="mob-mkt-row">
  <div style="display:flex;gap:8px">
    <button class="t-btn {_m_kr_active}" onclick="location.href='?mkt=KR'">KR</button>
    <button class="t-btn {_m_us_active}" onclick="location.href='?mkt=US'">US</button>
  </div>
  <div style="display:flex;align-items:center;gap:6px">
    <span class="ctrl-label">LANG</span>
    <div class="toggle-group">
      <button class="t-btn {_l_en_active}" onclick="location.href='?lang=en'">EN</button>
      <button class="t-btn {_l_ko_active}" onclick="location.href='?lang=ko'">KO</button>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# Handle mobile KR/US & LANG from query params
if st.query_params.get("mkt") in ("KR", "US"):
    st.session_state["market"] = st.query_params.get("mkt")
    st.query_params.clear(); st.rerun()
if st.query_params.get("lang") in ("en", "ko"):
    st.session_state["lang"] = st.query_params.get("lang")
    st.query_params.clear(); st.rerun()

# Mobile ticker strip
def _mob_ticker_strip(data: list) -> str:
    cells = ""
    for d in data:
        name = d["label_en"] if lang == "en" else d["label_ko"]
        if d["val"] is None:
            cells += (f'<div class="mob-ticker-cell">'
                      f'<span class="mob-ticker-name">{name}</span>'
                      f'<span class="mob-ticker-price" style="color:#2a3347">—</span>'
                      f'<span class="mob-ticker-dn">—</span></div>')
            continue
        val, chg, unit = d["val"], d["chg"], d["unit"]
        val_str = f'{unit}{val:,.2f}' if unit in ("$","₩") else f'{val:,.2f}'
        sign    = "+" if chg >= 0 else ""
        cls     = "mob-ticker-up" if chg >= 0 else "mob-ticker-dn"
        cells += (f'<div class="mob-ticker-cell">'
                  f'<span class="mob-ticker-name">{name}</span>'
                  f'<span class="mob-ticker-price">{val_str}</span>'
                  f'<span class="{cls}">{sign}{chg:.2f}%</span></div>')
    return f'<div class="mob-ticker-strip">{cells}</div>'

st.markdown(_mob_ticker_strip(indices_data), unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# DESKTOP top control bar (hidden on mobile via CSS)
# ════════════════════════════════════════════════════════════
st.markdown('<div class="desktop-ctrl-bar">', unsafe_allow_html=True)
ctrl_space, ctrl_lang, ctrl_mkt, ctrl_ref, ctrl_my = st.columns([4, 1, 1, 1, 1])

with ctrl_lang:
    if st.button("EN" if lang == "ko" else "KO", key="lang_btn"):
        st.session_state.lang = "ko" if lang == "en" else "en"
        st.rerun()

with ctrl_mkt:
    other_mkt = "US" if mkt_code == "KR" else "KR"
    if st.button(f"→ {other_mkt}", key="mkt_btn"):
        st.session_state.market = other_mkt
        st.session_state["_prev_market"] = "RESET"
        st.rerun()

with ctrl_ref:
    if _refreshing:
        st.markdown('<div style="text-align:center;padding:5px 0"><span class="spin-icon">↺</span></div>',
                    unsafe_allow_html=True)
    else:
        if st.button("↺", key="ref_btn"):
            start_background_refresh(); st.rerun()

with ctrl_my:
    if st.session_state.page == "main":
        if st.button("◉", key="my_btn"):
            if st.session_state.user:
                st.session_state.watchlist = load_watchlist(st.session_state.user)
            st.session_state.page = "my"; st.rerun()
    else:
        if st.button("←", key="back_btn"):
            st.session_state.page = "main"; st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# Market badge display (desktop)
st.markdown(
    f'<div style="display:none" class="desktop-ctrl-bar"></div>',
    unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# MY / LOGIN PAGE
# ════════════════════════════════════════════════════════════
if st.session_state.page == "my":

    st.markdown(
        '<div class="login-glow"></div><div class="login-grid"></div>',
        unsafe_allow_html=True)

    st.markdown('<div class="login-outer"><div class="login-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="login-logo">STOCK<em>al</em></div>'
        '<div class="login-sub">Please log in to continue</div>',
        unsafe_allow_html=True)

    if not st.session_state.user:
        tab_login, tab_signup = st.tabs([t("login"), t("signup")])

        with tab_login:
            with st.form("login_form"):
                uname = st.text_input(t("username"), placeholder="Enter your username")
                pw    = st.text_input(t("password"), type="password", placeholder="Enter your password")
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
                new_u = st.text_input(t("username"), placeholder="Choose a username", key="su_u")
                new_p = st.text_input(t("password"), type="password",
                                      placeholder="8+ characters", key="su_p")
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
        st.markdown(
            f'<div class="my-welcome">{t("welcome")}, <em>{st.session_state.user}</em></div>',
            unsafe_allow_html=True)
        col_logout, _ = st.columns([2, 5])
        with col_logout:
            if st.button(t("logout")):
                st.session_state.user      = None
                st.session_state.watchlist = []
                st.session_state.page      = "main"
                st.rerun()

    st.markdown('</div></div>', unsafe_allow_html=True)
    st.stop()


# ════════════════════════════════════════════════════════════
# MAIN CONTENT
# ════════════════════════════════════════════════════════════

# Breadcrumb helper
def _bc(label: str, subtitle: str = "") -> str:
    sub_part = f'<span class="bc-sep">→</span><span class="bc-sub">{subtitle}</span>' if subtitle else ""
    return (f'<div class="panel-bc">'
            f'<span class="bc-dot">◆</span>'
            f'<span class="bc-label">{label}</span>'
            f'{sub_part}</div>')

# Signal tab helper (using st.radio styled as tabs)
def _sig_tabs(key: str, labels: list[str], icons: list[str]) -> int:
    """Render signal tabs, return selected index (0 or 1)."""
    options = [f"{icons[i]} {labels[i]}" for i in range(len(labels))]
    st.markdown(f'<div data-role="signal-tabs" style="height:0;overflow:hidden"></div>',
                unsafe_allow_html=True)
    sel = st.radio("", options, horizontal=True,
                   key=key, label_visibility="collapsed",
                   index=0 if key not in st.session_state else None)
    return options.index(sel) if sel in options else 0


# ── MA20 ─────────────────────────────────────────────────────
if menu == "MA20":
    st.markdown(_bc("MA20", "ICHIMOKU"), unsafe_allow_html=True)

    # Signal tabs as radio
    sig_options = [f"▲ {t('a1')}", f"▼ {t('a2')}"]
    sig_sel = st.radio("", sig_options, horizontal=True,
                       key="sig_ma20", label_visibility="collapsed")
    sig_idx = sig_options.index(sig_sel) if sig_sel in sig_options else 0

    st.markdown('<div style="margin-top:0">', unsafe_allow_html=True)
    if sig_idx == 0:
        rows, pg, np_, tot = _get_page("A1", "page_a1", mkt_code)
        _render_table(rows, "dist_a_pct", "ma20", t("ma20"), total=tot)
        _page_nav(pg, np_, "page_a1")
    else:
        rows, pg, np_, tot = _get_page("A2", "page_a2", mkt_code)
        _render_table(rows, "dist_a_pct", "ma20", t("ma20"), total=tot)
        _page_nav(pg, np_, "page_a2")
    st.markdown('</div>', unsafe_allow_html=True)


# ── MA200 ────────────────────────────────────────────────────
elif menu == "MA200":
    st.markdown(_bc("MA200"), unsafe_allow_html=True)

    sig_options = [f"▲ {t('c1')}", f"▼ {t('c2')}"]
    sig_sel = st.radio("", sig_options, horizontal=True,
                       key="sig_ma200", label_visibility="collapsed")
    sig_idx = sig_options.index(sig_sel) if sig_sel in sig_options else 0

    if sig_idx == 0:
        rows, pg, np_, tot = _get_page("C1", "page_c1", mkt_code)
        _render_table(rows, "dist_200_pct", "ma200", t("ma200"), total=tot)
        _page_nav(pg, np_, "page_c1")
    else:
        rows, pg, np_, tot = _get_page("C2", "page_c2", mkt_code)
        _render_table(rows, "dist_200_pct", "ma200", t("ma200"), total=tot)
        _page_nav(pg, np_, "page_c2")


# ── WatchList ────────────────────────────────────────────────
elif menu == "WatchList":
    st.markdown(_bc("WatchList"), unsafe_allow_html=True)

    if not st.session_state.user:
        st.markdown(
            f'<div style="color:#8892A4;font-size:13px;padding:20px 0;opacity:0.7">'
            f'{t("login_req")}</div>',
            unsafe_allow_html=True)
    else:
        wl = st.session_state.watchlist
        yf_syms = tuple(
            (w["ticker"] + ".KS" if w["market"] == "KR" else w["ticker"])
            for w in wl
        )
        raw_prices = fetch_current_prices(yf_syms) if yf_syms else {}
        current_prices = {
            w["ticker"]: raw_prices.get(
                w["ticker"] + ".KS" if w["market"] == "KR" else w["ticker"]
            )
            for w in wl
        }

        if not wl:
            st.markdown(
                f'<div style="color:#8892A4;font-size:13px;padding:20px 0;opacity:0.7">'
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
                cur      = current_prices.get(w["ticker"])
                entry    = w.get("entry_price", 0)
                is_kr    = w["market"] == "KR"
                flag     = "🇰🇷" if is_kr else "🇺🇸"
                cur_str  = (f"{cur:,.0f}" if is_kr else f"${cur:,.2f}") if cur else "—"
                entry_str = (f"{entry:,.0f}" if is_kr else f"${entry:,.2f}") if entry else "—"

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
                        f'<div style="padding:6px 0">'
                        f'{flag} <span class="wl-ticker">{w.get("name", w["ticker"])}</span>'
                        f' <span style="font-family:JetBrains Mono,monospace;font-size:10px;'
                        f'color:#2a3347">{w["ticker"]}</span>'
                        f'<br><span class="wl-sub">'
                        f'{t("entry_price")}: {entry_str} → {t("current")}: {cur_str}'
                        f' · {t("added_at")}: {w.get("added_at","")}'
                        f'</span></div>',
                        unsafe_allow_html=True)
                with c_ret:
                    st.markdown(
                        f'<div class="{ret_cls}" style="padding-top:10px">{ret_str}</div>',
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


# ════════════════════════════════════════════════════════════
# MOBILE BOTTOM NAV (fixed, shown only on mobile via CSS)
# ════════════════════════════════════════════════════════════
_nav_items = [
    ("MA20",      "📈", "MA20"),
    ("MA200",     "📊", "MA200"),
    ("WatchList", "⭐", "Watch"),
    ("my",        "👤", "Login"),
]

def _mob_nav_html(current_menu: str, current_page: str) -> str:
    items_html = ""
    for nav_key, icon, label in _nav_items:
        if nav_key == "my":
            active = "active" if current_page == "my" else ""
            href   = "?page=my"
        else:
            active = "active" if (current_page == "main" and current_menu == nav_key) else ""
            href   = f"?menu={nav_key}"
        items_html += (
            f'<a class="mob-nav-item {active}" href="{href}">'
            f'<span class="mob-nav-icon">{icon}</span>'
            f'<span class="mob-nav-label">{label}</span>'
            f'</a>')
    return f'<div class="mob-bottom-nav">{items_html}</div>'

st.markdown(
    _mob_nav_html(st.session_state.menu, st.session_state.page),
    unsafe_allow_html=True)
