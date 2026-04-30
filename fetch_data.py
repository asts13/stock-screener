"""
fetch_data.py
한국(FinanceDataReader) + 미국(yfinance) 주식 데이터를 수집해
prices.parquet, universe.json 저장.

실행 예:
  python fetch_data.py --market all   # 전체
  python fetch_data.py --market kr    # 한국만
  python fetch_data.py --market us    # 미국만
"""

import os
import json
import time
import logging
import argparse
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf
import FinanceDataReader as fdr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PRICES_PATH = os.path.join(DATA_DIR, "prices.parquet")
UNIVERSE_PATH = os.path.join(DATA_DIR, "universe.json")

KR_MKTCAP_MIN = 500_000_000_000   # 5,000억원 (KRW)
DAYS_HISTORY = 120                 # 안전하게 120일치 (최소 78일 필요)


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────

def start_date_str() -> str:
    return (datetime.now() - timedelta(days=DAYS_HISTORY)).strftime("%Y-%m-%d")

def get_usd_krw() -> float:
    """USD/KRW 환율을 yfinance에서 가져온다."""
    try:
        hist = yf.Ticker("KRW=X").history(period="5d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            log.info(f"USD/KRW 환율: {rate:.2f}")
            return rate
    except Exception as e:
        log.warning(f"환율 조회 실패: {e}")
    log.warning("환율 기본값 1400 사용")
    return 1400.0


# ─────────────────────────────────────────────
# 한국 종목
# ─────────────────────────────────────────────

def fetch_korea() -> tuple[pd.DataFrame, list[dict]]:
    """
    FinanceDataReader로 KOSPI+KOSDAQ 종목 목록을 가져온 후
    시총 5,000억 이상만 필터링하고 일봉 120일치를 수집한다.
    """
    log.info("=== 한국 종목 수집 시작 ===")
    start = start_date_str()

    # 종목 목록 + 시총
    universe_rows = []
    for market_name in ["KOSPI", "KOSDAQ"]:
        try:
            listing = fdr.StockListing(market_name)
        except Exception as e:
            log.warning(f"{market_name} 목록 조회 실패: {e}")
            continue

        # 필요 컬럼 확인
        if "Marcap" not in listing.columns or "Code" not in listing.columns:
            log.warning(f"{market_name} 컬럼 구조 예상과 다름: {listing.columns.tolist()}")
            continue

        # 시총 필터
        filtered = listing[listing["Marcap"] >= KR_MKTCAP_MIN].copy()

        # 우선주 제외: 종목코드 마지막 자리가 0이 아닌 경우 (1~9)
        filtered = filtered[filtered["Code"].str[-1] == "0"]

        for _, row in filtered.iterrows():
            name = row.get("Name", row["Code"])
            universe_rows.append({
                "ticker": row["Code"],
                "name": name,
                "market": "KR",
                "market_cap_krw": int(row["Marcap"]),
                "market_cap_usd": None,
            })

    log.info(f"한국 유니버스: {len(universe_rows)}종목")

    # 일봉 수집
    all_frames = []
    failed = 0
    for i, info in enumerate(universe_rows):
        ticker = info["ticker"]
        try:
            ohlcv = fdr.DataReader(ticker, start)
            if ohlcv.empty or len(ohlcv) < 30:
                log.debug(f"[KR] {ticker} 데이터 부족({len(ohlcv)}행), 스킵")
                failed += 1
                continue

            ohlcv = ohlcv[["Open", "High", "Low", "Close", "Volume"]].copy()
            ohlcv.index = pd.to_datetime(ohlcv.index)
            ohlcv.index.name = "Date"
            ohlcv["ticker"] = ticker
            ohlcv["market"] = "KR"
            all_frames.append(ohlcv)
        except Exception as e:
            log.warning(f"[KR] {ticker} 실패: {e}")
            failed += 1

        if (i + 1) % 100 == 0:
            log.info(f"[KR] {i+1}/{len(universe_rows)} 처리 중 (실패: {failed})...")
        time.sleep(0.05)

    if not all_frames:
        log.warning("한국 데이터 없음")
        return pd.DataFrame(), universe_rows

    kr_df = pd.concat(all_frames)
    log.info(f"한국 수집 완료: {len(all_frames)}종목, {len(kr_df)}행 (실패: {failed})")
    return kr_df, universe_rows


# ─────────────────────────────────────────────
# 미국 종목
# ─────────────────────────────────────────────

def _fetch_nasdaq_symbols() -> list[str]:
    """NASDAQ Trader에서 NYSE+NASDAQ 보통주 목록을 가져온다."""
    urls = [
        "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    ]
    all_symbols = []
    for url in urls:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            lines = resp.text.splitlines()
            rows = [l.split("|") for l in lines[1:-1]]
            df = pd.DataFrame(rows, columns=lines[0].split("|"))

            # otherlisted 컬럼명 통일
            if "ACT Symbol" in df.columns:
                df = df.rename(columns={"ACT Symbol": "Symbol"})

            # ETF 제외
            if "ETF" in df.columns:
                df = df[df["ETF"].str.strip() != "Y"]
            if "Test Issue" in df.columns:
                df = df[df["Test Issue"].str.strip() != "Y"]

            # 보통주만: 1~5자리 알파벳
            df = df[df["Symbol"].str.match(r"^[A-Z]{1,5}$", na=False)]
            all_symbols.extend(df["Symbol"].tolist())
        except Exception as e:
            log.warning(f"NASDAQ Trader 목록 조회 실패 ({url}): {e}")

    symbols = list(set(all_symbols))
    log.info(f"NASDAQ Trader 보통주 종목 수: {len(symbols)}")
    return symbols


def fetch_usa(usd_krw: float) -> tuple[pd.DataFrame, list[dict]]:
    """
    NASDAQ Trader 목록 → yfinance 시총 필터 → 일봉 수집.
    """
    log.info("=== 미국 종목 수집 시작 ===")
    us_mktcap_min_usd = KR_MKTCAP_MIN / usd_krw
    log.info(f"미국 시총 기준: ${us_mktcap_min_usd/1e6:.0f}M (환율 {usd_krw:.0f})")

    all_symbols = _fetch_nasdaq_symbols()
    if not all_symbols:
        return pd.DataFrame(), []

    # 시총 확인 (배치당 100개)
    universe = []
    BATCH = 100
    for i in range(0, len(all_symbols), BATCH):
        batch = all_symbols[i:i+BATCH]
        try:
            raw = yf.download(
                batch,
                period="2d",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            # fast_info로 시총 확인
            tickers_obj = yf.Tickers(" ".join(batch))
            for sym in batch:
                try:
                    info = tickers_obj.tickers[sym].fast_info
                    cap = getattr(info, "market_cap", None)
                    if cap and cap >= us_mktcap_min_usd:
                        universe.append({
                            "ticker": sym,
                            "name": sym,
                            "market": "US",
                            "market_cap_krw": int(cap * usd_krw),
                            "market_cap_usd": int(cap),
                        })
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"[US] 배치 {i}~{i+BATCH} 시총 조회 실패: {e}")
        time.sleep(0.5)
        if (i // BATCH + 1) % 10 == 0:
            log.info(f"[US] 시총 확인 {min(i+BATCH, len(all_symbols))}/{len(all_symbols)}...")

    log.info(f"미국 유니버스: {len(universe)}종목")

    # 일봉 수집 (배치당 50개)
    us_tickers = [u["ticker"] for u in universe]
    all_frames = []
    OHLCV_BATCH = 50

    for i in range(0, len(us_tickers), OHLCV_BATCH):
        batch = us_tickers[i:i+OHLCV_BATCH]
        try:
            raw = yf.download(
                batch,
                period=f"{DAYS_HISTORY}d",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if raw.empty:
                continue

            # yfinance는 단일 종목도 멀티인덱스를 반환할 수 있음
            if isinstance(raw.columns, pd.MultiIndex):
                for sym in batch:
                    try:
                        sym_df = raw.xs(sym, axis=1, level=1)[
                            ["Open", "High", "Low", "Close", "Volume"]
                        ].dropna(how="all")
                        if len(sym_df) < 30:
                            continue
                        sym_df.index.name = "Date"
                        sym_df["ticker"] = sym
                        sym_df["market"] = "US"
                        all_frames.append(sym_df)
                    except Exception:
                        pass
            else:
                # 단일 종목 flat 컬럼 케이스
                raw.columns = [c[0] if isinstance(c, tuple) else c
                               for c in raw.columns]
                sym_df = raw[["Open", "High", "Low", "Close", "Volume"]].dropna(how="all")
                if len(sym_df) >= 30:
                    sym_df.index.name = "Date"
                    sym_df["ticker"] = batch[0]
                    sym_df["market"] = "US"
                    all_frames.append(sym_df)
        except Exception as e:
            log.warning(f"[US] 일봉 배치 {i}~{i+OHLCV_BATCH} 실패: {e}")
        time.sleep(1)
        if (i // OHLCV_BATCH + 1) % 5 == 0:
            log.info(f"[US] 일봉 {min(i+OHLCV_BATCH, len(us_tickers))}/{len(us_tickers)}...")

    if not all_frames:
        log.warning("미국 데이터 없음")
        return pd.DataFrame(), universe

    us_df = pd.concat(all_frames)
    log.info(f"미국 수집 완료: {len(all_frames)}종목, {len(us_df)}행")
    return us_df, universe


# ─────────────────────────────────────────────
# 저장 (증분 업데이트)
# ─────────────────────────────────────────────

def save(new_frames: list[pd.DataFrame], new_universe: list[dict],
         markets_updated: list[str]):
    """기존 parquet에서 갱신된 시장만 교체 후 저장."""
    os.makedirs(DATA_DIR, exist_ok=True)

    # 기존 데이터 로드
    old_prices = pd.DataFrame()
    old_universe = []
    if os.path.exists(PRICES_PATH):
        try:
            old_prices = pd.read_parquet(PRICES_PATH)
            old_prices = old_prices[~old_prices["market"].isin(markets_updated)]
        except Exception as e:
            log.warning(f"기존 parquet 로드 실패, 전체 재작성: {e}")

    if os.path.exists(UNIVERSE_PATH):
        try:
            with open(UNIVERSE_PATH, encoding="utf-8") as f:
                meta = json.load(f)
            old_universe = [u for u in meta.get("universe", [])
                            if u["market"] not in markets_updated]
        except Exception as e:
            log.warning(f"기존 universe.json 로드 실패: {e}")

    # 합치기
    all_frames = ([old_prices] if not old_prices.empty else []) + \
                 [f.reset_index() for f in new_frames if not f.empty]
    if not all_frames:
        log.error("저장할 데이터 없음")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"])
    combined.to_parquet(PRICES_PATH, index=False)
    log.info(f"저장: {PRICES_PATH} ({len(combined)}행)")

    all_universe = old_universe + new_universe
    with open(UNIVERSE_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now().isoformat(),
            "universe": all_universe,
        }, f, ensure_ascii=False, indent=2)
    log.info(f"저장: {UNIVERSE_PATH} ({len(all_universe)}종목)")


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="주식 데이터 수집")
    parser.add_argument(
        "--market",
        choices=["all", "kr", "us"],
        default="all",
        help="수집할 시장 (기본값: all)",
    )
    args = parser.parse_args()

    usd_krw = get_usd_krw()

    new_frames = []
    new_universe = []
    markets_updated = []

    if args.market in ("all", "kr"):
        kr_df, kr_universe = fetch_korea()
        if not kr_df.empty:
            new_frames.append(kr_df)
            new_universe.extend(kr_universe)
            markets_updated.append("KR")

    if args.market in ("all", "us"):
        us_df, us_universe = fetch_usa(usd_krw)
        if not us_df.empty:
            new_frames.append(us_df)
            new_universe.extend(us_universe)
            markets_updated.append("US")

    if new_frames:
        save(new_frames, new_universe, markets_updated)
    else:
        log.warning("수집된 데이터 없음, 저장 생략")

    log.info(f"=== 완료: {len(new_universe)}종목 갱신 ===")


if __name__ == "__main__":
    main()
