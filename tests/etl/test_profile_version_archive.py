"""Versioned profile archive + explicit active version pointer.

Phase 4 of docs/etl_profile_lifecycle.md. 과거 profile 정의를 버전별 파일로 보존하고,
신규 ETL 실행에 쓸 버전은 registry의 명시적 active_version으로만 고릅니다.

여기서는 archive 구조와 pointer 해석만 검증합니다. fingerprint 불변성은
tests/etl/test_profile_version_guardrail.py가 담당합니다.
"""
import json

import pytest

import etl.profile_loader as profile_loader
from etl.profile_loader import (
    ETL_PROFILE_DIR,
    ETLProfileNotFoundError,
    get_etl_profile_detail,
    get_profile_path,
    list_etl_profiles,
    load_profile,
)


ALLOWLISTED_PROFILE_IDS = (
    "sample_fashion_vendor_v1",
    "sample_marketplace_vendor_v1",
)
EXPECTED_ACTIVE_VERSION = "2"
EXPECTED_ARCHIVED_VERSIONS = ("1", "2")


def registry_entry(profile_id: str) -> dict:
    return profile_loader._ETL_PROFILE_REGISTRY[profile_id]


def test_allowlisted_profile_ids_are_unchanged():
    # profile_id의 '_v1'은 API/UI 식별자입니다. archive 도입으로 rename하지 않습니다.
    assert set(profile_loader._ETL_PROFILE_REGISTRY) == set(ALLOWLISTED_PROFILE_IDS)


def test_profile_list_response_contract_is_unchanged():
    profiles = list_etl_profiles()

    assert {profile["id"] for profile in profiles} == set(ALLOWLISTED_PROFILE_IDS)
    for profile in profiles:
        assert set(profile) == {"id", "display_name"}
        assert isinstance(profile["display_name"], str) and profile["display_name"]


@pytest.mark.parametrize("profile_id", ALLOWLISTED_PROFILE_IDS)
def test_active_version_is_an_explicit_registry_pointer(profile_id):
    info = registry_entry(profile_id)

    assert info["active_version"] == EXPECTED_ACTIVE_VERSION
    assert info["active_version"] in info["versions"]


@pytest.mark.parametrize("profile_id", ALLOWLISTED_PROFILE_IDS)
def test_registry_archives_every_published_version(profile_id):
    info = registry_entry(profile_id)

    assert tuple(sorted(info["versions"])) == EXPECTED_ARCHIVED_VERSIONS
    for version in info["versions"]:
        path = profile_loader.get_profile_version_path(profile_id, version)
        assert path.is_file()


@pytest.mark.parametrize("profile_id", ALLOWLISTED_PROFILE_IDS)
def test_get_profile_path_resolves_the_active_version_archive(profile_id):
    active_version = registry_entry(profile_id)["active_version"]

    active_path = get_profile_path(profile_id)

    assert active_path == profile_loader.get_profile_version_path(
        profile_id, active_version
    )
    assert load_profile(active_path).version == EXPECTED_ACTIVE_VERSION


@pytest.mark.parametrize("profile_id", ALLOWLISTED_PROFILE_IDS)
@pytest.mark.parametrize("version", EXPECTED_ARCHIVED_VERSIONS)
def test_every_archived_version_loads_through_the_existing_loader(profile_id, version):
    profile = load_profile(profile_loader.get_profile_version_path(profile_id, version))

    assert profile.version == version
    assert profile.name == registry_entry(profile_id)["profile_name"]


@pytest.mark.parametrize("profile_id", ALLOWLISTED_PROFILE_IDS)
def test_registry_identity_matches_the_archived_json(profile_id):
    # registry가 가리키는 파일이 실제로 그 이름·버전인지 확인해 drift를 막습니다.
    info = registry_entry(profile_id)

    for version in info["versions"]:
        path = profile_loader.get_profile_version_path(profile_id, version)
        data = json.loads(path.read_text(encoding="utf-8"))

        assert data["profile_name"] == info["profile_name"]
        assert data["profile_version"] == version


@pytest.mark.parametrize("profile_id", ALLOWLISTED_PROFILE_IDS)
def test_archived_paths_stay_inside_the_profile_directory(profile_id):
    profile_dir = ETL_PROFILE_DIR.resolve()

    for version in registry_entry(profile_id)["versions"]:
        resolved = profile_loader.get_profile_version_path(profile_id, version).resolve()

        assert resolved.is_relative_to(profile_dir)


