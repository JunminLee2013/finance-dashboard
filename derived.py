"""
파생 지표 계산 모듈
app.py와 migrate.py에서 공유하는 단일 진실 공급원(SSOT).
"""

import math
from datetime import date
import pandas as pd

# 실물자산 계산 상수 (부동산 갈아타지 않는 한 고정)
_REAL_BUY_PRICE = 916_000_000               # 신규 부동산 취득가
_REAL_EQUITY    = 916_000_000 - 630_000_000 # 투자 자본 = 286,000,000
_REAL_BASE_DATE = date(2021, 11, 13)        # 부동산 기준일


def calc_derived(d: dict, df_all: pd.DataFrame = None) -> dict:
    g = lambda k: float(d.get(k) or 0)

    exr  = g("exchange_rate") or 1300
    cash = g("jm_cash") + g("jm_subscription") + g("em_cash") + g("em_subscription") + g("coin_cash")
    stk  = g("jm_stock_value") + g("em_stock_value")   # 원화평가금액(총액)
    coin = g("coin_assets")
    fin_liq  = cash + stk + coin   # financial_assets = 현금+주식+코인
    real = g("real_estate")

    pension = (g("teachers_mutual_principal") + g("teachers_mutual_bonus") +
               g("jm_pension_principal") + g("jm_pension_profit") +
               g("em_pension_principal") + g("em_pension_profit") +
               g("jm_irp_principal") + g("jm_irp_profit") +
               g("em_irp_principal") + g("em_irp_profit"))

    liquid_a   = fin_liq + real        # 유동자산: 현금+주식+코인+부동산
    fin = fin_liq + pension  # 금융자산; 유동금융자산 + 연금
    illiquid_a = pension            # 비유동자산: 연금
    total_a    = liquid_a + illiquid_a

    fin_debt  = g("jm_fin_debt") + g("donggum_invest") + g("em_fin_debt") + g("jm_card_debt") + g("em_card_debt")
    real_debt = g("real_debt")
    total_d   = fin_debt + real_debt
    net       = total_a - total_d

    # 실물자산 수익률
    real_roe = (real - _REAL_BUY_PRICE) / _REAL_EQUITY if _REAL_EQUITY else 0

    ref_date = None
    try:
        ref_date = pd.to_datetime(d.get("reference_month") or d.get("date")).date()
    except Exception:
        pass
    days_held = (ref_date - _REAL_BASE_DATE).days if ref_date and ref_date > _REAL_BASE_DATE else 0
    real_cagr = ((1 + real_roe) ** (365 / days_held) - 1) if days_held > 0 and real_roe > -1 else 0

    r = {
        "cash_assets":       cash,
        "stock_assets":      stk,
        "coin_assets":       coin,
        "financial_assets":  fin,
        "fin_liq_assets":    fin_liq,
        "real_assets":       real,
        "liquid_assets":     liquid_a,
        "illiquid_assets":   illiquid_a,
        "total_assets":      total_a,
        "total_assets_usd":  round(total_a / exr, 0),
        "fin_debt":          fin_debt,
        "total_debt":        total_d,
        "total_debt_usd":    round(total_d / exr, 0),
        "net_assets":             net,
        "net_assets_usd":         round(net / exr, 0),
        "liquid_net_assets":      liquid_a - total_d,
        "liquid_net_assets_usd":  round((liquid_a - total_d) / exr, 0),
        "fin_net_assets":         fin - total_d,
        "fin_net_assets_usd":     round((fin - total_d) / exr, 0),
        "teachers_mutual":   g("teachers_mutual_principal") + g("teachers_mutual_bonus"),
        "real_asset_roe":    round(real_roe * 100, 2),
        "real_asset_cagr":   round(real_cagr * 100, 2),
        "debt_ratio":        round(total_d / net * 100, 2) if net else 0,
        "liquid_ratio":      round(liquid_a / total_a * 100, 2) if total_a else 0,
        "illiquid_ratio":    round(illiquid_a / total_a * 100, 2) if total_a else 0,
        "fin_asset_ratio":   round(fin / total_a * 100, 2) if total_a else 0,
        "real_asset_ratio":  round(real / total_a * 100, 2) if total_a else 0,
        "cash_ratio":        round(cash / fin_liq * 100, 2) if fin_liq else 0,
        "stock_ratio":       round(stk / fin_liq * 100, 2) if fin_liq else 0,
        "coin_ratio":        round(coin / fin_liq * 100, 2) if fin_liq else 0,
    }

    # YTD 계산: 1월이면 전년도 첫 레코드, 나머지는 당해연도 첫 레코드 기준
    if df_all is not None and not df_all.empty:
        ref_col  = "reference_month" if "reference_month" in df_all.columns else "date"
        ref_val  = pd.to_datetime(d.get("reference_month") or d.get("date"))
        base_yr  = ref_val.year - 1 if ref_val.month == 1 else ref_val.year
        base_df  = df_all[df_all[ref_col].dt.year == base_yr].sort_values(ref_col)
        if not base_df.empty:
            first         = base_df.iloc[0]
            net_start     = float(first["net_assets"])       if pd.notna(first.get("net_assets"))       else net
            net_start_usd = float(first["net_assets_usd"])   if pd.notna(first.get("net_assets_usd"))   else (net_start / exr)
            tot_start     = float(first["total_assets"])     if pd.notna(first.get("total_assets"))     else total_a
            tot_start_usd = float(first["total_assets_usd"]) if pd.notna(first.get("total_assets_usd")) else (tot_start / exr)
            real_start    = float(first["real_assets"])      if pd.notna(first.get("real_assets"))      else real
            fin_net          = fin - total_d
            liq_net          = liquid_a - total_d
            net_usd          = round(net / exr, 0)
            tot_usd          = round(total_a / exr, 0)
            fin_net_usd      = round(fin_net / exr, 0)
            liq_net_usd      = round(liq_net / exr, 0)

            fin_start        = float(first["financial_assets"])      if pd.notna(first.get("financial_assets"))      else fin
            liq_start        = float(first["liquid_assets"])         if pd.notna(first.get("liquid_assets"))         else liquid_a
            fin_net_start    = float(first["fin_net_assets"])        if pd.notna(first.get("fin_net_assets"))        else fin_net
            liq_net_start    = float(first["liquid_net_assets"])     if pd.notna(first.get("liquid_net_assets"))     else liq_net
            base_exr         = float(first.get("exchange_rate") or exr)
            fin_net_start_usd = round(fin_net_start / base_exr, 0)
            liq_net_start_usd = round(liq_net_start / base_exr, 0)
            fin_start_usd    = round(fin_start / base_exr, 0)
            liq_start_usd    = round(liq_start / base_exr, 0)

            # ── 순자산 YTD ──────────────────────────────────────────
            r["net_assets_krw_ytd"]        = net - net_start
            r["net_assets_usd_ytd"]        = round(net_usd - net_start_usd, 0)
            r["total_assets_krw_ytd"]      = total_a - tot_start
            r["total_assets_usd_ytd"]      = round(tot_usd - tot_start_usd, 0)
            r["total_assets_krw_ytd_pct"]  = round((total_a - tot_start) / tot_start * 100, 2)         if tot_start     else 0
            r["total_assets_usd_ytd_pct"]  = round((tot_usd - tot_start_usd) / tot_start_usd * 100, 2) if tot_start_usd else 0
            r["net_on_assets_krw_ytd_pct"] = round((net - net_start) / tot_start * 100, 2)             if tot_start     else 0
            r["net_on_assets_usd_ytd_pct"] = round((net_usd - net_start_usd) / tot_start_usd * 100, 2) if tot_start_usd else 0
            r["net_return_krw_ytd_pct"]    = round((net - net_start) / net_start * 100, 2)             if net_start     else 0
            r["net_return_usd_ytd_pct"]    = round((net_usd - net_start_usd) / net_start_usd * 100, 2) if net_start_usd else 0

            # ── 금융순자산 YTD ──────────────────────────────────────
            r["fin_net_krw_ytd"]             = fin_net - fin_net_start
            r["fin_net_usd_ytd"]             = round(fin_net_usd - fin_net_start_usd, 0)
            r["fin_net_return_krw_ytd_pct"]  = round((fin_net - fin_net_start) / fin_net_start * 100, 2)           if fin_net_start else 0
            r["fin_net_return_usd_ytd_pct"]  = round((fin_net_usd - fin_net_start_usd) / fin_net_start_usd * 100, 2) if fin_net_start_usd else 0
            r["fin_net_on_fin_krw_ytd_pct"]  = round((fin_net - fin_net_start) / fin_start * 100, 2)               if fin_start     else 0
            r["fin_net_on_fin_usd_ytd_pct"]  = round((fin_net_usd - fin_net_start_usd) / fin_start_usd * 100, 2)   if fin_start_usd else 0

            # ── 유동순자산 YTD ──────────────────────────────────────
            r["liq_net_krw_ytd"]             = liq_net - liq_net_start
            r["liq_net_usd_ytd"]             = round(liq_net_usd - liq_net_start_usd, 0)
            r["liq_net_return_krw_ytd_pct"]  = round((liq_net - liq_net_start) / liq_net_start * 100, 2)             if liq_net_start else 0
            r["liq_net_return_usd_ytd_pct"]  = round((liq_net_usd - liq_net_start_usd) / liq_net_start_usd * 100, 2) if liq_net_start_usd else 0
            r["liq_net_on_liq_krw_ytd_pct"]  = round((liq_net - liq_net_start) / liq_start * 100, 2)                if liq_start     else 0
            r["liq_net_on_liq_usd_ytd_pct"]  = round((liq_net_usd - liq_net_start_usd) / liq_start_usd * 100, 2)    if liq_start_usd else 0

            # ── 실물자산 YTD ────────────────────────────────────────
            r["real_asset_ytd"]            = real - real_start
            r["real_asset_ytd_pct"]        = round((real - real_start) / real_start * 100, 2) if real_start else 0

    return r
