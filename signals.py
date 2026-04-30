"""
signals.py
prices.parquet + universe.json 로드 → 지표 계산 → 시그널 판정 → results.json 저장.

지표:
  MA20  : 종가 20일 단순이동평균
  전환선 : (9일 최고가 + 9일 최저가) / 2
  기준선 : (26일 최고가 + 26일 최저가) / 2
  SSA   : (전환선 + 기준선) / 2  — 26일 앞으로 시프트
  SSB   : (52일 최고가 + 52일 최저가) / 2  — 26일 앞으로 시프트
  구름 상단 = max(SSA, SSB), 구름 하단 = min(SSA, SSB)  (오늘 기준)

시그널:
  A1 돌파 완료 : 어제 MA20 ≤ 어제 구름상단  AND  오늘 MA20 > 오늘 구름상단  AND  오늘 MA20 ≥ 어제 MA20
  A2 돌파 임박 : 오늘 MA20 < 오늘 구름상단  AND  거리(%) ≤ 1%  AND  오늘 MA20 ≥ 어제 MA20
  B1 돌파 완료 : 어제 종가 ≤ 어제 구름상단  AND  오늘 종가 > 오늘 구름상단  AND  최근5일 평균거래량 > 0
  B2 돌파 임박 : 오늘 종가 < 오늘 구름상단  AND  거리(%) ≤ 1%
"""

import os
import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd


