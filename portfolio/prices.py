"""한국 주식/ETF 가격 조회.

1차: yfinance (`{code}.KS` / `{code}.KQ`).
2차: Naver Finance JSON (yfinance가 빈 데이터를 반환하는 일부 ETF 대응).

실패 시 None을 반환하고 절대 예외를 페이지로 흘려보내지 않습니다 (UI에서 수동 입력 폴백).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date, timedelta

import streamlit as st


def _ticker_symbol(code: str, market: str) -> str:
    return f"{code}.{market}"


def _yfinance_current(code: str, market: str) -> float | None:
    try:
        import yfinance as yf

        sym = _ticker_symbol(code, market)
        hist = yf.Ticker(sym).history(period="5d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        return float(closes.iloc[-1])
    except Exception:
        return None


def _naver_current(code: str) -> float | None:
    """Naver Finance 모바일 JSON API로 KRX 상장 종목 현재가 조회."""
    url = f"https://m.stock.naver.com/api/stock/{code}/basic"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    # `closePrice` 가 표준 키 (예: "10,500"). 일부 응답은 `dealTrendInfos[0].closePrice`.
    candidates = [data.get("closePrice")]
    deals = data.get("dealTrendInfos") or []
    if deals and isinstance(deals, list):
        candidates.append(deals[0].get("closePrice"))
    for s in candidates:
        if not s:
            continue
        try:
            return float(str(s).replace(",", ""))
        except ValueError:
            continue
    return None


@st.cache_data(ttl=300, show_spinner=False)
def get_current_price(code: str, market: str) -> float | None:
    p = _yfinance_current(code, market)
    if p is not None:
        return p
    return _naver_current(code)


@st.cache_data(ttl=86400, show_spinner=False)
def get_historical_price(code: str, market: str, on: date) -> float | None:
    """주어진 날짜에 가장 가까운 종가(휴장 대비 ±5일 윈도우)."""
    try:
        import yfinance as yf

        sym = _ticker_symbol(code, market)
        start = on - timedelta(days=5)
        end = on + timedelta(days=2)
        hist = yf.Ticker(sym).history(start=start.isoformat(), end=end.isoformat(),
                                       auto_adjust=False)
        if hist is None or hist.empty:
            return None
        # `on` 이하 마지막 데이터, 없으면 첫 가용 데이터.
        hist = hist[hist.index.date <= on]
        if hist.empty:
            return None
        return float(hist["Close"].dropna().iloc[-1])
    except Exception:
        return None


def resolve_market(code: str) -> str | None:
    """KS 먼저 시도 → 데이터 있으면 'KS', 없으면 KQ. 둘 다 실패 시 None.

    시장 식별이 목적이므로 yfinance만 사용한다 (Naver는 KS/KQ 구분 없이
    같은 코드로 응답하므로 시장 판정에 쓸 수 없다)."""
    for m in ("KS", "KQ"):
        p = _yfinance_current(code, m)
        if p is not None and p > 0:
            return m
    return None
