"""Guardrail: an already published ETL profile version must not change in place.

Phase 3 of docs/etl_profile_lifecycle.md. Policy A(Published Version Immutable)와
Policy B(Semantic Change = Version Bump)를 CI에서 강제하기 위한 test-only 안전장치입니다.

runtime 동작은 바꾸지 않습니다. fingerprint 계산은 이 파일 안에만 있고
etl.profile_loader에는 새 API를 추가하지 않습니다.
"""
import json
from pathlib import Path

import pytest

from etl.models import ETLProfile
from etl.profile_fingerprint import (
    build_profile_semantic_payload as semantic_payload,
    compute_profile_definition_sha256 as fingerprint,
)
from etl.profile_loader import (
    _ETL_PROFILE_REGISTRY,
    get_profile_path,
    get_profile_version_path,
    list_etl_profiles,
    load_profile,
)


BASELINE_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "etl" / "profile_fingerprints.json"
)
_SHA256_HEX_LENGTH = 64
_SHA256_HEX_CHARACTERS = set("0123456789abcdef")

_IMMUTABILITY_HINT = (
    "Do not modify an already published version in place. "
    "Restore the published definition, or bump profile_version and ADD a new "
    "fingerprint record without changing or deleting the existing one."
)


def load_baseline() -> dict[str, dict[str, str]]:
    if not BASELINE_PATH.is_file():
        raise AssertionError(
            f"Published ETL profile fingerprint baseline is missing: {BASELINE_PATH}"
        )
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def published_profiles() -> list[ETLProfile]:
    """Load every archived profile version through the existing loader validation.

    Phase 4부터는 현재 active 버전만이 아니라 registry에 등록된 과거 버전도 불변이어야
    하므로, archive 전체를 검사합니다.
    """
    return [
        load_profile(get_profile_version_path(profile_id, version))
        for profile_id in _ETL_PROFILE_REGISTRY
        for version in _ETL_PROFILE_REGISTRY[profile_id]["versions"]
    ]


def active_profiles() -> list[ETLProfile]:
    """Load only the version each profile_id currently runs."""
    return [
        load_profile(get_profile_path(profile["id"]))
        for profile in list_etl_profiles()
    ]


def assert_profile_matches_baseline(
    profile: ETLProfile,
    baseline: dict[str, dict[str, str]],
) -> None:
    """Fail with actionable guidance when a published version drifted."""
    versions = baseline.get(profile.name, {})
    published_fingerprint = versions.get(profile.version)
    if published_fingerprint is None:
        raise AssertionError(
            "No published fingerprint is registered for "
            f"profile_name={profile.name} profile_version={profile.version}. "
            "If this version bump is intentional, ADD a new fingerprint entry to "
            f"{BASELINE_PATH.name}. Do not modify or delete the existing entries."
        )

    current_fingerprint = fingerprint(profile)
    if current_fingerprint != published_fingerprint:
        raise AssertionError(
            "Published ETL profile changed without a version bump: "
            f"profile_name={profile.name} profile_version={profile.version}\n"
            f"published fingerprint: {published_fingerprint}\n"
            f"current fingerprint:   {current_fingerprint}\n"
            + _IMMUTABILITY_HINT
        )


def replace_profile(profile: ETLProfile, **changes: object) -> ETLProfile:
    """Build an in-memory variant so tests never edit config/etl/*.json."""
    fields = {
        "name": profile.name,
        "version": profile.version,
        "source_columns": profile.source_columns,
        "required_source_columns": profile.required_source_columns,
        "defaults": profile.defaults,
    }
    fields.update(changes)
    return ETLProfile(**fields)


@pytest.fixture(name="fashion_profile")
def fixture_fashion_profile() -> ETLProfile:
    return load_profile(get_profile_path("sample_fashion_vendor_v1"))


def test_published_profiles_still_match_their_registered_fingerprint():
    # 핵심 guardrail입니다. archive의 모든 버전 파일을 읽어 비교하므로,
    # 과거 v1을 수정해도 현재 v2를 수정해도 실패합니다.
    baseline = load_baseline()

    for profile in published_profiles():
        assert_profile_matches_baseline(profile, baseline)


def test_active_profiles_still_match_their_registered_fingerprint():
    baseline = load_baseline()

    for profile in active_profiles():
        assert_profile_matches_baseline(profile, baseline)


def test_every_current_profile_version_has_a_baseline_entry():
    baseline = load_baseline()

    for profile in published_profiles():
        assert profile.name in baseline, (
            f"profile_name={profile.name} has no fingerprint record"
        )
        assert profile.version in baseline[profile.name], (
            f"profile_name={profile.name} profile_version={profile.version} "
            "has no fingerprint record"
        )


def test_guardrail_covers_every_archived_version_not_just_the_active_one():
    # active 버전만 검사하면 과거 v1을 조용히 고쳐도 CI가 통과합니다.
    checked = {(profile.name, profile.version) for profile in published_profiles()}
    expected = {
        (info["profile_name"], version)
        for info in _ETL_PROFILE_REGISTRY.values()
        for version in info["versions"]
    }

    assert checked == expected
    assert len(checked) > len(active_profiles())


