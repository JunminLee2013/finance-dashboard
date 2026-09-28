"""Supabase DB 전체 백업 → Gmail 발송.

데이터를 저장/삭제할 때마다 schedule_backup() 을 호출하면,
마지막 변경 후 DEBOUNCE_SEC 초 동안 추가 변경이 없을 때 전체 테이블을 CSV 로 묶은
ZIP 파일을 메일로 보낸다. (설정 탭처럼 한 번에 여러 행을 저장해도 메일은 1통)

메일 발송은 백그라운드 스레드에서 처리하므로 저장 속도에 영향을 주지 않고,
실패해도 저장 자체는 막지 않는다. 결과는 last_status() 로 확인한다.

필요한 Streamlit Secrets:
    BACKUP_GMAIL_USER         = "you@gmail.com"      # 보내는 Gmail 계정
    BACKUP_GMAIL_APP_PASSWORD = "abcd efgh ijkl mnop" # Gmail 앱 비밀번호 (16자리)
    BACKUP_EMAIL_TO           = "you@gmail.com"      # 받는 주소 (생략 시 보내는 계정)
"""

from __future__ import annotations

import io
import smtplib
import threading
import zipfile
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from supabase import create_client

# 테이블 → 페이지 조회 시 정렬 키 (복합 PK 테이블은 id 컬럼이 없음)
TABLES = {
    "finance_monthly": ["id"],
    "pf_accounts": ["id"],
    "pf_securities": ["id"],
    "pf_account_securities": ["account_id", "security_id"],
    "pf_snapshots": ["id"],
    "pf_snapshot_items": ["snapshot_id", "security_id"],
}
DEBOUNCE_SEC = 15
_PAGE = 1000  # Supabase 기본 조회 한도
_KST = ZoneInfo("Asia/Seoul")


class _State:
    def __init__(self):
        self.lock = threading.Lock()
        self.timer: threading.Timer | None = None
        self.last_ok: datetime | None = None
        self.last_error: str | None = None
        self.last_error_at: datetime | None = None


@st.cache_resource
def _state() -> _State:
    # 프로세스 전역에서 하나만 유지 (여러 세션/페이지가 공유)
    return _State()


def _config() -> dict | None:
    try:
        s = st.secrets
        user = s.get("BACKUP_GMAIL_USER")
        pw = s.get("BACKUP_GMAIL_APP_PASSWORD")
        if not user or not pw:
            return None
        return {
            "supabase_url": s["SUPABASE_URL"],
            "supabase_key": s["SUPABASE_KEY"],
            "user": user,
            "password": str(pw).replace(" ", ""),
            "to": s.get("BACKUP_EMAIL_TO") or user,
        }
    except Exception:
        return None


def is_configured() -> bool:
    return _config() is not None


# ── 덤프 ─────────────────────────────────────────────────────────
def _fetch_all(sb, table: str, order_cols: list[str]) -> list[dict]:
    rows: list[dict] = []
    start = 0
    while True:
        q = sb.table(table).select("*")
        for c in order_cols:
            q = q.order(c)
        res = q.range(start, start + _PAGE - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < _PAGE:
            return rows
        start += _PAGE


def build_backup_zip(supabase_url: str | None = None, supabase_key: str | None = None) -> tuple[bytes, dict[str, int]]:
    """전체 테이블을 CSV 로 묶은 ZIP 바이트와 테이블별 행 수를 반환."""
    sb = create_client(supabase_url or st.secrets["SUPABASE_URL"],
                       supabase_key or st.secrets["SUPABASE_KEY"])
    counts: dict[str, int] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for t, order_cols in TABLES.items():
            rows = _fetch_all(sb, t, order_cols)
            counts[t] = len(rows)
            zf.writestr(f"{t}.csv", pd.DataFrame(rows).to_csv(index=False, encoding="utf-8-sig"))
    return buf.getvalue(), counts


def backup_filename(now: datetime | None = None) -> str:
    now = now or datetime.now(_KST)
    return f"finance_backup_{now.strftime('%Y%m%d_%H%M%S')}.zip"


# ── 발송 ─────────────────────────────────────────────────────────
def _send(cfg: dict, reason: str) -> None:
    now = datetime.now(_KST)
    data, counts = build_backup_zip(cfg["supabase_url"], cfg["supabase_key"])

    msg = EmailMessage()
    msg["Subject"] = f"[재무 대시보드 백업] {now.strftime('%Y-%m-%d %H:%M')}"
    msg["From"] = cfg["user"]
    msg["To"] = cfg["to"]
    lines = [f"백업 시각: {now.strftime('%Y-%m-%d %H:%M:%S')} (KST)", f"사유: {reason}", ""]
    lines += [f"- {t}: {n}행" for t, n in counts.items()]
    msg.set_content("\n".join(lines))
    msg.add_attachment(data, maintype="application", subtype="zip", filename=backup_filename(now))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(cfg["user"], cfg["password"])
        smtp.send_message(msg)


def _run(state: _State, cfg: dict, reason: str) -> None:
    # 백그라운드 스레드에서 실행되므로 st.* 호출 없이 전달받은 값만 사용
    try:
        _send(cfg, reason)
        with state.lock:
            state.last_ok = datetime.now(_KST)
            state.last_error = None
    except Exception as e:
        with state.lock:
            state.last_error = f"{type(e).__name__}: {e}"
            state.last_error_at = datetime.now(_KST)


def schedule_backup(reason: str = "데이터 변경") -> None:
    """데이터 변경 후 호출. 설정이 없으면 아무것도 하지 않는다."""
    cfg = _config()
    if cfg is None:
        return
    state = _state()
    with state.lock:
        if state.timer is not None:
            state.timer.cancel()
        t = threading.Timer(DEBOUNCE_SEC, _run, args=(state, cfg, reason))
        t.daemon = True
        state.timer = t
        t.start()


def send_backup_now(reason: str = "수동 백업") -> None:
    """즉시 발송 (실패 시 예외 발생)."""
    cfg = _config()
    if cfg is None:
        raise RuntimeError("Gmail 백업 설정(BACKUP_GMAIL_USER / BACKUP_GMAIL_APP_PASSWORD)이 없습니다.")
    _send(cfg, reason)
    state = _state()
    with state.lock:
        state.last_ok = datetime.now(_KST)
        state.last_error = None


def last_status() -> dict:
    state = _state()
    with state.lock:
        return {
            "last_ok": state.last_ok,
            "last_error": state.last_error,
            "last_error_at": state.last_error_at,
            "pending": state.timer is not None and state.timer.is_alive(),
        }
