"""
GitHub Actions 스케줄 실행 스크립트
 - KR/US 유니버스 로드
 - 일봉 수집 (Parquet 캐시 업데이트)
 - 스크리닝 결과 저장
"""
import os, sys, logging, json
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("refresh")


def main():
    from core.kis_api import KISClient
    from core.universe import get_kr_universe, get_us_universe
    from core.prices import fetch_all_kr, fetch_all_us
    from core.screener import run_screening_kr, run_screening_us

    app_key    = os.environ.get("KIS_APP_KEY", "")
    app_secret = os.environ.get("KIS_APP_SECRET", "")
    if not app_key or not app_secret:
        log.error("KIS_APP_KEY / KIS_APP_SECRET 환경변수 없음")
        sys.exit(1)

    client = KISClient(app_key, app_secret)
    log.info("KIS 토큰 취득 중...")
    client.get_token()
    log.info("토큰 OK")

    # ── 한국 ─────────────────────────────────────────────────────────────
    log.info("KR 유니버스 로드 중...")
    kr_uni = get_kr_universe(client=client)
    log.info(f"KR 유니버스: {len(kr_uni)}개 종목")

    log.info("KR 일봉 수집 중...")
    fetch_all_kr(client, kr_uni["ticker"].tolist())
    log.info("KR 일봉 수집 완료")

    log.info("KR 스크리닝 중...")
    kr_res = run_screening_kr(kr_uni)
    a1_cnt = kr_res["a1"].sum()
    a2_cnt = kr_res["a2"].sum()
    b_cnt  = kr_res["b"].sum()
    log.info(f"KR 결과 — A1: {a1_cnt}, A2: {a2_cnt}, B: {b_cnt}")

    # ── 미국 ─────────────────────────────────────────────────────────────
    log.info("US 유니버스 로드 중...")
    us_uni = get_us_universe(client=client)
    log.info(f"US 유니버스: {len(us_uni)}개 종목")

    log.info("US 일봉 수집 중...")
    fetch_all_us(client, us_uni)
    log.info("US 일봉 수집 완료")

    log.info("US 스크리닝 중...")
    us_res = run_screening_us(us_uni)
    a1_cnt = us_res["a1"].sum()
    a2_cnt = us_res["a2"].sum()
    b_cnt  = us_res["b"].sum()
    log.info(f"US 결과 — A1: {a1_cnt}, A2: {a2_cnt}, B: {b_cnt}")

    # ── 갱신 시각 기록 ────────────────────────────────────────────────────
    from datetime import timezone
    import json
    last_update_file = ROOT / "data" / "last_update.json"
    last_update_file.parent.mkdir(parents=True, exist_ok=True)
    last_update_file.write_text(
        json.dumps({"ts": datetime.now(timezone.utc).astimezone().isoformat()})
    )
    log.info("전체 갱신 완료")


if __name__ == "__main__":
    main()
