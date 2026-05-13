"""
migrate_portfolio.py — Google Spreadsheet "포트폴리오" 시트 CSV → Supabase 마이그레이션.

기존 migrate.py 와 동일한 대화형 패턴.

CSV 레이아웃 (블록 구조 — 빈 줄로 구분된 계좌별 블록):
  [0] 계좌명, , , (오늘 날짜),,,,,,,,(date1), (date1), (date1), , (date2), ...
  [1] 종목, 종목코드, 비율, (총평가가치), 현재가격, 수량, 평가액(tobe), 매수, 평가액(asis), 현재비중, , 비율, 평가금액, 수량, , ...
  [2..] (종목명), (종목코드), (타겟%), ... (스킵-콜 D~J) ... , (비중%), (평가금액), (수량), , ...
  [N] , , 100.0%, (총평가), , , (총매수후평가), , (총asis평가), 100%, , (스냅샷별 총합)...
  [N+1] (빈 줄)

마이그레이션 대상:
  - K열(idx 10) 이후의 4컬럼 그룹 = 과거 스냅샷. (D~J열은 오늘 view라 스킵)
  - 각 종목: name+code → pf_securities (market='KS')
  - 각 (계좌, 종목): target_weight → pf_account_securities
  - 각 (계좌, 날짜): pf_snapshots (cash_balance=0)
    + 각 (스냅샷, 종목): price = round(평가금액 / 수량, 2), quantity. 둘 다 0이면 스킵.

사용법:
  pip install pandas requests
  python migrate_portfolio.py
"""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import date

import pandas as pd
import requests


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PCT_RE = re.compile(r"^-?\d+(?:\.\d+)?\s*%$")


