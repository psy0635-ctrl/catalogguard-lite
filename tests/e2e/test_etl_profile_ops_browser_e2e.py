"""Chromium coverage for the Streamlit ETL profile operations flow."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import pytest


pytestmark = pytest.mark.e2e


PROFILE_ID = "sample_fashion_vendor_v1"
PROFILE_DISPLAY_NAME = "패션 공급사 샘플"
DEPLOYMENT_DEFAULT_VERSION = "2"
ARCHIVED_VERSION = "1"
STREAMLIT_URL = os.environ.get("E2E_STREAMLIT_URL", "http://127.0.0.1:8501")
E2E_OPERATOR_USERNAME = os.environ.get("E2E_OPERATOR_USERNAME", "")
E2E_OPERATOR_PASSWORD = os.environ.get("E2E_OPERATOR_PASSWORD", "")
DEACTIVATE_CONFIRMATION = "이 프로필의 신규 ETL 실행을 중단하는 것을 확인했습니다."
RESET_CONFIRMATION = "런타임 설정을 제거하고 배포 기본값으로 되돌리는 것을 확인했습니다."


@dataclass(frozen=True)
class _ActivationRowSnapshot:
    id: int
    active_version: str | None
    actor_user_id: int | None
    actor_username: str | None
    updated_at: object


@dataclass(frozen=True)
class _ProfileOpsDatabaseSnapshot:
    activation_row: _ActivationRowSnapshot | None
    baseline_event_id: int


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


def _snapshot_and_clear_runtime_override() -> _ProfileOpsDatabaseSnapshot:
    """Start deterministically without creating a setup audit event.

    Activation current-state is persistent per profile.  The browser flow must prove
    the deployment-default state first, so local test setup removes only this
    profile's row directly instead of calling reset and adding an unexpected event.
    """
    from sqlalchemy import delete, func, select

    from db.models import ETLProfileActivation, ETLProfileActivationEvent

    with _new_session() as session:
        row = session.scalars(
            select(ETLProfileActivation).where(
                ETLProfileActivation.profile_id == PROFILE_ID
            )
        ).one_or_none()
        row_snapshot = (
            _ActivationRowSnapshot(
                id=row.id,
                active_version=row.active_version,
                actor_user_id=row.actor_user_id,
                actor_username=row.actor_username,
                updated_at=row.updated_at,
            )
            if row is not None
            else None
        )
        baseline_event_id = int(
            session.scalar(
                select(func.coalesce(func.max(ETLProfileActivationEvent.id), 0)).where(
                    ETLProfileActivationEvent.profile_id == PROFILE_ID
                )
            )
            or 0
        )
        session.execute(
            delete(ETLProfileActivation).where(
                ETLProfileActivation.profile_id == PROFILE_ID
            )
        )
        session.commit()
    return _ProfileOpsDatabaseSnapshot(
        activation_row=row_snapshot,
        baseline_event_id=baseline_event_id,
    )


def _restore_profile_ops_database(snapshot: _ProfileOpsDatabaseSnapshot) -> None:
    """Restore only this local E2E's current row and newly created audit events."""
    from sqlalchemy import delete

    from db.models import ETLProfileActivation, ETLProfileActivationEvent

    with _new_session() as session:
        # The history table is append-only in production.  This direct delete is
        # disposable-test cleanup, scoped to this profile, this actor, and events
        # created after this test's baseline so prior audit evidence stays intact.
        session.execute(
            delete(ETLProfileActivationEvent).where(
                ETLProfileActivationEvent.profile_id == PROFILE_ID,
                ETLProfileActivationEvent.actor_username == E2E_OPERATOR_USERNAME,
                ETLProfileActivationEvent.id > snapshot.baseline_event_id,
            )
        )
        session.execute(
            delete(ETLProfileActivation).where(
                ETLProfileActivation.profile_id == PROFILE_ID
            )
        )
        if snapshot.activation_row is not None:
            session.add(
                ETLProfileActivation(
                    id=snapshot.activation_row.id,
                    profile_id=PROFILE_ID,
                    active_version=snapshot.activation_row.active_version,
                    actor_user_id=snapshot.activation_row.actor_user_id,
                    actor_username=snapshot.activation_row.actor_username,
                    updated_at=snapshot.activation_row.updated_at,
                )
            )
        session.commit()

    from sqlalchemy import select

    with _new_session() as session:
        restored = session.scalars(
            select(ETLProfileActivation).where(
                ETLProfileActivation.profile_id == PROFILE_ID
            )
        ).one_or_none()
        if snapshot.activation_row is None:
            assert restored is None
        else:
            assert restored is not None
            assert restored.profile_id == PROFILE_ID
            assert restored.active_version == snapshot.activation_row.active_version
            assert restored.actor_user_id == snapshot.activation_row.actor_user_id
            assert restored.actor_username == snapshot.activation_row.actor_username
            assert restored.updated_at == snapshot.activation_row.updated_at


