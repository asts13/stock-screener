"""
STOCKal — 한·미 주식 스크리너
MA20 구름대 돌파 / MA200 근접 신호 탐지
"""
import sys, json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="STOCKal",
    page_icon="▣",
    layout="wide",
    initial_sidebar_state="collapsed",
)

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ══════════════════════════════════════════════════════════════════════════
# 헬퍼 함수
# ══════════════════════════════════════════════════════════════════════════

def _get_last_update() -> str:
    last_file = ROOT / "data" / "last_update.json"
    if last_file.exists():
        try:
            data = json.loads(last_file.read_text())
            ts   = data.get("ts", "")
            if ts:
                dt = datetime.fromisoformat(ts)
                return dt.strftime("%Y.%m.%d %H:%M")
        except Exception:
            pass
    return "—"


@st.cache_data(ttl=300)
def _load_results(mkt: str) -> pd.DataFrame:
    try:
        from core.screener import load_results as _lr
        return _lr(mkt)
    except Exception:
        return pd.DataFrame()


def _apply_filter(df: pd.DataFrame, tab: str, b_mode: str) -> pd.DataFrame:
    if df.empty:
        return df
    if tab == "A1":
        mask = df.get("a1", pd.Series(False, index=df.index)) == True
    elif tab == "A2":
        mask = df.get("a2", pd.Series(False, index=df.index)) == True
    elif tab == "B_ABOVE":
        mask = df.get("b", pd.Series(False, index=df.index)) == True
        ratio = (df["close"] - df["ma200"]) / df["ma200"].replace(0, float("nan"))
        mask &= ratio > 0
    elif tab == "B_BELOW":
        mask = df.get("b", pd.Series(False, index=df.index)) == True
        ratio = (df["close"] - df["ma200"]) / df["ma200"].replace(0, float("nan"))
        mask &= ratio < 0
    else:  # WL = 전체
        mask = pd.Series(True, index=df.index)
    return df[mask].reset_index(drop=True)


def _format_mktcap(val, mkt: str) -> str:
    if not val or pd.isna(val) or float(val) <= 0:
        return "—"
    v = float(val)
    if mkt == "KR":
        if v >= 10000:
            return f"₩{v/10000:.1f}조"
        return f"₩{v:,.0f}억"
    else:
        if v >= 1000:
            return f"${v/1000:.1f}B"
        return f"${v:.0f}M"


def _dist_pct(close, ma) -> float | None:
    try:
        c, m = float(close), float(ma)
        if m > 0 and c > 0:
            return (c - m) / m * 100
    except Exception:
        pass
    return None


def _prepare_table(df: pd.DataFrame, tab: str, mkt: str) -> pd.DataFrame:
    if df.empty:
        return df
    out_rows = []
    for _, r in df.iterrows():
        close = r.get("close", 0) or 0
        ma_val = r.get("ma20" if tab in ("A1","A2") else "ma200", 0) or 0
        dist = _dist_pct(close, ma_val)

        row = {
            "TICKER":  r.get("ticker", ""),
            "NAME":    r.get("name", ""),
            "PRICE":   round(float(close), 2) if close else None,
            "MA":      round(float(ma_val), 2) if ma_val else None,
            "DIST%":   round(dist, 2) if dist is not None else None,
            "MKTCAP":  _format_mktcap(
                r.get("market_cap_eok" if mkt == "KR" else "market_cap_m"), mkt
            ),
        }
        out_rows.append(row)
    return pd.DataFrame(out_rows)


# ══════════════════════════════════════════════════════════════════════════
# URL 쿼리 파라미터
# ══════════════════════════════════════════════════════════════════════════
params  = st.query_params
market  = params.get("market",  "KR")     # KR | US
menu    = params.get("menu",    "MA20")   # MA20 | MA200 | WL
sigtab  = params.get("sigtab",  "A1")     # A1 | A2  (MA20 메뉴)
                                           # B_ABOVE | B_BELOW  (MA200 메뉴)

# ══════════════════════════════════════════════════════════════════════════
# CSS — 디자인 토큰 정확히 매핑
# ══════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  --bg:     #0A0E1A;
  --bg2:    #111827;
  --bg3:    #1A2236;
  --border: rgba(255,255,255,0.07);
  --text:   #F0F2F7;
  --muted:  #8892A4;
  --accent: #C6F135;
  --accent2:#00D4AA;
  --red:    #FF4D4D;
  --green:  #22C55E;
  --mono:   'JetBrains Mono', monospace;
}

