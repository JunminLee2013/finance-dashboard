import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from supabase import create_client, Client
from datetime import datetime, date
import math

def require_auth():
    if st.session_state.get("authenticated"):
        return
    st.markdown("### 🔒 이 페이지는 로그인이 필요합니다")
    pw = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
    if st.button("로그인", use_container_width=True):
        if pw == st.secrets["APP_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다")
    st.stop()


# ── 페이지 설정 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="재무 대시보드!",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 스타일 ────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background: #f6f8fa; color: #24292f; }
[data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #d0d7de; }

.metric-card {
    background: #ffffff; border: 1px solid #d0d7de; border-radius: 12px;
    padding: 18px 20px; position: relative; overflow: hidden; margin-bottom: 4px;
}
.metric-card::before {
    content:''; position:absolute; top:0; left:0; right:0; height:3px;
    background: linear-gradient(90deg,#1a7f37,#2da44e);
}
.metric-card.red::before  { background: linear-gradient(90deg,#cf222e,#fa4549); }
.metric-card.blue::before { background: linear-gradient(90deg,#0550ae,#0969da); }
.metric-card.gold::before { background: linear-gradient(90deg,#7d4e00,#bf8700); }
.metric-card.gray::before { background: linear-gradient(90deg,#57606a,#8c959f); }

.metric-label { font-size:11px; color:#57606a; letter-spacing:.08em; text-transform:uppercase; margin-bottom:6px; }
.metric-value { font-family:'Space Mono',monospace; font-size:22px; font-weight:700; color:#24292f; line-height:1; }
.metric-sub   { font-size:11px; color:#57606a; margin-top:5px; }
.metric-delta { font-size:12px; margin-top:4px; font-family:'Space Mono',monospace; }
.dp { color:#1a7f37; } .dn { color:#cf222e; }

.sec { font-size:12px; font-weight:500; color:#57606a; text-transform:uppercase;
       letter-spacing:.1em; padding:14px 0 8px; border-bottom:1px solid #d0d7de; margin-bottom:14px; }

div[data-testid="stForm"] { background:#ffffff; border:1px solid #d0d7de; border-radius:12px; padding:20px; }
.stButton>button { background:#1a7f37!important; color:white!important; border:none!important;
                   border-radius:6px!important; font-weight:500!important; width:100%; }
.stButton>button:hover { background:#2da44e!important; }
.stTabs [data-baseweb="tab-list"] { background:transparent; border-bottom:1px solid #d0d7de; }
.stTabs [data-baseweb="tab"] { color:#57606a; background:transparent; border:none; padding:8px 18px; font-size:14px; }
.stTabs [aria-selected="true"] { color:#24292f!important; border-bottom:2px solid #1a7f37!important; }
.stNumberInput input, .stTextInput input, .stDateInput input {
    background:#ffffff!important; border:1px solid #d0d7de!important; color:#24292f!important; border-radius:6px!important;
}
h1,h2,h3 { color:#24292f!important; }
</style>
""", unsafe_allow_html=True)

# ── Supabase 연결 ─────────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

# ── 데이터 로드 ───────────────────────────────────────────────────
@st.cache_data(ttl=120)
def load_data() -> pd.DataFrame:
    sb = get_supabase()
    res = sb.table("finance_monthly").select("*").order("date", desc=False).execute()
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df["date"] = pd.to_datetime(df["date"])
    if "reference_month" in df.columns:
        df["reference_month"] = pd.to_datetime(df["reference_month"])
    num_cols = df.columns.difference(["id", "created_at", "date", "reference_month"])
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")
    return df

def save_row(record: dict):
    sb = get_supabase()
    sb.table("finance_monthly").upsert(record, on_conflict="date").execute()
    st.cache_data.clear()

def delete_row(row_id: int):
    sb = get_supabase()
    sb.table("finance_monthly").delete().eq("id", row_id).execute()
    st.cache_data.clear()

# ── 파생 지표 계산 ────────────────────────────────────────────────
# 실물자산 계산 상수 (부동산 갈아타지 않는 한 고정)
_REAL_BUY_PRICE = 916_000_000            # 신규 부동산 취득가
_REAL_EQUITY    = 916_000_000 - 630_000_000   # 투자 자본 = 286,000,000
_REAL_BASE_DATE = date(2021, 11, 13)     # 부동산 기준일

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

    fin_debt  = g("jm_fin_debt") + g("donggum_invest") + g("em_fin_debt") + g("card_debt")
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

# ── 포맷 헬퍼 ─────────────────────────────────────────────────────
def fmt_krw(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "—"
    if abs(v) >= 1e8: return f"₩{v/1e8:.1f}억"
    if abs(v) >= 1e4: return f"₩{v/1e4:.0f}만"
    return f"₩{v:,.0f}"

def fmt_usd(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "—"
    if abs(v) >= 1e6: return f"${v/1e6:.2f}M"
    return f"${v:,.0f}"

def fmt_pct(v):
    if v is None or (isinstance(v, float) and math.isnan(v)): return "—"
    return f"{v:+.1f}%" if v != 0 else "0.0%"

def delta_span(v, is_pct=False):
    if v is None or (isinstance(v, float) and math.isnan(v)): return ""
    fmt = f"{v:+.1f}%" if is_pct else fmt_krw(v)
    cls = "dp" if v >= 0 else "dn"
    arrow = "▲" if v >= 0 else "▼"
    return f'<span class="{cls}">{arrow} {fmt}</span>'

def card(label, val, sub="", delta=None, delta_pct=None, color="green"):
    d = ""
    if delta is not None: d += delta_span(delta)
    if delta_pct is not None: d += f" &nbsp;{delta_span(delta_pct, True)}"
    cc = {"green":"metric-card","red":"metric-card red","blue":"metric-card blue",
          "gold":"metric-card gold","gray":"metric-card gray"}.get(color,"metric-card")
    st.markdown(f"""
    <div class="{cc}">
      <div class="metric-label">{label}</div>
      <div class="metric-value">{val}</div>
      {'<div class="metric-sub">'+sub+'</div>' if sub else ''}
      {'<div class="metric-delta">'+d+'</div>' if d else ''}
    </div>""", unsafe_allow_html=True)

LAYOUT = dict(
    paper_bgcolor="#ffffff", plot_bgcolor="#f6f8fa",
    font=dict(color="#57606a", family="Noto Sans KR"),
    xaxis=dict(gridcolor="#d0d7de", linecolor="#d0d7de"),
    yaxis=dict(gridcolor="#d0d7de", linecolor="#d0d7de"),
    legend=dict(bgcolor="#ffffff", bordercolor="#d0d7de", borderwidth=1),
    margin=dict(l=0, r=0, t=40, b=0), hovermode="x unified",
)

def _add_markers(fig):
    fig.update_traces(mode="lines+markers", marker=dict(size=5),
                      selector=dict(type="scatter"))
    return fig

@st.cache_data(ttl=3600)
def fetch_exchange_rate():
    try:
        import urllib.request, json as _json
        with urllib.request.urlopen("https://open.er-api.com/v6/latest/USD", timeout=5) as r:
            data = _json.loads(r.read())
            if data.get("result") == "success":
                return round(data["rates"]["KRW"])
    except Exception:
        pass
    return None

# ── 사이드바 ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 💰 재무 대시보드!")
    st.markdown("---")
    page = st.radio("메뉴", ["📊 대시보드", "📝 데이터 입력", "📋 데이터 관리", "📈 상세 분석"],
                    label_visibility="collapsed")
    st.markdown("---")
    if st.button("🔄 새로고침"):
        st.cache_data.clear(); st.rerun()
    st.markdown(f"<div style='color:#57606a;font-size:11px'>{datetime.now().strftime('%Y-%m-%d %H:%M')} 기준</div>",
                unsafe_allow_html=True)

df = load_data()

# ══════════════════════════════════════════════════════════════════
# 📊 대시보드
# ══════════════════════════════════════════════════════════════════
if page == "📊 대시보드":
    st.markdown("# 재무 현황")

    if df.empty:
        st.info("데이터가 없습니다. '데이터 입력' 탭에서 추가해주세요.")
        st.stop()

    latest = df.iloc[-1]

    st.markdown(f"<div style='color:#57606a;font-size:13px;margin-bottom:20px'>"
                f"📅 최신: <b style='color:#24292f'>{latest['date'].strftime('%Y년 %m월')}</b>"
                f" &nbsp;|&nbsp; 총 {len(df)}개월 기록</div>", unsafe_allow_html=True)

    # YTD 성과
    st.markdown('<div class="sec">YTD 성과</div>', unsafe_allow_html=True)
    def _ytd(col):
        v = latest.get(col)
        return v if v is not None and not (isinstance(v, float) and math.isnan(v)) else None
    def _ser(c): return df[c] if c in df.columns else pd.Series(dtype=float)

    # 요약 카드 — 자산 대비 % 기준
    cy1, cy2, cy3 = st.columns(3)
    with cy1:
        st.markdown("**순자산** (연초 자산 대비)")
        ca, cb = st.columns(2)
        ca.metric("₩", fmt_pct(_ytd("net_on_assets_krw_ytd_pct")))
        cb.metric("$", fmt_pct(_ytd("net_on_assets_usd_ytd_pct")))
    with cy2:
        st.markdown("**금융순자산** (연초 금융자산 대비)")
        ca, cb = st.columns(2)
        ca.metric("₩", fmt_pct(_ytd("fin_net_on_fin_krw_ytd_pct")))
        cb.metric("$", fmt_pct(_ytd("fin_net_on_fin_usd_ytd_pct")))
    with cy3:
        st.markdown("**유동순자산** (연초 유동자산 대비)")
        ca, cb = st.columns(2)
        ca.metric("₩", fmt_pct(_ytd("liq_net_on_liq_krw_ytd_pct")))
        cb.metric("$", fmt_pct(_ytd("liq_net_on_liq_usd_ytd_pct")))

    st.markdown("<br>", unsafe_allow_html=True)

    # 3열 토글 차트
    ch1, ch2, ch3 = st.columns(3)
    _ref_col = "reference_month" if "reference_month" in df.columns and df["reference_month"].notna().any() else "date"
    # 1월 데이터는 전년도 그룹으로 (YTD 계산 기준과 동일)
    _disp_yr = df[_ref_col].dt.year.where(df[_ref_col].dt.month != 1, df[_ref_col].dt.year - 1)
    _year_palette = ["#0969da", "#1a7f37", "#bf8700", "#8250df", "#cf222e", "#57606a"]

    # 통계청 가계금융복지조사 순자산 분위 경계값 (lbl, 2024값원, 2025값원, color)
    _NET_THR = [
        ("상위 50%", 240_000_000,   238_600_000,   "#aaaaaa"),
        ("상위 40%", 328_380_000,   330_500_000,   "#999999"),
        ("상위 30%", 453_560_000,   461_800_000,   "#bf8700"),
        ("상위 20%", 664_500_000,   693_800_000,   "#0969da"),
        ("상위 10%", 1_045_920_000, 1_100_200_000, "#8250df"),
    ]

    def _ytd_chart(col, title, ret_krw, ret_usd, on_krw, on_usd, key, thresholds=None,
                   base_net_col="net_assets", base_tot_col="total_assets"):
        with col:
            mode = st.radio("기준", ["연초 자산 대비", "연초 순자산 대비"],
                            horizontal=True, label_visibility="collapsed", key=key)
            is_asset_base = (mode == "연초 자산 대비")
            krw_col = on_krw if is_asset_base else ret_krw
            usd_col = on_usd if is_asset_base else ret_usd
            fig = go.Figure()
            years = sorted(_disp_yr.dropna().unique().astype(int))
            for i, yr in enumerate(years):
                clr = _year_palette[i % len(_year_palette)]
                mask = _disp_yr == yr
                yr_df = df[mask]
                if krw_col in df.columns and yr_df[krw_col].notna().any():
                    fig.add_trace(go.Scatter(
                        x=yr_df["date"], y=yr_df[krw_col], name=f"{yr}₩",
                        line=dict(color=clr, width=2)))
                if usd_col in df.columns and yr_df[usd_col].notna().any():
                    fig.add_trace(go.Scatter(
                        x=yr_df["date"], y=yr_df[usd_col], name=f"{yr}$",
                        line=dict(color=clr, width=1.5, dash="dash")))

            if thresholds:
                for yr in years:
                    # 연도별 YTD 기준값: 해당 캘린더 연도의 첫 번째 레코드
                    base_df = df[df[_ref_col].dt.year == yr].sort_values(_ref_col)
                    if base_df.empty:
                        continue
                    base     = base_df.iloc[0]
                    net_s    = float(base.get(base_net_col) or 0)
                    tot_s    = float(base.get(base_tot_col) or 0)
                    mask     = _disp_yr == yr
                    yr_df    = df[mask]
                    if yr_df.empty:
                        continue
                    xs, xe = yr_df["date"].min(), yr_df["date"].max()
                    for lbl, v24, v25, clr in thresholds:
                        thr = v24 if yr <= 2024 else v25
                        denom = tot_s if is_asset_base else net_s
                        if not denom:
                            continue
                        pct = (thr - net_s) / denom * 100
                        is_last = (yr == max(years))
                        fig.add_trace(go.Scatter(
                            x=[xs, xe], y=[pct, pct],
                            mode="lines",
                            line=dict(color=clr, width=1, dash="dot"),
                            showlegend=False,
                            hovertemplate=f"{lbl} ({yr}): {pct:.1f}%<extra></extra>",
                        ))
                        if is_last:
                            fig.add_annotation(
                                x=1, xref="paper", y=pct, yref="y",
                                text=lbl, showarrow=False,
                                xanchor="right", font=dict(size=9, color=clr),
                            )

            fig.update_layout(**LAYOUT, title=title, yaxis_title="%")
            fig.update_layout(margin=dict(l=0, r=0, t=40, b=60),
                              legend=dict(orientation="h", yanchor="top", y=-0.18, x=0))
            st.plotly_chart(_add_markers(fig), use_container_width=True, key=f"ytd_{key}")

    _ytd_chart(ch1, "순자산 YTD (%)",
               "net_return_krw_ytd_pct",    "net_return_usd_ytd_pct",
               "net_on_assets_krw_ytd_pct", "net_on_assets_usd_ytd_pct",
               key="ytd_net")
    _ytd_chart(ch2, "금융순자산 YTD (%)",
               "fin_net_return_krw_ytd_pct",  "fin_net_return_usd_ytd_pct",
               "fin_net_on_fin_krw_ytd_pct",  "fin_net_on_fin_usd_ytd_pct",
               key="ytd_fin")
    _ytd_chart(ch3, "유동순자산 YTD (%)",
               "liq_net_return_krw_ytd_pct",  "liq_net_return_usd_ytd_pct",
               "liq_net_on_liq_krw_ytd_pct",  "liq_net_on_liq_usd_ytd_pct",
               key="ytd_liq")

# ══════════════════════════════════════════════════════════════════
# 📝 데이터 입력
# ══════════════════════════════════════════════════════════════════
elif page == "📝 데이터 입력":
    require_auth()
    st.markdown("# 월별 데이터 입력")
    st.markdown("<div style='color:#57606a;font-size:13px;margin-bottom:24px'>"
                "매월 말 기준 데이터를 입력하세요. 파생 지표는 자동 계산됩니다.</div>",
                unsafe_allow_html=True)

    # 마지막 행으로 기본값
    last = df.iloc[-1].to_dict() if not df.empty else {}
    def dv(k, fallback=0.0):
        v = last.get(k)
        if v is None or (isinstance(v, float) and math.isnan(v)): return float(fallback)
        return float(v)

    GROUPS = [
        ("💵 현금성 자산", [
            ("jm_cash",        "num", dv("jm_cash")),
            ("jm_subscription","num", dv("jm_subscription")),
            ("em_cash",        "num", dv("em_cash")),
            ("em_subscription","num", dv("em_subscription")),
        ]),
        ("📈 주식", [
            ("jm_stock_value", "num", dv("jm_stock_value")),
            ("jm_stock_pnl",   "num", dv("jm_stock_pnl")),
            ("em_stock_value", "num", dv("em_stock_value")),
            ("em_stock_pnl",   "num", dv("em_stock_pnl")),
        ]),
        ("🪙 코인", [
            ("coin_total_buy", "num", dv("coin_total_buy")),
            ("coin_assets",    "num", dv("coin_assets")),
            ("coin_cash",      "num", dv("coin_cash")),
        ]),
        ("🏠 실물자산", [
            ("real_estate",    "num", dv("real_estate")),
        ]),
        ("💳 금융부채", [
            ("jm_fin_debt",    "num", dv("jm_fin_debt")),
            ("donggum_invest", "num", dv("donggum_invest")),
            ("em_fin_debt",    "num", dv("em_fin_debt")),
            ("card_debt",      "num", dv("card_debt")),
        ]),
        ("🏦 실물부채 (주담대)", [
            ("real_debt",      "num", dv("real_debt")),
        ]),
        ("🎯 연금", [
            ("teachers_mutual_principal", "num", dv("teachers_mutual_principal")),
            ("teachers_mutual_bonus",     "num", dv("teachers_mutual_bonus")),
            ("jm_pension_principal",      "num", dv("jm_pension_principal")),
            ("jm_pension_profit",         "num", dv("jm_pension_profit")),
            ("em_pension_principal",      "num", dv("em_pension_principal")),
            ("em_pension_profit",         "num", dv("em_pension_profit")),
            ("jm_irp_principal",          "num", dv("jm_irp_principal")),
            ("jm_irp_profit",             "num", dv("jm_irp_profit")),
            ("em_irp_principal",          "num", dv("em_irp_principal")),
            ("em_irp_profit",             "num", dv("em_irp_profit")),
        ]),
    ]

    LABELS = {
        "reference_month":"기준월","date":"기록일","exchange_rate":"환율 (₩/$)",
        "jm_cash":"준민 현금","jm_subscription":"준민 주택청약",
        "em_cash":"은미 현금","em_subscription":"은미 주택청약",
        "jm_stock_value":"준민 주식 원화평가금액","jm_stock_pnl":"준민 주식 원화평가손익",
        "em_stock_value":"은미 주식 원화평가금액","em_stock_pnl":"은미 주식 원화평가손익",
        "coin_total_buy":"코인 총매수","coin_assets":"코인 총평가","coin_cash":"코인 현금",
        "real_estate":"부동산",
        "jm_fin_debt":"준민 금융부채","donggum_invest":"동금씨 투자금",
        "em_fin_debt":"은미 금융부채","card_debt":"카드값",
        "real_debt":"실물부채 (주담대)",
        "teachers_mutual":"교직원공제회","teachers_mutual_principal":"└ 원금",
        "teachers_mutual_bonus":"└ 부가금",
        "jm_pension_principal":"준민연금저축 원금","jm_pension_profit":"└ 수익금",
        "em_pension_principal":"은미연금저축 원금","em_pension_profit":"└ 수익금",
        "jm_irp_principal":"준민IRP 원금","jm_irp_profit":"└ 수익금",
        "em_irp_principal":"은미IRP 원금","em_irp_profit":"└ 수익금",
    }

    auto_exr = fetch_exchange_rate()

    inp = {}

    # ─── 기본 정보 ───────────────────────────────────────────
    st.markdown("### 📅 기본 정보")
    _last_ref = last.get("reference_month")
    _def_ref  = (pd.to_datetime(_last_ref) + pd.DateOffset(months=1)
                 if _last_ref and pd.notna(_last_ref)
                 else pd.to_datetime(date.today()))
    _years    = list(range(2020, date.today().year + 2))
    ci1, ci2, ci3 = st.columns(3)
    sel_year  = ci1.selectbox("기준 연도", _years, index=_years.index(_def_ref.year))
    sel_month = ci2.selectbox("기준 월", range(1, 13), index=_def_ref.month - 1,
                              format_func=lambda m: f"{m}월")
    inp["reference_month"] = f"{sel_year}-{sel_month:02d}-01"
    inp["date"]            = date.today().strftime("%Y-%m-%d")
    _exr_label   = "환율 (₩/$) 🔄자동" if auto_exr else "환율 (₩/$)"
    _exr_default = float(auto_exr) if auto_exr else dv("exchange_rate", 1300)
    inp["exchange_rate"] = ci3.number_input(_exr_label, value=_exr_default, step=1.0, format="%g")

    # ─── 나머지 항목 ─────────────────────────────────────────
    for group_name, fields in GROUPS:
        st.markdown(f"### {group_name}")
        ncols = min(len(fields), 4)
        cols  = st.columns(ncols)
        for i, (key, _, default) in enumerate(fields):
            with cols[i % ncols]:
                inp[key] = st.number_input(LABELS.get(key, key), value=default, step=10000.0, format="%g")
                delta = inp[key] - dv(key)
                if delta != 0:
                    color = "#1a7f37" if delta >= 0 else "#cf222e"
                    sign  = "+" if delta > 0 else ""
                    st.markdown(
                        f"<div style='color:{color};font-size:11px;margin-top:-14px'>"
                        f"{sign}{fmt_krw(delta)}</div>",
                        unsafe_allow_html=True,
                    )

    # 미리보기
    st.markdown("---")
    st.markdown("#### 🔢 자동 계산 미리보기")
    derived = calc_derived(inp, df)
    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    r1c1.metric("총 자산",    fmt_krw(derived["total_assets"]),  f"USD {fmt_usd(derived['total_assets_usd'])}")
    r1c2.metric("총 부채",    fmt_krw(derived["total_debt"]))
    r1c3.metric("순자산",     fmt_krw(derived["net_assets"]),    f"USD {fmt_usd(derived['net_assets_usd'])}")
    r1c4.metric("부채 비율",  fmt_pct(derived["debt_ratio"]))
    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    r2c1.metric("금융순자산", fmt_krw(derived.get("fin_net_assets", 0)))
    r2c2.metric("유동순자산", fmt_krw(derived.get("liquid_net_assets", 0)))
    _ytd_krw = derived.get("net_assets_krw_ytd")
    _ytd_pct = derived.get("net_on_assets_krw_ytd_pct")
    r2c3.metric("순자산 YTD", fmt_krw(_ytd_krw) if _ytd_krw is not None else "—")
    r2c4.metric("순자산 YTD %", fmt_pct(_ytd_pct) if _ytd_pct is not None else "—")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("✅ 저장하기", use_container_width=True):
        full = {**inp, **derived}
        try:
            save_row(full)
            st.success(f"✅ {inp['reference_month'][:7]} 데이터가 저장됐습니다!")
            st.balloons()
        except Exception as e:
            st.error(f"저장 실패: {e}")

# ══════════════════════════════════════════════════════════════════
# 📋 데이터 관리
# ══════════════════════════════════════════════════════════════════
elif page == "📋 데이터 관리":
    require_auth()
    st.markdown("# 데이터 관리")
    if df.empty:
        st.info("저장된 데이터가 없습니다."); st.stop()

    tab_sum, tab_raw, tab_all = st.tabs(["📊 요약", "📝 원본 입력", "🗂️ 전체 데이터"])

    with tab_sum:
        disp = df[["id","date","total_assets","total_debt","net_assets",
                   "financial_assets","real_assets","cash_assets","stock_assets",
                   "coin_assets","debt_ratio","exchange_rate"]].copy()
        disp["date"] = disp["date"].dt.strftime("%Y-%m")
        for c in disp.columns:
            if c in ("id","date"): continue
            if "ratio" in c or "pct" in c:
                disp[c] = disp[c].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "—")
            elif c == "exchange_rate":
                disp[c] = disp[c].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
            else:
                disp[c] = disp[c].apply(fmt_krw)
        disp.columns = ["ID","날짜","자산","부채","순자산","금융자산","실물자산","현금성","주식","코인","부채비율","환율"]
        st.dataframe(disp.iloc[::-1], use_container_width=True, hide_index=True)

    with tab_raw:
        RAW_COLS = {
            "id": "ID", "reference_month": "기준월", "date": "기록일",
            "jm_cash": "준민현금", "jm_subscription": "준민청약",
            "em_cash": "은미현금", "em_subscription": "은미청약",
            "jm_stock_value": "준민주식(장부)", "jm_stock_pnl": "준민주식(평가)",
            "em_stock_value": "은미주식(장부)", "em_stock_pnl": "은미주식(평가)",
            "coin_total_buy": "코인총매수", "coin_assets": "코인총평가", "coin_cash": "코인현금",
            "real_estate": "부동산", "exchange_rate": "환율",
            "jm_fin_debt": "준민금융부채", "donggum_invest": "동금씨투자금",
            "em_fin_debt": "은미금융부채", "card_debt": "카드값", "real_debt": "실물부채",
            "teachers_mutual": "교직원공제회", "teachers_mutual_principal": "공제회원금",
            "teachers_mutual_bonus": "공제회부가금",
            "jm_pension_principal": "준민연금원금", "jm_pension_profit": "준민연금수익",
            "em_pension_principal": "은미연금원금", "em_pension_profit": "은미연금수익",
            "jm_irp_principal": "준민IRP원금", "jm_irp_profit": "준민IRP수익",
            "em_irp_principal": "은미IRP원금", "em_irp_profit": "은미IRP수익",
        }
        existing = [c for c in RAW_COLS if c in df.columns]
        raw = df[existing].copy()
        raw["date"] = raw["date"].dt.strftime("%Y-%m-%d")
        if "reference_month" in raw.columns:
            raw["reference_month"] = raw["reference_month"].dt.strftime("%Y-%m")
        for c in raw.columns:
            if c in ("id","date","reference_month"): continue
            if c == "exchange_rate":
                raw[c] = raw[c].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "—")
            else:
                raw[c] = raw[c].apply(fmt_krw)
        raw.columns = [RAW_COLS[c] for c in existing]
        st.dataframe(raw.iloc[::-1], use_container_width=True, hide_index=True)

    with tab_all:
        all_disp = df.copy()
        all_disp["date"] = all_disp["date"].dt.strftime("%Y-%m")
        st.dataframe(all_disp.iloc[::-1], use_container_width=True, hide_index=True)

    st.markdown("---")
    c1, c2 = st.columns([3, 1])
    with c1:
        csv = df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📥 CSV 다운로드", csv,
            f"재무데이터_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")
    with c2:
        del_id = st.number_input("삭제할 ID", min_value=1, step=1, value=1)
        if st.button("🗑️ 삭제"):
            delete_row(int(del_id))
            st.success(f"ID {del_id} 삭제 완료"); st.rerun()

# ══════════════════════════════════════════════════════════════════
# 📈 상세 분석
# ══════════════════════════════════════════════════════════════════
elif page == "📈 상세 분석":
    require_auth()
    st.markdown("# 상세 분석")
    if df.empty or len(df) < 2:
        st.info("최소 2개월 이상의 데이터가 필요합니다."); st.stop()

    latest = df.iloc[-1]
    prev   = df.iloc[-2] if len(df) > 1 else None
    _ref_col = "reference_month" if "reference_month" in df.columns and df["reference_month"].notna().any() else "date"

    # 핵심 지표
    st.markdown('<div class="sec">핵심 지표</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        d = latest["net_assets"] - prev["net_assets"] if prev is not None else None
        card("순자산", fmt_krw(latest["net_assets"]),
             sub=f"USD {fmt_usd(latest['net_assets_usd'])}", delta=d, color="green")
    with c2:
        d = latest["total_assets"] - prev["total_assets"] if prev is not None else None
        card("총 자산", fmt_krw(latest["total_assets"]),
             sub=f"USD {fmt_usd(latest['total_assets_usd'])}", delta=d, color="blue")
    with c3:
        d = latest["total_debt"] - prev["total_debt"] if prev is not None else None
        card("총 부채", fmt_krw(latest["total_debt"]),
             sub=f"부채비율 {fmt_pct(latest['debt_ratio'])}", delta=d, color="red")
    with c4:
        card("환율", f"₩{latest.get('exchange_rate', 0):,.0f}", sub="원/달러", color="gray")

    st.markdown("<br>", unsafe_allow_html=True)

    # 자산 구성
    st.markdown('<div class="sec">자산 구성</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    for col, (lbl, vk, rk, clr) in zip([c1,c2,c3,c4,c5], [
        ("금융자산",   "financial_assets", "fin_asset_ratio",  "blue"),
        ("실물자산",   "real_assets",      "real_asset_ratio", "gray"),
        ("현금성 자산", "cash_assets",      "cash_ratio",       "green"),
        ("주식",      "stock_assets",     "stock_ratio",      "blue"),
        ("코인",      "coin_assets",      "coin_ratio",       "gold"),
    ]):
        with col:
            card(lbl, fmt_krw(latest.get(vk)), sub=f"비중 {fmt_pct(latest.get(rk))}", color=clr)

    st.markdown("<br>", unsafe_allow_html=True)

    # 차트 탭
    tab1, tab1b, tab1c, tab2, tab3, tab4 = st.tabs(["📈 순자산 추이", "💹 금융순자산 추이", "💧 유동순자산 추이", "🏦 자산 구성", "💳 부채 현황", "🎯 연금"])
    with tab1:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df["date"], y=df["net_assets"],    name="순자산(KRW)",
            line=dict(color="#1a7f37",width=2.5), fill="tozeroy", fillcolor="rgba(26,127,55,0.08)"), secondary_y=False)
        fig.add_trace(go.Scatter(x=df["date"], y=df["total_assets"],  name="총자산(KRW)",
            line=dict(color="#0969da",width=1.5,dash="dot")), secondary_y=False)
        fig.add_trace(go.Scatter(x=df["date"], y=df["total_debt"],    name="총부채(KRW)",
            line=dict(color="#cf222e",width=1.5,dash="dot")), secondary_y=False)
        fig.add_trace(go.Scatter(x=df["date"], y=df["net_assets_usd"],   name="순자산(USD)",
            line=dict(color="#2da44e",width=2,dash="dash")), secondary_y=True)
        fig.add_trace(go.Scatter(x=df["date"], y=df["total_assets_usd"], name="총자산(USD)",
            line=dict(color="#388bfd",width=1,dash="dash")), secondary_y=True)
        fig.add_trace(go.Scatter(x=df["date"], y=df["total_debt_usd"],   name="총부채(USD)",
            line=dict(color="#fa4549",width=1,dash="dash")), secondary_y=True)
        # 통계청 가계금융복지조사 연도별 순자산 분위 경계값 (단위: 원)
        # (lbl, 2024값, 2025값, color)
        _NET_THR = [
            ("상위 50%", 240_000_000,   238_600_000,   "#aaaaaa"),
            ("상위 40%", 328_380_000,   330_500_000,   "#999999"),
            ("상위 30%", 453_560_000,   461_800_000,   "#bf8700"),
            ("상위 20%", 664_500_000,   693_800_000,   "#0969da"),
            ("상위 10%", 1_045_920_000, 1_100_200_000, "#8250df"),
        ]
        _thr_segs = {
            2024: pd.Timestamp("2024-01-01"),
            2025: pd.Timestamp("2025-01-01"),
            2026: pd.Timestamp("2026-01-01"),
        }
        _thr_end = df["date"].max() + pd.DateOffset(months=2)
        for _lbl, _v24, _v25, _clr in _NET_THR:
            for _xs, _xe, _val in [
                (pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31"), _v24),
                (pd.Timestamp("2025-01-01"), _thr_end,                   _v25),
            ]:
                fig.add_trace(go.Scatter(
                    x=[_xs, _xe], y=[_val, _val],
                    mode="lines",
                    line=dict(color=_clr, width=1, dash="dot"),
                    showlegend=False,
                    hovertemplate=f"{_lbl}: {fmt_krw(_val)}<extra></extra>",
                ), secondary_y=False)
            fig.add_annotation(
                x=1, xref="paper", y=_v25, yref="y",
                text=_lbl, showarrow=False,
                xanchor="right", font=dict(size=10, color=_clr),
            )
        fig.update_layout(**LAYOUT, title="순자산 / 자산 / 부채 추이",
                          yaxis_title="원(₩)", yaxis2_title="달러($)")
        st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_net_assets")
    with tab1b:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["date"], y=df["financial_assets"], name="금융자산",
            line=dict(color="#0969da",width=2)))
        fig.add_trace(go.Scatter(x=df["date"], y=df["total_debt"],       name="총부채",
            line=dict(color="#cf222e",width=2,dash="dot")))
        fig.add_trace(go.Scatter(x=df["date"], y=df["fin_net_assets"],   name="금융순자산",
            line=dict(color="#1a7f37",width=2.5), fill="tozeroy", fillcolor="rgba(26,127,55,0.08)"))
        fig.update_layout(**LAYOUT, title="금융순자산 추이", yaxis_title="원(₩)")
        st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_fin_net")
    with tab1c:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["date"], y=df["liquid_assets"],     name="유동자산",
            line=dict(color="#0969da",width=2)))
        fig.add_trace(go.Scatter(x=df["date"], y=df["total_debt"],        name="총부채",
            line=dict(color="#cf222e",width=2,dash="dot")))
        fig.add_trace(go.Scatter(x=df["date"], y=df["liquid_net_assets"], name="유동순자산",
            line=dict(color="#1a7f37",width=2.5), fill="tozeroy", fillcolor="rgba(26,127,55,0.08)"))
        # 통계청 가계금융복지조사 연도별 순자산 분위 경계값 (단위: 원)
        for _lbl, _v24, _v25, _clr in _NET_THR:
            for _xs, _xe, _val in [
                (pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31"), _v24),
                (pd.Timestamp("2025-01-01"), _thr_end,                   _v25),
            ]:
                fig.add_trace(go.Scatter(
                    x=[_xs, _xe], y=[_val, _val],
                    mode="lines",
                    line=dict(color=_clr, width=1, dash="dot"),
                    showlegend=False,
                    hovertemplate=f"{_lbl}: {fmt_krw(_val)}<extra></extra>",
                ))
            fig.add_annotation(
                x=1, xref="paper", y=_v25, yref="y",
                text=_lbl, showarrow=False,
                xanchor="right", font=dict(size=10, color=_clr),
            )
        fig.update_layout(**LAYOUT, title="유동순자산 추이", yaxis_title="원(₩)")
        st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_liq_net")
    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["date"], y=df["financial_assets"], name="금융자산",
                line=dict(color="#0969da",width=2)))
            fig.add_trace(go.Scatter(x=df["date"], y=df["real_assets"],      name="실물자산",
                line=dict(color="#bf8700",width=2)))
            fig.update_layout(**LAYOUT, title="금융 vs 실물 추이", yaxis_title="원(₩)")
            st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_fin_real")
        with c2:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["date"], y=df["liquid_assets"],   name="유동자산",
                line=dict(color="#0969da",width=2)))
            fig.add_trace(go.Scatter(x=df["date"], y=df["illiquid_assets"], name="비유동자산",
                line=dict(color="#8c959f",width=2)))
            fig.update_layout(**LAYOUT, title="유동 vs 비유동 추이", yaxis_title="원(₩)")
            st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_liq_illiq")
        def _c(col): return df[col].fillna(0) if col in df.columns else pd.Series(0, index=df.index, dtype=float)
        _r2  = _c("real_assets").where(_c("real_assets") > 0, _c("real_estate"))
        _ca2 = _c("cash_assets"); _st2 = _c("stock_assets"); _co2 = _c("coin_assets")
        _tm2 = _c("teachers_mutual")
        _jp2 = _c("jm_pension_principal") + _c("jm_pension_profit")
        _ep2 = _c("em_pension_principal") + _c("em_pension_profit")
        _ji2 = _c("jm_irp_principal")     + _c("jm_irp_profit")
        _ei2 = _c("em_irp_principal")     + _c("em_irp_profit")
        _liq2 = _ca2 + _st2 + _co2
        _ill2 = _tm2 + _jp2 + _ep2 + _ji2 + _ei2
        view2 = st.radio("보기 방식", ["요약 (3가지)", "세부 (9가지)"], horizontal=True,
                         label_visibility="collapsed", key="anal_asset_view")
        traces2 = ([(_r2,"실물","#8c959f"),(_liq2,"유동금융자산","#0969da"),(_ill2,"비유동금융자산(연금)","#bf8700")]
                   if view2 == "요약 (3가지)" else
                   [(_r2,"실물","#8c959f"),(_co2,"코인","#bf8700"),(_st2,"주식","#0969da"),
                    (_ca2,"현금성","#2da44e"),(_tm2,"교직원공제회","#8250df"),(_jp2,"준민연금저축","#bc8cff"),
                    (_ep2,"은미연금저축","#d2a8ff"),(_ji2,"준민IRP","#cf4945"),(_ei2,"은미IRP","#fa8a87")])
        fig = go.Figure()
        for vals, name, color in traces2:
            fig.add_trace(go.Bar(x=df["date"], y=vals, name=name, marker_color=color))
        fig.update_layout(**LAYOUT, barmode="stack", title="자산 구성 추이 (원화)", yaxis_title="원(₩)")
        st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_asset_stack")
    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df["date"], y=df["fin_debt"],  name="금융부채", marker_color="#f85149"))
            fig.add_trace(go.Bar(x=df["date"], y=df["real_debt"], name="실물부채", marker_color="#da3633"))
            fig.update_layout(**LAYOUT, barmode="stack", title="부채 구성 추이")
            st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_debt_stack")
        with c2:
            fig = go.Figure(go.Scatter(x=df["date"], y=df["debt_ratio"], name="부채비율",
                line=dict(color="#f85149",width=2), fill="tozeroy", fillcolor="rgba(248,81,73,0.08)"))
            fig.update_layout(**LAYOUT, title="부채 비율 추이 (%)", yaxis_title="%")
            st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_debt_ratio")
    with tab4:
        st.markdown('<div class="sec">최신 연금 현황</div>', unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns(5)
        def _pv(a, b=None): return float(latest.get(a) or 0) + (float(latest.get(b) or 0) if b else 0)
        def _ps(a, b=None):
            s = df[a].fillna(0) if a in df.columns else pd.Series(0, index=df.index)
            return s + (df[b].fillna(0) if (b and b in df.columns) else pd.Series(0, index=df.index))
        pension_defs = [
            ("교직원공제회", "teachers_mutual",      None),
            ("준민연금저축", "jm_pension_principal", "jm_pension_profit"),
            ("은미연금저축", "em_pension_principal", "em_pension_profit"),
            ("준민IRP",    "jm_irp_principal",      "jm_irp_profit"),
            ("은미IRP",    "em_irp_principal",      "em_irp_profit"),
        ]
        clrs_p = ["#388bfd","#2ea043","#d29922","#bc8cff","#f78166"]
        for col, (lbl, a, b) in zip([c1,c2,c3,c4,c5], pension_defs):
            with col: card(lbl, fmt_krw(_pv(a, b)), color="gold")
        fig = go.Figure()
        for i, (lbl, a, b) in enumerate(pension_defs):
            fig.add_trace(go.Scatter(x=df["date"], y=_ps(a, b), name=lbl,
                line=dict(color=clrs_p[i], width=2)))
        fig.update_layout(**LAYOUT, title="연금 자산 추이")
        st.plotly_chart(_add_markers(fig), use_container_width=True, key="tab4_pension")

    st.markdown("<br>", unsafe_allow_html=True)
    year = pd.to_datetime(latest[_ref_col]).year
    ydf  = df[df[_ref_col].dt.year == year].sort_values(_ref_col)

    if len(ydf) > 1:
        st.markdown('<div class="sec">올해 YTD</div>', unsafe_allow_html=True)
        y0 = ydf.iloc[0]
        c1,c2,c3,c4 = st.columns(4)
        def yd(k): return float(latest.get(k) or 0) - float(y0.get(k) or 0)
        _net_ytd_krw = latest.get("net_assets_krw_ytd") or yd("net_assets")
        _ret_krw_pct = latest.get("net_return_krw_ytd_pct") or 0
        with c1: card("순자산 증감(₩)", fmt_krw(_net_ytd_krw),
                      sub=fmt_pct(latest.get("net_return_usd_ytd_pct")), delta=_net_ytd_krw, color="green")
        with c2: card("자산 증감(₩)", fmt_krw(latest.get("total_assets_krw_ytd") or yd("total_assets")),
                      sub=fmt_pct(latest.get("total_assets_krw_ytd_pct")), delta=yd("total_assets"), color="blue")
        with c3: card("부채 증감", fmt_krw(yd("total_debt")), delta=yd("total_debt"), color="red")
        with c4: card("순자산수익률(₩)", fmt_pct(_ret_krw_pct),
                      sub=f"$ {fmt_pct(latest.get('net_return_usd_ytd_pct'))}", color="gold")

    st.markdown("<br>", unsafe_allow_html=True)

    # 월간 증감
    st.markdown('<div class="sec">월간 순자산 증감</div>', unsafe_allow_html=True)
    dd = df.copy(); dd["delta"] = dd["net_assets"].diff(); dd = dd.dropna(subset=["delta"])
    fig = go.Figure(go.Bar(x=dd["date"], y=dd["delta"],
        marker_color=["#2ea043" if v>=0 else "#f85149" for v in dd["delta"]]))
    fig.update_layout(**LAYOUT, title="월간 순자산 증감", yaxis_title="원")
    st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_monthly_delta")

    # 자산 비중
    st.markdown('<div class="sec">자산 비중 변화</div>', unsafe_allow_html=True)
    def _col(col): return df[col].fillna(0) if col in df.columns else pd.Series(0, index=df.index, dtype=float)
    _real    = _col("real_assets").where(_col("real_assets") > 0, _col("real_estate"))
    _cash    = _col("cash_assets")
    _stk     = _col("stock_assets")
    _coin    = _col("coin_assets")
    _tm      = _col("teachers_mutual")
    _jm_pen  = _col("jm_pension_principal") + _col("jm_pension_profit")
    _em_pen  = _col("em_pension_principal") + _col("em_pension_profit")
    _jm_irp  = _col("jm_irp_principal")     + _col("jm_irp_profit")
    _em_irp  = _col("em_irp_principal")     + _col("em_irp_profit")
    # 유동금융 = cash+stk+coin 직접 합산 (financial_assets는 연금 포함될 수 있어 제외)
    _liq_fin_sum  = _cash + _stk + _coin
    _illiquid_fin = _tm + _jm_pen + _em_pen + _jm_irp + _em_irp

    view = st.radio("보기 방식", ["요약 (3가지)", "세부 (9가지)"], horizontal=True, label_visibility="collapsed")
    fig = go.Figure()
    if view == "요약 (3가지)":
        traces = [
            (_real,         "실물",               "#8c959f"),
            (_liq_fin_sum,  "유동금융자산",        "#0969da"),
            (_illiquid_fin, "비유동금융자산(연금)", "#bf8700"),
        ]
    else:
        traces = [
            (_real,    "실물",         "#8c959f"),
            (_coin,    "코인",         "#bf8700"),
            (_stk,     "주식",         "#0969da"),
            (_cash,    "현금성",       "#2da44e"),
            (_tm,      "교직원공제회",  "#8250df"),
            (_jm_pen,  "준민연금저축",  "#bc8cff"),
            (_em_pen,  "은미연금저축",  "#d2a8ff"),
            (_jm_irp,  "준민IRP",      "#cf4945"),
            (_em_irp,  "은미IRP",      "#fa8a87"),
        ]
    for vals, name, color in traces:
        fig.add_trace(go.Scatter(x=df["date"], y=vals, name=name,
            line=dict(color=color, width=2), stackgroup="one", groupnorm="percent"))
    fig.update_layout(**LAYOUT, title="자산 비중 추이 (%)", yaxis_title="%")
    fig.update_yaxes(tickformat=".1f")
    st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_asset_ratio")

    # 연금
    st.markdown('<div class="sec">연금 자산 추이</div>', unsafe_allow_html=True)
    fig = go.Figure()
    for i, (lbl, vals) in enumerate([
        ("교직원공제회", _tm),
        ("준민연금저축", _jm_pen),
        ("은미연금저축", _em_pen),
        ("준민IRP",    _jm_irp),
        ("은미IRP",    _em_irp),
    ]):
        fig.add_trace(go.Scatter(x=df["date"], y=vals, name=lbl,
            line=dict(color=["#388bfd","#2ea043","#d29922","#bc8cff","#f78166"][i], width=2)))
    fig.update_layout(**LAYOUT, title="연금 자산 추이")
    st.plotly_chart(_add_markers(fig), use_container_width=True, key="det_pension")
