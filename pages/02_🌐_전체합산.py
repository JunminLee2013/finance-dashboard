"""포트폴리오 — 전체 합산 (Streamlit 멀티페이지).

모든 계좌의 최근 스냅샷 × 실시간 현재가 + 예수금을 합산한 통합 포트폴리오.
선택 계좌와 무관한 전역 뷰이므로 계좌별 페이지에서 분리한다.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from portfolio import db, prices, rebalance, ui


# ── 페이지 설정 / 인증 ───────────────────────────────────────────
ui.setup_page("전체합산", "🌐")
ui.require_auth()

st.title("🌐 포트폴리오 — 전체 합산")

accounts = db.list_accounts()
if not accounts:
    st.info("계좌가 없습니다. '⚙️ 관리' 페이지에서 계좌를 먼저 추가하세요.")
else:
    st.caption("모든 계좌의 최근 스냅샷 보유수량 × 실시간 현재가 + 예수금을 합산한 "
               "통합 포트폴리오입니다. 타겟비중은 각 계좌 평가액으로 가중 평균합니다.")

    accounts_data = []
    skipped = []
    for a in accounts:
        aid = a["id"]
        latest = db.latest_snapshot(aid)
        meta = db.get_account_securities(aid)
        if not latest:
            skipped.append(a["name"])
            # 스냅샷이 없어도 타겟만 있는 계좌는 평가액 0 → 합산 기여 없음. 스킵.
            continue
        live = {h["code"]: (prices.get_current_price(h["code"], h["market"]) or 0.0)
                for h in meta}
        items = [
            {
                "security_id": it["security_id"],
                "code": it["code"],
                "name": it["name"],
                "quantity": it["quantity"],
                "price": live.get(it["code"], 0.0),
            }
            for it in latest["items"]
        ]
        targets = {h["security_id"]: h["target_weight"] for h in meta}
        accounts_data.append({
            "account_name": a["name"],
            "items": items,
            "cash_balance": latest["cash_balance"],
            "targets": targets,
        })

    if not accounts_data:
        st.info("합산할 스냅샷이 없습니다. 각 계좌의 '⚖️ 리밸런싱' 탭에서 스냅샷을 먼저 저장하세요.")
    else:
        combined = rebalance.compute_combined_portfolio(accounts_data)
        grand = combined["grand_total"]
        cash = combined["cash"]

        m1, m2, m3 = st.columns(3)
        m1.metric("전체 평가가치", ui.fmt_krw(grand))
        m2.metric("주식 평가가치", ui.fmt_krw(grand - cash["value"]))
        m3.metric("합산 계좌 수", f"{len(accounts_data)}개")
        if skipped:
            st.caption(f"⚠️ 스냅샷이 없어 제외된 계좌: {', '.join(skipped)}")

        rows_all = [
            {
                "종목명": r["name"],
                "코드": r["code"],
                "평가액": r["value"],
                "현재비중(%)": r["weight"] * 100,
                "타겟비중(%)": r["target_weight"] * 100,
                "드리프트(%)": (r["weight"] - r["target_weight"]) * 100,
            }
            for r in combined["rows"]
        ]
        rows_all.append({
            "종목명": "현금",
            "코드": "—",
            "평가액": cash["value"],
            "현재비중(%)": cash["weight"] * 100,
            "타겟비중(%)": cash["target_weight"] * 100,
            "드리프트(%)": (cash["weight"] - cash["target_weight"]) * 100,
        })
        df_all = pd.DataFrame(rows_all)
        st.dataframe(
            df_all,
            hide_index=True,
            use_container_width=True,
            column_config={
                "평가액": st.column_config.NumberColumn(format="₩%.0f"),
                "현재비중(%)": st.column_config.NumberColumn(format="%.2f"),
                "타겟비중(%)": st.column_config.NumberColumn(format="%.2f"),
                "드리프트(%)": st.column_config.NumberColumn(format="%+.2f"),
            },
        )

        # 도넛: 현재 vs 타겟 (현금 포함)
        labels = [r["종목명"] for r in rows_all]
        cur_vals = [r["평가액"] for r in rows_all]
        tgt_vals = [r["타겟비중(%)"] / 100 * grand for r in rows_all]

        fig = go.Figure()
        fig.add_trace(go.Pie(labels=labels, values=cur_vals, hole=0.55, name="현재",
                             domain={"x": [0, 0.48]}, title="현재",
                             textposition="inside", textinfo="percent",
                             insidetextorientation="horizontal"))
        fig.add_trace(go.Pie(labels=labels, values=tgt_vals, hole=0.55, name="타겟",
                             domain={"x": [0.52, 1]}, title="타겟",
                             textposition="inside", textinfo="percent",
                             insidetextorientation="horizontal"))
        fig.update_layout(
            height=520, margin=dict(t=30, b=10, l=10, r=10),
            showlegend=True, uniformtext=dict(minsize=10, mode="hide"),
            legend=dict(orientation="h", yanchor="top", y=-0.05,
                        xanchor="center", x=0.5, font=dict(size=11)),
        )
        st.plotly_chart(fig, use_container_width=True)

        # 드리프트 막대 (현금 제외)
        drift_rows = [r for r in rows_all if r["종목명"] != "현금"]
        if drift_rows:
            bar = go.Figure(
                go.Bar(
                    x=[r["종목명"] for r in drift_rows],
                    y=[r["드리프트(%)"] for r in drift_rows],
                    marker_color=["#cf222e" if r["드리프트(%)"] > 0 else "#1a7f37"
                                  for r in drift_rows],
                )
            )
            bar.update_layout(height=280, margin=dict(t=30, b=10, l=10, r=10),
                              title="타겟 대비 드리프트 (%, 양수=과보유)")
            st.plotly_chart(bar, use_container_width=True)
