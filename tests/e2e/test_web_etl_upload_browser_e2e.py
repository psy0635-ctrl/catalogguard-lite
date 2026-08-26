"""Chromium coverage for the Streamlit Web ETL CSV upload flow."""

import os
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.e2e


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "e2e" / "web_etl_upload_vendor.csv"
STREAMLIT_URL = os.environ.get("E2E_STREAMLIT_URL", "http://127.0.0.1:8501")
SOURCE_FILENAME = os.environ.get("E2E_WEB_UPLOAD_SOURCE_FILENAME", FIXTURE_PATH.name)
E2E_OPERATOR_USERNAME = os.environ.get("E2E_OPERATOR_USERNAME", "")
E2E_OPERATOR_PASSWORD = os.environ.get("E2E_OPERATOR_PASSWORD", "")
API_URL = os.environ.get(
    "E2E_API_URL",
    os.environ.get("CATALOGGUARD_API_BASE_URL", "http://127.0.0.1:8000"),
)
PROFILE_ID = "sample_marketplace_vendor_v1"
PRODUCT_IDS = (
    "CG-E2E-WEB-UPLOAD-BLK-M",
    "CG-E2E-WEB-UPLOAD-WHT-L",
)


def _login_as_operator(page) -> None:
    from playwright.sync_api import expect

    assert E2E_OPERATOR_USERNAME and E2E_OPERATOR_PASSWORD, (
        "E2E_OPERATOR_USERNAME/E2E_OPERATOR_PASSWORD 환경변수가 필요합니다."
    )
    expect(page.locator("body")).to_contain_text(
        "좌측 사이드바에서 로그인한 뒤 이용해 주세요."
    )
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


def _expected_profile_definition_sha256() -> str:
    from etl.profile_fingerprint import compute_profile_definition_sha256
    from etl.profile_loader import get_profile_path, load_profile

    return compute_profile_definition_sha256(load_profile(get_profile_path(PROFILE_ID)))


def _expected_application_commit_sha() -> str | None:
    from etl.application_lineage import resolve_application_commit_sha

    return resolve_application_commit_sha()


def _assert_web_upload_persisted(etl_load_run_id: int) -> tuple[str, str | None]:
    from sqlalchemy import func, select

    from db.models import CatalogProductStaging, ETLLoadRun
    from db.session import create_session_factory

    session_factory = create_session_factory(database_url=os.environ["DATABASE_URL"])
    with session_factory() as session:
        load_run = session.get(ETLLoadRun, etl_load_run_id)
        assert load_run is not None
        assert load_run.source_filename == SOURCE_FILENAME
        assert load_run.profile_name == "sample_marketplace_vendor"
        assert load_run.profile_version == "2"
        expected_fingerprint = _expected_profile_definition_sha256()
        assert load_run.profile_definition_sha256 == expected_fingerprint
        expected_application_commit_sha = _expected_application_commit_sha()
        assert load_run.application_commit_sha == expected_application_commit_sha
        assert load_run.initial_source_type == "upload"
        assert load_run.initial_source_ref == SOURCE_FILENAME

        product_count = session.scalar(
            select(func.count())
            .select_from(CatalogProductStaging)
            .where(CatalogProductStaging.etl_load_run_id == etl_load_run_id)
        )
        assert product_count == 2
        staging_product_ids = set(
            session.scalars(
                select(CatalogProductStaging.product_id).where(
                    CatalogProductStaging.etl_load_run_id == etl_load_run_id
                )
            )
        )
        assert staging_product_ids == set(PRODUCT_IDS)
    return expected_fingerprint, expected_application_commit_sha


