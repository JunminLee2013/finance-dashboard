"""
migrate.py - 구글 스프레드시트 CSV -> Supabase 마이그레이션 스크립트

전략:
  1. CSV에선 raw input(원본 입력 항목)만 읽는다.
  2. derived.calc_derived 로 모든 파생 지표/YTD를 재계산한다.
  3. 재계산 결과를 Supabase에 upsert 한다.
  -> app.py와 동일한 계산식이 보장되고, 컬럼이 추가돼도 derived.py만 고치면 됨.

사용법:
  1. 구글 스프레드시트 -> 파일 -> 다운로드 -> CSV 저장 -> data.csv로 이름 변경
  2. 이 폴더에 data.csv 넣기
  3. pip install pandas requests
  4. python migrate.py
"""

import math
import json
import pandas as pd
import requests

from derived import calc_derived

# ── 설정 ──────────────────────────────────────────────────────────
SUPABASE_URL = input("Supabase URL을 입력하세요: ").strip().rstrip("/")
SUPABASE_KEY = input("Supabase anon key를 입력하세요: ").strip()
CSV_FILE     = input("CSV 파일 경로 (기본: data.csv): ").strip() or "data.csv"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates,return=minimal",
}
API_URL = f"{SUPABASE_URL}/rest/v1/finance_monthly"
print(f"\n접속 URL: {API_URL}\n")

# ── CSV 컬럼 정의 ─────────────────────────────────────────────────
# 실제 CSV 헤더 순서대로 컬럼명 직접 지정 (76개)
# 중복 컬럼은 위치 기반 구분 (평가액, 납입누계, 수익금 등)
CSV_COLUMNS = [
    "날짜",
    "자산_USD", "부채_USD", "순자산_USD",
    "순자산YTD_USD", "순자산YTD_PCT",
    "환율",
    "자산", "부채", "순자산",
    "유동자산", "비유동자산",
    "유동자산_비중", "비유동자산_비중",
    "유동순자산", "유동자산_주담대",
    "금융자산", "실물자산",
    "금융자산_비중", "실물자산_비중",
    "금융순자산", "금융순자산YTD",
    "유동금융자산", "비유동금융자산",
    "현금성자산", "현금성자산_비중",
    "주식", "주식_비중",
    "코인", "코인_비중",
    "준민_현금", "준민_주택청약",
    "은미_현금", "은미_주택청약",
    "준민_주식", "준민_주식_평가액",
    "은미_주식", "은미_주식_평가액",
    "코인_총매수", "코인_현금",
    "부동산",
    "실물자산_ROE", "실물자산_CAGR",
    "실물자산_YTD_KRW", "실물자산_YTD_PCT",
    "금융부채",
    "준민_금융부채", "동금씨_투자금", "은미_금융부채", "카드값",
    "금융부채_증감", "금융부채_증감율",
    "실물부채", "부채총계", "부채_YTD", "부채_비율",
    "순자산2", "순자산_증감", "순자산_YTD", "순자산_YTD_vs자산",
    "교직원공제회",
    "교직원공제회_원금", "교직원공제회_부가금",
    "준민연금저축",
    "준민연금저축_납입누계", "준민연금저축_수익금",
    "은미연금저축",
    "은미연금저축_납입누계", "은미연금저축_수익금",
    "준민IRP",
    "준민IRP_납입누계", "준민IRP_수익금",
    "은미IRP",
    "은미IRP_납입누계", "은미IRP_수익금",
]

