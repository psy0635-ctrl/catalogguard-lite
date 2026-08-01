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
PROMOTION_SOURCE_FILENAME = os.environ.get(
    "E2E_PROMOTION_SOURCE_FILENAME",
    "etl_browser_promotion_vendor.csv",
)
API_URL = os.environ.get(
    "E2E_API_URL",
    os.environ.get("CATALOGGUARD_API_BASE_URL", "http://127.0.0.1:8000"),
)
PROMOTION_PRODUCT_IDS = (
    "CG-E2E-PROMO-BLK-M",
    "CG-E2E-PROMO-WHT-L",
)


def _preserve_browser_failure_artifacts(page) -> None:
    artifact_dir = os.environ.get("E2E_ARTIFACT_DIR", "").strip()
    if not artifact_dir:
        return
    output_dir = Path(artifact_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(output_dir / "failure.png"), full_page=True)
        (output_dir / "page.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass


def _assert_catalog_promotion_persisted(page) -> dict[str, int]:
    from sqlalchemy import func, select

    from db.models import (
        CatalogProduct,
        CatalogProductChange,
        CatalogPromotionRun,
        ETLLoadRun,
    )
    from db.session import create_session_factory

    response = page.request.get(
        f"{API_URL}/api/v1/etl-loads",
        params={
            "filename": PROMOTION_SOURCE_FILENAME,
            "profile_name": "sample_marketplace_vendor",
            "limit": "10",
        },
    )
    assert response.ok, response.text()
    load_items = response.json()["items"]
    assert len(load_items) == 1
    load_run_id = load_items[0]["etl_load_run_id"]

    session_factory = create_session_factory(
        database_url=os.environ["DATABASE_URL"],
    )
    with session_factory() as session:
        load_run = session.get(ETLLoadRun, load_run_id)
        assert load_run is not None

        succeeded_runs = list(
            session.scalars(
                select(CatalogPromotionRun).where(
                    CatalogPromotionRun.etl_load_run_id == load_run_id,
                    CatalogPromotionRun.status == "succeeded",
                )
            )
        )
        assert len(succeeded_runs) == 1
        promotion_run = succeeded_runs[0]
        assert promotion_run.preview_hash is not None
        assert len(promotion_run.preview_hash) == 64

        applying_count = session.scalar(
            select(func.count()).select_from(CatalogPromotionRun).where(
                CatalogPromotionRun.etl_load_run_id == load_run_id,
                CatalogPromotionRun.status == "applying",
            )
        )
        assert applying_count == 0

        catalog_product_count = session.scalar(
            select(func.count()).select_from(CatalogProduct).where(
                CatalogProduct.supplier_key == "sample_marketplace_vendor",
                CatalogProduct.external_product_id.in_(PROMOTION_PRODUCT_IDS),
            )
        )
        assert catalog_product_count == len(PROMOTION_PRODUCT_IDS)

        change_count = session.scalar(
            select(func.count()).select_from(CatalogProductChange).where(
                CatalogProductChange.promotion_run_id == promotion_run.id,
                CatalogProductChange.action.in_(("insert", "update")),
            )
        )
        assert change_count >= 1
        promotion_run_count = session.scalar(
            select(func.count()).select_from(CatalogPromotionRun).where(
                CatalogPromotionRun.etl_load_run_id == load_run_id
            )
        )
        return {
            "load_run_id": load_run_id,
            "promotion_run_id": promotion_run.id,
            "promotion_run_count": int(promotion_run_count or 0),
            "change_count": int(change_count or 0),
            "catalog_product_count": int(catalog_product_count or 0),
        }


def _run_catalog_promotion_success_scenario(page) -> None:
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

    page.get_by_label("원본 파일명").fill(PROMOTION_SOURCE_FILENAME)
    page.get_by_label("공급사 프로필").fill("sample_marketplace_vendor")
    page.get_by_role("button", name="조회", exact=True).click()

    expect(page.locator("body")).to_contain_text(PROMOTION_SOURCE_FILENAME)
    expect(page.locator("body")).to_contain_text("sample_marketplace_vendor")

    batch_selector = page.get_by_role("combobox", name="적재 배치 선택")
    batch_selector.click()
    page.get_by_role(
        "option",
        name=re.compile(re.escape(PROMOTION_SOURCE_FILENAME)),
    ).click()
    expect(batch_selector).to_have_attribute(
        "aria-label",
        re.compile(re.escape(PROMOTION_SOURCE_FILENAME)),
    )

    preview_button = page.get_by_role(
        "button",
        name="운영 반영 미리보기",
        exact=True,
    )
    expect(preview_button).to_be_enabled()
    preview_button.click()

    expect(page.locator("body")).to_contain_text("반영 가능")
    expect(page.locator("body")).to_contain_text("신규 등록 예정")
    expect(page.locator("body")).to_contain_text("전체 대상 상품")
    expect(page.locator("body")).to_contain_text("상품별 변경 내용")
    expect(page.locator("body")).to_contain_text("공급사")
    expect(page.locator("body")).to_contain_text("외부 상품 ID")
    expect(page.locator("body")).to_contain_text("변경 유형")
    expect(page.locator("body")).to_contain_text("변경 필드")
    expect(page.locator("body")).to_contain_text("변경 전 값")
    expect(page.locator("body")).to_contain_text("변경 후 값")
    expect(page.locator("body")).to_contain_text("신규 등록")
    for product_id in PROMOTION_PRODUCT_IDS:
        expect(page.locator("body")).to_contain_text(product_id)

    promotion_button = page.get_by_role(
        "button",
        name="운영 상품에 반영",
        exact=True,
    )
    expect(promotion_button).to_be_disabled()

    confirmation = page.get_by_label(
        "미리보기 내용을 확인했으며 운영 상품 반영에 동의합니다."
    )
    expect(confirmation).to_be_enabled()
    approval_label = page.get_by_text(
        "미리보기 내용을 확인했으며 운영 상품 반영에 동의합니다.",
        exact=True,
    )
    expect(approval_label).to_be_visible()
    approval_label.click()
    expect(confirmation).to_be_checked()
    expect(promotion_button).to_be_enabled()
    promotion_button.click()

    expect(page.locator("body")).to_contain_text(
        re.compile(
            r"운영 상품 반영이 완료되었습니다\.|"
            r"이미 처리된 ETL 적재 결과입니다\."
        )
    )
    before_history_snapshot = _assert_catalog_promotion_persisted(page)

    expect(page.locator("body")).to_contain_text("Promotion 실행 이력")
    history_selector = page.get_by_role(
        "combobox",
        name="Promotion 실행 선택",
    )
    history_selector.click()
    page.get_by_role(
        "option",
        name=re.compile(r"succeeded"),
    ).click()
    page.get_by_role(
        "button",
        name="Promotion 상세 조회",
        exact=True,
    ).click()

    expect(page.locator("body")).to_contain_text("Promotion 실행 상세")
    expect(page.locator("body")).to_contain_text("상태: succeeded")
    expect(page.locator("body")).to_contain_text("상품 변경 Audit")
    for product_id in PROMOTION_PRODUCT_IDS:
        expect(page.locator("body")).to_contain_text(product_id)

    after_history_snapshot = _assert_catalog_promotion_persisted(page)
    assert after_history_snapshot == before_history_snapshot

    assert not console_errors, f"Unexpected browser console errors: {console_errors}"
    assert not page_errors, f"Unexpected browser page errors: {page_errors}"


def test_catalog_promotion_success_flow_in_real_browser(page):
    try:
        _run_catalog_promotion_success_scenario(page)
    except BaseException:
        _preserve_browser_failure_artifacts(page)
        raise


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

    batch_selector = page.get_by_role("combobox", name="적재 배치 선택")
    batch_selector.click()
    page.get_by_role(
        "option",
        name=re.compile(re.escape(SOURCE_FILENAME)),
    ).click()
    expect(batch_selector).to_have_attribute(
        "aria-label",
        re.compile(re.escape(SOURCE_FILENAME)),
    )

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