def _api_headers(page) -> dict[str, str]:
    response = page.request.post(
        f"{API_URL}/api/v1/auth/login",
        data={"username": E2E_OPERATOR_USERNAME, "password": E2E_OPERATOR_PASSWORD},
    )
    assert response.ok, response.text()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _run_web_etl_upload_scenario(page) -> None:
    from playwright.sync_api import expect

    assert FIXTURE_PATH.is_file(), f"Browser E2E fixture is missing: {FIXTURE_PATH}"

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
    expect(page.locator("body")).to_contain_text("ETL 실행")

    profile_selector = page.get_by_role("combobox", name="ETL 실행 프로필")
    expect(profile_selector).to_be_visible()
    profile_selector.click()
    page.get_by_role("option", name="마켓플레이스 공급사 샘플", exact=True).click()
    expect(page.locator("body")).to_contain_text("sample_marketplace_vendor")
    expect(page.locator("body")).to_contain_text("프로필 버전")
    expect(page.locator("body")).to_contain_text(re.compile(r"프로필 버전\s*2"))

    uploader_dropzone = page.get_by_label("공급사 CSV 파일", exact=True)
    file_input = uploader_dropzone.locator('input[type="file"]')
    expect(file_input).to_have_count(1)
    file_input.set_input_files(str(FIXTURE_PATH))
    run_button = page.get_by_role("button", name="ETL 실행", exact=True)
    expect(run_button).to_be_enabled()
    run_button.click()

    success_pattern = re.compile(r"ETL 실행이 완료되었습니다\. 적재 배치 ID:\s*(\d+)")
    expect(page.locator("body")).to_contain_text(success_pattern)
    expect(page.locator("body")).not_to_contain_text(
        "동일한 입력으로 이미 처리된 적재 배치입니다."
    )
    body_text = page.locator("body").inner_text()
    match = success_pattern.search(body_text)
    assert match is not None
    etl_load_run_id = int(match.group(1))
    expected_fingerprint, expected_application_commit_sha = _assert_web_upload_persisted(etl_load_run_id)
    detail_response = page.request.get(
        f"{API_URL}/api/v1/etl-loads/{etl_load_run_id}", headers=_api_headers(page)
    )
    assert detail_response.ok, detail_response.text()
    assert detail_response.json()["profile_definition_sha256"] == expected_fingerprint
    assert detail_response.json()["application_commit_sha"] == expected_application_commit_sha

    expect(page.locator("body")).to_contain_text("ETL 적재 이력")
    page.get_by_label("원본 파일명").fill(SOURCE_FILENAME)
    page.get_by_label("공급사 프로필").fill("sample_marketplace_vendor")
    page.get_by_role("button", name="조회", exact=True).click()
    expect(page.locator("body")).to_contain_text(SOURCE_FILENAME)
    expect(page.locator("body")).to_contain_text("sample_marketplace_vendor")

    batch_selector = page.get_by_role("combobox", name="적재 배치 선택")
    batch_selector.click()
    page.get_by_role(
        "option", name=re.compile(rf"{etl_load_run_id} · {re.escape(SOURCE_FILENAME)}")
    ).click()
    page.get_by_role("button", name="상세 조회", exact=True).click()

    expect(page.locator("body")).to_contain_text("적재 배치 상세")
    expect(page.locator("body")).to_contain_text(f"원본 파일명: {SOURCE_FILENAME}")
    expect(page.locator("body")).to_contain_text(
        "공급사 프로필: sample_marketplace_vendor"
    )
    expect(page.locator("body")).to_contain_text("프로필 버전: 2")
    expect(page.locator("body")).to_contain_text("프로필 정의 SHA-256")
    expect(page.locator("body")).to_contain_text(expected_fingerprint)
    expect(page.locator("body")).to_contain_text("애플리케이션 Commit SHA")
    expect(page.locator("body")).to_contain_text(
        expected_application_commit_sha or "알 수 없음 (legacy/미확인)"
    )
    expect(page.locator("body")).to_contain_text("정상 적재")
    expect(page.locator("body")).to_contain_text("전체 입력")
    expect(page.locator("body")).to_contain_text(PRODUCT_IDS[0])

    assert not console_errors, f"Unexpected browser console errors: {console_errors}"
    assert not page_errors, f"Unexpected browser page errors: {page_errors}"


def test_web_etl_upload_flow_in_real_browser(page):
    try:
        _run_web_etl_upload_scenario(page)
    except BaseException:
        _preserve_browser_failure_artifacts(page)
        raise
