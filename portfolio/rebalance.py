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