def safe_num(v) -> float | None:
    """숫자 파싱: ₩, 쉼표, %, 괄호음수 처리. 빈/대시는 None."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).replace(",", "").replace("₩", "").replace("$", "").strip()
    if s in ("", "-", "—", "N/A", "#N/A", "nan", "None"):
        return None
    s = s.rstrip("%").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except Exception:
        return None


def parse_pct_as_ratio(v) -> float | None:
    """`'25.0%'` → 0.25. None 시 None."""
    n = safe_num(v)
    if n is None:
        return None
    return n / 100.0


# ── 입력 ──────────────────────────────────────────────────────────
SUPABASE_URL = input("Supabase URL을 입력하세요: ").strip().rstrip("/")
SUPABASE_KEY = input("Supabase anon key를 입력하세요: ").strip()
CSV_FILE = input("CSV 파일 경로 (기본: portfolio_export.csv): ").strip() or "portfolio_export.csv"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}
HEADERS_UPSERT = {**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"}
HEADERS_RETURN = {**HEADERS, "Prefer": "return=representation"}


def api(path: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{path}"


# ── Supabase 헬퍼 ────────────────────────────────────────────────
def upsert_one(table: str, payload: dict, on_conflict: str) -> dict:
    """단일 행 upsert, 새 행 또는 기존 행 반환 (id 추출용)."""
    resp = requests.post(
        api(table),
        headers=HEADERS_UPSERT,
        params={"on_conflict": on_conflict},
        data=json.dumps(payload),
    )
    resp.raise_for_status()
    data = resp.json()
    return data[0] if isinstance(data, list) and data else data


def select_one(table: str, **filters) -> dict | None:
    params = {f"{k}": f"eq.{v}" for k, v in filters.items()}
    params["limit"] = "1"
    resp = requests.get(api(table), headers=HEADERS, params=params)
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else None


def delete_where(table: str, **filters):
    params = {f"{k}": f"eq.{v}" for k, v in filters.items()}
    resp = requests.delete(api(table), headers=HEADERS, params=params)
    resp.raise_for_status()


def insert_many(table: str, rows: list[dict]):
    if not rows:
        return
    resp = requests.post(api(table), headers=HEADERS, data=json.dumps(rows))
    resp.raise_for_status()


# ── CSV 파싱 ─────────────────────────────────────────────────────
def find_account_blocks(df: pd.DataFrame) -> list[tuple[int, str]]:
    """계좌 블록 시작 행 탐색: col0 non-empty AND col1 empty AND col2 empty."""
    blocks = []
    for i in range(len(df)):
        c0 = str(df.iat[i, 0]).strip()
        c1 = str(df.iat[i, 1]).strip()
        c2 = str(df.iat[i, 2]).strip()
        if c0 and not c1 and not c2:
            blocks.append((i, c0))
    return blocks


def extract_snapshot_dates(row: pd.Series) -> list[tuple[int, date]]:
    """블록 시작 행에서 (col_idx, date) 추출. col 11부터 step 4."""
    out = []
    j = 11
    while j < len(row):
        v = str(row.iloc[j]).strip()
        if DATE_RE.match(v):
            out.append((j, date.fromisoformat(v)))
        j += 4
    return out


def extract_security_rows(df: pd.DataFrame, start_idx: int) -> list[int]:
    """헤더(start_idx+1) 다음 행부터 종목 행 인덱스 수집. col0과 col1 모두 비어있지 않은 행만."""
    out = []
    k = start_idx + 2
    while k < len(df):
        c0 = str(df.iat[k, 0]).strip()
        c1 = str(df.iat[k, 1]).strip()
        if c0 and c1:
            out.append(k)
            k += 1
        else:
            break
    return out


# ── 메인 ─────────────────────────────────────────────────────────
def main():
    print(f"\nCSV 읽는 중: {CSV_FILE}")
    try:
        df = pd.read_csv(CSV_FILE, encoding="utf-8-sig", header=None, dtype=str, keep_default_na=False)
    except UnicodeDecodeError:
        df = pd.read_csv(CSV_FILE, encoding="cp949", header=None, dtype=str, keep_default_na=False)
    print(f"  shape={df.shape}")

    blocks = find_account_blocks(df)
    print(f"  계좌 블록 {len(blocks)}개 발견: {[name for _, name in blocks]}\n")

    securities_seen: dict[str, str] = {}   # code -> name (마지막에 등장한 이름이 우선)
    snapshot_count = 0
    item_count = 0

    for block_idx, account_name in blocks:
        print(f"── 계좌: {account_name} ──")
        try:
            account = upsert_one("pf_accounts", {"name": account_name}, on_conflict="name")
            account_id = account["id"]
        except requests.HTTPError as e:
            print(f"  계좌 upsert 실패: {e.response.text[:200]}")
            continue

        block_start_row = df.iloc[block_idx]
        date_cols = extract_snapshot_dates(block_start_row)
        sec_rows = extract_security_rows(df, block_idx)
        print(f"  종목 {len(sec_rows)}개, 스냅샷 {len(date_cols)}개")

        # 종목/타겟 비중 적재
        sec_id_by_code: dict[str, int] = {}
        display_order = 0
        for sec_row_idx in sec_rows:
            row = df.iloc[sec_row_idx]
            name = str(row.iloc[0]).strip()
            code = str(row.iloc[1]).strip()
            target_w = parse_pct_as_ratio(row.iloc[2]) or 0.0

            # 종목명 통일: 같은 코드면 가장 최근 등장 이름 우선 (한 번 더 등장 시 덮어쓰기)
            securities_seen[code] = name

            try:
                sec = upsert_one(
                    "pf_securities",
                    {"code": code, "name": name, "market": "KS"},
                    on_conflict="code",
                )
                sec_id = sec["id"]
                sec_id_by_code[code] = sec_id
            except requests.HTTPError as e:
                print(f"    종목 upsert 실패 {code}/{name}: {e.response.text[:200]}")
                continue

            try:
                upsert_one(
                    "pf_account_securities",
                    {
                        "account_id": account_id,
                        "security_id": sec_id,
                        "target_weight": round(target_w, 4),
                        "display_order": display_order,
                    },
                    on_conflict="account_id,security_id",
                )
            except requests.HTTPError as e:
                print(f"    타겟 비중 upsert 실패 {code}: {e.response.text[:200]}")
            display_order += 1

        # 스냅샷 적재
        for col_idx, snap_date in date_cols:
            try:
                snap = upsert_one(
                    "pf_snapshots",
                    {
                        "account_id": account_id,
                        "snapshot_date": snap_date.isoformat(),
                        "cash_balance": 0,
                    },
                    on_conflict="account_id,snapshot_date",
                )
                snapshot_id = snap["id"]
            except requests.HTTPError as e:
                print(f"    스냅샷 upsert 실패 {snap_date}: {e.response.text[:200]}")
                continue

            # 기존 items 삭제 후 재삽입 (멱등)
            delete_where("pf_snapshot_items", snapshot_id=snapshot_id)

            items: list[dict] = []
            for sec_row_idx in sec_rows:
                row = df.iloc[sec_row_idx]
                code = str(row.iloc[1]).strip()
                sec_id = sec_id_by_code.get(code)
                if not sec_id:
                    continue
                # col_idx: 비율, col_idx+1: 평가금액, col_idx+2: 수량
                if col_idx + 2 >= len(row):
                    continue
                value = safe_num(row.iloc[col_idx + 1])
                qty = safe_num(row.iloc[col_idx + 2])
                if not value or not qty or qty <= 0:
                    continue
                price = round(value / qty, 2)
                items.append(
                    {
                        "snapshot_id": snapshot_id,
                        "security_id": sec_id,
                        "quantity": int(qty),
                        "price": price,
                    }
                )

            try:
                insert_many("pf_snapshot_items", items)
                print(f"    {snap_date}: {len(items)} 종목 적재")
                snapshot_count += 1
                item_count += len(items)
            except requests.HTTPError as e:
                print(f"    items insert 실패 {snap_date}: {e.response.text[:200]}")

    print(f"\n완료. 계좌 {len(blocks)}개, 스냅샷 {snapshot_count}개, 종목 행 {item_count}개 적재.")


if __name__ == "__main__":
    main()
