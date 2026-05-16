"""사이드바 자동 생성 라벨 'app'을 '💰 자산 관리'로 치환.

Streamlit 멀티페이지는 메인 스크립트 파일명(app.py)을 그대로 사이드바
라벨로 쓰는데, 파일명을 바꾸면 Streamlit Cloud의 'Main file path' 설정이
깨지므로 파일명은 유지하고 DOM에서만 라벨을 덮어쓴다.
"""

import streamlit.components.v1 as components

_TARGET = "💰 자산 관리"


def apply():
    components.html(
        f"""
        <script>
        (function() {{
            const TARGET = {_TARGET!r};
            const doc = window.parent.document;
            function rewrite() {{
                const links = doc.querySelectorAll('[data-testid="stSidebarNavLink"]');
                for (const link of links) {{
                    const txt = link.textContent.trim();
                    if (txt === 'app' || txt === TARGET) {{
                        if (txt === TARGET) return true;
                        const walker = doc.createTreeWalker(link, NodeFilter.SHOW_TEXT);
                        let node;
                        while ((node = walker.nextNode())) {{
                            if (node.textContent.trim() === 'app') {{
                                node.textContent = TARGET;
                                return true;
                            }}
                        }}
                    }}
                }}
                return false;
            }}
            let tries = 0;
            const t = setInterval(() => {{
                if (rewrite() || ++tries > 40) clearInterval(t);
            }}, 100);
            new MutationObserver(rewrite).observe(doc.body, {{childList: true, subtree: true}});
        }})();
        </script>
        """,
        height=0,
    )
