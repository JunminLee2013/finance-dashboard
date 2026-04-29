-- ================================================================
-- 재무 대시보드 Supabase 테이블 생성 SQL
-- Supabase → SQL Editor 에 붙여넣고 실행하세요
-- (운영 DB 스키마와 동기화: 2026-04)
-- ================================================================

CREATE TABLE IF NOT EXISTS public.finance_monthly (
    id                          BIGSERIAL PRIMARY KEY,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),

    -- 날짜
    date                        DATE NOT NULL UNIQUE,
    reference_month             DATE,                    -- 기준월 (YTD 계산 기준; 해당 월 1일)

    -- 환율
    exchange_rate               NUMERIC,

    -- ── 원본 입력 항목 (raw inputs) ────────────────────────────────
    -- 현금성 자산
    jm_cash                     NUMERIC DEFAULT 0,       -- 준민 현금
    jm_subscription             NUMERIC DEFAULT 0,       -- 준민 주택청약
    em_cash                     NUMERIC DEFAULT 0,       -- 은미 현금
    em_subscription             NUMERIC DEFAULT 0,       -- 은미 주택청약

    -- 주식
    jm_stock_value              NUMERIC DEFAULT 0,       -- 준민 주식 평가액
    jm_stock_pnl                NUMERIC DEFAULT 0,       -- 준민 주식 평가손익
    em_stock_value              NUMERIC DEFAULT 0,       -- 은미 주식 평가액
    em_stock_pnl                NUMERIC DEFAULT 0,       -- 은미 주식 평가손익

    -- 코인
    coin_total_buy              NUMERIC DEFAULT 0,       -- 코인 총매수
    coin_cash                   NUMERIC DEFAULT 0,       -- 코인 현금

    -- 실물자산
    real_estate                 NUMERIC DEFAULT 0,       -- 부동산

    -- 금융부채
    jm_fin_debt                 NUMERIC DEFAULT 0,       -- 준민 금융부채
    donggum_invest              NUMERIC DEFAULT 0,       -- 동금씨 투자금
    em_fin_debt                 NUMERIC DEFAULT 0,       -- 은미 금융부채
    card_debt                   NUMERIC DEFAULT 0,       -- 카드값

    -- 실물부채
    real_debt                   NUMERIC DEFAULT 0,       -- 주담대 등

    -- 연금
    teachers_mutual             NUMERIC DEFAULT 0,       -- 교직원공제회 (원금+부가금 합)
    teachers_mutual_principal   NUMERIC DEFAULT 0,       -- 교직원공제회 원금
    teachers_mutual_bonus       NUMERIC DEFAULT 0,       -- 교직원공제회 부가금
    jm_pension_principal        NUMERIC DEFAULT 0,       -- 준민연금저축 원금
    jm_pension_profit           NUMERIC DEFAULT 0,       -- 준민연금저축 수익금
    em_pension_principal        NUMERIC DEFAULT 0,       -- 은미연금저축 원금
    em_pension_profit           NUMERIC DEFAULT 0,       -- 은미연금저축 수익금
    jm_irp_principal            NUMERIC DEFAULT 0,       -- 준민IRP 원금
    jm_irp_profit               NUMERIC DEFAULT 0,       -- 준민IRP 수익금
    em_irp_principal            NUMERIC DEFAULT 0,       -- 은미IRP 원금
    em_irp_profit               NUMERIC DEFAULT 0,       -- 은미IRP 수익금

    -- ── 파생 지표 (derived.py 에서 자동 계산) ─────────────────────

    -- 자산
    cash_assets                 NUMERIC,                 -- 현금성 자산 합
    stock_assets                NUMERIC,                 -- 주식 평가액 합
    coin_assets                 NUMERIC,                 -- 코인 평가액
    fin_liq_assets              NUMERIC,                 -- 유동금융자산 (현금+주식+코인)
    financial_assets            NUMERIC,                 -- 금융자산 (유동금융자산 + 연금)
    real_assets                 NUMERIC,                 -- 실물자산
    liquid_assets               NUMERIC,                 -- 유동자산 (현금+주식+코인+부동산)
    illiquid_assets             NUMERIC,                 -- 비유동자산 (연금)
    total_assets                NUMERIC,                 -- 자산 합계
    total_assets_usd            NUMERIC,                 -- 자산 합계 (USD)

    -- 비중
    liquid_ratio                NUMERIC,                 -- 유동자산 비중 %
    illiquid_ratio              NUMERIC,                 -- 비유동자산 비중 %
    fin_asset_ratio             NUMERIC,                 -- 금융자산 비중 %
    real_asset_ratio            NUMERIC,                 -- 실물자산 비중 %
    cash_ratio                  NUMERIC,                 -- 현금성 자산 비중 %
    stock_ratio                 NUMERIC,                 -- 주식 비중 %
    coin_ratio                  NUMERIC,                 -- 코인 비중 %

    -- 부채
    fin_debt                    NUMERIC,                 -- 금융부채 합
    total_debt                  NUMERIC,                 -- 부채 총계
    total_debt_usd              NUMERIC,                 -- 부채 총계 (USD)
    debt_ratio                  NUMERIC,                 -- 부채 비율 %

    -- 순자산
    net_assets                  NUMERIC,                 -- 순자산
    net_assets_usd              NUMERIC,                 -- 순자산 (USD)
    liquid_net_assets           NUMERIC,                 -- 유동순자산
    liquid_net_assets_usd       NUMERIC,                 -- 유동순자산 (USD)
    fin_net_assets              NUMERIC,                 -- 금융순자산
    fin_net_assets_usd          NUMERIC,                 -- 금융순자산 (USD)
    fin_net_assets_ytd          NUMERIC,                 -- (legacy) 금융순자산 YTD

    -- 실물자산 수익률
    real_asset_roe              NUMERIC,                 -- 실물자산 ROE %
    real_asset_cagr             NUMERIC,                 -- 실물자산 CAGR %
    real_asset_ytd              NUMERIC,                 -- 실물자산 YTD (KRW)
    real_asset_ytd_pct          NUMERIC,                 -- 실물자산 YTD %

    -- 자산 YTD
    total_assets_krw_ytd        NUMERIC,
    total_assets_usd_ytd        NUMERIC,
    total_assets_krw_ytd_pct    NUMERIC,
    total_assets_usd_ytd_pct    NUMERIC,

    -- 순자산 YTD
    net_assets_krw_ytd          NUMERIC,
    net_assets_usd_ytd          NUMERIC,
    net_on_assets_krw_ytd_pct   NUMERIC,                 -- 순자산 증감 / 연초 자산
    net_on_assets_usd_ytd_pct   NUMERIC,
    net_return_krw_ytd_pct      NUMERIC,                 -- 순자산 증감 / 연초 순자산
    net_return_usd_ytd_pct      NUMERIC,

    -- 금융순자산 YTD
    fin_net_krw_ytd             NUMERIC,
    fin_net_usd_ytd             NUMERIC,
    fin_net_return_krw_ytd_pct  NUMERIC,                 -- / 연초 금융순자산
    fin_net_return_usd_ytd_pct  NUMERIC,
    fin_net_on_fin_krw_ytd_pct  NUMERIC,                 -- / 연초 금융자산
    fin_net_on_fin_usd_ytd_pct  NUMERIC,

    -- 유동순자산 YTD
    liq_net_krw_ytd             NUMERIC,
    liq_net_usd_ytd             NUMERIC,
    liq_net_return_krw_ytd_pct  NUMERIC,                 -- / 연초 유동순자산
    liq_net_return_usd_ytd_pct  NUMERIC,
    liq_net_on_liq_krw_ytd_pct  NUMERIC,                 -- / 연초 유동자산
    liq_net_on_liq_usd_ytd_pct  NUMERIC
);

-- 날짜 기준 인덱스
CREATE INDEX IF NOT EXISTS idx_finance_monthly_date
    ON public.finance_monthly USING btree (date DESC);

-- Row Level Security (선택사항 - 비공개 운영 시)
-- ALTER TABLE public.finance_monthly ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.finance_monthly IS '월별 재무상태표 - 개인 자산/부채 트래킹';
