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
E2E_OPERATOR_USERNAME = os.environ.get("E2E_OPERATOR_USERNAME", "")
E2E_OPERATOR_PASSWORD = os.environ.get("E2E_OPERATOR_PASSWORD", "")


def _login_as_operator(page) -> None:
    from playwright.sync_api import expect

    assert E2E_OPERATOR_USERNAME and E2E_OPERATOR_PASSWORD, (
        "E2E_OPERATOR_USERNAME/E2E_OPERATOR_PASSWORD 환경변수가 필요합니다."
    )
    expect(page.locator("body")).to_contain_text("좌측 사이드바에서 로그인한 뒤 이용해 주세요.")
    page.get_by_label("아이디").fill(E2E_OPERATOR_USERNAME)
    page.get_by_label("비밀번호").fill(E2E_OPERATOR_PASSWORD)
    page.get_by_role("button", name="로그인", exact=True).click()
    expect(page.get_by_role("tab", name="ETL 적재 이력")).to_be_visible()


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


def _read_rollback_change_audit_text(page) -> str:
    """Return the text of the "상품 Rollback 변경 Audit" section only.

    Promotion Audit renders the same fixture product IDs earlier on the page,
    so page-wide assertions cannot prove the rollback change grid itself was
    rendered from the rollback changes API.
    """
    heading = "상품 Rollback 변경 Audit"
    caption_prefix = "Change Audit "
    body_text = page.locator("body").text_content() or ""
    start = body_text.index(heading) + len(heading)
    end = body_text.index(caption_prefix, start)
    return body_text[start:end]


def _assert_catalog_promotion_persisted(page) -> dict[str, int]:
    from sqlalchemy import func, select

    from db.models import (
        CatalogProduct,
        CatalogProductChange,
        CatalogPromotionRun,
        ETLLoadRun,
    )
    from db.session import create_session_factory

    login_response = page.request.post(
        f"{API_URL}/api/v1/auth/login",
        data={
            "username": E2E_OPERATOR_USERNAME,
            "password": E2E_OPERATOR_PASSWORD,
        },
    )
    assert login_response.ok, login_response.text()
    access_token = login_response.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    response = page.request.get(
        f"{API_URL}/api/v1/etl-loads",
        headers=auth_headers,
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
        insert_change_count = session.scalar(
            select(func.count()).select_from(CatalogProductChange).where(
                CatalogProductChange.promotion_run_id == promotion_run.id,
                CatalogProductChange.action == "insert",
            )
        )
        update_change_count = session.scalar(
            select(func.count()).select_from(CatalogProductChange).where(
                CatalogProductChange.promotion_run_id == promotion_run.id,
                CatalogProductChange.action == "update",
            )
        )
        assert (insert_change_count or 0) + (update_change_count or 0) == change_count
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
            "insert_change_count": int(insert_change_count or 0),
            "update_change_count": int(update_change_count or 0),
            "catalog_product_count": int(catalog_product_count or 0),
        }