def test_archived_paths_are_not_shared_between_versions():
    seen: set = set()

    for profile_id in ALLOWLISTED_PROFILE_IDS:
        for version in registry_entry(profile_id)["versions"]:
            resolved = profile_loader.get_profile_version_path(
                profile_id, version
            ).resolve()
            assert resolved not in seen
            seen.add(resolved)


@pytest.mark.parametrize(
    "version",
    ["999", "3", "", " ", "v2.json", "../1", "..\\1", "/etc/passwd", "1/../2"],
)
def test_unknown_or_traversal_like_versions_are_rejected(version):
    with pytest.raises(ETLProfileNotFoundError):
        profile_loader.get_profile_version_path("sample_fashion_vendor_v1", version)


@pytest.mark.parametrize("profile_id", ["unknown_profile", "", "../secret"])
def test_version_lookup_rejects_non_allowlisted_profile_ids(profile_id):
    with pytest.raises(ETLProfileNotFoundError):
        profile_loader.get_profile_version_path(profile_id, "2")


def test_registry_paths_escaping_the_profile_directory_are_rejected(monkeypatch):
    # registry 값이 실수로 archive root 밖을 가리켜도 거부해야 합니다.
    monkeypatch.setitem(
        profile_loader._ETL_PROFILE_REGISTRY,
        "sample_fashion_vendor_v1",
        {
            "display_name": "패션 공급사 샘플",
            "profile_name": "sample_fashion_vendor",
            "active_version": "2",
            "versions": {"2": "../../config/settings.py"},
        },
    )

    with pytest.raises(ETLProfileNotFoundError):
        get_profile_path("sample_fashion_vendor_v1")


def test_active_version_is_not_inferred_from_the_largest_version(monkeypatch):
    # Policy H: "가장 큰 버전 = active"로 추론하지 않습니다. 명시적 pointer만 씁니다.
    monkeypatch.setitem(
        profile_loader._ETL_PROFILE_REGISTRY,
        "sample_fashion_vendor_v1",
        {
            "display_name": "패션 공급사 샘플",
            "profile_name": "sample_fashion_vendor",
            "active_version": "2",
            "versions": {
                "2": "sample_fashion_vendor/v2.json",
                "10": "sample_fashion_vendor/v1.json",
            },
        },
    )

    active_path = get_profile_path("sample_fashion_vendor_v1")

    # 숫자로 크지도(10), 문자열 정렬로 마지막도 아닌 명시적 "2"를 써야 합니다.
    assert active_path.name == "v2.json"
    assert load_profile(active_path).version == "2"


def test_active_version_missing_from_versions_is_rejected(monkeypatch):
    monkeypatch.setitem(
        profile_loader._ETL_PROFILE_REGISTRY,
        "sample_fashion_vendor_v1",
        {
            "display_name": "패션 공급사 샘플",
            "profile_name": "sample_fashion_vendor",
            "active_version": "3",
            "versions": {"2": "sample_fashion_vendor/v2.json"},
        },
    )

    with pytest.raises(ETLProfileNotFoundError):
        get_profile_path("sample_fashion_vendor_v1")


@pytest.mark.parametrize("profile_id", ALLOWLISTED_PROFILE_IDS)
def test_profile_detail_still_describes_the_active_version(profile_id):
    detail = get_etl_profile_detail(profile_id)

    assert detail["id"] == profile_id
    assert detail["profile_version"] == EXPECTED_ACTIVE_VERSION
    assert detail["profile_name"] == registry_entry(profile_id)["profile_name"]
    # archive 경로·파일명·registry 내부 구조는 계속 노출하지 않습니다.
    assert set(detail) == {
        "id",
        "display_name",
        "profile_name",
        "profile_version",
        "source_columns",
        "required_source_columns",
        "defaults",
    }


@pytest.mark.parametrize("profile_id", ALLOWLISTED_PROFILE_IDS)
def test_etl_execution_path_still_uses_the_active_version(profile_id):
    # etl.web_service.run_web_etl()이 쓰는 것과 같은 경로 해석입니다.
    from etl.web_service import get_profile_path as web_service_get_profile_path

    profile = load_profile(web_service_get_profile_path(profile_id))

    assert profile.version == EXPECTED_ACTIVE_VERSION
