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
import re
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

KR_MKTCAP_MIN = 100_000_000_000    # 1,000억원 (KRW)
US_MKTCAP_MIN_USD = 400_000_000    # 4억 달러
DAYS_HISTORY = 220                 # 200MA 계산을 위해 220일치 필요


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
    FinanceDataReader로 종목 목록·시총을 가져온 후
    yfinance 배치 다운로드로 일봉 120일치를 수집한다.
    (개별 요청 대비 10~20배 빠름)
    """
    log.info("=== 한국 종목 수집 시작 ===")

    # 종목 목록 + 시총 (FDR — 빠름)
    universe_rows = []
    for market_name, yf_suffix in [("KOSPI", ".KS"), ("KOSDAQ", ".KQ")]:
        try:
            listing = fdr.StockListing(market_name)
        except Exception as e:
            log.warning(f"{market_name} 목록 조회 실패: {e}")
            continue

        if "Marcap" not in listing.columns or "Code" not in listing.columns:
            log.warning(f"{market_name} 컬럼 구조 예상과 다름: {listing.columns.tolist()}")
            continue

        filtered = listing[listing["Marcap"] >= KR_MKTCAP_MIN].copy()
        filtered = filtered[filtered["Code"].str[-1] == "0"]   # 우선주 제외

        for _, row in filtered.iterrows():
            universe_rows.append({
                "ticker":         row["Code"],
                "yf_ticker":      row["Code"] + yf_suffix,
                "name":           row.get("Name", row["Code"]),
                "market":         "KR",
                "market_cap_krw": int(row["Marcap"]),
                "market_cap_usd": None,
            })

    log.info(f"한국 유니버스: {len(universe_rows)}종목")

    # 일봉 수집 — yfinance 배치 (50종목씩)
    yf_tickers = [u["yf_ticker"] for u in universe_rows]
    code_map   = {u["yf_ticker"]: u["ticker"] for u in universe_rows}
    all_frames = []
    BATCH = 50

    for i in range(0, len(yf_tickers), BATCH):
        batch = yf_tickers[i:i+BATCH]
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

            if isinstance(raw.columns, pd.MultiIndex):
                for yf_sym in batch:
                    try:
                        sym_df = raw.xs(yf_sym, axis=1, level=1)[
                            ["Open", "High", "Low", "Close", "Volume"]
                        ].dropna(how="all")
                        if len(sym_df) < 30:
                            continue
                        sym_df.index.name = "Date"
                        sym_df["ticker"] = code_map[yf_sym]
                        sym_df["market"] = "KR"
                        all_frames.append(sym_df)
                    except Exception:
                        pass
            else:
                raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
                sym_df = raw[["Open", "High", "Low", "Close", "Volume"]].dropna(how="all")
                if len(sym_df) >= 30:
                    sym_df.index.name = "Date"
                    sym_df["ticker"] = code_map.get(batch[0], batch[0])
                    sym_df["market"] = "KR"
                    all_frames.append(sym_df)
        except Exception as e:
            log.warning(f"[KR] 배치 {i}~{i+BATCH} 실패: {e}")

        time.sleep(0.5)
        log.info(f"[KR] {min(i+BATCH, len(yf_tickers))}/{len(yf_tickers)} 완료...")

    if not all_frames:
        log.warning("한국 데이터 없음")
        return pd.DataFrame(), universe_rows

    kr_df = pd.concat(all_frames)
    log.info(f"한국 수집 완료: {len(all_frames)}종목, {len(kr_df)}행")
    return kr_df, universe_rows


# ─────────────────────────────────────────────
# 미국 종목
# ─────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def _fetch_us_symbols() -> list[str]:
    """
    NYSE + NASDAQ 상장 종목 목록 수집.
    1순위: FinanceDataReader (Yahoo Finance 기반, GitHub Actions 정상 동작)
    2순위: Wikipedia S&P500 + NASDAQ-100 폴백
    """
    from io import StringIO
    all_symbols = []

    # ── 1순위: FinanceDataReader ──────────────────────────────
    for market in ["NYSE", "NASDAQ"]:
        try:
            listing = fdr.StockListing(market)
            sym_col = next(
                (c for c in listing.columns if str(c).lower() in ["symbol", "code", "ticker"]),
                listing.columns[0],
            )
            syms = listing[sym_col].dropna().astype(str).str.strip()
            syms = [s for s in syms if re.match(r"^[A-Z]{1,5}$", s)]
            all_symbols.extend(syms)
            log.info(f"FDR {market}: {len(syms)}종목")
        except Exception as e:
            log.warning(f"FDR {market} 목록 조회 실패: {e}")

    # ── 2순위: Wikipedia 폴백 (FDR 결과 없을 때) ─────────────
    if len(all_symbols) < 100:
        log.info("FDR 목록 부족 → Wikipedia 폴백 사용")
        for name, url in [
            ("S&P500",     "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"),
            ("NASDAQ-100", "https://en.wikipedia.org/wiki/NASDAQ-100"),
        ]:
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=30)
                resp.raise_for_status()
                tables = pd.read_html(StringIO(resp.text))
                for df in tables:
                    col = next(
                        (c for c in df.columns
                         if "ticker" in str(c).lower() or "symbol" in str(c).lower()),
                        None,
                    )
                    if col and len(df) >= 90:
                        syms = df[col].dropna().astype(str).str.strip()
                        syms = [s for s in syms if re.match(r"^[A-Z]{1,5}$", s)]
                        all_symbols.extend(syms)
                        log.info(f"Wikipedia {name} (폴백): {len(syms)}종목")
                        break
            except Exception as e:
                log.warning(f"Wikipedia {name} 폴백 실패: {e}")

    symbols = list(set(all_symbols))
    log.info(f"US 상장 종목 합산: {len(symbols)}개 (시총 필터 전)")
    return symbols


def fetch_usa(usd_krw: float) -> tuple[pd.DataFrame, list[dict]]:
    """
    NYSE+NASDAQ 목록 → 시총 $400M 이상 필터 → 일봉 수집.
    """
    log.info("=== 미국 종목 수집 시작 ===")
    log.info(f"미국 시총 기준: ${US_MKTCAP_MIN_USD/1e6:.0f}M (환율 {usd_krw:.0f})")

    all_symbols = _fetch_us_symbols()
    if not all_symbols:
        return pd.DataFrame(), []

    # ── 시총 필터링 (fast_info, 배치당 100개) ────────────────
    universe = []
    CAP_BATCH = 100
    for i in range(0, len(all_symbols), CAP_BATCH):
        batch = all_symbols[i:i+CAP_BATCH]
        try:
            tickers_obj = yf.Tickers(" ".join(batch))
            for sym in batch:
                try:
                    cap = getattr(tickers_obj.tickers[sym].fast_info, "market_cap", None)
                    if cap and cap >= US_MKTCAP_MIN_USD:
                        universe.append({
                            "ticker": sym, "name": sym, "market": "US",
                            "market_cap_krw": int(cap * usd_krw),
                            "market_cap_usd": int(cap),
                        })
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"[US] 시총 조회 실패 배치 {i}: {e}")
        time.sleep(0.3)
        if (i // CAP_BATCH + 1) % 20 == 0:
            log.info(f"[US] 시총 확인 {min(i+CAP_BATCH, len(all_symbols))}/{len(all_symbols)} "
                     f"(통과: {len(universe)})")

    log.info(f"미국 유니버스 (시총 필터 후): {len(universe)}종목")

    # ── 일봉 수집 (배치당 50개) ───────────────────────────────
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
                raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
                sym_df = raw[["Open", "High", "Low", "Close", "Volume"]].dropna(how="all")
                if len(sym_df) >= 30:
                    sym_df.index.name = "Date"
                    sym_df["ticker"] = batch[0]
                    sym_df["market"] = "US"
                    all_frames.append(sym_df)
        except Exception as e:
            log.warning(f"[US] 일봉 배치 {i}~{i+OHLCV_BATCH} 실패: {e}")
        time.sleep(0.5)
        if (i // OHLCV_BATCH + 1) % 10 == 0:
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

    # yf_ticker 같은 내부 전용 필드 제거 후 저장
    keep_keys = {"ticker", "name", "market", "market_cap_krw", "market_cap_usd"}
    clean_universe = [
        {k: v for k, v in u.items() if k in keep_keys}
        for u in old_universe + new_universe
    ]
    with open(UNIVERSE_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now().isoformat(),
            "universe": clean_universe,
        }, f, ensure_ascii=False, indent=2)
    log.info(f"저장: {UNIVERSE_PATH} ({len(clean_universe)}종목)")


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