html, body, [class*="css"] { font-family:'DM Sans',sans-serif!important; }
.stApp { background:var(--bg)!important; }
header[data-testid="stHeader"] { display:none!important; }
section[data-testid="stSidebar"] { display:none!important; }
.block-container {
  padding:0!important;
  max-width:100%!important;
}
/* 스크롤바 */
::-webkit-scrollbar { width:4px; height:4px; }
::-webkit-scrollbar-track { background:var(--bg); }
::-webkit-scrollbar-thumb { background:var(--bg3); border-radius:2px; }

/* ─ NAV ─ */
.nav {
  background:var(--bg);
  border-bottom:1px solid var(--border);
  padding:0 24px;
  height:56px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  position:sticky;
  top:0;
  z-index:100;
}
.nav-logo { font-size:20px; font-weight:700; letter-spacing:-0.03em; color:var(--text); text-decoration:none; }
.nav-logo .al { color:var(--accent); font-style:normal; }
.nav-right { display:flex; align-items:center; gap:12px; }
.mkt-toggle { display:flex; background:var(--bg3); border-radius:8px; padding:3px; gap:2px; }
.mkt-btn {
  padding:4px 12px; border-radius:6px; font-size:12px; font-weight:600;
  letter-spacing:0.04em; color:var(--muted); text-decoration:none;
  transition:all 0.15s;
}
.mkt-btn.active { background:var(--accent); color:#000; }
.nav-update { font-family:var(--mono); font-size:11px; color:var(--muted); }

/* ─ TICKER BAR ─ */
.horiz-ticker-bar {
  background:var(--bg2);
  border-bottom:1px solid var(--border);
  padding:0 24px;
  height:48px;
  display:flex;
  align-items:center;
  gap:0;
  overflow-x:auto;
  scrollbar-width:none;
}
.horiz-ticker-bar::-webkit-scrollbar { display:none; }
.htc {
  display:flex; flex-direction:column; gap:1px;
  padding:0 20px; border-right:1px solid var(--border);
  flex-shrink:0; min-width:90px;
}
.htc:first-child { padding-left:0; }
.htc:last-child  { border-right:none; }
.htc-name  { font-size:10px; font-weight:600; color:var(--muted); letter-spacing:0.06em; }
.htc-price { font-family:var(--mono); font-size:13px; font-weight:500; color:var(--text); }
.htc-chg   { font-family:var(--mono); font-size:11px; font-weight:600; }
.up { color:var(--green); }
.dn { color:var(--red);   }

/* ─ MAIN LAYOUT ─ */
.main-layout { display:flex; height:calc(100vh - 104px); overflow:hidden; }

/* ─ SIDEBAR ─ */
.sidebar {
  width:200px; flex-shrink:0;
  border-right:1px solid var(--border);
  background:var(--bg);
  padding:16px 12px;
  display:flex; flex-direction:column; gap:2px;
  overflow-y:auto;
}
.sb-section { font-size:10px; font-weight:600; letter-spacing:0.08em; color:var(--muted); padding:10px 8px 4px; text-transform:uppercase; }
.sb-item {
  display:flex; align-items:center; gap:10px;
  padding:8px 10px; border-radius:8px;
  font-size:13px; font-weight:500; color:var(--muted);
  text-decoration:none; transition:all 0.15s;
}
.sb-item:hover { color:var(--text); background:var(--bg3); }
.sb-item.active { color:var(--text); background:var(--bg3); }
.sb-dot { width:6px; height:6px; border-radius:50%; background:var(--bg3); flex-shrink:0; }
.sb-item.active .sb-dot { background:var(--accent); }

/* ─ CONTENT ─ */
.content { flex:1; overflow-y:auto; padding:24px; }

/* ─ SECTION HEADER ─ */
.sec-hd { display:flex; align-items:center; justify-content:space-between; margin-bottom:4px; }
.sec-title {
  font-size:12px; font-weight:600; color:var(--muted);
  letter-spacing:0.06em; text-transform:uppercase;
  display:flex; align-items:center; gap:8px;
}
.sec-dot { width:6px; height:6px; border-radius:50%; background:var(--accent); }
.breadcrumb { font-size:12px; color:var(--muted); }
.breadcrumb span { color:var(--accent); font-weight:700; }

/* ─ SIGNAL TABS ─ */
.sig-tabs { display:flex; gap:0; border-bottom:1px solid var(--border); margin-bottom:0; }
.sig-tab {
  padding:8px 16px; font-size:11px; font-weight:700; letter-spacing:0.05em;
  color:var(--muted); text-decoration:none;
  border-bottom:2px solid transparent; margin-bottom:-1px;
  transition:all 0.15s; text-transform:uppercase;
}
.sig-tab:hover { color:var(--text); }
.sig-tab.active { color:var(--accent); border-bottom-color:var(--accent); }

/* ─ PANEL ─ */
.panel {
  background:var(--bg2);
  border:1px solid var(--border);
  border-radius:12px;
  overflow:hidden;
  margin-top:16px;
}

/* ─ TABLE ─ */
.stk-table { width:100%; border-collapse:collapse; }
.stk-head th {
  padding:10px 8px; font-size:10px; font-weight:600; letter-spacing:0.08em;
  color:var(--muted); text-align:left; text-transform:uppercase;
  border-bottom:1px solid var(--border); white-space:nowrap;
}
.stk-row { border-bottom:1px solid var(--border); transition:background 0.1s; }
.stk-row:last-child { border-bottom:none; }
.stk-row:hover { background:rgba(255,255,255,0.02); }
.stk-row td { padding:10px 8px; font-size:13px; vertical-align:middle; }
.ticker-cell .tkr { font-family:var(--mono); font-weight:600; color:var(--text); font-size:13px; }
.ticker-cell .nm  { color:var(--muted); font-size:11px; margin-top:1px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:130px; }
.num { font-family:var(--mono); font-weight:500; color:var(--text); text-align:right; }
.dist-pos { font-family:var(--mono); font-size:12px; color:var(--green); text-align:right; font-weight:600; }
.dist-neg { font-family:var(--mono); font-size:12px; color:var(--red);   text-align:right; font-weight:600; }
.dist-neu { font-family:var(--mono); font-size:12px; color:var(--muted); text-align:right; }
.mktcap-cell { font-family:var(--mono); font-size:11px; color:var(--muted); text-align:right; }
.toss-btn {
  display:inline-flex; align-items:center; justify-content:center;
  width:28px; height:28px; border-radius:6px;
  background:var(--bg3); color:var(--muted); font-size:14px;
  text-decoration:none; transition:all 0.15s; border:1px solid var(--border);
}
.toss-btn:hover { background:rgba(198,241,53,0.12); color:var(--accent); border-color:rgba(198,241,53,0.3); }

/* ─ EMPTY STATE ─ */
.empty-state {
  text-align:center; padding:64px 24px;
  color:var(--muted); font-size:13px;
}
.empty-state code {
  display:inline-block; margin-top:8px;
  background:var(--bg3); color:var(--accent);
  padding:3px 10px; border-radius:5px;
  font-family:var(--mono); font-size:12px;
}

/* ─ METRIC CHIPS ─ */
.chip-row { display:flex; gap:10px; margin-bottom:16px; flex-wrap:wrap; }
.chip {
  background:var(--bg2); border:1px solid var(--border); border-radius:8px;
  padding:10px 16px; min-width:110px;
}
.chip-num   { font-family:var(--mono); font-size:1.3rem; font-weight:600; color:var(--accent); line-height:1.1; }
.chip-label { font-size:0.68rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.07em; margin-top:3px; }

/* ─ RESPONSIVE ─ */
@media (max-width:768px) {
  .sidebar { display:none; }
  .main-layout { height:auto; }
  .content { padding:16px; }
  .htc { min-width:70px; padding:0 12px; }
}

/* Streamlit 제거 */
#MainMenu, footer, .stDeployButton { display:none!important; }
div[data-testid="stToolbar"] { display:none!important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# 데이터 로드
# ══════════════════════════════════════════════════════════════════════════
df_full  = _load_results(market)
has_data = not df_full.empty

a1_cnt  = int(df_full["a1"].sum()) if has_data and "a1" in df_full.columns else 0
a2_cnt  = int(df_full["a2"].sum()) if has_data and "a2" in df_full.columns else 0
b_cnt   = int(df_full["b"].sum())  if has_data and "b"  in df_full.columns else 0

# ══════════════════════════════════════════════════════════════════════════
# NAV
# ══════════════════════════════════════════════════════════════════════════
kr_act = "active" if market == "KR" else ""
us_act = "active" if market == "US" else ""

st.markdown(f"""
<nav class="nav">
  <a href="?market={market}&menu={menu}&sigtab={sigtab}" class="nav-logo">STOCK<em class="al">al</em></a>
  <div class="nav-right">
    <div class="mkt-toggle">
      <a href="?market=KR&menu={menu}&sigtab={sigtab}" class="mkt-btn {kr_act}">KR</a>
      <a href="?market=US&menu={menu}&sigtab={sigtab}" class="mkt-btn {us_act}">US</a>
    </div>
    <span class="nav-update">갱신 {_get_last_update()}</span>
  </div>
</nav>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# TICKER BAR (시장 지수)
# ══════════════════════════════════════════════════════════════════════════
# 고정 더미 데이터 (실제 연동 시 KIS API 로 교체)
TICKERS = [
    ("KOSPI",    "2,635.44", "+1.23%",  True),
    ("KOSDAQ",   "733.21",   "+0.88%",  True),
    ("NASDAQ",   "17,928",   "-0.31%",  False),
    ("S&P 500",  "5,187",    "+0.12%",  True),
    ("DOW",      "39,411",   "+0.07%",  True),
    ("WTI",      "78.42",    "-0.54%",  False),
    ("GOLD",     "2,347",    "+0.22%",  True),
    ("USD/KRW",  "1,362",    "+0.09%",  True),
]
ticker_cells = ""
for name, price, chg, is_up in TICKERS:
    chg_cls = "up" if is_up else "dn"
    ticker_cells += (
        f'<div class="htc">'
        f'<span class="htc-name">{name}</span>'
        f'<span class="htc-price">{price}</span>'
        f'<span class="htc-chg {chg_cls}">{chg}</span>'
        f'</div>'
    )

st.markdown(f'<div class="horiz-ticker-bar">{ticker_cells}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# MAIN LAYOUT (사이드바 + 콘텐츠)
# ══════════════════════════════════════════════════════════════════════════

# 사이드바 메뉴 아이템
def _sb_item(label, code, icon):
    act = "active" if menu == code else ""
    return (
        f'<a href="?market={market}&menu={code}&sigtab={sigtab}" '
        f'class="sb-item {act}">'
        f'<span class="sb-dot"></span>{icon} {label}</a>'
    )

sidebar_html = f"""
<div class="sidebar">
  <div class="sb-section">STRATEGY</div>
  {_sb_item("MA20", "MA20", "▲")}
  {_sb_item("MA200", "MA200", "◎")}
  {_sb_item("WatchList", "WL", "★")}
</div>
"""

# ── 콘텐츠 영역 ──────────────────────────────────────────────────────────

def _sig_tab_link(label, code):
    act = "active" if sigtab == code else ""
    return (
        f'<a href="?market={market}&menu={menu}&sigtab={code}" '
        f'class="sig-tab {act}">{label}</a>'
    )


def _render_table(df_flt: pd.DataFrame) -> str:
    if df_flt.empty:
        return (
            '<div class="empty-state">'
            '<p>조건을 만족하는 종목이 없습니다</p>'
            '</div>'
        )
    tbl = _prepare_table(df_flt, sigtab, market)
    ma_label = "MA20" if sigtab in ("A1","A2") else "MA200"
    rows_html = ""
    for _, r in tbl.iterrows():
        dist = r.get("DIST%")
        if dist is not None:
            dist_cls = "dist-pos" if dist > 0 else ("dist-neg" if dist < 0 else "dist-neu")
            dist_str = f"{'+' if dist > 0 else ''}{dist:.2f}%"
        else:
            dist_cls = "dist-neu"
            dist_str = "—"

        price = r.get("PRICE")
        price_str = f"{price:,.0f}" if market == "KR" and price else (f"{price:.2f}" if price else "—")

        ma_val = r.get("MA")
        ma_str = f"{ma_val:,.0f}" if market == "KR" and ma_val else (f"{ma_val:.2f}" if ma_val else "—")

        tkr  = r.get("TICKER","")
        name = r.get("NAME","")[:18]
        mktcap = r.get("MKTCAP","—")

        # 차트 링크
        chart_url = f"/차트?ticker={tkr}&market={market}"

        rows_html += f"""
        <tr class="stk-row">
          <td class="ticker-cell">
            <a href="{chart_url}" style="text-decoration:none">
              <div class="tkr">{tkr}</div>
              <div class="nm">{name}</div>
            </a>
          </td>
          <td class="num">{price_str}</td>
          <td class="num">{ma_str}</td>
          <td class="{dist_cls}">{dist_str}</td>
          <td class="mktcap-cell">{mktcap}</td>
          <td style="text-align:center">
            <a href="{chart_url}" class="toss-btn" title="차트 보기">→</a>
          </td>
        </tr>"""

    return f"""
    <table class="stk-table">
      <thead class="stk-head">
        <tr>
          <th>MKT · TICKER</th>
          <th style="text-align:right">PRICE</th>
          <th style="text-align:right">{ma_label}</th>
          <th style="text-align:right">DIST%</th>
          <th style="text-align:right">MKTCAP</th>
          <th style="text-align:center">CHART</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>"""


# ── 메뉴별 콘텐츠 구성 ────────────────────────────────────────────────────
if menu == "MA20":
    breadcrumb = '▲ MA20 <span style="color:var(--muted)">→</span> <span>ICHIMOKU</span>'
    sig_tabs_html = (
        _sig_tab_link("▲ CROSSOVER (신규 돌파)", "A1") +
        _sig_tab_link("▲ ABOVE CLOUD (돌파 유지)", "A2")
    )
    df_flt = _apply_filter(df_full, sigtab, "")
    cnt    = len(df_flt)
    table_html = _render_table(df_flt)
    chip_label = "신규 돌파" if sigtab == "A1" else "돌파 유지"
    chip_cnt   = a1_cnt if sigtab == "A1" else a2_cnt

elif menu == "MA200":
    breadcrumb = '◎ MA200'
    if sigtab not in ("B_ABOVE","B_BELOW"):
        sigtab = "B_ABOVE"
    sig_tabs_html = (
        _sig_tab_link("▲ ABOVE MA200 3%", "B_ABOVE") +
        _sig_tab_link("▼ BELOW MA200 3%", "B_BELOW")
    )
    df_flt = _apply_filter(df_full, sigtab, "")
    cnt    = len(df_flt)
    table_html = _render_table(df_flt)
    chip_label = "MA200 위" if sigtab == "B_ABOVE" else "MA200 아래"
    chip_cnt   = b_cnt

else:  # WL
    breadcrumb  = '★ WatchList'
    sig_tabs_html = ""
    df_flt = pd.DataFrame()
    cnt = 0
    table_html = (
        '<div class="empty-state">'
        '<p>WatchList 기능은 준비 중입니다.</p>'
        '</div>'
    )
    chip_label = ""
    chip_cnt   = 0


content_html = f"""
<div class="content">
  <div class="sec-hd">
    <div class="sec-title">
      <span class="sec-dot"></span>
      <span class="breadcrumb">{breadcrumb}</span>
    </div>
    <span style="font-size:11px;color:var(--muted);font-family:var(--mono)">{cnt:,}개 종목</span>
  </div>
  <div class="chip-row">
    <div class="chip">
      <div class="chip-num">{a1_cnt:,}</div>
      <div class="chip-label">신규 돌파 A1</div>
    </div>
    <div class="chip">
      <div class="chip-num">{a2_cnt:,}</div>
      <div class="chip-label">돌파 유지 A2</div>
    </div>
    <div class="chip">
      <div class="chip-num">{b_cnt:,}</div>
      <div class="chip-label">MA200 근접 B</div>
    </div>
  </div>
  {'<div class="sig-tabs">' + sig_tabs_html + '</div>' if sig_tabs_html else ''}
  <div class="panel">
    {table_html}
  </div>
  <p style="margin-top:20px;font-size:0.68rem;color:#374151;text-align:center">
    본 스크리너는 투자 참고용이며 투자를 권고하지 않습니다.
    데이터 오류·지연이 있을 수 있으며 모든 투자 결정의 책임은 본인에게 있습니다.
  </p>
</div>
"""

# ── 전체 레이아웃 조합 ────────────────────────────────────────────────────
if not has_data:
    st.markdown(f"""
    <div class="main-layout">
      {sidebar_html}
      <div class="content">
        <div class="empty-state">
          <p style="font-size:15px;color:var(--muted);margin-bottom:8px">스크리닝 데이터가 없습니다</p>
          <p style="font-size:12px;color:#374151">로컬에서 실행:</p>
          <code>python jobs/scheduled_refresh.py</code>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div class="main-layout">
      {sidebar_html}
      {content_html}
    </div>
    """, unsafe_allow_html=True)
