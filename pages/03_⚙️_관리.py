"""포트폴리오 — 관리 (Streamlit 멀티페이지).

전역 설정만 담당한다: 계좌 추가/삭제, 종목 마스터(종목 등록/삭제).
계좌별 종목/타겟 비중 설정은 '포트폴리오(계좌별)' 페이지의 '⚙️ 설정' 탭으로 이동했다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import backup
from portfolio import db, prices, ui


# ── 페이지 설정 / 인증 ───────────────────────────────────────────
ui.setup_page("관리", "⚙️")
ui.require_auth()

st.title("⚙️ 포트폴리오 — 관리")

accounts = db.list_accounts()

# ── 계좌 ─────────────────────────────────────────────────────────
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

# ── 종목 마스터 ──────────────────────────────────────────────────
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

st.caption("💡 계좌별 종목 선택 / 타겟 비중 설정은 **포트폴리오(계좌별)** 페이지의 '⚙️ 설정' 탭에서 합니다.")

st.divider()

# ── DB 백업 ──────────────────────────────────────────────────────
st.subheader("DB 백업")
if backup.is_configured():
    st.caption(
        f"데이터를 저장/삭제하면 약 {backup.DEBOUNCE_SEC}초 뒤 전체 DB(CSV 묶음 ZIP)가 메일로 자동 발송됩니다."
    )
    status = backup.last_status()
    if status["pending"]:
        st.info("⏳ 백업 발송 대기 중...")
    if status["last_ok"]:
        st.success(f"마지막 백업 발송: {status['last_ok'].strftime('%Y-%m-%d %H:%M:%S')}")
    if status["last_error"]:
        st.error(f"백업 발송 실패 ({status['last_error_at'].strftime('%Y-%m-%d %H:%M:%S')}): {status['last_error']}")
    if st.button("📧 지금 메일로 백업 보내기"):
        with st.spinner("백업 발송 중..."):
            try:
                backup.send_backup_now()
                st.success("백업 메일을 보냈습니다.")
            except Exception as e:
                st.error(f"발송 실패: {e}")
else:
    st.warning(
        "메일 자동 백업이 설정되지 않았습니다. Streamlit Secrets 에 "
        "`BACKUP_GMAIL_USER`, `BACKUP_GMAIL_APP_PASSWORD` 를 추가하세요 (README 참고)."
    )

if st.button("📦 백업 파일 만들기"):
    with st.spinner("전체 테이블 조회 중..."):
        try:
            data, counts = backup.build_backup_zip()
            st.session_state["pf_backup_zip"] = (backup.backup_filename(), data, counts)
        except Exception as e:
            st.error(f"백업 생성 실패: {e}")
if "pf_backup_zip" in st.session_state:
    fname, data, counts = st.session_state["pf_backup_zip"]
    st.caption(" · ".join(f"{t} {n}행" for t, n in counts.items()))
    st.download_button("📥 ZIP 다운로드", data, fname, "application/zip")
