"""Streamlit Community Cloud 앱 휴면 방지.

앱 URL을 실제 브라우저로 열고, 휴면 화면이면 "Yes, get this app back up!" 버튼을 눌러 깨운다.
(curl 같은 단순 HTTP 요청으로는 깨어나지 않음)

사용: python scripts/wake_streamlit.py https://financed.streamlit.app
"""
import re
import sys

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

WAKE_BUTTON = re.compile(r"get this app back up", re.I)


def main(url: str) -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        button = page.get_by_role("button", name=WAKE_BUTTON)
        try:
            button.wait_for(state="visible", timeout=15_000)
        except PWTimeout:
            print("앱이 이미 깨어 있음")
            browser.close()
            return 0

        print("휴면 상태 감지 → 깨우는 중")
        button.click()
        try:
            button.wait_for(state="hidden", timeout=180_000)
        except PWTimeout:
            print("버튼을 눌렀지만 3분 안에 앱이 올라오지 않음", file=sys.stderr)
            browser.close()
            return 1
        print("앱 깨우기 완료")
        browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
