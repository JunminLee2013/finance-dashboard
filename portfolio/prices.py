"""yfinance 래퍼 — 한국 주식 (.KS / .KQ) 현재가/과거가 조회.

실패 시 None을 반환하고 절대 예외를 페이지로 흘려보내지 않습니다 (UI에서 수동 입력 폴백).
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st


def _ticker_symbol(code: str, market: str) -> str:
    return f"{code}.{market}"


@st.cache_data(ttl=300, show_spinner=False)
def get_current_price(code: str, market: str) -> float | None:
    try:
        import yfinance as yf

        sym = _ticker_symbol(code, market)
        hist = yf.Ticker(sym).history(period="5d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        return float(hist["Close"].dropna().iloc[-1])
    except Exception:
        return None


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
    """KS 먼저 시도 → 데이터 있으면 'KS', 없으면 KQ. 둘 다 실패 시 None."""
    for m in ("KS", "KQ"):
        p = get_current_price(code, m)
        if p is not None and p > 0:
            return m
    return None
