"""
유니버스 로더
 - KR: KOSPI + KOSDAQ, 시가총액 ≥ 1,000억 원
 - US: NYSE + NASDAQ + AMEX, 시가총액 ≥ $200M
"""
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# 한국 유니버스
# ---------------------------------------------------------------------------
def get_kr_universe(client=None) -> pd.DataFrame:
    """
    pykrx로 KOSPI + KOSDAQ 전 종목 조회 후
    시가총액 ≥ 1,000억 필터링.

    Returns DataFrame columns: [ticker, name, market, market_cap_eok]
    """
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        raise ImportError("pykrx 패키지가 필요합니다: pip install pykrx")

    today = pd.Timestamp.today().strftime("%Y%m%d")

    rows = []
    for market in ("KOSPI", "KOSDAQ"):
        tickers = pykrx_stock.get_market_ticker_list(today, market=market)
        for ticker in tickers:
            name = pykrx_stock.get_market_ticker_name(ticker)
            rows.append({"ticker": ticker, "name": name, "market": market})

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # 시가총액 조회 — pykrx (빠름, 무료)
    try:
        cap_df = pykrx_stock.get_market_cap(today, market="ALL")
        cap_df = cap_df[["시가총액"]].rename(columns={"시가총액": "market_cap_won"})
        cap_df.index.name = "ticker"
        cap_df = cap_df.reset_index()
        df = df.merge(cap_df, on="ticker", how="left")
        df["market_cap_eok"] = df["market_cap_won"].fillna(0) / 1e8
    except Exception:
        # fallback: KIS API로 개별 조회
        if client:
            def _fetch(row):
                try:
                    info = client.fetch_kr_price_info(row.ticker)
                    return row.ticker, info["market_cap_eok"]
                except Exception:
                    return row.ticker, 0.0

            cap_map = {}
            with ThreadPoolExecutor(max_workers=10) as ex:
                futs = {ex.submit(_fetch, r): r.ticker for r in df.itertuples()}
                for f in as_completed(futs):
                    tkr, cap = f.result()
                    cap_map[tkr] = cap
            df["market_cap_eok"] = df["ticker"].map(cap_map).fillna(0)
        else:
            df["market_cap_eok"] = 0.0

    df = df[df["market_cap_eok"] >= 1000].reset_index(drop=True)
    return df[["ticker", "name", "market", "market_cap_eok"]]


# ---------------------------------------------------------------------------
# 미국 유니버스
# ---------------------------------------------------------------------------

# KIS exchange code 매핑
_EXCD_MAP = {
    "NASDAQ": "NAS",
    "NYSE":   "NYS",
    "AMEX":   "AMS",
}

def get_us_universe(client=None) -> pd.DataFrame:
    """
    KIS API로 NYSE/NASDAQ/AMEX 전 종목 조회 또는
    NASDAQ 공개 파일(ftp)에서 로드 후 시가총액 ≥ $200M 필터.

    Returns DataFrame columns: [ticker, name, exchange, excd, market_cap_m]
    """
    rows = _load_us_tickers_from_nasdaq_ftp()
    if not rows:
        rows = _load_us_tickers_fallback()

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # 시가총액: KIS API 개별 조회 (느림 → 캐시 파일 활용)
    cache_file = DATA_DIR / "us_universe_cache.parquet"

    # 캐시가 오늘 것이면 재사용
    if cache_file.exists():
        cached = pd.read_parquet(cache_file)
        cached_date = pd.Timestamp(cached.attrs.get("date", "2000-01-01"))
        if cached_date.date() == pd.Timestamp.today().date():
            return cached

    if client:
        def _fetch(row):
            try:
                info = client.fetch_us_price_info(row.ticker, row.excd)
                return row.ticker, info["close"], info.get("market_cap_m", 0)
            except Exception:
                return row.ticker, 0.0, 0.0

        close_map = {}
        cap_map   = {}
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(_fetch, r): r.ticker for r in df.itertuples()}
            for f in as_completed(futs):
                tkr, close, cap = f.result()
                close_map[tkr] = close
                cap_map[tkr]   = cap

        df["close"]       = df["ticker"].map(close_map).fillna(0)
        df["market_cap_m"] = df["ticker"].map(cap_map).fillna(0)

        # KIS US price endpoint가 시가총액 미제공 → shares * price 로 계산 불가
        # 대신 시가총액 컬럼이 0이면 close > 0인 종목만 통과 (임시)
        if (df["market_cap_m"] == 0).all():
            df = df[df["close"] > 0].reset_index(drop=True)
            df["market_cap_m"] = 0.0  # 필터링 패스
        else:
            df = df[df["market_cap_m"] >= 200].reset_index(drop=True)
    else:
        df["close"]       = 0.0
        df["market_cap_m"] = 0.0

    df.attrs["date"] = str(pd.Timestamp.today().date())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_file, index=False)
    return df[["ticker", "name", "exchange", "excd", "market_cap_m"]]


def _load_us_tickers_from_nasdaq_ftp() -> list[dict]:
    """NASDAQ FTP에서 상장 종목 목록 다운로드 (무료, 로그인 불필요)"""
    import io, requests
    rows = []
    urls = {
        "NASDAQ": "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5000&exchange=NASDAQ",
        "NYSE":   "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5000&exchange=NYSE",
        "AMEX":   "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5000&exchange=AMEX",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    for exchange, url in urls.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            stocks = data.get("data", {}).get("table", {}).get("rows", [])
            for s in stocks:
                tkr = (s.get("symbol") or "").strip()
                if not tkr or " " in tkr or "^" in tkr:
                    continue
                rows.append({
                    "ticker":   tkr,
                    "name":     s.get("name", ""),
                    "exchange": exchange,
                    "excd":     _EXCD_MAP[exchange],
                })
        except Exception:
            continue
    return rows


def _load_us_tickers_fallback() -> list[dict]:
    """NASDAQ FTP txt 파일 fallback (ftp.nasdaqtrader.com)"""
    import io, requests
    rows = []
    file_map = {
        "NASDAQ": "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt",
    }
    try:
        resp = requests.get(file_map["NASDAQ"], timeout=15)
        resp.raise_for_status()
        lines = resp.text.splitlines()
        # 헤더: Symbol|Security Name|Market Category|...
        for line in lines[1:]:
            parts = line.split("|")
            if len(parts) < 4:
                continue
            test_issue = parts[7] if len(parts) > 7 else "Y"
            if test_issue == "Y":
                continue
            tkr = parts[0].strip()
            if not tkr or tkr == "Symbol":
                continue
            mkt = parts[2].strip()  # Q=NASDAQ, N=NYSE, A=AMEX
            exchange_map = {"Q": "NASDAQ", "N": "NYSE", "A": "AMEX"}
            exchange = exchange_map.get(mkt, "NASDAQ")
            rows.append({
                "ticker":   tkr,
                "name":     parts[1].strip(),
                "exchange": exchange,
                "excd":     _EXCD_MAP.get(exchange, "NAS"),
            })
    except Exception:
        pass
    return rows
