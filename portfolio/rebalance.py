"""포트폴리오 리밸런싱 순수 계산. streamlit/외부 IO 없음."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Holding:
    security_id: int
    code: str
    name: str
    target_weight: float       # 0..1
    current_qty: int


@dataclass
class RebalanceRow:
    security_id: int
    code: str
    name: str
    price: float
    current_qty: int
    target_weight: float        # 0..1
    target_value: float
    target_qty: int
    delta_qty: int              # +매수, -매도
    projected_value: float
    projected_weight: float     # 0..1, total_value 기준


def compute_rebalance(
    total_value: float,
    holdings: list[Holding],
    prices: dict[str, float],
) -> tuple[list[RebalanceRow], float]:
    """반환: (행 목록, 예상 잔여현금).

    target_qty_i = floor(total_value * w_i / p_i)
    delta_qty_i  = target_qty_i - current_qty_i
    expected_cash = total_value - Σ(target_qty_i * p_i)
    """
    rows: list[RebalanceRow] = []
    invested = 0.0
    tv = max(float(total_value), 0.0)
    for h in holdings:
        p = float(prices.get(h.code, 0) or 0)
        w = float(h.target_weight or 0)
        tgt_val = tv * w
        tgt_qty = int(math.floor(tgt_val / p)) if p > 0 else 0
        proj_val = tgt_qty * p
        invested += proj_val
        rows.append(
            RebalanceRow(
                security_id=h.security_id,
                code=h.code,
                name=h.name,
                price=p,
                current_qty=int(h.current_qty or 0),
                target_weight=w,
                target_value=tgt_val,
                target_qty=tgt_qty,
                delta_qty=tgt_qty - int(h.current_qty or 0),
                projected_value=proj_val,
                projected_weight=(proj_val / tv) if tv > 0 else 0.0,
            )
        )
    expected_cash = tv - invested
    return rows, expected_cash


def compute_current_weights(
    items: list[dict],
    prices: dict[str, float],
    cash_balance: float = 0.0,
) -> tuple[list[dict], float]:
    """현재 비중 계산.

    items: [{security_id, code, name, quantity, ...}]
    prices: code -> 라이브 가격
    반환: ([{...items, price, value, weight}], total_value including cash)
    """
    enriched = []
    stock_total = 0.0
    for it in items:
        p = float(prices.get(it["code"], 0) or 0)
        qty = int(it.get("quantity", 0) or 0)
        v = p * qty
        stock_total += v
        enriched.append({**it, "price": p, "value": v})
    total = stock_total + float(cash_balance or 0)
    for e in enriched:
        e["weight"] = (e["value"] / total) if total > 0 else 0.0
    return enriched, total


# 현금 row 의 security_id 자리에 쓰는 sentinel.
CASH_SID = 0


def compute_pre_post_weights(snapshots: list[dict]) -> list[dict]:
    """스냅샷 시계열에서 종목(+현금)별 Pre/Post 비중을 계산.

    각 스냅샷 t (시계열상 두 번째부터) 에 대해 종목 i 및 현금에 대해:

        pre_value_{i,t}  = q_{i,t-1} * p_{i,t}        # 직전 수량 × 당일 가격
        post_value_{i,t} = q_{i,t}   * p_{i,t}        # 당일 수량 × 당일 가격
        pre_cash_{t}     = cash_{t-1}
        post_cash_{t}    = cash_{t}
        weight = value / (Σ value_securities + cash)

    첫 스냅샷은 post 만 산출 (pre 기준 직전 데이터가 없음).
    가격은 스냅샷에 저장된 값(p_{i,t}) 사용 — 시점 정합성 위해 yfinance 호출 없음.

    snapshots: list_snapshots_full() 반환 형태.
        [{snapshot_date: date, cash_balance: float,
          items: [{security_id, code, name, quantity, price}, ...]}, ...]

    반환: [{snapshot_date, security_id, label, kind ('pre'|'post'), value, weight_pct}, ...]
    """
    if not snapshots:
        return []

    # 종목 라벨 안정화: 등장 순서대로 union (이후 등장한 종목도 포함)
    label_map: dict[int, str] = {}
    for snap in snapshots:
        for it in snap["items"]:
            sid = it["security_id"]
            if sid not in label_map:
                label_map[sid] = it.get("name") or it.get("code") or f"#{sid}"
    sec_ids = list(label_map.keys())

    rows: list[dict] = []
    for idx, snap in enumerate(snapshots):
        snap_date = snap["snapshot_date"]
        cur_by_sid = {it["security_id"]: it for it in snap["items"]}
        cur_cash = float(snap.get("cash_balance") or 0)

        # post: 당일 수량 × 당일 가격
        post_vals: dict[int, float] = {}
        for sid in sec_ids:
            it = cur_by_sid.get(sid)
            if not it:
                post_vals[sid] = 0.0
                continue
            post_vals[sid] = float(it.get("quantity", 0) or 0) * float(it.get("price", 0) or 0)
        post_total = sum(post_vals.values()) + cur_cash
        if post_total > 0:
            for sid in sec_ids:
                rows.append({
                    "snapshot_date": snap_date,
                    "security_id": sid,
                    "label": label_map[sid],
                    "kind": "post",
                    "value": post_vals[sid],
                    "weight_pct": post_vals[sid] / post_total * 100,
                })
            rows.append({
                "snapshot_date": snap_date,
                "security_id": CASH_SID,
                "label": "현금",
                "kind": "post",
                "value": cur_cash,
                "weight_pct": cur_cash / post_total * 100,
            })

        # pre: 직전 수량 × 당일 가격 (첫 스냅샷은 스킵)
        if idx == 0:
            continue
        prev = snapshots[idx - 1]
        prev_by_sid = {it["security_id"]: it for it in prev["items"]}
        prev_cash = float(prev.get("cash_balance") or 0)
        pre_vals: dict[int, float] = {}
        for sid in sec_ids:
            prev_it = prev_by_sid.get(sid)
            cur_it = cur_by_sid.get(sid)
            if not prev_it or not cur_it:
                pre_vals[sid] = 0.0
                continue
            pre_vals[sid] = float(prev_it.get("quantity", 0) or 0) * float(cur_it.get("price", 0) or 0)
        pre_total = sum(pre_vals.values()) + prev_cash
        if pre_total > 0:
            for sid in sec_ids:
                rows.append({
                    "snapshot_date": snap_date,
                    "security_id": sid,
                    "label": label_map[sid],
                    "kind": "pre",
                    "value": pre_vals[sid],
                    "weight_pct": pre_vals[sid] / pre_total * 100,
                })
            rows.append({
                "snapshot_date": snap_date,
                "security_id": CASH_SID,
                "label": "현금",
                "kind": "pre",
                "value": prev_cash,
                "weight_pct": prev_cash / pre_total * 100,
            })
    return rows