# CSV 컬럼 -> DB 컬럼 매핑 (raw input만)
# 파생 지표는 절대 매핑하지 않음 — calc_derived가 모두 재계산함.
RAW_INPUT_MAP = {
    "환율":                     "exchange_rate",
    # 현금성 자산
    "준민_현금":                "jm_cash",
    "준민_주택청약":            "jm_subscription",
    "은미_현금":                "em_cash",
    "은미_주택청약":            "em_subscription",
    # 주식
    "준민_주식":                "jm_stock_value",
    "준민_주식_평가액":         "jm_stock_pnl",
    "은미_주식":                "em_stock_value",
    "은미_주식_평가액":         "em_stock_pnl",
    # 코인
    "코인":                     "coin_assets",
    "코인_총매수":              "coin_total_buy",
    "코인_현금":                "coin_cash",
    # 실물
    "부동산":                   "real_estate",
    # 금융부채
    "준민_금융부채":            "jm_fin_debt",
    "동금씨_투자금":            "donggum_invest",
    "은미_금융부채":            "em_fin_debt",
    "카드값":                   "card_debt",
    # 실물부채
    "실물부채":                 "real_debt",
    # 연금
    "교직원공제회_원금":        "teachers_mutual_principal",
    "교직원공제회_부가금":      "teachers_mutual_bonus",
    "준민연금저축_납입누계":    "jm_pension_principal",
    "준민연금저축_수익금":      "jm_pension_profit",
    "은미연금저축_납입누계":    "em_pension_principal",
    "은미연금저축_수익금":      "em_pension_profit",
    "준민IRP_납입누계":         "jm_irp_principal",
    "준민IRP_수익금":           "jm_irp_profit",
    "은미IRP_납입누계":         "em_irp_principal",
    "은미IRP_수익금":           "em_irp_profit",
}


def safe_num(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        s = str(v).replace(",", "").replace("%", "").replace("$", "").replace("₩", "").strip()
        if s in ("", "-", "—", "N/A", "#N/A", "nan"):
            return None
        # 괄호 음수: (123) -> -123
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]
        return float(s)
    except Exception:
        return None


def parse_date(v):
    try:
        return pd.to_datetime(str(v)).strftime("%Y-%m-%d")
    except Exception:
        return None


# ── CSV 로드 ──────────────────────────────────────────────────────
print(f"CSV 읽는 중: {CSV_FILE}")
try:
    raw = pd.read_csv(CSV_FILE, encoding="utf-8-sig", header=0)
except UnicodeDecodeError:
    raw = pd.read_csv(CSV_FILE, encoding="cp949", header=0)

print(f"  -> {len(raw)}행, {len(raw.columns)}열 발견")

if len(raw.columns) != len(CSV_COLUMNS):
    print(f"  ⚠ 컬럼 수 불일치 (기대 {len(CSV_COLUMNS)}, 실제 {len(raw.columns)}) — 위치 기반 매핑이 어긋날 수 있음")

raw.columns = CSV_COLUMNS[:len(raw.columns)]


# ── 행 → raw input 레코드 추출 ────────────────────────────────────
def extract_raw(row) -> dict:
    rec = {}
    # 날짜
    d = parse_date(row.get("날짜"))
    if not d:
        return {}
    rec["date"] = d
    rec["reference_month"] = d[:7] + "-01"
    # raw input 컬럼들
    for csv_col, db_col in RAW_INPUT_MAP.items():
        if csv_col not in row.index:
            continue
        num = safe_num(row[csv_col])
        if num is not None:
            rec[db_col] = num
    return rec


# ── 처리: 날짜순 정렬 후 누적 df_all 로 YTD 계산 ──────────────────
records = []
for _, row in raw.iterrows():
    rec = extract_raw(row)
    if rec:
        records.append(rec)

records.sort(key=lambda r: r["date"])
print(f"  -> 유효 행: {len(records)}개\n")

print("Supabase 업로드 중...\n")
success, fail = 0, 0
processed_full = []  # 누적 (raw + derived) 레코드 — YTD 기준 계산용

for rec in records:
    # 누적 데이터를 df_all 로 변환 (calc_derived가 reference_month 컬럼 기대)
    df_all = None
    if processed_full:
        df_all = pd.DataFrame(processed_full)
        df_all["reference_month"] = pd.to_datetime(df_all["reference_month"])

    derived = calc_derived(rec, df_all)
    full = {**rec, **derived}

    resp = requests.post(
        API_URL,
        headers=HEADERS,
        data=json.dumps(full),
        params={"on_conflict": "date"},
    )

    if resp.status_code in (200, 201, 204):
        print(f"  OK {rec['date']}")
        success += 1
        processed_full.append(full)
    else:
        print(f"  FAIL {rec['date']}: {resp.status_code} {resp.text[:200]}")
        fail += 1

print(f"\n완료! 성공: {success}건 / 실패: {fail}건")
