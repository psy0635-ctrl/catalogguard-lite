"""Chromium coverage for the Streamlit ETL quality observability flow."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest


pytestmark = pytest.mark.e2e


PROFILE_NAME = "browser_e2e_quality_vendor"
STREAMLIT_URL = os.environ.get("E2E_STREAMLIT_URL", "http://127.0.0.1:8501")
API_URL = os.environ.get(
    "E2E_API_URL",
    os.environ.get("CATALOGGUARD_API_BASE_URL", "http://127.0.0.1:8000"),
)
E2E_OPERATOR_USERNAME = os.environ.get("E2E_OPERATOR_USERNAME", "")
E2E_OPERATOR_PASSWORD = os.environ.get("E2E_OPERATOR_PASSWORD", "")


@dataclass(frozen=True)
class _QualityBatchSnapshot:
    id: int
    source_filename: str
    profile_name: str
    profile_version: str
    input_file_sha256: str
    output_file_sha256: str
    total_rows: int
    loaded_rows: int
    rejected_rows: int
    error_counts: dict[str, int]
    initial_source_type: str
    initial_source_ref: str | None
    actor_user_id: int | None
    actor_username: str | None
    created_at: datetime


@dataclass(frozen=True)
class _QualityFixture:
    previous: _QualityBatchSnapshot
    latest: _QualityBatchSnapshot
    baseline_max_load_run_id: int

    @property
    def created_ids(self) -> tuple[int, int]:
        return (self.previous.id, self.latest.id)


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


def _new_session():
    from db.session import create_session_factory

    return create_session_factory(database_url=os.environ["DATABASE_URL"])()


def _snapshot_batch(load_run) -> _QualityBatchSnapshot:
    assert load_run.total_rows is not None
    assert load_run.rejected_rows is not None
    assert load_run.error_counts is not None
    return _QualityBatchSnapshot(
        id=load_run.id,
        source_filename=load_run.source_filename,
        profile_name=load_run.profile_name,
        profile_version=load_run.profile_version,
        input_file_sha256=load_run.input_file_sha256,
        output_file_sha256=load_run.output_file_sha256,
        total_rows=load_run.total_rows,
        loaded_rows=load_run.loaded_rows,
        rejected_rows=load_run.rejected_rows,
        error_counts=dict(load_run.error_counts),
        initial_source_type=load_run.initial_source_type,
        initial_source_ref=load_run.initial_source_ref,
        actor_user_id=load_run.actor_user_id,
        actor_username=load_run.actor_username,
        created_at=load_run.created_at,
    )


def _make_hash() -> str:
    return uuid4().hex * 2


def _create_quality_fixture() -> _QualityFixture:
    """Create only the two quality-metadata rows this read-only E2E needs."""
    from sqlalchemy import func, select

    from db.models import ETLLoadRun

    with _new_session() as session:
        previous = ETLLoadRun(
            source_filename="browser_e2e_quality_previous.csv",
            profile_name=PROFILE_NAME,
            profile_version="e2e-quality",
            input_file_sha256=_make_hash(),
            output_file_sha256=_make_hash(),
            total_rows=10,
            loaded_rows=8,
            rejected_rows=2,
            error_counts={"missing_required": 2},
            created_at=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        )
        latest = ETLLoadRun(
            source_filename="browser_e2e_quality_latest.csv",
            profile_name=PROFILE_NAME,
            profile_version="e2e-quality",
            input_file_sha256=_make_hash(),
            output_file_sha256=_make_hash(),
            total_rows=10,
            loaded_rows=9,
            rejected_rows=1,
            error_counts={"missing_required": 1},
            created_at=datetime(2026, 1, 1, 11, tzinfo=timezone.utc),
        )
        session.add_all((previous, latest))
        session.flush()
        fixture = _QualityFixture(
            previous=_snapshot_batch(previous),
            latest=_snapshot_batch(latest),
            baseline_max_load_run_id=int(
                session.scalar(select(func.max(ETLLoadRun.id)))
            ),
        )
        session.commit()
    return fixture


def _assert_fixture_unchanged(fixture: _QualityFixture) -> None:
    from sqlalchemy import func, select

    from db.models import ETLLoadRun

    with _new_session() as session:
        rows = {
            row.id: _snapshot_batch(row)
            for row in session.scalars(
                select(ETLLoadRun).where(ETLLoadRun.id.in_(fixture.created_ids))
            )
        }
        assert rows == {
            fixture.previous.id: fixture.previous,
            fixture.latest.id: fixture.latest,
        }
        assert int(session.scalar(select(func.max(ETLLoadRun.id))) or 0) == (
            fixture.baseline_max_load_run_id
        )


def _cleanup_quality_fixture(fixture: _QualityFixture) -> None:
    from sqlalchemy import delete, select

    from db.models import ETLLoadRun

    with _new_session() as session:
        # Exact primary keys are retained from setup. This never deletes another
        # supplier's history or rows created by the existing browser scenarios.
        session.execute(delete(ETLLoadRun).where(ETLLoadRun.id.in_(fixture.created_ids)))
        session.commit()

    with _new_session() as session:
        remaining = list(
            session.scalars(
                select(ETLLoadRun.id).where(ETLLoadRun.id.in_(fixture.created_ids))
            )
        )
    assert remaining == []


def _api_headers(page) -> dict[str, str]:
    response = page.request.post(
        f"{API_URL}/api/v1/auth/login",
        data={
            "username": E2E_OPERATOR_USERNAME,
            "password": E2E_OPERATOR_PASSWORD,
        },
    )
    assert response.ok, response.text()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _dataframe_grid_with_column(page, column_name: str):
    """Locate a Streamlit dataframe through stable ARIA roles, not UI classes."""
    return page.locator("table[role='grid']").filter(
        has=page.locator(
            "th[role='columnheader']",
            has_text=re.compile(rf"^{re.escape(column_name)}$"),
        )
    )


def _dataframe_grid_cell(grid, value: str):
    return grid.locator(
        "td[role='gridcell']",
        has_text=re.compile(rf"^{re.escape(value)}$"),
    )


def _metric_text(page, value: str):
    """Scope values to metric paragraphs, excluding dataframe grid cells."""
    return page.locator("p").filter(has_text=re.compile(rf"^{re.escape(value)}$"))


def _assert_api_observability(page, fixture: _QualityFixture) -> None:
    headers = _api_headers(page)
    profiles_response = page.request.get(
        f"{API_URL}/api/v1/etl-loads/quality-observability/profiles",
        headers=headers,
    )
    assert profiles_response.ok, profiles_response.text()
    assert {"profile_name": PROFILE_NAME} in profiles_response.json()["items"]

    response = page.request.get(
        f"{API_URL}/api/v1/etl-loads/quality-observability",
        headers=headers,
        params={"profile_name": PROFILE_NAME, "limit": "10"},
    )
    assert response.ok, response.text()
    payload = response.json()
    assert payload["profile_name"] == PROFILE_NAME
    assert payload["batch_count"] == 2
    assert payload["latest_batch"] == {
        "etl_load_run_id": fixture.latest.id,
        "created_at": fixture.latest.created_at.isoformat().replace("+00:00", "Z"),
        "total_rows": 10,
        "loaded_rows": 9,
        "rejected_rows": 1,
        "rejection_rate": 10.0,
    }
    assert payload["previous_batch"] == {
        "etl_load_run_id": fixture.previous.id,
        "created_at": fixture.previous.created_at.isoformat().replace("+00:00", "Z"),
        "total_rows": 10,
        "loaded_rows": 8,
        "rejected_rows": 2,
        "rejection_rate": 20.0,
    }
    assert payload["rejection_rate_delta"] == -10.0
    assert payload["direction"] == "improved"
    assert payload["error_codes"] == [
        {
            "error_code": "missing_required",
            "total_count": 3,
            "affected_batch_count": 2,
        }
    ]
    assert [item["etl_load_run_id"] for item in payload["recent_batches"]] == [
        fixture.previous.id,
        fixture.latest.id,
    ]


def _run_quality_observability_scenario(page, fixture: _QualityFixture) -> None:
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

    expect(page.get_by_text("ETL 품질 관찰", exact=True)).to_be_visible()
    profile_selector = page.get_by_role("combobox", name="관찰할 공급사")
    expect(profile_selector).to_be_visible()
    _assert_api_observability(page, fixture)
    profile_selector.click()
    page.get_by_role("option", name=PROFILE_NAME, exact=True).click()

    expect(page.get_by_text("최신 Reject 비율", exact=True)).to_be_visible()
    expect(page.get_by_text("직전 Reject 비율", exact=True)).to_be_visible()
    expect(page.get_by_text("변화량", exact=True)).to_be_visible()
    expect(page.get_by_text("방향", exact=True)).to_be_visible()
    for value in ("10.00%", "20.00%", "-10.00%p", "개선"):
        expect(_metric_text(page, value)).to_have_count(1)
        expect(_metric_text(page, value)).to_be_visible()
    expect(
        page.get_by_text("Reject 비율이 직전 배치보다 낮아졌습니다.", exact=True)
    ).to_be_visible()

    expect(page.get_by_text("주요 오류 코드", exact=True)).to_be_visible()
    # Streamlit dataframe cells are accessibility fallbacks beneath the canvas.
    # Assert the unique error-code boundary here; API/DB assertions above prove
    # its complete count aggregation without depending on virtualized rows.
    error_code_grid = _dataframe_grid_with_column(page, "오류 코드")
    expect(error_code_grid).to_have_count(1)
    expect(_dataframe_grid_cell(error_code_grid, "missing_required")).to_have_count(1)

    expect(page.get_by_text("관찰한 배치", exact=True)).to_be_visible()
    expect(page.locator("body")).to_contain_text(
        "품질 정보가 있는 최근 2개 배치입니다. 오래된 배치부터 표시합니다."
    )
    # The page-wide load history also uses this header. Its grid does not have
    # both percentage values, so identify the observed-batches table by the
    # complete, deterministic semantic content instead of DOM position.
    observed_batches_grid = _dataframe_grid_with_column(page, "적재 배치 ID")
    observed_grid_texts = observed_batches_grid.all_inner_texts()
    assert any(
        all(
            value in grid_text
            for value in (
                str(fixture.previous.id),
                str(fixture.latest.id),
                "20.00%",
                "10.00%",
            )
        )
        for grid_text in observed_grid_texts
    )

    _assert_fixture_unchanged(fixture)
    assert not console_errors, f"Unexpected browser console errors: {console_errors}"
    assert not page_errors, f"Unexpected browser page errors: {page_errors}"


def test_etl_quality_observability_in_real_browser(page):
    fixture = _create_quality_fixture()
    try:
        _run_quality_observability_scenario(page, fixture)
    except BaseException:
        _preserve_browser_failure_artifacts(page)
        raise
    finally:
        _cleanup_quality_fixture(fixture)