def _assert_current_state(*, active_version: str | None) -> None:
    from sqlalchemy import select

    from db.models import ETLProfileActivation

    with _new_session() as session:
        row = session.scalars(
            select(ETLProfileActivation).where(
                ETLProfileActivation.profile_id == PROFILE_ID
            )
        ).one_or_none()
    if active_version is None:
        assert row is not None
        assert row.active_version is None
        assert row.actor_username == E2E_OPERATOR_USERNAME
    else:
        assert row is not None
        assert row.active_version == active_version
        assert row.actor_username == E2E_OPERATOR_USERNAME


def _assert_reset_removed_current_state() -> None:
    from sqlalchemy import select

    from db.models import ETLProfileActivation

    with _new_session() as session:
        row = session.scalars(
            select(ETLProfileActivation).where(
                ETLProfileActivation.profile_id == PROFILE_ID
            )
        ).one_or_none()
    assert row is None


def _assert_new_history(snapshot: _ProfileOpsDatabaseSnapshot) -> None:
    from sqlalchemy import select

    from db.models import ETLProfileActivationEvent

    with _new_session() as session:
        events = list(
            session.scalars(
                select(ETLProfileActivationEvent)
                .where(
                    ETLProfileActivationEvent.profile_id == PROFILE_ID,
                    ETLProfileActivationEvent.actor_username == E2E_OPERATOR_USERNAME,
                    ETLProfileActivationEvent.id > snapshot.baseline_event_id,
                )
                .order_by(ETLProfileActivationEvent.id)
            )
        )

    assert [event.action for event in events] == ["deactivate", "activate", "reset"]
    deactivate, activate, reset = events
    assert deactivate.runtime_override_exists is True
    assert deactivate.runtime_active_version is None
    assert deactivate.effective_active_version is None
    assert activate.runtime_override_exists is True
    assert activate.runtime_active_version == ARCHIVED_VERSION
    assert activate.effective_active_version == ARCHIVED_VERSION
    assert reset.runtime_override_exists is False
    assert reset.runtime_active_version is None
    assert reset.effective_active_version == DEPLOYMENT_DEFAULT_VERSION
    assert all(event.actor_username == E2E_OPERATOR_USERNAME for event in events)


def _visible_history_actions(page) -> list[str]:
    """Read visible dataframe cells only; the full virtual grid is not guaranteed."""
    action_labels = {
        "비활성화",
        "버전 활성화",
        "배포 기본값으로 되돌리기",
    }
    return [
        text
        for text in page.locator("td[role='gridcell']").all_inner_texts()
        if text in action_labels
    ]


def _history_action_cell(page, action_label: str):
    """Use the dataframe's semantic cell role, which Streamlit puts below canvas."""
    return page.locator(
        "td[role='gridcell']",
        has_text=re.compile(rf"^{re.escape(action_label)}$"),
    )


