"""포트폴리오 페이지 공용 헬퍼/스타일.

포트폴리오 관련 멀티페이지(계좌별 / 전체합산 / 관리)가 공유하는 인증·포맷·수식 파서와
페이지 초기화(set_page_config + 네비 라벨 + 공통 CSS)를 한곳에 모은다.
app.py 무수정 원칙을 유지하기 위해 app.py 에서 import 하지 않고 동일 로직을 여기 둔다.
"""

from __future__ import annotations

import ast
import operator as _op
from typing import Any

import streamlit as st

import _nav_label


# ── 페이지 초기화 (각 페이지의 첫 Streamlit 호출) ────────────────────
_STYLE = """
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
"""


def setup_page(page_title: str, page_icon: str) -> None:
    """st.set_page_config + 네비 라벨 보정 + 공통 스타일을 한 번에 적용.

    set_page_config 는 페이지의 첫 Streamlit 명령이어야 하므로 각 페이지 최상단에서 호출한다.
    """
    st.set_page_config(page_title=page_title, page_icon=page_icon, layout="wide")
    _nav_label.apply()
    st.markdown(_STYLE, unsafe_allow_html=True)


# ── 수식/숫자 입력 파서 ─────────────────────────────────────────────
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
    """반환: (값:float, 에러메시지:str|None, 수식여부:bool)"""
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


# ── 인증 ─────────────────────────────────────────────────────────
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


# ── 포맷터 ───────────────────────────────────────────────────────
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