def _assert_catalog_rollback_persisted(
    promotion_snapshot: dict[str, int],
) -> dict[str, int]:
    from sqlalchemy import func, select

    from db.models import (
        CatalogProduct,
        CatalogProductChange,
        CatalogPromotionRollback,
        CatalogPromotionRollbackChange,
    )
    from db.session import create_session_factory

    session_factory = create_session_factory(
        database_url=os.environ["DATABASE_URL"],
    )
    with session_factory() as session:
        succeeded_rollbacks = list(
            session.scalars(
                select(CatalogPromotionRollback).where(
                    CatalogPromotionRollback.target_promotion_run_id
                    == promotion_snapshot["promotion_run_id"],
                    CatalogPromotionRollback.status == "succeeded",
                )
            )
        )
        assert len(succeeded_rollbacks) == 1
        rollback_run = succeeded_rollbacks[0]
        assert rollback_run.preview_hash is not None
        assert re.fullmatch(r"[0-9a-f]{64}", rollback_run.preview_hash)
        assert rollback_run.preview_schema_version
        assert rollback_run.conflict_count == 0
        assert rollback_run.restored_count == promotion_snapshot["update_change_count"]
        assert rollback_run.deleted_count == promotion_snapshot["insert_change_count"]
        assert rollback_run.actor_username == E2E_OPERATOR_USERNAME

        applying_count = session.scalar(
            select(func.count()).select_from(CatalogPromotionRollback).where(
                CatalogPromotionRollback.target_promotion_run_id
                == promotion_snapshot["promotion_run_id"],
                CatalogPromotionRollback.status == "applying",
            )
        )
        assert applying_count == 0

        rollback_changes = list(
            session.scalars(
                select(CatalogPromotionRollbackChange).where(
                    CatalogPromotionRollbackChange.rollback_run_id == rollback_run.id
                )
            )
        )
        assert len(rollback_changes) == promotion_snapshot["change_count"]
        assert sum(change.action == "delete" for change in rollback_changes) == (
            promotion_snapshot["insert_change_count"]
        )
        assert sum(change.action == "restore" for change in rollback_changes) == (
            promotion_snapshot["update_change_count"]
        )

        assert {
            (change.before_data or {}).get("external_product_id")
            for change in rollback_changes
        } == set(PROMOTION_PRODUCT_IDS)

        promotion_audit_count = session.scalar(
            select(func.count()).select_from(CatalogProductChange).where(
                CatalogProductChange.promotion_run_id
                == promotion_snapshot["promotion_run_id"]
            )
        )
        assert promotion_audit_count == promotion_snapshot["change_count"]

        promotion_audit_ids = set(
            session.scalars(
                select(CatalogProductChange.id).where(
                    CatalogProductChange.promotion_run_id
                    == promotion_snapshot["promotion_run_id"]
                )
            )
        )
        assert {
            change.original_audit_id for change in rollback_changes
        } == promotion_audit_ids

        catalog_product_count = session.scalar(
            select(func.count()).select_from(CatalogProduct).where(
                CatalogProduct.supplier_key == "sample_marketplace_vendor",
                CatalogProduct.external_product_id.in_(PROMOTION_PRODUCT_IDS),
            )
        )
        assert catalog_product_count == promotion_snapshot["update_change_count"]

        return {
            "rollback_run_id": rollback_run.id,
            "restored_count": rollback_run.restored_count,
            "deleted_count": rollback_run.deleted_count,
            "conflict_count": rollback_run.conflict_count,
            "rollback_change_count": len(rollback_changes),
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

    _login_as_operator(page)

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

    rollback_preview_button = page.get_by_role(
        "button",
        name="Rollback Preview",
        exact=True,
    )
    expect(rollback_preview_button).to_be_enabled()
    rollback_preview_button.click()

    expect(page.locator("body")).to_contain_text("Rollback is available.")
    expect(page.locator("body")).to_contain_text(
        re.compile(
            rf"Restore\s*{before_history_snapshot['update_change_count']}"
        )
    )
    expect(page.locator("body")).to_contain_text(
        re.compile(
            rf"Delete\s*{before_history_snapshot['insert_change_count']}"
        )
    )
    expect(page.locator("body")).to_contain_text(re.compile(r"Conflict\s*0"))

    rollback_button = page.get_by_role(
        "button",
        name="Execute Rollback",
        exact=True,
    )
    expect(rollback_button).to_be_disabled()
    rollback_confirmation = page.get_by_label(
        "I reviewed the rollback preview and confirm execution."
    )
    expect(rollback_confirmation).to_be_enabled()
    rollback_confirmation_label = page.get_by_text(
        "I reviewed the rollback preview and confirm execution.",
        exact=True,
    )
    expect(rollback_confirmation_label).to_be_visible()
    rollback_confirmation_label.click()
    expect(rollback_confirmation).to_be_checked()
    expect(rollback_button).to_be_enabled()
    rollback_button.click()

    expect(page.locator("body")).to_contain_text(
        "Rollback completed. Rollback run ID:"
    )
    expect(page.locator("body")).to_contain_text(
        f"Executed by: {E2E_OPERATOR_USERNAME}"
    )
    expect(page.locator("body")).to_contain_text("Rollback 실행 이력")

    rollback_snapshot = _assert_catalog_rollback_persisted(before_history_snapshot)
    rollback_history_selector = page.get_by_role(
        "combobox",
        name="Rollback 실행 선택",
    )
    rollback_history_selector.click()
    page.get_by_role(
        "option",
        name=re.compile(
            rf"{rollback_snapshot['rollback_run_id']} · Promotion "
            rf"{before_history_snapshot['promotion_run_id']} · succeeded"
        ),
    ).click()
    page.get_by_role(
        "button",
        name="Rollback 상세 조회",
        exact=True,
    ).click()

    expect(page.locator("body")).to_contain_text("Rollback 실행 상세")
    expect(page.locator("body")).to_contain_text(
        f"Rollback ID: {rollback_snapshot['rollback_run_id']}"
    )
    expect(page.locator("body")).to_contain_text(
        f"대상 Promotion ID: {before_history_snapshot['promotion_run_id']}"
    )
    expect(page.locator("body")).to_contain_text("상태: succeeded")
    expect(page.locator("body")).to_contain_text(
        f"실행 사용자: {E2E_OPERATOR_USERNAME}"
    )
    expect(page.locator("body")).to_contain_text(
        re.compile(rf"복구 상품\s*{rollback_snapshot['restored_count']}")
    )
    expect(page.locator("body")).to_contain_text(
        re.compile(rf"삭제 상품\s*{rollback_snapshot['deleted_count']}")
    )
    expect(page.locator("body")).to_contain_text(
        re.compile(rf"충돌\s*{rollback_snapshot['conflict_count']}")
    )
    page.get_by_text("Rollback Preview 정보", exact=True).click()
    expect(page.locator("body")).to_contain_text("Preview schema version:")
    expect(page.locator("body")).to_contain_text(
        re.compile(r"Preview SHA-256:\s*[0-9a-f]{64}")
    )

    expect(
        page.get_by_role("heading", name="상품 Rollback 변경 Audit")
    ).to_be_visible()
    expect(page.locator("body")).to_contain_text(
        "Rollback으로 삭제·복원된 상품의 필드별 변경 이력입니다."
    )
    expect(page.locator("body")).to_contain_text(
        "Change Audit 1 / 1 페이지 · 전체 "
        f"{rollback_snapshot['rollback_change_count']}건"
    )
    expect(
        page.get_by_role("button", name="Change 이전", exact=True)
    ).to_be_disabled()
    expect(
        page.get_by_role("button", name="Change 다음", exact=True)
    ).to_be_disabled()

    # 표 헤더와 셀 값은 캡션·버튼보다 늦게 그려지므로 표가 실제로 렌더링될 때까지
    # 기다린 뒤에 Change Audit 영역 텍스트를 읽습니다.
    expect(page.locator("body")).to_contain_text("원본 Audit ID")
    expect(page.locator("body")).to_contain_text("삭제됨")

    change_audit_text = _read_rollback_change_audit_text(page)
    for column_name in (
        "원본 Audit ID",
        "외부 상품 ID",
        "변경 유형",
        "변경 필드",
        "변경 전",
        "변경 후",
    ):
        assert column_name in change_audit_text, (
            f"Rollback change audit column {column_name!r} is missing: "
            f"{change_audit_text!r}"
        )
    assert "상품 삭제" in change_audit_text, (
        f"Rollback change audit is missing the delete action label: "
        f"{change_audit_text!r}"
    )
    assert "이전 상태 복원" not in change_audit_text, (
        f"Rollback change audit unexpectedly reported a restore: "
        f"{change_audit_text!r}"
    )
    assert "삭제됨" in change_audit_text, (
        f"Rollback change audit is missing the deleted after-value: "
        f"{change_audit_text!r}"
    )
    # st.dataframe은 가상 스크롤이라 접근성 DOM에 첫 화면 행만 노출됩니다. 두 상품이
    # 모두 Rollback Change로 저장됐다는 검증은 _assert_catalog_rollback_persisted의
    # PostgreSQL assertion이 담당하고, 여기서는 렌더링 경계에 의존하지 않도록
    # fixture 상품이 최소 하나 표시되는지만 확인합니다.
    assert any(
        product_id in change_audit_text for product_id in PROMOTION_PRODUCT_IDS
    ), (
        f"Rollback change audit shows none of {PROMOTION_PRODUCT_IDS}: "
        f"{change_audit_text!r}"
    )
    for field_name in ("category", "color", "product_name"):
        assert field_name in change_audit_text, (
            f"Rollback change audit is missing changed field {field_name!r}: "
            f"{change_audit_text!r}"
        )

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

    _login_as_operator(page)

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
