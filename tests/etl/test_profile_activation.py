"""Deployment-based activation / deactivation of an ETL profile.

Phase 5A of docs/etl_profile_lifecycle.md. active_version은 "버전 문자열" 또는 None이고,
None은 Policy G의 Deactivate(삭제 아님)입니다. 신규 ETL 실행만 막고 archive는 남습니다.

active pointer 해석 자체(자동 추론 금지, 잘못된 pointer 거부)는
tests/etl/test_profile_version_archive.py가 이미 고정하고 있으므로 여기서는
"활성 / 비활성" 두 상태의 차이만 검증합니다.
"""
import pytest

import etl.profile_loader as profile_loader
from etl.profile_loader import (
    ETLProfileInactiveError,
    ETLProfileNotFoundError,
    get_etl_profile_detail,
    get_profile_path,
    get_profile_version_path,
    list_etl_profiles,
    load_profile,
)


FASHION_PROFILE_ID = "sample_fashion_vendor_v1"
MARKETPLACE_PROFILE_ID = "sample_marketplace_vendor_v1"


def registry_entry_with(profile_id: str, **changes: object) -> dict:
    """Copy one registry entry so a test never mutates the shared registry."""
    entry = dict(profile_loader._ETL_PROFILE_REGISTRY[profile_id])
    entry.update(changes)
    return entry


@pytest.fixture(name="deactivate")
def fixture_deactivate(monkeypatch):
    def apply(profile_id: str) -> None:
        monkeypatch.setitem(
            profile_loader._ETL_PROFILE_REGISTRY,
            profile_id,
            registry_entry_with(profile_id, active_version=None),
        )

    return apply


# --- Activation ------------------------------------------------------------


def test_current_profiles_stay_active_on_version_two():
    # Phase 5A는 실제 프로필을 비활성화하는 작업이 아닙니다. 두 프로필 모두 active v2입니다.
    for profile_id in (FASHION_PROFILE_ID, MARKETPLACE_PROFILE_ID):
        assert profile_loader._ETL_PROFILE_REGISTRY[profile_id]["active_version"] == "2"
        assert load_profile(get_profile_path(profile_id)).version == "2"


@pytest.mark.parametrize(("active_version", "expected_filename"), [("2", "v2.json"), ("1", "v1.json")])
def test_active_pointer_selects_exactly_that_version(
    monkeypatch, active_version, expected_filename
):
    monkeypatch.setitem(
        profile_loader._ETL_PROFILE_REGISTRY,
        FASHION_PROFILE_ID,
        registry_entry_with(FASHION_PROFILE_ID, active_version=active_version),
    )

    active_path = get_profile_path(FASHION_PROFILE_ID)

    assert active_path.name == expected_filename
    assert load_profile(active_path).version == active_version


# --- Deactivation ----------------------------------------------------------


def test_deactivated_profile_blocks_a_new_etl_run(deactivate):
    deactivate(FASHION_PROFILE_ID)

    with pytest.raises(ETLProfileInactiveError):
        get_profile_path(FASHION_PROFILE_ID)


def test_deactivated_profile_does_not_fall_back_to_an_archived_version(deactivate):
    deactivate(FASHION_PROFILE_ID)

    # archive는 그대로 있는데도 실행용 경로를 주면 안 됩니다. 비활성은 "무엇을 실행할지
    # 정해지지 않은" 상태이지 "아무 버전이나 써도 되는" 상태가 아닙니다.
    assert profile_loader._ETL_PROFILE_REGISTRY[FASHION_PROFILE_ID]["versions"]
    with pytest.raises(ETLProfileInactiveError):
        get_profile_path(FASHION_PROFILE_ID)