def _to_python(obj):
    """numpy/pandas 타입을 재귀적으로 파이썬 기본 타입으로 변환."""
    if isinstance(obj, dict):
        return {k: _to_python(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_python(v) for v in obj]
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PRICES_PATH = os.path.join(DATA_DIR, "prices.parquet")
UNIVERSE_PATH = os.path.join(DATA_DIR, "universe.json")
RESULTS_PATH = os.path.join(DATA_DIR, "results.json")


# ─────────────────────────────────────────────
# 지표 계산
# ─────────────────────────────────────────────

def calc_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    종목 하나의 OHLCV DataFrame을 받아 지표를 추가해 반환.
    최소 78행(52+26) 필요. 부족하면 빈 DataFrame 반환.
    """
    if len(df) < 78:
        return pd.DataFrame()

    df = df.sort_index().copy()

    # MA20, MA200
    df["ma20"]  = df["Close"].rolling(20).mean()
    df["ma200"] = df["Close"].rolling(200).mean()

    # 최근 5일 변동률
    df["chg1d"] = df["Close"].pct_change(1) * 100
    df["chg5d"] = df["Close"].pct_change(5) * 100

    # 일목균형표
    high9  = df["High"].rolling(9).max()
    low9   = df["Low"].rolling(9).min()
    high26 = df["High"].rolling(26).max()
    low26  = df["Low"].rolling(26).min()
    high52 = df["High"].rolling(52).max()
    low52  = df["Low"].rolling(52).min()

    tenkan  = (high9  + low9)  / 2
    kijun   = (high26 + low26) / 2
    ssa_raw = (tenkan + kijun) / 2
    ssb_raw = (high52 + low52) / 2

    df["ssa"] = ssa_raw.shift(26)
    df["ssb"] = ssb_raw.shift(26)

    df["cloud_top"]    = df[["ssa", "ssb"]].max(axis=1)
    df["cloud_bottom"] = df[["ssa", "ssb"]].min(axis=1)

    return df


# ─────────────────────────────────────────────
# 시그널 판정 (종목 1개)
# ─────────────────────────────────────────────

def detect_signals(df: pd.DataFrame) -> dict:
    """
    지표가 계산된 DataFrame의 마지막 2행으로 시그널 판정.
    """
    needed = ["ma20", "cloud_top", "Close", "Volume"]
    df_clean = df.dropna(subset=needed)
    if len(df_clean) < 2:
        return {}

    today     = df_clean.iloc[-1]
    yesterday = df_clean.iloc[-2]

    ma20_t  = today["ma20"]
    ma20_y  = yesterday["ma20"]
    ct_t    = today["cloud_top"]
    ct_y    = yesterday["cloud_top"]
    close_t = today["Close"]
    close_y = yesterday["Close"]

    # 거리(%) — 음수면 이미 돌파
    dist_a = (ct_t - ma20_t)  / ma20_t  * 100
    dist_b = (ct_t - close_t) / close_t * 100

    vol5 = df_clean["Volume"].iloc[-5:].mean()

    a1 = bool(ma20_y <= ct_y and ma20_t > ct_t and ma20_t >= ma20_y)
    a2 = bool(ma20_t < ct_t and 0 < dist_a <= 1.0 and ma20_t >= ma20_y)
    b1 = bool(close_y <= ct_y and close_t > ct_t and vol5 > 0)
    b2 = bool(close_t < ct_t and 0 < dist_b <= 1.0)

    # ── 200MA ±2% 근접 시그널 ──────────────────────
    ma200_t  = today.get("ma200", float("nan"))
    c1 = c2  = False
    dist_200 = None
    if not (ma200_t != ma200_t):   # nan 체크
        dist_200 = (close_t - ma200_t) / ma200_t * 100  # 양수=위, 음수=아래
        c1 = bool(0 <= dist_200 <= 2.0 and vol5 > 0)   # 200MA 위 2% + 거래정지 제외
        c2 = bool(-2.0 <= dist_200 < 0 and vol5 > 0)   # 200MA 아래 2% + 거래정지 제외

    # ── 5일 변동률 ────────────────────────────────
    chg1d = today.get("chg1d", None)
    chg5d = today.get("chg5d", None)

    return {
        "A1": a1, "A2": a2, "B1": b1, "B2": b2,
        "C1": c1, "C2": c2,
        "dist_a":   round(float(dist_a), 2),
        "dist_b":   round(float(dist_b), 2),
        "dist_200": round(float(dist_200), 2) if dist_200 is not None else None,
        "chg1d":    round(float(chg1d), 2) if chg1d == chg1d and chg1d is not None else None,
        "chg5d":    round(float(chg5d), 2) if chg5d == chg5d and chg5d is not None else None,
        "ma20_today":      round(float(ma20_t),  2),
        "ma200_today":     round(float(ma200_t), 2) if ma200_t == ma200_t else None,
        "close_today":     round(float(close_t), 2),
        "cloud_top_today": round(float(ct_t),    2),
    }


# ─────────────────────────────────────────────
# 메인 루프
# ─────────────────────────────────────────────

def run():
    # 데이터 로드
    if not os.path.exists(PRICES_PATH):
        log.error(f"{PRICES_PATH} 없음. fetch_data.py를 먼저 실행하세요.")
        return

    log.info(f"prices.parquet 로드 중...")
    prices = pd.read_parquet(PRICES_PATH)
    prices["Date"] = pd.to_datetime(prices["Date"])

    # universe.json 로드 (종목명·시총 참조용)
    universe_map = {}
    if os.path.exists(UNIVERSE_PATH):
        with open(UNIVERSE_PATH, encoding="utf-8") as f:
            meta = json.load(f)
        for u in meta.get("universe", []):
            universe_map[u["ticker"]] = u

    tickers = prices["ticker"].unique()
    log.info(f"총 {len(tickers)}종목 시그널 계산 시작")

    results = {"A1": [], "A2": [], "B1": [], "B2": [], "C1": [], "C2": []}
    counts  = {"A1": 0, "A2": 0, "B1": 0, "B2": 0, "C1": 0, "C2": 0}

    for i, ticker in enumerate(tickers):
        try:
            df = prices[prices["ticker"] == ticker].set_index("Date").sort_index()
            df = calc_indicators(df)
            if df.empty:
                continue

            sig = detect_signals(df)
            if not sig:
                continue

            info    = universe_map.get(ticker, {})
            market  = info.get("market", df["market"].iloc[-1] if "market" in df.columns else "?")
            name    = info.get("name", ticker)
            cap_krw = info.get("market_cap_krw")
            cap_usd = info.get("market_cap_usd")

            row = {
                "ticker":         ticker,
                "name":           name,
                "market":         market,
                "close":          sig["close_today"],
                "ma20":           sig["ma20_today"],
                "ma200":          sig.get("ma200_today"),
                "cloud_top":      sig["cloud_top_today"],
                "dist_a_pct":     sig["dist_a"],
                "dist_b_pct":     sig["dist_b"],
                "dist_200_pct":   sig.get("dist_200"),
                "chg1d":          sig.get("chg1d"),
                "chg5d":          sig.get("chg5d"),
                "market_cap_krw": cap_krw,
                "market_cap_usd": cap_usd,
            }

            for signal in ("A1", "A2", "B1", "B2", "C1", "C2"):
                if sig.get(signal):
                    results[signal].append(row)
                    counts[signal] += 1

        except Exception as e:
            log.warning(f"{ticker} 처리 실패: {e}")

        if (i + 1) % 200 == 0:
            log.info(f"진행: {i+1}/{len(tickers)}")

    # 각 탭 정렬: 거리(%) 오름차순
    for signal in ("A1", "A2"):
        results[signal].sort(key=lambda x: x["dist_a_pct"])
    for signal in ("B1", "B2"):
        results[signal].sort(key=lambda x: x["dist_b_pct"])
    for signal in ("C1", "C2"):
        results[signal].sort(key=lambda x: abs(x["dist_200_pct"] or 0))

    log.info(f"시그널 결과 — A1:{counts['A1']} A2:{counts['A2']} B1:{counts['B1']} B2:{counts['B2']} C1:{counts['C1']} C2:{counts['C2']}")

    output = {
        "generated_at": datetime.now().isoformat(),
        "signals": results,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(_to_python(output), f, ensure_ascii=False, indent=2)
    log.info(f"저장: {RESULTS_PATH}")


if __name__ == "__main__":
    run()
