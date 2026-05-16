"""사이드바 자동 생성 라벨 'app'을 '💰 자산 관리'로 치환.

Streamlit Cloud의 'Main file path' 설정이 app.py를 가리키므로 파일명은
유지하고 CSS로 첫 번째 nav 링크의 텍스트만 덮어쓴다.
"""

import streamlit as st


_CSS = """
<style>
/* 사이드바 첫 번째 nav 링크(메인 app.py)의 원본 텍스트 숨김 */
[data-testid="stSidebarNav"] > ul > li:first-child a {
    color: transparent !important;
    position: relative !important;
}
[data-testid="stSidebarNav"] > ul > li:first-child a > * {
    visibility: hidden !important;
}
/* 같은 위치에 커스텀 라벨 오버레이 */
[data-testid="stSidebarNav"] > ul > li:first-child a::before {
    content: "💰 자산 관리";
    visibility: visible !important;
    color: rgb(49, 51, 63);
    position: absolute;
    left: 1rem;
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.875rem;
    z-index: 1;
}
</style>
"""


def apply():
    st.markdown(_CSS, unsafe_allow_html=True)
