"""
일봉 일괄 수집 & 캐싱
 - KR/US 종목 리스트를 ThreadPoolExecutor(≤10)로 병렬 수집
 - 결과는 data/kr_prices/ 또는 data/us_prices/ 아래 Parquet로 저장
"""
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DATA_DIR    = Path(__file__).parent.parent / "data"
KR_PRICE_DIR = DATA_DIR / "kr_prices"
US_PRICE_DIR = DATA_DIR / "us_prices"

N_DAYS = 400   # 지표 계산에 필요한 최소 일봉 수

# ---------------------------------------------------------------------------
# 한국
# ---------------------------------------------------------------------------
def fetch_all_kr(client, tickers: list[str], n_days: int = N_DAYS) -> dict[str, pd.DataFrame]:
    """
    tickers: ['005930', '000660', ...]
    Returns {ticker: DataFrame[date,open,high,low,close,volume]}
    """
    KR_PRICE_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}
    today = pd.Timestamp.today().normalize()

    def _fetch_one(ticker: str):
        cache = KR_PRICE_DIR / f"{ticker}.parquet"
        # 오늘 이미 수집한 경우 캐시 반환
        if cache.exists():
            try:
                df = pd.read_parquet(cache)
                df["date"] = pd.to_datetime(df["date"])
                last = df["date"].max()
                if last.date() == today.date() or last.date() == (today - pd.Timedelta(days=1)).date():
                    return ticker, df
            except Exception:
                pass
        df = client.fetch_kr_daily_full(ticker, n_days=n_days)
        if not df.empty:
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache, index=False)
        return ticker, df

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_fetch_one, t): t for t in tickers}
        for f in as_completed(futs):
            tkr, df = f.result()
            if not df.empty:
                result[tkr] = df

    return result


# ---------------------------------------------------------------------------
# 미국
# ---------------------------------------------------------------------------
def fetch_all_us(client, universe_df: pd.DataFrame, n_days: int = N_DAYS) -> dict[str, pd.DataFrame]:
    """
    universe_df: DataFrame with columns [ticker, excd, ...]
    Returns {ticker: DataFrame[date,open,high,low,close,volume]}
    """
    US_PRICE_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, pd.DataFrame] = {}
    today = pd.Timestamp.today().normalize()

    def _fetch_one(ticker: str, excd: str):
        cache = US_PRICE_DIR / f"{ticker}.parquet"
        if cache.exists():
            try:
                df = pd.read_parquet(cache)
                df["date"] = pd.to_datetime(df["date"])
                last = df["date"].max()
                if last.date() == today.date() or last.date() == (today - pd.Timedelta(days=1)).date():
                    return ticker, df
            except Exception:
                pass
        df = client.fetch_us_daily_full(ticker, excd, n_days=n_days)
        if not df.empty:
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache, index=False)
        return ticker, df

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {
            ex.submit(_fetch_one, row.ticker, row.excd): row.ticker
            for row in universe_df.itertuples()
        }
        for f in as_completed(futs):
            tkr, df = f.result()
            if not df.empty:
                result[tkr] = df

    return result


# ---------------------------------------------------------------------------
# 캐시 읽기 유틸
# ---------------------------------------------------------------------------
def load_kr_price(ticker: str) -> pd.DataFrame:
    cache = KR_PRICE_DIR / f"{ticker}.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").reset_index(drop=True)
    return pd.DataFrame()


def load_us_price(ticker: str) -> pd.DataFrame:
    cache = US_PRICE_DIR / f"{ticker}.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").reset_index(drop=True)
    return pd.DataFrame()
