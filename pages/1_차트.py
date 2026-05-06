"""
STOCKal — 종목 차트 페이지
캔들스틱 + MA(20/120/200) + 일목균형표 5선 + 구름 영역
"""
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(
    page_title="STOCKal — 차트",
    page_icon="▣",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,600;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, [class*="css"] { font-family:'DM Sans',sans-serif !important; }
.stApp { background:#0A0E1A !important; }
header[data-testid="stHeader"] { background:rgba(10,14,26,0.96)!important; border-bottom:1px solid #1E2740; }
.block-container { padding-top:1.5rem!important; padding-bottom:3rem!important; max-width:1280px; }
hr.divider { border:none; border-top:1px solid #1E2740; margin:14px 0; }
.pill { display:inline-block; padding:5px 14px; border-radius:100px; font-size:0.78rem; font-weight:600;
        text-decoration:none!important; border:1.5px solid transparent; line-height:1.5; }
.pill-active   { background:#C6F135; color:#0A0E1A; border-color:#C6F135; }
.pill-inactive { background:transparent; color:#8892A4; border-color:#1E2740; }
.pill-inactive:hover { border-color:#C6F135; color:#C6F135; }
.badge { display:inline-block; padding:2px 8px; border-radius:100px; font-size:0.7rem;
         font-family:'JetBrains Mono',monospace; font-weight:600; }
.badge-a1 { background:#1A2E1A; color:#4ADE80; border:1px solid #2D5A2D; }
.badge-a2 { background:#162445; color:#60A5FA; border:1px solid #1E3A6E; }
.badge-b  { background:#2D1F3D; color:#C084FC; border:1px solid #4A2E6E; }
#MainMenu, footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

# ── 파라미터 ──────────────────────────────────────────────────────────────
params  = st.query_params
ticker  = params.get("ticker",  "")
market  = params.get("market",  "KR")
excd    = params.get("excd",    "NAS")
kr_color = params.get("krcolor", "1")   # 1=한국식(양봉빨강) 0=미국식(양봉녹색)
show_chikou = params.get("chikou", "1") # 1=표시

# ── 헤더 ──────────────────────────────────────────────────────────────────
col_back, col_title = st.columns([1, 7])
with col_back:
    back_url = f"/?market={market}"
    st.markdown(
        f'<a href="{back_url}" style="display:inline-flex;align-items:center;gap:6px;'
        f'color:#8892A4;font-size:0.82rem;text-decoration:none;padding-top:6px">'
        f'← 목록으로</a>',
        unsafe_allow_html=True,
    )
with col_title:
    st.markdown(
        '<h1 style="font-size:1.85rem;font-weight:700;letter-spacing:-0.04em;'
        'color:#F0F2F7;margin:0;line-height:1.2;padding-top:2px">'
        'STOCK<em style="color:#C6F135;font-style:normal">al</em></h1>',
        unsafe_allow_html=True,
    )

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ── 티커 없을 때 ──────────────────────────────────────────────────────────
if not ticker:
    st.markdown(
        '<div style="background:#111827;border:1px solid #1E2740;border-radius:12px;'
        'padding:52px 24px;text-align:center">'
        '<p style="color:#4B5563;font-size:0.95rem">종목을 선택해 주세요.</p>'
        '<a href="/" style="color:#C6F135;font-size:0.85rem">← 스크리닝 목록으로</a>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ── 데이터 로드 ───────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_ohlcv(tkr: str, mkt: str) -> pd.DataFrame:
    try:
        if mkt == "KR":
            from core.prices import load_kr_price
            return load_kr_price(tkr)
        else:
            from core.prices import load_us_price
            return load_us_price(tkr)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_signals(tkr: str, mkt: str) -> dict:
    try:
        from core.screener import check_signals
        df = load_ohlcv(tkr, mkt)
        return check_signals(df)
    except Exception:
        return {}

raw = load_ohlcv(ticker, market)
if raw.empty:
    st.error(f"'{ticker}' 데이터를 불러올 수 없습니다.")
    st.stop()

from core.indicators import add_indicators
df = add_indicators(raw)
sig = load_signals(ticker, market)

# ── 종목 정보 헤더 ────────────────────────────────────────────────────────
close_price = df["close"].iloc[-1] if not df.empty else 0
prev_close  = df["close"].iloc[-2] if len(df) >= 2 else close_price
change      = close_price - prev_close
change_pct  = change / prev_close * 100 if prev_close > 0 else 0
color_chg   = "#4ADE80" if change >= 0 else "#F87171"
sign        = "+" if change >= 0 else ""

badges = ""
if sig.get("a1"): badges += '<span class="badge badge-a1">A1 신규돌파</span> '
if sig.get("a2"): badges += '<span class="badge badge-a2">A2 돌파유지</span> '
if sig.get("b"):  badges += '<span class="badge badge-b">B MA200근접</span> '

mkt_label = "KOSPI/KOSDAQ" if market == "KR" else excd
price_fmt = f"{close_price:,.0f}" if market == "KR" else f"{close_price:.2f}"

st.markdown(
    f'<div style="display:flex;align-items:flex-start;gap:24px;flex-wrap:wrap;margin-bottom:16px">'
    f'<div>'
    f'<p style="color:#8892A4;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;margin:0">'
    f'{mkt_label}</p>'
    f'<h2 style="color:#F0F2F7;font-size:1.6rem;font-weight:700;margin:2px 0;line-height:1.1">'
    f'{ticker}</h2>'
    f'</div>'
    f'<div style="padding-top:18px">'
    f'<span style="font-size:1.6rem;font-weight:700;color:#F0F2F7;font-family:JetBrains Mono,monospace">'
    f'{price_fmt}</span>'
    f'<span style="font-size:0.9rem;color:{color_chg};margin-left:10px;font-family:JetBrains Mono,monospace">'
    f'{sign}{change_pct:.2f}%</span>'
    f'</div>'
    f'<div style="padding-top:22px">{badges}</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── 차트 옵션 토글 ────────────────────────────────────────────────────────
opt_col1, opt_col2 = st.columns([4, 5])
with opt_col1:
    kr_cls = "pill pill-active"   if kr_color == "1" else "pill pill-inactive"
    us_cls = "pill pill-active"   if kr_color == "0" else "pill pill-inactive"
    st.markdown(
        f'<span style="color:#4B5563;font-size:0.72rem;margin-right:8px">캔들 색상</span>'
        f'<a href="?ticker={ticker}&market={market}&excd={excd}&krcolor=1&chikou={show_chikou}" '
        f'class="{kr_cls}">🇰🇷 한국식</a> '
        f'<a href="?ticker={ticker}&market={market}&excd={excd}&krcolor=0&chikou={show_chikou}" '
        f'class="{us_cls}">🇺🇸 미국식</a>',
        unsafe_allow_html=True,
    )
with opt_col2:
    ck_cls = "pill pill-active"   if show_chikou == "1" else "pill pill-inactive"
    ck_off = "pill pill-active"   if show_chikou == "0" else "pill pill-inactive"
    st.markdown(
        f'<span style="color:#4B5563;font-size:0.72rem;margin-right:8px">후행스팬</span>'
        f'<a href="?ticker={ticker}&market={market}&excd={excd}&krcolor={kr_color}&chikou=1" '
        f'class="{ck_cls}">표시</a> '
        f'<a href="?ticker={ticker}&market={market}&excd={excd}&krcolor={kr_color}&chikou=0" '
        f'class="{ck_off}">숨김</a>',
        unsafe_allow_html=True,
    )

st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════
# Plotly 차트
# ══════════════════════════════════════════════════════════════════════════
def build_chart(df: pd.DataFrame, use_kr_colors: bool, show_ck: bool) -> go.Figure:
    dates = df["date"]

    # 일목균형표 미래 영역을 위해 빈 날짜 26봉 확장
    last_date = dates.iloc[-1]
    if hasattr(last_date, 'to_pydatetime'):
        freq = pd.tseries.frequencies.to_offset("B")  # 영업일
    else:
        freq = "B"
    future_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=26)
    future_df    = pd.DataFrame({
        "date": future_dates,
        **{c: np.nan for c in ["open","high","low","close","volume",
                                "ma20","ma120","ma200",
                                "tenkan","kijun","span_a","span_b","chikou","cloud_top"]}
    })
    df_ext = pd.concat([df, future_df], ignore_index=True)

    all_dates   = df_ext["date"]
    span_a_ext  = df_ext["span_a"]
    span_b_ext  = df_ext["span_b"]

    # 양봉/음봉 색상
    if use_kr_colors:
        up_color, dn_color = "#F87171", "#60A5FA"   # 한국식: 양봉=빨강, 음봉=파랑
    else:
        up_color, dn_color = "#4ADE80", "#F87171"   # 미국식: 양봉=녹색, 음봉=빨강

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.78, 0.22],
        vertical_spacing=0.02,
    )

    # ── 캔들스틱 ────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=dates,
        open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=up_color, increasing_fillcolor=up_color,
        decreasing_line_color=dn_color, decreasing_fillcolor=dn_color,
        name="캔들",
        showlegend=False,
        line_width=1,
    ), row=1, col=1)

    # ── 구름 (Span A / Span B fill) ─────────────────────────────────────
    # 구름 색: Span A > Span B → 양운(녹색), 아니면 음운(적색)
    fig.add_trace(go.Scatter(
        x=all_dates, y=span_a_ext,
        mode="lines", line=dict(width=0),
        name="선행스팬A", showlegend=True,
        legendgroup="cloud",
        line_color="rgba(74,222,128,0.6)",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=all_dates, y=span_b_ext,
        mode="lines", line=dict(width=0),
        fill="tonexty",
        fillcolor="rgba(74,222,128,0.12)",
        name="선행스팬B", showlegend=True,
        legendgroup="cloud",
        line_color="rgba(248,113,113,0.6)",
    ), row=1, col=1)

    # ── MA Lines ─────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=dates, y=df["ma20"],
        mode="lines", name="MA20",
        line=dict(color="#60A5FA", width=1.5),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=df["ma120"],
        mode="lines", name="MA120",
        line=dict(color="#FBBF24", width=1.5),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=df["ma200"],
        mode="lines", name="MA200",
        line=dict(color="#F87171", width=1.8),
    ), row=1, col=1)

    # ── 전환선 / 기준선 ──────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=dates, y=df["tenkan"],
        mode="lines", name="전환선(9)",
        line=dict(color="#E879F9", width=1.2, dash="dot"),
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=dates, y=df["kijun"],
        mode="lines", name="기준선(26)",
        line=dict(color="#38BDF8", width=1.2, dash="dot"),
    ), row=1, col=1)

    # ── 후행스팬 ─────────────────────────────────────────────────────────
    if show_ck:
        fig.add_trace(go.Scatter(
            x=dates, y=df["chikou"],
            mode="lines", name="후행스팬",
            line=dict(color="#A3E635", width=1.2, dash="dash"),
            opacity=0.7,
        ), row=1, col=1)

    # ── 거래량 ───────────────────────────────────────────────────────────
    vol_colors = [
        up_color if (df["close"].iloc[i] >= df["open"].iloc[i]) else dn_color
        for i in range(len(df))
    ]
    fig.add_trace(go.Bar(
        x=dates, y=df["volume"],
        marker_color=vol_colors,
        name="거래량",
        showlegend=False,
        opacity=0.6,
    ), row=2, col=1)

    # ── 레이아웃 ─────────────────────────────────────────────────────────
    fig.update_layout(
        height=640,
        paper_bgcolor="#0A0E1A",
        plot_bgcolor="#0D1220",
        font=dict(family="DM Sans, sans-serif", color="#8892A4", size=11),
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(
            bgcolor="rgba(13,18,32,0.8)",
            bordercolor="#1E2740",
            borderwidth=1,
            font=dict(size=10, color="#8892A4"),
            orientation="h",
            yanchor="bottom", y=1.01,
            xanchor="left", x=0,
        ),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
    )
    fig.update_xaxes(
        showgrid=True, gridcolor="#1E2740", gridwidth=1,
        showline=False, zeroline=False,
        tickfont=dict(color="#4B5563", size=10),
    )
    fig.update_yaxes(
        showgrid=True, gridcolor="#1E2740", gridwidth=1,
        showline=False, zeroline=False,
        tickfont=dict(color="#4B5563", size=10),
    )
    # 거래량 y축 오른쪽
    fig.update_yaxes(title_text="거래량", row=2, col=1)

    return fig


fig = build_chart(df, kr_color == "1", show_chikou == "1")
st.plotly_chart(fig, use_container_width=True)

# ── 지표 수치 요약 ─────────────────────────────────────────────────────────
last = df.dropna(subset=["ma20"]).iloc[-1] if not df.empty else None
if last is not None:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    info_cols = st.columns(6)
    def _info(col, label, value, color="#F0F2F7"):
        with col:
            st.markdown(
                f'<div style="background:#111827;border:1px solid #1E2740;border-radius:8px;padding:10px 14px">'
                f'<div style="color:#4B5563;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.07em">{label}</div>'
                f'<div style="color:{color};font-size:0.92rem;font-weight:600;font-family:JetBrains Mono,monospace;margin-top:4px">{value}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    price_unit = "" if market == "US" else "원"
    fmt_p = lambda v: f"{v:,.0f}{price_unit}" if market == "KR" else f"{v:.2f}"
    fmt_r = lambda v: f"{v:.2f}%" if pd.notna(v) else "—"

    ma200_gap = ((last["close"] - last["ma200"]) / last["ma200"] * 100
                 if pd.notna(last.get("ma200")) and last["ma200"] > 0 else float("nan"))

    _info(info_cols[0], "현재가",   fmt_p(last["close"]))
    _info(info_cols[1], "MA20",     fmt_p(last["ma20"]))
    _info(info_cols[2], "MA200",    fmt_p(last["ma200"]) if pd.notna(last.get("ma200")) else "—")
    _info(info_cols[3], "구름상단",  fmt_p(last["cloud_top"]) if pd.notna(last.get("cloud_top")) else "—")
    _info(info_cols[4], "MA200 괴리", fmt_r(ma200_gap),
          "#4ADE80" if not pd.isna(ma200_gap) and ma200_gap >= 0 else "#F87171")
    _info(info_cols[5], "데이터수",  f"{len(df):,}봉")