def _run_profile_operations_scenario(page, snapshot: _ProfileOpsDatabaseSnapshot) -> None:
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

    expect(page.get_by_text("ETL 프로필 운영 관리", exact=True)).to_be_visible()
    profile_selector = page.get_by_role("combobox", name="관리할 ETL 프로필")
    expect(profile_selector).to_be_visible()
    profile_selector.click()
    page.get_by_role("option", name=PROFILE_DISPLAY_NAME, exact=True).click()

    # The direct test-only setup above makes the first UI state deployment default.
    expect(page.locator("body")).to_contain_text("🟢 활성")
    expect(page.locator("body")).to_contain_text(f"v{DEPLOYMENT_DEFAULT_VERSION}")
    expect(
        page.get_by_text(
            "런타임 설정: 런타임 override 없음 (배포 기본값 사용)",
            exact=True,
        )
    ).to_be_visible()

    deactivate_button = page.get_by_role("button", name="비활성화", exact=True)
    expect(deactivate_button).to_be_disabled()
    deactivate_confirmation = page.get_by_label(DEACTIVATE_CONFIRMATION)
    expect(deactivate_confirmation).to_be_enabled()
    page.get_by_text(DEACTIVATE_CONFIRMATION, exact=True).click()
    expect(deactivate_confirmation).to_be_checked()
    expect(deactivate_button).to_be_enabled()
    deactivate_button.click()

    expect(page.get_by_text(f"{PROFILE_ID} 프로필을 비활성화했습니다.", exact=True)).to_be_visible()
    expect(page.locator("body")).to_contain_text("🔴 비활성")
    expect(
        page.get_by_text("런타임 설정: 런타임에서 비활성으로 지정", exact=True)
    ).to_be_visible()
    _assert_current_state(active_version=None)

    expect(page.get_by_text("Activation 운영 이력", exact=True)).to_be_visible()
    # Streamlit paints dataframe values on canvas and keeps its semantic table as
    # an accessibility fallback, so the cell itself is intentionally hidden.
    expect(_history_action_cell(page, "비활성화")).to_have_count(1)

    version_selector = page.get_by_role("combobox", name="활성화할 보존 버전")
    version_selector.click()
    page.get_by_role("option", name=f"v{ARCHIVED_VERSION}", exact=True).click()
    activate_button = page.get_by_role("button", name="선택한 버전 활성화", exact=True)
    expect(activate_button).to_be_enabled()
    activate_button.click()

    expect(
        page.get_by_text(
            f"{PROFILE_ID} 프로필을 v{ARCHIVED_VERSION}(으)로 활성화했습니다.",
            exact=True,
        )
    ).to_be_visible()
    expect(page.locator("body")).to_contain_text("🟢 활성")
    expect(page.locator("body")).to_contain_text(f"v{ARCHIVED_VERSION}")
    expect(
        page.get_by_text(
            f"런타임 설정: 런타임에서 v{ARCHIVED_VERSION} 활성으로 지정",
            exact=True,
        )
    ).to_be_visible()
    _assert_current_state(active_version=ARCHIVED_VERSION)

    reset_button = page.get_by_role("button", name="배포 기본값으로 되돌리기", exact=True)
    expect(reset_button).to_be_disabled()
    reset_confirmation = page.get_by_label(RESET_CONFIRMATION)
    expect(reset_confirmation).to_be_enabled()
    page.get_by_text(RESET_CONFIRMATION, exact=True).click()
    expect(reset_confirmation).to_be_checked()
    expect(reset_button).to_be_enabled()
    reset_button.click()

    expect(
        page.get_by_text(
            f"{PROFILE_ID} 프로필의 런타임 설정을 제거했습니다. "
            f"이제 배포 기본값 v{DEPLOYMENT_DEFAULT_VERSION}을(를) 따릅니다.",
            exact=True,
        )
    ).to_be_visible()
    expect(page.locator("body")).to_contain_text("🟢 활성")
    expect(
        page.get_by_text(
            "런타임 설정: 런타임 override 없음 (배포 기본값 사용)",
            exact=True,
        )
    ).to_be_visible()
    _assert_reset_removed_current_state()
    _assert_new_history(snapshot)

    expect(page.get_by_text("Activation 운영 이력", exact=True)).to_be_visible()
    for action_label in (
        "배포 기본값으로 되돌리기",
        "버전 활성화",
        "비활성화",
    ):
        expect(_history_action_cell(page, action_label)).to_have_count(1)
    # st.dataframe is virtualized, so this asserts only the currently rendered
    # rows; PostgreSQL assertions above establish the complete event set.
    assert _visible_history_actions(page) == [
        "배포 기본값으로 되돌리기",
        "버전 활성화",
        "비활성화",
    ]

    assert not console_errors, f"Unexpected browser console errors: {console_errors}"
    assert not page_errors, f"Unexpected browser page errors: {page_errors}"


def test_etl_profile_operations_deactivate_activate_and_reset_in_real_browser(page):
    snapshot = _snapshot_and_clear_runtime_override()
    try:
        _run_profile_operations_scenario(page, snapshot)
    except BaseException:
        _preserve_browser_failure_artifacts(page)
        raise
    finally:
        _restore_profile_ops_database(snapshot)
