import os
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.e2e


STREAMLIT_URL = os.environ.get(
    "E2E_STREAMLIT_URL",
    "http://127.0.0.1:8501",
)
SOURCE_FILENAME = os.environ.get(
    "E2E_SOURCE_FILENAME",
    "etl_browser_vendor.csv",
)


def _run_etl_reject_details_scenario(page):
    from playwright.sync_api import expect

    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    page.goto(STREAMLIT_URL, wait_until="domcontentloaded")
    expect(page.locator("body")).to_contain_text("CatalogGuard Lite")
    expect(page.locator("body")).not_to_contain_text("StreamlitAPIException")

    page.get_by_role("tab", name="ETL 적재 이력").click()
    expect(page.locator("body")).to_contain_text("ETL 적재 이력")

    page.get_by_label("원본 파일명").fill(SOURCE_FILENAME)
    page.get_by_label("공급사 프로필").fill("sample_marketplace_vendor")
    page.get_by_role("button", name="조회", exact=True).click()

    expect(page.locator("body")).to_contain_text(SOURCE_FILENAME)
    expect(page.locator("body")).to_contain_text("sample_marketplace_vendor")

    page.get_by_role("button", name="상세 조회", exact=True).click()
    expect(page.locator("body")).to_contain_text("적재 배치 상세")
    expect(page.locator("body")).to_contain_text("전체 입력")
    expect(page.locator("body")).to_contain_text("3행")
    expect(page.locator("body")).to_contain_text("정상 적재")
    expect(page.locator("body")).to_contain_text("2행")
    expect(page.locator("body")).to_contain_text("변환 거부")
    expect(page.locator("body")).to_contain_text("1행")
    expect(page.locator("body")).to_contain_text("66.7%")

    expect(page.locator("body")).to_contain_text("INVALID_PRICE")
    expect(page.locator("body")).to_contain_text("NEGATIVE_STOCK")
    expect(page.locator("body")).to_contain_text("staging 상품 ID")
    expect(page.locator("body")).to_contain_text("E2E-100-BLK-M")
    expect(page.locator("body")).to_contain_text("E2E-100-WHT-L")

    page.get_by_text(re.compile(r"원본 행 4\s*-\s*마스킹 원본")).click()
    expect(page.locator("body")).to_contain_text("거부 행 상세")
    expect(page.locator("body")).to_contain_text("price")
    expect(page.locator("body")).to_contain_text("stock")
    expect(page.locator("body")).to_contain_text("가격 값을 숫자로 변환할 수 없습니다.")
    expect(page.locator("body")).to_contain_text("재고는 음수일 수 없습니다.")
    expect(page.locator("body")).to_contain_text("te**@example.com")
    expect(page.locator("body")).to_contain_text("010-****-5678")
    expect(page.locator("body")).to_contain_text("123-***-***012")
    expect(page.locator("body")).to_contain_text("900101-*******")

    body_text = page.locator("body").inner_text()
    page_content = page.content()
    for raw_value in (
        "test@example.com",
        "010-1234-5678",
        "123-456-789012",
        "900101-1234567",
    ):
        assert raw_value not in body_text
        assert raw_value not in page_content

    assert not console_errors, f"Unexpected browser console errors: {console_errors}"
    assert not page_errors, f"Unexpected browser page errors: {page_errors}"


def test_etl_reject_details_are_visible_and_masked_in_real_browser(page):
    try:
        _run_etl_reject_details_scenario(page)
    except BaseException:
        artifact_dir = os.environ.get("E2E_ARTIFACT_DIR", "").strip()
        if artifact_dir:
            output_dir = Path(artifact_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(
                    path=str(output_dir / "failure.png"),
                    full_page=True,
                )
                (output_dir / "page.html").write_text(
                    page.content(),
                    encoding="utf-8",
                )
            except Exception:
                pass
        raise
