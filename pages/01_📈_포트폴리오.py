"""포트폴리오 리밸런싱 페이지 (Streamlit 멀티페이지).

기존 app.py와 독립된 페이지. 인증은 st.session_state.authenticated 를 공유한다.
헬퍼(require_auth, parse_num_or_formula)는 app.py 무수정 원칙을 유지하기 위해
import 사이드 이펙트를 피하고 여기서 동일 로직을 다시 정의한다.
"""

from __future__ import annotations

import ast
import operator as _op
from datetime import date
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from portfolio import db, prices, rebalance


# ── 페이지 설정 ──────────────────────────────────────────────────
st.set_page_config(page_title="포트폴리오", page_icon="📈", layout="wide")

# 공통 스타일 (app.py 와 비슷한 톤만 가볍게 적용)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&family=Space+Mono:wght@400;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
    .stApp { background:#f6f8fa; color:#24292f; }
    h1,h2,h3 { color:#24292f!important; }
    .stTabs [data-baseweb="tab-list"] { border-bottom:1px solid #d0d7de; }
    .stTabs [aria-selected="true"] { color:#24292f!important; border-bottom:2px solid #1a7f37!important; }
    .stButton>button { background:#1a7f37!important; color:white!important; border:none!important;
                       border-radius:6px!important; font-weight:500!important; }
    .stButton>button:hover { background:#2da44e!important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── 헬퍼 ─────────────────────────────────────────────────────────
_SAFE_OPS = {
    ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul,
    ast.Div: _op.truediv, ast.Mod: _op.mod, ast.Pow: _op.pow,
    ast.FloorDiv: _op.floordiv, ast.USub: _op.neg, ast.UAdd: _op.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("허용되지 않은 식")


def parse_num_or_formula(s: Any, default: float = 0.0):
    if s is None:
        return float(default), None, False
    text = str(s).strip()
    if text == "":
        return float(default), None, False
    is_formula = text.startswith("=")
    expr = (text[1:] if is_formula else text).replace(",", "")
    try:
        if is_formula:
            val = _safe_eval(ast.parse(expr, mode="eval"))
        else:
            val = float(expr)
        return float(val), None, is_formula
    except Exception as e:
        return float(default), f"{e}", is_formula


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


def fmt_krw(v: float | int | None) -> str:
    if v is None:
        return "—"
    try:
        v = float(v)
    except Exception:
        return "—"
    if abs(v) >= 1e8:
        return f"₩{v / 1e8:.2f}억"
    if abs(v) >= 1e4:
        return f"₩{v / 1e4:.0f}만"
    return f"₩{v:,.0f}"


def fmt_pct(v: float | None, digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.{digits}f}%"


# ── 인증 ─────────────────────────────────────────────────────────
require_auth()

st.title("📈 포트폴리오 리밸런싱")

# ── 계좌 선택 ────────────────────────────────────────────────────
accounts = db.list_accounts()
if not accounts:
    st.info("계좌가 없습니다. 아래 '⚙️ 관리' 탭에서 계좌를 먼저 추가하세요.")
    # 그래도 관리 탭은 띄워줘야 계좌 생성 가능
    selected_account = None
else:
    account_names = [a["name"] for a in accounts]
    sel_idx = 0
    if "pf_selected_account" in st.session_state:
        try:
            sel_idx = account_names.index(st.session_state["pf_selected_account"])
        except ValueError:
            sel_idx = 0
    selected_name = st.selectbox("계좌", account_names, index=sel_idx)
    st.session_state["pf_selected_account"] = selected_name
    selected_account = next(a for a in accounts if a["name"] == selected_name)

tab_reb, tab_now, tab_hist, tab_trend, tab_admin = st.tabs(
    ["⚖️ 리밸런싱", "📊 현재 비중", "📅 과거 스냅샷", "📈 추이", "⚙️ 관리"]
)


# =================================================================
# ⚖️ 리밸런싱
# =================================================================
with tab_reb:
    if not selected_account:
        st.info("계좌를 먼저 생성하세요.")
    else:
        acct_id = selected_account["id"]
        holdings_meta = db.get_account_securities(acct_id)
        latest = db.latest_snapshot(acct_id)

        if not holdings_meta:
            st.info("이 계좌에 등록된 종목이 없습니다. '⚙️ 관리' 탭에서 종목을 추가하세요.")
        else:
            target_sum = sum(h["target_weight"] for h in holdings_meta)
            cash_target = max(0.0, 1.0 - target_sum)
            colA, colB, colC = st.columns([2, 1, 1])
            with colA:
                raw_total = st.text_input(
                    "현재 총 평가가치 (주식 + 예수금) — `=` 로 수식 가능",
                    value=st.session_state.get(f"pf_total_input_{acct_id}", ""),
                    placeholder="예: 10,000,000  또는  =5000000+3000000",
                    key=f"pf_total_input_widget_{acct_id}",
                )
                st.session_state[f"pf_total_input_{acct_id}"] = raw_total
            total_value, err, _ = parse_num_or_formula(raw_total, 0.0)
            if err:
                st.warning(f"입력 오류: {err}")
            with colB:
                st.metric("타겟 합", fmt_pct(target_sum))
            with colC:
                st.metric("현금 타겟(잔여)", fmt_pct(cash_target))

            if target_sum > 1.0 + 1e-9:
                st.error(f"타겟 비중 합이 100%를 초과합니다 ({fmt_pct(target_sum)}). '⚙️ 관리'에서 조정하세요.")

            fetch = st.button("💹 현재가 조회", use_container_width=True)

            # 가격 상태: session_state 에 보관 (조회 후 수동 오버라이드 가능)
            price_key = f"pf_prices_{acct_id}"
            if fetch or price_key not in st.session_state:
                st.session_state[price_key] = {
                    h["code"]: prices.get_current_price(h["code"], h["market"]) for h in holdings_meta
                }

            # 보유수량 (최근 스냅샷 기준)
            current_qty_map = {}
            if latest:
                for it in latest["items"]:
                    current_qty_map[it["code"]] = it["quantity"]

            st.markdown("##### 가격 / 보유수량 (필요 시 수동 수정)")
            price_inputs: dict[str, float] = {}
            qty_inputs: dict[str, int] = {}
            for h in holdings_meta:
                c1, c2, c3, c4, c5 = st.columns([3, 1.5, 1.5, 1.5, 1])
                with c1:
                    st.markdown(f"**{h['name']}** ·  `{h['code']}.{h['market']}`")
                with c2:
                    auto_p = st.session_state[price_key].get(h["code"])
                    label = "현재가" + ("" if auto_p else " (수동)")
                    price_inputs[h["code"]] = st.number_input(
                        label,
                        min_value=0.0,
                        value=float(auto_p) if auto_p else 0.0,
                        step=10.0,
                        key=f"pf_p_{acct_id}_{h['code']}",
                        label_visibility="collapsed",
                    )
                with c3:
                    qty_inputs[h["code"]] = st.number_input(
                        "보유수량",
                        min_value=0,
                        value=int(current_qty_map.get(h["code"], 0)),
                        step=1,
                        key=f"pf_q_{acct_id}_{h['code']}",
                        label_visibility="collapsed",
                    )
                with c4:
                    st.markdown(f"<div style='padding-top:6px;color:#57606a'>목표 {fmt_pct(h['target_weight'])}</div>",
                                unsafe_allow_html=True)
                with c5:
                    if not st.session_state[price_key].get(h["code"]):
                        st.markdown("<span style='color:#cf222e;font-size:12px'>API 실패</span>",
                                    unsafe_allow_html=True)

            holdings_obj = [
                rebalance.Holding(
                    security_id=h["security_id"],
                    code=h["code"],
                    name=h["name"],
                    target_weight=h["target_weight"],
                    current_qty=qty_inputs.get(h["code"], 0),
                )
                for h in holdings_meta
            ]
            rows, expected_cash = rebalance.compute_rebalance(total_value, holdings_obj, price_inputs)

            df = pd.DataFrame(
                [
                    {
                        "종목명": r.name,
                        "코드": r.code,
                        "현재가": r.price,
                        "보유수량": r.current_qty,
                        "목표비중(%)": r.target_weight * 100,
                        "추천 매수·매도": r.delta_qty,
                        "목표수량": r.target_qty,
                        "체결수량": r.target_qty,
                    }
                    for r in rows
                ]
            )

            st.markdown("##### 리밸런싱 결과 — 체결수량 입력 후 저장")
            st.caption("**체결수량** 컬럼이 실제 매매 수량입니다. 기본값은 목표수량이며, "
                       "더 사거나 덜 산 경우 직접 수정하세요. 잔여현금/실제 비중은 자동 재계산됩니다.")
            edited = st.data_editor(
                df,
                hide_index=True,
                use_container_width=True,
                disabled=["종목명", "코드", "현재가", "보유수량",
                          "목표비중(%)", "추천 매수·매도", "목표수량"],
                column_config={
                    "현재가": st.column_config.NumberColumn(format="₩%.0f"),
                    "목표비중(%)": st.column_config.NumberColumn(format="%.2f"),
                    "체결수량": st.column_config.NumberColumn(min_value=0, step=1),
                },
                key=f"pf_edit_rows_{acct_id}",
            )

            # 체결수량 기준 실제 평가액/잔여현금 재계산 (rows 순서와 edited 순서 일치 가정)
            actual_qty: dict[int, int] = {}
            actual_invested = 0.0
            for r, (_, erow) in zip(rows, edited.iterrows()):
                q = int(erow["체결수량"] or 0)
                actual_qty[r.security_id] = q
                actual_invested += q * r.price
            actual_cash = total_value - actual_invested
            actual_total = actual_invested + max(actual_cash, 0.0)

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("입력 총가치", fmt_krw(total_value))
            mc2.metric("실제 잔여현금", fmt_krw(actual_cash),
                       delta=f"추천 {fmt_krw(expected_cash)}")
            mc3.metric("주식 투자액", fmt_krw(actual_invested))
            if actual_cash < 0:
                st.warning("체결수량 합이 입력 총가치를 초과합니다. 총가치 또는 체결수량을 확인하세요.")

            st.markdown("---")
            save_date = st.date_input("스냅샷 날짜", value=date.today(), key=f"pf_save_date_{acct_id}")
            confirm = st.checkbox(
                f"`{save_date}` 날짜의 기존 스냅샷이 있다면 **덮어씁니다**. 진행 확인",
                key=f"pf_save_confirm_{acct_id}",
            )
            if st.button("💾 스냅샷으로 저장 (체결수량 기준)", disabled=not confirm,
                         use_container_width=True, key=f"pf_save_btn_{acct_id}"):
                items_payload = [
                    (r.security_id, actual_qty[r.security_id], r.price) for r in rows
                ]
                db.save_snapshot(acct_id, save_date, max(actual_cash, 0.0), items_payload)
                st.success(f"{save_date} 스냅샷 저장 완료.")
                st.rerun()


# =================================================================
# 📊 현재 비중
# =================================================================
with tab_now:
    if not selected_account:
        st.info("계좌를 먼저 생성하세요.")
    else:
        acct_id = selected_account["id"]
        latest = db.latest_snapshot(acct_id)
        holdings_meta = db.get_account_securities(acct_id)
        if not latest:
            st.info("저장된 스냅샷이 없습니다.")
        elif not holdings_meta:
            st.info("이 계좌에 등록된 종목이 없습니다.")
        else:
            st.caption(f"최근 스냅샷: **{latest['snapshot_date']}**  ·  예수금 {fmt_krw(latest['cash_balance'])}")
            live_prices = {h["code"]: (prices.get_current_price(h["code"], h["market"]) or 0.0) for h in holdings_meta}
            enriched, total = rebalance.compute_current_weights(
                latest["items"], live_prices, latest["cash_balance"]
            )
            tw_map = {h["code"]: h["target_weight"] for h in holdings_meta}

            rows_now = []
            for it in enriched:
                tw = tw_map.get(it["code"], 0.0)
                rows_now.append(
                    {
                        "종목명": it["name"],
                        "코드": it["code"],
                        "현재가": it["price"],
                        "보유수량": it["quantity"],
                        "평가액": it["value"],
                        "현재비중(%)": it["weight"] * 100,
                        "타겟비중(%)": tw * 100,
                        "드리프트(%)": (it["weight"] - tw) * 100,
                    }
                )
            df = pd.DataFrame(rows_now)
            st.dataframe(
                df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "현재가": st.column_config.NumberColumn(format="₩%.0f"),
                    "평가액": st.column_config.NumberColumn(format="₩%.0f"),
                    "현재비중(%)": st.column_config.NumberColumn(format="%.2f"),
                    "타겟비중(%)": st.column_config.NumberColumn(format="%.2f"),
                    "드리프트(%)": st.column_config.NumberColumn(format="%+.2f"),
                },
            )

            m1, m2 = st.columns(2)
            m1.metric("총 평가가치", fmt_krw(total))
            m2.metric("주식 평가가치", fmt_krw(total - latest["cash_balance"]))

            # 도넛: 현재 vs 타겟
            labels = [r["종목명"] for r in rows_now] + ["현금"]
            cur_vals = [r["평가액"] for r in rows_now] + [latest["cash_balance"]]
            tgt_vals = [total * tw_map.get(r["코드"], 0) for r in rows_now] + \
                       [total * max(0.0, 1 - sum(tw_map.values()))]

            fig = go.Figure()
            fig.add_trace(go.Pie(labels=labels, values=cur_vals, hole=0.55, name="현재",
                                 domain={"x": [0, 0.48]}, title="현재"))
            fig.add_trace(go.Pie(labels=labels, values=tgt_vals, hole=0.55, name="타겟",
                                 domain={"x": [0.52, 1]}, title="타겟"))
            fig.update_layout(height=380, margin=dict(t=20, b=10, l=10, r=10),
                              showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

            # 드리프트 막대
            bar = go.Figure(
                go.Bar(
                    x=[r["종목명"] for r in rows_now],
                    y=[r["드리프트(%)"] for r in rows_now],
                    marker_color=["#cf222e" if r["드리프트(%)"] > 0 else "#1a7f37" for r in rows_now],
                )
            )
            bar.update_layout(height=280, margin=dict(t=30, b=10, l=10, r=10),
                              title="타겟 대비 드리프트 (%, 양수=과보유)")
            st.plotly_chart(bar, use_container_width=True)


# =================================================================
# 📅 과거 스냅샷
# =================================================================
with tab_hist:
    if not selected_account:
        st.info("계좌를 먼저 생성하세요.")
    else:
        acct_id = selected_account["id"]
        snap_dates = db.list_snapshot_dates(acct_id)
        if not snap_dates:
            st.info("저장된 스냅샷이 없습니다.")
        else:
            sel = st.selectbox(
                "스냅샷 날짜",
                snap_dates,
                format_func=lambda d: d.isoformat(),
                key=f"pf_hist_date_{acct_id}",
            )
            snap = db.get_snapshot(acct_id, sel)
            if snap:
                stock_total = sum(it["quantity"] * it["price"] for it in snap["items"])
                total = stock_total + snap["cash_balance"]
                rows = []
                for it in snap["items"]:
                    v = it["quantity"] * it["price"]
                    rows.append(
                        {
                            "종목명": it["name"],
                            "코드": it["code"],
                            "수량": it["quantity"],
                            "단가": it["price"],
                            "평가액": v,
                            "비중(%)": ((v / total) * 100) if total > 0 else 0.0,
                        }
                    )
                df = pd.DataFrame(rows)
                st.dataframe(
                    df,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "단가": st.column_config.NumberColumn(format="₩%.0f"),
                        "평가액": st.column_config.NumberColumn(format="₩%.0f"),
                        "비중(%)": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
                c1, c2, c3 = st.columns(3)
                c1.metric("총 평가가치", fmt_krw(total))
                c2.metric("주식 평가가치", fmt_krw(stock_total))
                c3.metric("예수금", fmt_krw(snap["cash_balance"]))

                with st.expander("이 스냅샷 삭제"):
                    if st.button("🗑️ 삭제", key=f"pf_hist_del_{acct_id}_{sel}"):
                        db.delete_snapshot(acct_id, sel)
                        st.success(f"{sel} 삭제 완료.")
                        st.rerun()


# =================================================================
# 📈 추이 (Pre/Post 비중 시계열)
# =================================================================
with tab_trend:
    if not selected_account:
        st.info("계좌를 먼저 생성하세요.")
    else:
        acct_id = selected_account["id"]
        snapshots = db.list_snapshots_full(acct_id)
        holdings_meta = db.get_account_securities(acct_id)
        target_map = {h["security_id"]: h["target_weight"] for h in holdings_meta}

        if not snapshots:
            st.info("저장된 스냅샷이 없습니다.")
        elif len(snapshots) < 2:
            st.info("추이 비교를 위해 최소 2개 이상의 스냅샷이 필요합니다.")
        else:
            rows_w = rebalance.compute_pre_post_weights(snapshots)
            wdf = pd.DataFrame(rows_w)
            wdf["snapshot_date"] = pd.to_datetime(wdf["snapshot_date"])

            # 같은 날짜 두 점을 시각적으로 분리: pre 는 -12h, post 는 +12h
            offset = pd.Timedelta(hours=12)
            wdf["x"] = wdf.apply(
                lambda r: r["snapshot_date"] + (-offset if r["kind"] == "pre" else offset),
                axis=1,
            )

            # 종목 순서/색상 — display_order 기준, 그 뒤에 holdings_meta 에 없는 종목, 마지막에 현금
            order_sids: list[int] = []
            seen: set[int] = set()
            for h in holdings_meta:
                if h["security_id"] in target_map:
                    order_sids.append(h["security_id"])
                    seen.add(h["security_id"])
            for sid in wdf["security_id"].unique():
                if sid == rebalance.CASH_SID or sid in seen:
                    continue
                order_sids.append(int(sid))
                seen.add(int(sid))
            order_sids.append(rebalance.CASH_SID)  # 현금 마지막

            palette = ["#0969da", "#1a7f37", "#bf8700", "#8250df", "#cf222e",
                       "#0550ae", "#2da44e", "#d29922", "#bc8cff", "#fa4549"]
            color_map: dict[int, str] = {}
            for i, sid in enumerate(s for s in order_sids if s != rebalance.CASH_SID):
                color_map[sid] = palette[i % len(palette)]
            color_map[rebalance.CASH_SID] = "#8c959f"

            label_for: dict[int, str] = (
                wdf.drop_duplicates("security_id").set_index("security_id")["label"].to_dict()
            )

            # ── 차트 1: Pre/Post 비중 stacked area ──────────────────
            st.markdown("##### 종목 비중 추이 (Pre / Post)")
            area = go.Figure()
            for sid in order_sids:
                sub = wdf[wdf["security_id"] == sid].sort_values("x")
                if sub.empty:
                    continue
                lbl = label_for.get(sid, "?") if sid != rebalance.CASH_SID else "현금"
                cdata = [
                    [("pre" if k == "pre" else "post"), str(pd.Timestamp(d).date())]
                    for k, d in zip(sub["kind"], sub["snapshot_date"])
                ]
                area.add_trace(go.Scatter(
                    x=sub["x"], y=sub["weight_pct"], name=lbl,
                    stackgroup="one",
                    line=dict(color=color_map[sid], width=1),
                    customdata=cdata,
                    hovertemplate=f"{lbl}: %{{y:.1f}}%<br>%{{customdata[0]}} @ %{{customdata[1]}}<extra></extra>",
                ))
            area.update_layout(
                height=420, margin=dict(t=20, b=10, l=10, r=10),
                yaxis=dict(title="비중 (%)", range=[0, 100], ticksuffix="%"),
                hovermode="x unified",
            )
            st.plotly_chart(area, use_container_width=True)
            st.caption(
                "같은 날짜에 두 점: **pre** = 직전 스냅샷 수량 × 당일 스냅샷 가격 "
                "(리밸런싱 직전, 보유기간 동안 가격 변동으로 drift 된 비중). "
                "**post** = 당일 수량 × 당일 가격 (리밸런싱 직후 실제 비중). "
                "두 점 사이의 수직 점프 = 리밸런싱 효과, 스냅샷 사이의 경사 = 보유기간 가격 drift."
            )

            # ── 차트 2: 종목별 small multiples ──────────────────────
            st.markdown("##### 종목별 비중 (Small Multiples)")
            chart_sids = [sid for sid in order_sids if sid != rebalance.CASH_SID]
            if chart_sids:
                n = len(chart_sids)
                ncols = 2 if n > 1 else 1
                nrows = (n + ncols - 1) // ncols
                sm = make_subplots(
                    rows=nrows, cols=ncols,
                    subplot_titles=[label_for.get(sid, "?") for sid in chart_sids],
                    vertical_spacing=0.12, horizontal_spacing=0.08,
                )
                for i, sid in enumerate(chart_sids):
                    r = i // ncols + 1
                    c = i % ncols + 1
                    sub = wdf[wdf["security_id"] == sid].sort_values("snapshot_date")
                    sub_post = sub[sub["kind"] == "post"]
                    sub_pre  = sub[sub["kind"] == "pre"]
                    clr = color_map[sid]
                    if not sub_post.empty:
                        sm.add_trace(go.Scatter(
                            x=sub_post["snapshot_date"], y=sub_post["weight_pct"],
                            name="post", legendgroup="post", showlegend=(i == 0),
                            mode="lines+markers",
                            line=dict(color=clr, width=2),
                            marker=dict(size=6),
                        ), row=r, col=c)
                    if not sub_pre.empty:
                        sm.add_trace(go.Scatter(
                            x=sub_pre["snapshot_date"], y=sub_pre["weight_pct"],
                            name="pre", legendgroup="pre", showlegend=(i == 0),
                            mode="lines+markers",
                            line=dict(color=clr, width=1, dash="dot"),
                            marker=dict(size=5, symbol="circle-open"),
                        ), row=r, col=c)
                    tgt_pct = float(target_map.get(sid, 0)) * 100
                    if tgt_pct > 0:
                        sm.add_hline(
                            y=tgt_pct, line=dict(color="#57606a", width=1, dash="dash"),
                            row=r, col=c,
                            annotation_text=f"target {tgt_pct:.1f}%",
                            annotation_position="top right",
                            annotation_font_size=10,
                        )
                    sm.update_yaxes(ticksuffix="%", row=r, col=c)
                sm.update_layout(
                    height=260 * nrows, margin=dict(t=40, b=10, l=10, r=10),
                    hovermode="x",
                )
                st.plotly_chart(sm, use_container_width=True)


# =================================================================
# ⚙️ 관리
# =================================================================
with tab_admin:
    st.subheader("계좌")
    with st.form("pf_new_account", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            new_account_name = st.text_input("새 계좌 이름", placeholder="예: 장기투자 ISA")
        with col2:
            submitted = st.form_submit_button("계좌 추가")
        if submitted and new_account_name.strip():
            try:
                db.create_account(new_account_name.strip())
                st.success(f"계좌 '{new_account_name}' 생성됨.")
                st.rerun()
            except Exception as e:
                st.error(f"생성 실패: {e}")

    if accounts:
        for a in accounts:
            ac1, ac2 = st.columns([5, 1])
            ac1.markdown(f"• **{a['name']}** (id {a['id']})")
            if ac2.button("삭제", key=f"pf_del_acc_{a['id']}"):
                try:
                    db.delete_account(a["id"])
                    st.success("삭제 완료.")
                    st.rerun()
                except Exception as e:
                    st.error(f"삭제 실패 (스냅샷/종목이 연결되어 있을 수 있음): {e}")

    st.divider()
    st.subheader("종목 마스터")
    securities = db.list_securities()
    with st.form("pf_new_sec", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([2, 3, 1.5, 1])
        with c1:
            new_code = st.text_input("종목코드", placeholder="069500")
        with c2:
            new_name = st.text_input("종목명", placeholder="KODEX 200")
        with c3:
            new_market = st.selectbox("시장", ["자동 감지", "KS (코스피)", "KQ (코스닥)"])
        with c4:
            sec_submit = st.form_submit_button("추가")
        if sec_submit and new_code.strip() and new_name.strip():
            code = new_code.strip()
            if new_market.startswith("자동"):
                with st.spinner("시장 자동 감지 중..."):
                    m = prices.resolve_market(code)
                if not m:
                    st.error("자동 감지 실패. KS/KQ 를 직접 선택하세요.")
                    m = None
            else:
                m = "KS" if new_market.startswith("KS") else "KQ"
            if m:
                try:
                    db.upsert_security(code, new_name.strip(), m)
                    st.success(f"{new_name} ({code}.{m}) 등록.")
                    st.rerun()
                except Exception as e:
                    st.error(f"등록 실패: {e}")

    if securities:
        sec_df = pd.DataFrame(
            [{"id": s["id"], "코드": s["code"], "종목명": s["name"], "시장": s["market"]} for s in securities]
        )
        st.dataframe(sec_df, hide_index=True, use_container_width=True)
        del_id = st.number_input("삭제할 종목 id", min_value=0, value=0, step=1)
        if st.button("종목 삭제", key="pf_del_sec_btn") and del_id > 0:
            try:
                db.delete_security(int(del_id))
                st.success("삭제 완료.")
                st.rerun()
            except Exception as e:
                st.error(f"삭제 실패 (어딘가에 사용 중일 수 있음): {e}")

    st.divider()
    st.subheader("계좌별 종목 / 타겟 비중")
    if not selected_account:
        st.info("계좌를 먼저 생성하세요.")
    elif not securities:
        st.info("먼저 종목 마스터에 종목을 추가하세요.")
    else:
        acct_id = selected_account["id"]
        current = db.get_account_securities(acct_id)
        current_ids = {c["security_id"] for c in current}
        sec_by_id = {s["id"]: s for s in securities}

        rows = []
        for c in current:
            rows.append(
                {
                    "포함": True,
                    "security_id": c["security_id"],
                    "코드": c["code"],
                    "종목명": c["name"],
                    "시장": c["market"],
                    "타겟비중(%)": round(c["target_weight"] * 100, 2),
                    "순서": c["display_order"],
                }
            )
        for s in securities:
            if s["id"] not in current_ids:
                rows.append(
                    {
                        "포함": False,
                        "security_id": s["id"],
                        "코드": s["code"],
                        "종목명": s["name"],
                        "시장": s["market"],
                        "타겟비중(%)": 0.0,
                        "순서": 0,
                    }
                )
        edit_df = pd.DataFrame(rows)
        edited = st.data_editor(
            edit_df,
            hide_index=True,
            use_container_width=True,
            disabled=["security_id", "코드", "종목명", "시장"],
            column_config={
                "타겟비중(%)": st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=0.1),
                "순서": st.column_config.NumberColumn(min_value=0, step=1),
            },
            key=f"pf_edit_acc_sec_{acct_id}",
        )
        weight_sum = edited.loc[edited["포함"] == True, "타겟비중(%)"].sum()
        st.caption(f"선택 종목 타겟 합계: **{weight_sum:.2f}%**  ·  현금(잔여) 타겟: **{max(0.0, 100 - weight_sum):.2f}%**")
        if weight_sum > 100 + 1e-6:
            st.error("타겟 합계가 100%를 초과합니다.")
        if st.button("💾 변경 저장", use_container_width=True, key=f"pf_save_acc_sec_{acct_id}"):
            try:
                for _, r in edited.iterrows():
                    sid = int(r["security_id"])
                    if bool(r["포함"]):
                        db.upsert_account_security(
                            acct_id, sid, float(r["타겟비중(%)"]) / 100.0, int(r["순서"])
                        )
                    else:
                        if sid in current_ids:
                            db.delete_account_security(acct_id, sid)
                st.success("저장 완료.")
                st.rerun()
            except Exception as e:
                st.error(f"저장 실패: {e}")