def test_baseline_file_has_a_valid_structure():
    baseline = load_baseline()

    assert isinstance(baseline, dict) and baseline
    for profile_name, versions in baseline.items():
        assert isinstance(profile_name, str) and profile_name.strip()
        assert isinstance(versions, dict) and versions
        for profile_version, recorded_fingerprint in versions.items():
            assert isinstance(profile_version, str) and profile_version.strip()
            assert isinstance(recorded_fingerprint, str)
            assert len(recorded_fingerprint) == _SHA256_HEX_LENGTH
            assert set(recorded_fingerprint) <= _SHA256_HEX_CHARACTERS


def test_changed_source_columns_change_the_fingerprint(fashion_profile):
    changed_mapping = dict(fashion_profile.source_columns)
    changed_mapping["vendor_sku"] = ("product_id",)
    changed = replace_profile(fashion_profile, source_columns=changed_mapping)

    assert fingerprint(changed) != fingerprint(fashion_profile)


def test_changed_required_source_columns_change_the_fingerprint(fashion_profile):
    changed = replace_profile(
        fashion_profile,
        required_source_columns=fashion_profile.required_source_columns[:-1],
    )

    assert fingerprint(changed) != fingerprint(fashion_profile)


def test_reordered_required_source_columns_change_the_fingerprint(fashion_profile):
    # 이 순서는 reject 오류 배열 순서로 출력에 드러나므로 정규화하지 않습니다.
    reordered = tuple(reversed(fashion_profile.required_source_columns))
    changed = replace_profile(fashion_profile, required_source_columns=reordered)

    assert fingerprint(changed) != fingerprint(fashion_profile)


def test_changed_defaults_change_the_fingerprint(fashion_profile):
    changed = replace_profile(fashion_profile, defaults={"stock": "1"})

    assert fingerprint(changed) != fingerprint(fashion_profile)


def test_reordered_mapping_keys_keep_the_same_fingerprint(fashion_profile):
    # source_columns의 dict 순서는 변환 결과를 바꾸지 않습니다. 하나의 표준 컬럼에는
    # 한 공급사 컬럼만 매핑될 수 있어(_validate_mapping의 Duplicate target 검사)
    # 어떤 순서로 채워도 같은 행이 나옵니다.
    reordered_mapping = dict(reversed(list(fashion_profile.source_columns.items())))
    reordered_defaults = dict(reversed(list(fashion_profile.defaults.items())))
    reordered = replace_profile(
        fashion_profile,
        source_columns=reordered_mapping,
        defaults=reordered_defaults,
    )

    assert fingerprint(reordered) == fingerprint(fashion_profile)


def test_fingerprint_ignores_profile_identity_and_display_metadata(fashion_profile):
    # display_name은 애초에 payload에 없고, profile_name/profile_version은 key로만 씁니다.
    payload = semantic_payload(fashion_profile)

    assert set(payload) == {
        "source_columns",
        "required_source_columns",
        "defaults",
    }
    renamed = replace_profile(fashion_profile, name="other_vendor", version="99")
    assert fingerprint(renamed) == fingerprint(fashion_profile)


def test_fingerprint_is_lowercase_sha256_hex(fashion_profile):
    value = fingerprint(fashion_profile)

    assert len(value) == _SHA256_HEX_LENGTH
    assert set(value) <= _SHA256_HEX_CHARACTERS


def test_drifted_profile_reports_the_published_version_and_the_bump_rule(fashion_profile):
    baseline = {fashion_profile.name: {fashion_profile.version: "0" * 64}}

    with pytest.raises(AssertionError) as error:
        assert_profile_matches_baseline(fashion_profile, baseline)

    message = str(error.value)
    assert f"profile_name={fashion_profile.name}" in message
    assert f"profile_version={fashion_profile.version}" in message
    assert "without a version bump" in message
    assert "ADD a new" in message


def test_bumped_version_without_a_new_baseline_entry_fails(fashion_profile):
    # v2를 v3로 올렸는데 새 entry를 추가하지 않은 상황입니다.
    baseline = {fashion_profile.name: {"2": fingerprint(fashion_profile)}}
    bumped = replace_profile(fashion_profile, version="3")

    with pytest.raises(AssertionError) as error:
        assert_profile_matches_baseline(bumped, baseline)

    message = str(error.value)
    assert "No published fingerprint is registered" in message
    assert "ADD a new fingerprint entry" in message
    assert "Do not modify or delete the existing entries" in message


def test_historical_fingerprint_entries_are_allowed(fashion_profile):
    # 과거 version entry는 계속 남습니다. baseline은 append-only로 자랍니다.
    baseline = {
        fashion_profile.name: {
            "1": "a" * 64,
            fashion_profile.version: fingerprint(fashion_profile),
        },
        "retired_vendor": {"1": "b" * 64},
    }

    assert_profile_matches_baseline(fashion_profile, baseline)
