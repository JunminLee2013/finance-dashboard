"""
migrate.py - 구글 스프레드시트 CSV -> Supabase 마이그레이션 스크립트

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

# CSV 로드
print(f"CSV 읽는 중: {CSV_FILE}")
try:
    raw = pd.read_csv(CSV_FILE, encoding="utf-8-sig", header=0)
except UnicodeDecodeError:
    raw = pd.read_csv(CSV_FILE, encoding="cp949", header=0)

print(f"  -> {len(raw)}행, {len(raw.columns)}열 발견")

# 실제 CSV 헤더 순서대로 컬럼명 직접 지정
# 중복 컬럼(평가액, 납입누계, 수익금, 은미연금저축 등)을 위치 기반으로 구분
raw.columns = [
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

# DB 컬럼 매핑 (CSV 컬럼명 -> DB 컬럼명)
COL_MAP = {
    "날짜":                   "date",
    "환율":                   "exchange_rate",

    # USD
    "자산_USD":               "total_assets_usd",
    "부채_USD":               "total_debt_usd",
    "순자산_USD":               "net_assets_usd",
    "순자산YTD_USD":           "net_assets_ytd_usd",
    "순자산YTD_PCT":           "net_assets_ytd_pct",

    # 자산/부채/순자산 합계
    "자산":                   "total_assets",
    "부채":                   "total_debt",
    "순자산":                  "net_assets",

    # 유동/비유동
    "유동자산":                "liquid_assets",
    "비유동자산":               "illiquid_assets",
    "유동자산_비중":            "liquid_ratio",
    "비유동자산_비중":           "illiquid_ratio",
    "유동순자산":               "liquid_net_assets",

    # 금융/실물
    "금융자산":                "financial_assets",
    "실물자산":                "real_assets",
    "금융자산_비중":            "fin_asset_ratio",
    "실물자산_비중":            "real_asset_ratio",
    "금융순자산":               "fin_net_assets",
    "금융순자산YTD":            "fin_net_assets_ytd",

    # 현금/주식/코인 합산
    "유동금융자산":             "financial_assets",  # 수정: 유동금융자산(현금+주식+코인)
    "현금성자산":               "cash_assets",
    "현금성자산_비중":           "cash_ratio",
    "주식":                   "stock_assets",
    "주식_비중":               "stock_ratio",
    "코인":                   "coin_assets",
    "코인_비중":               "coin_ratio",

    # 원본 입력값
    "준민_현금":               "jm_cash",
    "준민_주택청약":            "jm_subscription",
    "은미_현금":               "em_cash",
    "은미_주택청약":            "em_subscription",
    "준민_주식":               "jm_stock_book",
    "준민_주식_평가액":          "jm_stock_value",
    "은미_주식":               "em_stock_book",
    "은미_주식_평가액":          "em_stock_value",
    "코인_총매수":              "coin_total_buy",
    "코인_현금":               "coin_cash",
    "부동산":                  "real_estate",

    # 실물자산 수익률
    "실물자산_ROE":            "real_asset_roe",
    "실물자산_CAGR":           "real_asset_cagr",
    "실물자산_YTD_KRW":        "real_asset_ytd",
    "실물자산_YTD_PCT":        "real_asset_ytd_pct",

    # 부채
    "금융부채":                "fin_debt",
    "준민_금융부채":            "jm_fin_debt",
    "동금씨_투자금":            "donggum_invest",
    "은미_금융부채":            "em_fin_debt",
    "카드값":                  "card_debt",
    "실물부채":                "real_debt",
    "부채_비율":               "debt_ratio",

    # 연금
    "교직원공제회":             "teachers_mutual",
    "교직원공제회_원금":         "teachers_mutual_principal",
    "교직원공제회_부가금":        "teachers_mutual_bonus",
    "준민연금저축_납입누계":      "jm_pension_principal",
    "준민연금저축_수익금":        "jm_pension_profit",
    "은미연금저축_납입누계":      "em_pension_principal",
    "은미연금저축_수익금":        "em_pension_profit",
    "준민IRP_납입누계":          "jm_irp_principal",
    "준민IRP_수익금":            "jm_irp_profit",
    "은미IRP_납입누계":          "em_irp_principal",
    "은미IRP_수익금":            "em_irp_profit",
}

def safe_num(v):
    if v is None: return None
    if isinstance(v, float) and math.isnan(v): return None
    try:
        # 달러($), 원화(₩), 쉼표, 퍼센트 기호 제거 및 양옆 공백 제거
        s = str(v).replace(",", "").replace("%", "").replace("$", "").replace("₩", "").strip()

        if s in ("", "-", "—", "N/A", "#N/A", "nan"): return None

        # 괄호로 묶인 음수 처리: (123) -> -123
        if s.startswith("(") and s.endswith(")"):
            s = "-" + s[1:-1]

        return float(s)
    except:
        return None

def parse_date(v):
    try:
        return pd.to_datetime(str(v)).strftime("%Y-%m-%d")
    except:
        return None

# 업로드
print("Supabase 업로드 중...\n")
success, fail = 0, 0

for _, row in raw.iterrows():
    record = {}
    for csv_col, db_col in COL_MAP.items():
        if csv_col not in row.index:
            continue
        val = row[csv_col]
        if db_col == "date":
            parsed = parse_date(val)
            if parsed:
                record["date"] = parsed
                # reference_month = 해당 월의 1일 (YTD 기준월)
                record["reference_month"] = parsed[:7] + "-01"
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