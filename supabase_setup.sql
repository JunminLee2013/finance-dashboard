-- ================================================================
-- 재무 대시보드 Supabase 테이블 생성 SQL
-- Supabase → SQL Editor 에 붙여넣고 실행하세요
-- ================================================================

CREATE TABLE IF NOT EXISTS finance_monthly (
    id                      BIGSERIAL PRIMARY KEY,
    created_at              TIMESTAMPTZ DEFAULT NOW(),

    -- 날짜
    date                    DATE NOT NULL UNIQUE,

    -- 환율
    exchange_rate           NUMERIC,

    -- 원본 입력 항목: 현금성 자산
    jm_cash                 NUMERIC DEFAULT 0,   -- 준민 현금
    jm_subscription         NUMERIC DEFAULT 0,   -- 준민 주택청약
    em_cash                 NUMERIC DEFAULT 0,   -- 은미 현금
    em_subscription         NUMERIC DEFAULT 0,   -- 은미 주택청약

    -- 원본 입력 항목: 주식
    jm_stock_book           NUMERIC DEFAULT 0,   -- 준민 주식 (장부가/납입)
    jm_stock_value          NUMERIC DEFAULT 0,   -- 준민 주식 평가액
    em_stock_book           NUMERIC DEFAULT 0,   -- 은미 주식 (장부가/납입)
    em_stock_value          NUMERIC DEFAULT 0,   -- 은미 주식 평가액

    -- 원본 입력 항목: 코인
    coin_total_buy          NUMERIC DEFAULT 0,   -- 코인-총매수
    coin_cash               NUMERIC DEFAULT 0,   -- 코인-현금 (평가액)

    -- 원본 입력 항목: 실물자산
    real_estate             NUMERIC DEFAULT 0,   -- 부동산

    -- 원본 입력 항목: 금융부채
    jm_fin_debt             NUMERIC DEFAULT 0,   -- 준민 금융부채
    donggum_invest          NUMERIC DEFAULT 0,   -- 동금씨 투자금
    em_fin_debt             NUMERIC DEFAULT 0,   -- 은미 금융부채
    card_debt               NUMERIC DEFAULT 0,   -- 카드값

    -- 원본 입력 항목: 실물부채
    real_debt               NUMERIC DEFAULT 0,   -- 실물부채 (주담대)

    -- 연금
    teachers_mutual         NUMERIC DEFAULT 0,   -- 교직원공제회
    teachers_mutual_principal NUMERIC DEFAULT 0, -- 교직원공제회 원금
    teachers_mutual_bonus   NUMERIC DEFAULT 0,   -- 교직원공제회 부가금
    jm_pension_total        NUMERIC DEFAULT 0,   -- 준민연금저축 납입누계
    jm_pension_profit       NUMERIC DEFAULT 0,   -- 준민연금저축 수익금
    em_pension_total        NUMERIC DEFAULT 0,   -- 은미연금저축 납입누계
    em_pension_profit       NUMERIC DEFAULT 0,   -- 은미연금저축 수익금
    jm_irp_total            NUMERIC DEFAULT 0,   -- 준민IRP 납입누계
    jm_irp_profit           NUMERIC DEFAULT 0,   -- 준민IRP 수익금
    em_irp_total            NUMERIC DEFAULT 0,   -- 은미IRP 납입누계
    em_irp_profit           NUMERIC DEFAULT 0,   -- 은미IRP 수익금

    -- ── 파생 지표 (자동 계산, 저장) ──────────────────────────────

    -- 자산
    liquid_assets           NUMERIC,   -- 유동자산 (금융자산)
    illiquid_assets         NUMERIC,   -- 비유동자산 (실물)
    financial_assets        NUMERIC,   -- 금융자산
    real_assets             NUMERIC,   -- 실물자산
    total_assets            NUMERIC,   -- 자산 합계
    total_assets_usd        NUMERIC,   -- 자산(USD)

    -- 현금/주식/코인
    cash_assets             NUMERIC,   -- 현금성 자산
    stock_assets            NUMERIC,   -- 주식 (평가액 합)
    coin_assets             NUMERIC,   -- 코인 (평가액)

    -- 비중
    liquid_ratio            NUMERIC,   -- 유동자산 비중 %
    illiquid_ratio          NUMERIC,   -- 비유동자산 비중 %
    fin_asset_ratio         NUMERIC,   -- 금융자산 비중 %
    real_asset_ratio        NUMERIC,   -- 실물자산 비중 %
    cash_ratio              NUMERIC,   -- 현금성 자산 비중 %
    stock_ratio             NUMERIC,   -- 주식 비중 %
    coin_ratio              NUMERIC,   -- 코인 비중 %

    -- 부채
    fin_debt                NUMERIC,   -- 금융부채 합
    total_debt              NUMERIC,   -- 부채총계
    total_debt_usd          NUMERIC,   -- 부채(USD)
    debt_ratio              NUMERIC,   -- 부채 비율 %

    -- 순자산
    net_assets              NUMERIC,   -- 순자산
    net_assets_usd          NUMERIC,   -- 순자산(USD)
    liquid_net_assets       NUMERIC,   -- 유동순자산
    fin_net_assets          NUMERIC,   -- 금융순자산

    -- YTD (앱에서 계산해서 저장)
    net_assets_ytd_krw      NUMERIC,   -- 순자산YTD(KRW)
    net_assets_ytd_usd      NUMERIC,   -- 순자산YTD(USD)
    net_assets_ytd_pct      NUMERIC,   -- 순자산YTD(%)
    fin_net_assets_ytd      NUMERIC,   -- 금융순자산YTD
    real_asset_ytd          NUMERIC,   -- 실물자산YTD

    -- 연금 합산
    total_pension           NUMERIC    -- 연금 합계
);

-- 날짜 기준 인덱스
CREATE INDEX IF NOT EXISTS idx_finance_monthly_date ON finance_monthly(date DESC);

-- Row Level Security (선택사항 - 비공개 운영 시)
-- ALTER TABLE finance_monthly ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE finance_monthly IS '월별 재무상태표 - 개인 자산/부채 트래킹';
