"""
스크리닝 필터
 Filter A-1: MA20이 구름 상단을 당일 새로 돌파 (신규 골든크로스)
 Filter A-2: MA20이 구름 상단 위에 위치 (지속 상태)
 Filter B:   |Close - MA200| / MA200 ≤ 0.03  (MA200 ±3% 근접)
"""
import pandas as pd
import numpy as np
from pathlib import Path
from .indicators import add_indicators, has_enough_data
from .prices import load_kr_price, load_us_price

DATA_DIR = Path(__file__).parent.parent / "data"
RESULT_KR = DATA_DIR / "result_kr.parquet"
RESULT_US = DATA_DIR / "result_us.parquet"


# ---------------------------------------------------------------------------
# 단일 종목 필터
# ---------------------------------------------------------------------------
def check_signals(df: pd.DataFrame) -> dict:
    """
    Returns:
      {
        'a1': bool,     # 신규 MA20 구름 돌파
        'a2': bool,     # MA20 구름 위 지속
        'b':  bool,     # MA200 ±3% 근접
        'close': float,
        'ma20':  float,
        'ma200': float,
        'cloud_top': float,
      }
    """
    empty = {"a1": False, "a2": False, "b": False,
             "close": 0., "ma20": 0., "ma200": 0., "cloud_top": 0.}

    if df is None or df.empty:
        return empty

    df = add_indicators(df)

    if not has_enough_data(df):
        return empty

    # 마지막 두 행 (인덱스 -2, -1)
    last2 = df.dropna(subset=["ma20", "cloud_top"]).tail(2)
    if len(last2) < 2:
        return empty

    prev = last2.iloc[-2]
    curr = last2.iloc[-1]

    close     = float(curr["close"])
    ma20      = float(curr["ma20"])
    ma200_val = curr["ma200"]
    cloud_top = float(curr["cloud_top"])

    # Filter A-1: 전일 MA20 ≤ cloud_top AND 당일 MA20 > cloud_top
    a1 = (float(prev["ma20"]) <= float(prev["cloud_top"])
          and ma20 > cloud_top)

    # Filter A-2: 당일 MA20 > cloud_top
    a2 = ma20 > cloud_top

    # Filter B: |close - MA200| / MA200 ≤ 0.03
    b = False
    ma200 = 0.
    if not pd.isna(ma200_val) and float(ma200_val) > 0:
        ma200 = float(ma200_val)
        b = abs(close - ma200) / ma200 <= 0.03

    return {
        "a1": a1,
        "a2": a2,
        "b":  b,
        "close":     close,
        "ma20":      ma20,
        "ma200":     ma200,
        "cloud_top": cloud_top,
    }


# ---------------------------------------------------------------------------
# 전 유니버스 스크리닝
# ---------------------------------------------------------------------------
def run_screening_kr(universe_df: pd.DataFrame) -> pd.DataFrame:
    """
    universe_df: columns [ticker, name, market, market_cap_eok, ...]
    Returns result DataFrame
    """
    records = []
    for row in universe_df.itertuples():
        df = load_kr_price(row.ticker)
        sig = check_signals(df)
        records.append({
            "ticker":       row.ticker,
            "name":         row.name,
            "market":       row.market,
            "market_cap_eok": getattr(row, "market_cap_eok", 0),
            **sig,
        })

    result = pd.DataFrame(records)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result.to_parquet(RESULT_KR, index=False)
    return result


def run_screening_us(universe_df: pd.DataFrame) -> pd.DataFrame:
    """
    universe_df: columns [ticker, name, exchange, excd, market_cap_m, ...]
    Returns result DataFrame
    """
    records = []
    for row in universe_df.itertuples():
        df = load_us_price(row.ticker)
        sig = check_signals(df)
        records.append({
            "ticker":      row.ticker,
            "name":        row.name,
            "exchange":    row.exchange,
            "market_cap_m": getattr(row, "market_cap_m", 0),
            **sig,
        })

    result = pd.DataFrame(records)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result.to_parquet(RESULT_US, index=False)
    return result


# ---------------------------------------------------------------------------
# 결과 로드
# ---------------------------------------------------------------------------
def load_results(market: str = "KR") -> pd.DataFrame:
    """
    market: 'KR' | 'US'
    Returns screening result DataFrame (빈 DataFrame if not yet generated)
    """
    path = RESULT_KR if market == "KR" else RESULT_US
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)
