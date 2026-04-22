"""
migrate.py - 구글 스프레드시트 CSV -> Supabase 마이그레이션 스크립트
supabase 라이브러리 없이 requests만 사용 (버전 충돌 방지)

사용법:
  1. 구글 스프레드시트 -> 파일 -> 다운로드 -> CSV 저장 -> data.csv로 이름 변경
  2. 이 폴더에 data.csv 넣기
  3. pip install pandas requests
  4. python migrate.py
"""

import pandas as pd
import requests
import json
import math

# 설정
SUPABASE_URL = input("Supabase URL을 입력하세요: ").strip().rstrip("/")
SUPABASE_KEY = input("Supabase anon key를 입력하세요: ").strip()
CSV_FILE     = input("CSV 파일 경로 (기본: data.csv): ").strip() or "data.csv"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",
}
API_URL = f"{SUPABASE_URL}/rest/v1/finance_monthly"
print(f"\n접속 URL: {API_URL}\n")

# 컬럼 매핑
COL_MAP = {
    "날짜":           "date",
    "환율":           "exchange_rate",
    "준민 현금":       "jm_cash",
    "준민 주택청약":   "jm_subscription",
    "은미 현금":       "em_cash",
    "은미 주택청약":   "em_subscription",
    "준민 주식":       "jm_stock_book",
    "은미 주식":       "em_stock_book",
    "코인-총매수":     "coin_total_buy",
    "코인-현금":       "coin_cash",
    "부동산":         "real_estate",
    "준민 금융부채":   "jm_fin_debt",
    "동금씨 투자금":   "donggum_invest",
    "은미 금융부채":   "em_fin_debt",
    "카드값":         "card_debt",
    "실물부채":        "real_debt",
    "교직원공제회":    "teachers_mutual",
    "원금":           "teachers_mutual_principal",
    "부가금":         "teachers_mutual_bonus",
    "자산(USD)":      "total_assets_usd",
    "부채(USD)":      "total_debt_usd",
    "순자산(USD)":    "net_assets_usd",
    "순자산YTD(USD)": "net_assets_ytd_usd",
    "순자산YTD(%)":   "net_assets_ytd_pct",
    "자산":           "total_assets",
    "부채":           "total_debt",
    "순자산":         "net_assets",
    "유동자산":        "liquid_assets",
    "비유동자산":      "illiquid_assets",
    "유동자산 비중":   "liquid_ratio",
    "비유동자산 비중": "illiquid_ratio",
    "유동순자산":      "liquid_net_assets",
    "금융자산":        "financial_assets",
    "실물자산":        "real_assets",
    "금융자산 비중":   "fin_asset_ratio",
    "실물자산 비중":   "real_asset_ratio",
    "금융순자산":      "fin_net_assets",
    "금융순자산YTD":   "fin_net_assets_ytd",
    "현금성 자산":     "cash_assets",
    "현금성 자산 비중":"cash_ratio",
    "주식":           "stock_assets",
    "주식 비중":       "stock_ratio",
    "코인":           "coin_assets",
    "코인 비중":       "coin_ratio",
    "금융부채":        "fin_debt",
    "부채 비율":       "debt_ratio",
    "순자산 증감":     "net_assets_ytd_krw",
}

def safe_num(v):
    if v is None: return None
    if isinstance(v, float) and math.isnan(v): return None
    try:
        s = str(v).replace(",", "").replace("%", "").strip()
        if s in ("", "-", "—", "N/A", "#N/A", "nan"): return None
        return float(s)
    except:
        return None

def parse_date(v):
    try:
        return pd.to_datetime(str(v)).strftime("%Y-%m-%d")
    except:
        return None

# CSV 로드
print(f"CSV 읽는 중: {CSV_FILE}")
try:
    raw = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
except UnicodeDecodeError:
    raw = pd.read_csv(CSV_FILE, encoding="cp949")

print(f"  -> {len(raw)}행 발견")

# 중복 컬럼 처리
cols = list(raw.columns)

eval_idx = [i for i, c in enumerate(cols) if c == "평가액"]
if len(eval_idx) >= 1: cols[eval_idx[0]] = "준민 주식 평가액"; COL_MAP["준민 주식 평가액"] = "jm_stock_value"
if len(eval_idx) >= 2: cols[eval_idx[1]] = "은미 주식 평가액"; COL_MAP["은미 주식 평가액"] = "em_stock_value"

cum_idx = [i for i, c in enumerate(cols) if c == "납입누계"]
for i, (ci, ck) in enumerate(zip(cum_idx, ["jm_pension_total","em_pension_total","jm_irp_total","em_irp_total"])):
    name = f"납입누계_{i+1}"; cols[ci] = name; COL_MAP[name] = ck

profit_idx = [i for i, c in enumerate(cols) if c == "수익금"]
for i, (pi, pk) in enumerate(zip(profit_idx, ["jm_pension_profit","em_pension_profit","jm_irp_profit","em_irp_profit"])):
    name = f"수익금_{i+1}"; cols[pi] = name; COL_MAP[name] = pk

raw.columns = cols

# 업로드
print("Supabase 업로드 중...\n")
success, fail = 0, 0

for _, row in raw.iterrows():
    record = {}
    for sheet_col, db_col in COL_MAP.items():
        if sheet_col in row.index:
            val = row[sheet_col]
            if db_col == "date":
                parsed = parse_date(val)
                if parsed: record["date"] = parsed
            else:
                num = safe_num(val)
                if num is not None:
                    record[db_col] = num

    if "date" not in record:
        fail += 1
        continue

    resp = requests.post(
        API_URL,
        headers=HEADERS,
        data=json.dumps(record),
        params={"on_conflict": "date"},
    )

    if resp.status_code in (200, 201):
        print(f"  OK {record['date']}")
        success += 1
    else:
        print(f"  FAIL {record.get('date','?')}: {resp.status_code} {resp.text[:200]}")
        fail += 1

print(f"\n완료! 성공: {success}건 / 실패: {fail}건")