def test_inactive_is_a_different_state_from_unknown_profile(deactivate):
    # 두 상태가 섞이면 "오타로 없는 프로필"과 "운영이 내린 프로필"을 구분할 수 없습니다.
    assert not issubclass(ETLProfileInactiveError, ETLProfileNotFoundError)
    assert not issubclass(ETLProfileNotFoundError, ETLProfileInactiveError)

    deactivate(FASHION_PROFILE_ID)

    with pytest.raises(ETLProfileInactiveError):
        get_profile_path(FASHION_PROFILE_ID)
    # 없는 profile_id는 기존 계약(NotFound) 그대로입니다.
    with pytest.raises(ETLProfileNotFoundError):
        get_profile_path("unknown_profile")


@pytest.mark.parametrize("placeholder", ["", " ", "disabled", "none", "null"])
def test_placeholder_strings_are_not_a_deactivation_marker(monkeypatch, placeholder):
    # 오직 None만 비활성입니다. 다른 값은 versions에 없는 pointer이므로 그대로 실패합니다.
    monkeypatch.setitem(
        profile_loader._ETL_PROFILE_REGISTRY,
        FASHION_PROFILE_ID,
        registry_entry_with(FASHION_PROFILE_ID, active_version=placeholder),
    )

    with pytest.raises(ETLProfileNotFoundError):
        get_profile_path(FASHION_PROFILE_ID)


# --- Deactivate is not Delete ---------------------------------------------


@pytest.mark.parametrize("version", ["1", "2"])
def test_archived_versions_stay_readable_while_deactivated(deactivate, version):
    deactivate(FASHION_PROFILE_ID)

    archived_path = get_profile_version_path(FASHION_PROFILE_ID, version)

    assert archived_path.is_file()
    assert load_profile(archived_path).version == version


def test_deactivation_does_not_remove_the_registry_entry_or_its_versions(deactivate):
    deactivate(FASHION_PROFILE_ID)

    entry = profile_loader._ETL_PROFILE_REGISTRY[FASHION_PROFILE_ID]

    assert entry["active_version"] is None
    assert tuple(sorted(entry["versions"])) == ("1", "2")
    assert entry["profile_name"] == "sample_fashion_vendor"


# --- Executable profile list ----------------------------------------------


def test_deactivated_profile_is_not_selectable_for_a_new_run(deactivate):
    deactivate(FASHION_PROFILE_ID)

    listed_ids = {profile["id"] for profile in list_etl_profiles()}

    assert FASHION_PROFILE_ID not in listed_ids
    # 다른 프로필은 그대로 남습니다. 비활성 하나가 목록 전체를 비우면 안 됩니다.
    assert MARKETPLACE_PROFILE_ID in listed_ids


def test_profile_list_response_shape_is_unchanged_after_filtering(deactivate):
    deactivate(FASHION_PROFILE_ID)

    for profile in list_etl_profiles():
        assert set(profile) == {"id", "display_name"}


# --- Profile detail --------------------------------------------------------


def test_detail_of_a_deactivated_profile_does_not_claim_an_active_version(deactivate):
    deactivate(FASHION_PROFILE_ID)

    # 마지막 active 버전의 detail을 그대로 보여 주면 "지금 이 버전으로 실행된다"는
    # 거짓이 됩니다. 존재하지 않는다(NotFound)고 말하지도 않습니다.
    with pytest.raises(ETLProfileInactiveError):
        get_etl_profile_detail(FASHION_PROFILE_ID)


# --- Execution path --------------------------------------------------------


def test_web_etl_execution_path_uses_the_same_activation_check(deactivate):
    # run_web_etl()이 부르는 것과 같은 함수 참조입니다.
    from etl.web_service import get_profile_path as web_service_get_profile_path

    deactivate(FASHION_PROFILE_ID)

    with pytest.raises(ETLProfileInactiveError):
        web_service_get_profile_path(FASHION_PROFILE_ID)
    # 활성 프로필은 영향을 받지 않습니다.
    assert load_profile(web_service_get_profile_path(MARKETPLACE_PROFILE_ID)).version == "2"
