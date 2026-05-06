"""
기술적 지표 계산
 - MA(20, 120, 200)
 - Ichimoku Kinko Hyo: Tenkan(9), Kijun(26), SpanA, SpanB(52), Chikou
"""
import pandas as pd
import numpy as np


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    입력: DataFrame [date, open, high, low, close, volume]
    출력: 원본에 지표 컬럼 추가 후 반환

    추가 컬럼:
      ma20, ma120, ma200
      tenkan, kijun, span_a, span_b, chikou
      cloud_top  (= max(span_a, span_b))
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    close = df["close"]
    high  = df["high"]
    low   = df["low"]

    # ── 이동평균 ─────────────────────────────────────────────────────────
    df["ma20"]  = close.rolling(20,  min_periods=20).mean()
    df["ma120"] = close.rolling(120, min_periods=120).mean()
    df["ma200"] = close.rolling(200, min_periods=200).mean()

    # ── Ichimoku ─────────────────────────────────────────────────────────
    # 전환선 Tenkan-sen: (9기간 고가 + 저가) / 2
    df["tenkan"] = (high.rolling(9,  min_periods=9).max()
                  + low.rolling(9,  min_periods=9).min()) / 2

    # 기준선 Kijun-sen: (26기간 고가 + 저가) / 2
    df["kijun"]  = (high.rolling(26, min_periods=26).max()
                  + low.rolling(26, min_periods=26).min()) / 2

    # 선행스팬A (Span A): (전환선 + 기준선) / 2  → 26봉 앞 시프트
    span_a_raw   = (df["tenkan"] + df["kijun"]) / 2
    df["span_a"] = span_a_raw.shift(26)

    # 선행스팬B (Span B): 52기간 중간가 → 26봉 앞 시프트
    span_b_raw   = (high.rolling(52, min_periods=52).max()
                  + low.rolling(52, min_periods=52).min()) / 2
    df["span_b"] = span_b_raw.shift(26)

    # 후행스팬 Chikou: 현재 종가를 26봉 뒤로
    df["chikou"] = close.shift(-26)

    # 구름 상단 (cloud top): max(span_a, span_b)
    df["cloud_top"] = df[["span_a", "span_b"]].max(axis=1)

    return df


def has_enough_data(df: pd.DataFrame, min_rows: int = 260) -> bool:
    """최소 데이터 행 수 체크 (MA200 + 선행스팬 시프트 26봉 여유)"""
    return len(df) >= min_rows and not df["ma200"].isna().all()
