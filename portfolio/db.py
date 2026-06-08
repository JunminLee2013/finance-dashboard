"""Supabase CRUD for the portfolio rebalancing system.

기존 app.py의 get_supabase()는 @st.cache_resource로 캐시된 클라이언트를 반환합니다.
import 사이드 이펙트를 피하기 위해 supabase 클라이언트는 매 호출 시 가져옵니다.
"""

from __future__ import annotations

import functools
import time
from datetime import date
from typing import Iterable

import httpx
import streamlit as st
from supabase import Client, create_client


@st.cache_resource
def _client() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])


def _invalidate():
    st.cache_data.clear()


_RETRYABLE_EXC = (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError)


def _retryable(fn):
    """연결 오류 시 클라이언트 캐시를 초기화하고 최대 2회 재시도."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        last_exc: BaseException | None = None
        for attempt in range(3):
            try:
                return fn(*args, **kwargs)
            except _RETRYABLE_EXC as e:
                last_exc = e
                _client.clear()
                if attempt < 2:
                    time.sleep(0.3 * (2 ** attempt))
        raise last_exc  # type: ignore[misc]
    return wrapper


# ── 계좌 ─────────────────────────────────────────────────────────
@_retryable
def list_accounts() -> list[dict]:
    res = _client().table("pf_accounts").select("*").order("name").execute()
    return res.data or []


@_retryable
def create_account(name: str) -> dict:
    res = _client().table("pf_accounts").insert({"name": name}).execute()
    _invalidate()
    return res.data[0]


@_retryable
def delete_account(account_id: int):
    _client().table("pf_accounts").delete().eq("id", account_id).execute()
    _invalidate()


# ── 종목 마스터 ───────────────────────────────────────────────────
@_retryable
def list_securities() -> list[dict]:
    res = _client().table("pf_securities").select("*").order("code").execute()
    return res.data or []


@_retryable
def upsert_security(code: str, name: str, market: str) -> dict:
    payload = {"code": code, "name": name, "market": market}
    res = _client().table("pf_securities").upsert(payload, on_conflict="code").execute()
    _invalidate()
    return res.data[0]


@_retryable
def delete_security(security_id: int):
    _client().table("pf_securities").delete().eq("id", security_id).execute()
    _invalidate()


# ── 계좌 × 종목 (타겟 비중) ───────────────────────────────────────
@_retryable
def get_account_securities(account_id: int) -> list[dict]:
    """반환: [{security_id, code, name, market, target_weight, display_order}, ...]"""
    res = (
        _client()
        .table("pf_account_securities")
        .select("security_id, target_weight, display_order, pf_securities(code, name, market)")
        .eq("account_id", account_id)
        .order("display_order")
        .execute()
    )
    out = []
    for r in res.data or []:
        sec = r.get("pf_securities") or {}
        out.append(
            {
                "security_id": r["security_id"],
                "code": sec.get("code"),
                "name": sec.get("name"),
                "market": sec.get("market"),
                "target_weight": float(r["target_weight"] or 0),
                "display_order": r.get("display_order") or 0,
            }
        )
    return out


@_retryable
def upsert_account_security(
    account_id: int, security_id: int, target_weight: float, display_order: int = 0
):
    payload = {
        "account_id": account_id,
        "security_id": security_id,
        "target_weight": round(float(target_weight), 4),
        "display_order": int(display_order),
    }
    _client().table("pf_account_securities").upsert(
        payload, on_conflict="account_id,security_id"
    ).execute()
    _invalidate()


@_retryable
def delete_account_security(account_id: int, security_id: int):
    (
        _client()
        .table("pf_account_securities")
        .delete()
        .eq("account_id", account_id)
        .eq("security_id", security_id)
        .execute()
    )
    _invalidate()


# ── 스냅샷 ───────────────────────────────────────────────────────
@_retryable
def list_snapshot_dates(account_id: int) -> list[date]:
    res = (
        _client()
        .table("pf_snapshots")
        .select("snapshot_date")
        .eq("account_id", account_id)
        .order("snapshot_date", desc=True)
        .execute()
    )
    return [date.fromisoformat(r["snapshot_date"]) for r in (res.data or [])]


@_retryable
def get_snapshot(account_id: int, snapshot_date: date) -> dict | None:
    """반환: {id, snapshot_date, cash_balance, items: [{security_id, code, name, quantity, price}]}"""
    sb = _client()
    res = (
        sb.table("pf_snapshots")
        .select("id, snapshot_date, cash_balance")
        .eq("account_id", account_id)
        .eq("snapshot_date", snapshot_date.isoformat())
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    head = res.data[0]
    items_res = (
        sb.table("pf_snapshot_items")
        .select("security_id, quantity, price, pf_securities(code, name, market)")
        .eq("snapshot_id", head["id"])
        .execute()
    )
    items = []
    for r in items_res.data or []:
        sec = r.get("pf_securities") or {}
        items.append(
            {
                "security_id": r["security_id"],
                "code": sec.get("code"),
                "name": sec.get("name"),
                "market": sec.get("market"),
                "quantity": int(r["quantity"] or 0),
                "price": float(r["price"] or 0),
            }
        )
    return {
        "id": head["id"],
        "snapshot_date": date.fromisoformat(head["snapshot_date"]),
        "cash_balance": float(head["cash_balance"] or 0),
        "items": items,
    }


def latest_snapshot(account_id: int) -> dict | None:
    dates = list_snapshot_dates(account_id)
    if not dates:
        return None
    return get_snapshot(account_id, dates[0])


@_retryable
def list_snapshots_full(account_id: int) -> list[dict]:
    """모든 스냅샷 + 아이템을 한 번에 로딩 (스냅샷 날짜 오름차순).

    반환: [{id, snapshot_date, cash_balance,
            items: [{security_id, code, name, market, quantity, price}, ...]}, ...]
    """
    sb = _client()
    snap_res = (
        sb.table("pf_snapshots")
        .select("id, snapshot_date, cash_balance")
        .eq("account_id", account_id)
        .order("snapshot_date")
        .execute()
    )
    snaps = snap_res.data or []
    if not snaps:
        return []
    snap_ids = [s["id"] for s in snaps]
    items_res = (
        sb.table("pf_snapshot_items")
        .select("snapshot_id, security_id, quantity, price, pf_securities(code, name, market)")
        .in_("snapshot_id", snap_ids)
        .execute()
    )
    by_snap: dict[int, list[dict]] = {}
    for r in items_res.data or []:
        sec = r.get("pf_securities") or {}
        by_snap.setdefault(r["snapshot_id"], []).append(
            {
                "security_id": r["security_id"],
                "code": sec.get("code"),
                "name": sec.get("name"),
                "market": sec.get("market"),
                "quantity": int(r["quantity"] or 0),
                "price": float(r["price"] or 0),
            }
        )
    return [
        {
            "id": s["id"],
            "snapshot_date": date.fromisoformat(s["snapshot_date"]),
            "cash_balance": float(s["cash_balance"] or 0),
            "items": by_snap.get(s["id"], []),
        }
        for s in snaps
    ]


@_retryable
def save_snapshot(
    account_id: int,
    snapshot_date: date,
    cash_balance: float,
    items: Iterable[tuple[int, int, float]],
):
    """items: iterable of (security_id, quantity, price). Upsert by (account_id, snapshot_date)."""
    sb = _client()
    head_payload = {
        "account_id": account_id,
        "snapshot_date": snapshot_date.isoformat(),
        "cash_balance": round(float(cash_balance), 2),
    }
    res = sb.table("pf_snapshots").upsert(
        head_payload, on_conflict="account_id,snapshot_date"
    ).execute()
    snapshot_id = res.data[0]["id"]

    # 기존 items 전부 삭제 후 재삽입 (in-place upsert는 항목 추가/삭제를 다루기 번거로움)
    sb.table("pf_snapshot_items").delete().eq("snapshot_id", snapshot_id).execute()
    item_rows = [
        {
            "snapshot_id": snapshot_id,
            "security_id": int(sid),
            "quantity": int(qty),
            "price": round(float(price), 2),
        }
        for sid, qty, price in items
    ]
    if item_rows:
        sb.table("pf_snapshot_items").insert(item_rows).execute()
    _invalidate()
    return snapshot_id


@_retryable
def delete_snapshot(account_id: int, snapshot_date: date):
    (
        _client()
        .table("pf_snapshots")
        .delete()
        .eq("account_id", account_id)
        .eq("snapshot_date", snapshot_date.isoformat())
        .execute()
    )
    _invalidate()
