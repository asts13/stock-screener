"""KIS Open API 클라이언트 — token 관리, KR/US 일봉 조회, 시가총액 조회"""
import os, json, time, threading, requests, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

BASE_URL   = "https://openapi.koreainvestment.com:9443"
TOKEN_FILE = Path(__file__).parent.parent / "data" / ".kis_token.json"

# ---------------------------------------------------------------------------
# Rate Limiter (18 req/s 제한)
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self, max_calls: int = 18, period: float = 1.0):
        self._max   = max_calls
        self._period = period
        self._lock  = threading.Lock()
        self._calls: list[float] = []

    def acquire(self):
        while True:
            with self._lock:
                now = time.monotonic()
                self._calls = [t for t in self._calls if now - t < self._period]
                if len(self._calls) < self._max:
                    self._calls.append(now)
                    return
                wait = self._period - (now - self._calls[0])
            time.sleep(max(wait, 0.01))

_limiter = RateLimiter()

# ---------------------------------------------------------------------------
# KIS Client
# ---------------------------------------------------------------------------
class KISClient:
    def __init__(self, app_key: str, app_secret: str):
        self._key    = app_key
        self._secret = app_secret
        self._token: str | None = None
        self._token_exp: datetime | None = None
        self._lock = threading.Lock()

    # ── Token ────────────────────────────────────────────────────────────
    def get_token(self) -> str:
        with self._lock:
            # 1) 메모리 캐시
            if self._token and self._token_exp and datetime.now() < self._token_exp:
                return self._token
            # 2) 파일 캐시
            if TOKEN_FILE.exists():
                try:
                    cached = json.loads(TOKEN_FILE.read_text())
                    exp = datetime.fromisoformat(cached["expires_at"])
                    if datetime.now() < exp - timedelta(minutes=10):
                        self._token     = cached["access_token"]
                        self._token_exp = exp
                        return self._token
                except Exception:
                    pass
            # 3) 신규 발급
            resp = requests.post(
                f"{BASE_URL}/oauth2/tokenP",
                json={"grant_type": "client_credentials",
                      "appkey":     self._key,
                      "appsecret":  self._secret},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            token  = data["access_token"]
            # KIS 토큰 만료 = 발급 후 86400초(24h)
            exp_dt = datetime.now() + timedelta(seconds=int(data.get("expires_in", 86400)))
            self._token     = token
            self._token_exp = exp_dt
            TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_FILE.write_text(json.dumps({
                "access_token": token,
                "expires_at":   exp_dt.isoformat()
            }))
            return token

    # ── 공통 헤더 ────────────────────────────────────────────────────────
    def _h(self, tr_id: str) -> dict:
        return {
            "Content-Type":  "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_token()}",
            "appkey":        self._key,
            "appsecret":     self._secret,
            "tr_id":         tr_id,
            "custtype":      "P",
        }

    # ── KR 일봉 (FHKST03010100) ──────────────────────────────────────────
    def fetch_kr_daily(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """
        start/end: 'YYYYMMDD'
        Returns DataFrame [date, open, high, low, close, volume]
        """
        _limiter.acquire()
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd":         ticker,
            "fid_input_date_1":       start,
            "fid_input_date_2":       end,
            "fid_period_div_code":    "D",
            "fid_org_adj_prc":        "0",
        }
        r = requests.get(
            f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            headers=self._h("FHKST03010100"),
            params=params,
            timeout=15,
        )
        try:
            r.raise_for_status()
        except Exception:
            return pd.DataFrame()
        rows = r.json().get("output2", [])
        return _parse_kr(rows)

    def fetch_kr_daily_full(self, ticker: str, n_days: int = 400) -> pd.DataFrame:
        """n_days 치 일봉 수집 (100개씩 backward chunking)"""
        end_dt   = datetime.today()
        collected: list[pd.DataFrame] = []
        while True:
            end_str   = end_dt.strftime("%Y%m%d")
            start_str = (end_dt - timedelta(days=150)).strftime("%Y%m%d")
            try:
                chunk = self.fetch_kr_daily(ticker, start_str, end_str)
            except Exception:
                break
            if chunk.empty:
                break
            collected.append(chunk)
            total = pd.concat(collected).drop_duplicates("date")
            if len(total) >= n_days:
                break
            end_dt = chunk["date"].min() - timedelta(days=1)
            if (datetime.today() - end_dt).days > 800:
                break
        if not collected:
            return pd.DataFrame()
        df = pd.concat(collected).drop_duplicates("date").sort_values("date").reset_index(drop=True)
        return df.tail(n_days).reset_index(drop=True)

    # ── US 일봉 (HHDFS76240000) ──────────────────────────────────────────
    def fetch_us_daily(self, ticker: str, excd: str, end: str = "") -> pd.DataFrame:
        """
        excd: 'NAS' | 'NYS' | 'AMS'
        end:  'YYYYMMDD' (빈 문자열 → 오늘)
        Returns DataFrame [date, open, high, low, close, volume]
        """
        if not end:
            end = datetime.today().strftime("%Y%m%d")
        _limiter.acquire()
        params = {
            "AUTH":      "",
            "EXCD":      excd,
            "SYMB":      ticker,
            "GUBN":      "0",   # 0=일봉
            "BYMD":      end,
            "MODP":      "1",   # 수정주가
            "KEYB":      "",
        }
        r = requests.get(
            f"{BASE_URL}/uapi/overseas-price/v1/quotations/dailyprice",
            headers=self._h("HHDFS76240000"),
            params=params,
            timeout=15,
        )
        try:
            r.raise_for_status()
        except Exception:
            return pd.DataFrame()
        rows = r.json().get("output2", [])
        return _parse_us(rows)

    def fetch_us_daily_full(self, ticker: str, excd: str, n_days: int = 400) -> pd.DataFrame:
        """n_days 치 일봉 수집 (backward chunking)"""
        end_dt   = datetime.today()
        collected: list[pd.DataFrame] = []
        while True:
            end_str = end_dt.strftime("%Y%m%d")
            try:
                chunk = self.fetch_us_daily(ticker, excd, end_str)
            except Exception:
                break
            if chunk.empty:
                break
            collected.append(chunk)
            total = pd.concat(collected).drop_duplicates("date")
            if len(total) >= n_days:
                break
            end_dt = chunk["date"].min() - timedelta(days=1)
            if (datetime.today() - end_dt).days > 800:
                break
        if not collected:
            return pd.DataFrame()
        df = pd.concat(collected).drop_duplicates("date").sort_values("date").reset_index(drop=True)
        return df.tail(n_days).reset_index(drop=True)

    # ── KR 현재가 + 시가총액 ──────────────────────────────────────────────
    def fetch_kr_price_info(self, ticker: str) -> dict:
        """Returns {'close': float, 'market_cap_eok': float}"""
        _limiter.acquire()
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd":         ticker,
        }
        r = requests.get(
            f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._h("FHKST01010100"),
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        out = r.json().get("output", {})
        close      = float(out.get("stck_prpr", 0) or 0)
        # hts_avls: 시가총액(억원)
        mktcap_eok = float(out.get("hts_avls", 0) or 0)
        return {"close": close, "market_cap_eok": mktcap_eok}

    # ── US 현재가 + 시가총액 ──────────────────────────────────────────────
    def fetch_us_price_info(self, ticker: str, excd: str) -> dict:
        """Returns {'close': float, 'market_cap_m': float}  (USD M)"""
        _limiter.acquire()
        params = {
            "AUTH": "",
            "EXCD": excd,
            "SYMB": ticker,
        }
        r = requests.get(
            f"{BASE_URL}/uapi/overseas-price/v1/quotations/price",
            headers=self._h("HHDFS00000300"),
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        out   = r.json().get("output", {})
        close = float(out.get("last", 0) or 0)
        # KIS US price endpoint doesn't return market cap — use shares * price
        # rsym 필드에서 시가총액 정보 없음 → 0 반환, universe 필터는 별도 처리
        mktcap_m = 0.0
        return {"close": close, "market_cap_m": mktcap_m}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------
def _parse_kr(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    records = []
    for r in rows:
        d = r.get("stck_bsop_date", "")
        if not d:
            continue
        try:
            records.append({
                "date":   pd.Timestamp(d),
                "open":   float(r.get("stck_oprc", 0) or 0),
                "high":   float(r.get("stck_hgpr", 0) or 0),
                "low":    float(r.get("stck_lwpr", 0) or 0),
                "close":  float(r.get("stck_clpr", 0) or 0),
                "volume": float(r.get("acml_vol", 0) or 0),
            })
        except Exception:
            continue
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df = df[df["close"] > 0].sort_values("date").reset_index(drop=True)
    return df


def _parse_us(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    records = []
    for r in rows:
        d = r.get("xymd", "")
        if not d:
            continue
        try:
            records.append({
                "date":   pd.Timestamp(d),
                "open":   float(r.get("open", 0) or 0),
                "high":   float(r.get("high", 0) or 0),
                "low":    float(r.get("llow", r.get("low", 0)) or 0),
                "close":  float(r.get("clos", 0) or 0),
                "volume": float(r.get("tvol", 0) or 0),
            })
        except Exception:
            continue
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df = df[df["close"] > 0].sort_values("date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def get_client() -> KISClient:
    """Streamlit secrets 또는 환경변수에서 KIS 자격증명 로드"""
    try:
        import streamlit as st
        key    = st.secrets["kis"]["app_key"]
        secret = st.secrets["kis"]["app_secret"]
    except Exception:
        key    = os.environ.get("KIS_APP_KEY", "")
        secret = os.environ.get("KIS_APP_SECRET", "")
    if not key or not secret:
        raise RuntimeError(
            "KIS 자격증명 없음. .streamlit/secrets.toml 또는 환경변수를 확인하세요."
        )
    return KISClient(key, secret)
