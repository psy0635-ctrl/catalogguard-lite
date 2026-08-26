import hashlib

from etl.models import ETLProfile
from etl.profile_fingerprint import (
    build_profile_semantic_payload,
    canonicalize_profile_semantic_payload,
    compute_profile_definition_sha256,
    compute_profile_definition_sha256_from_payload,
)


def _profile() -> ETLProfile:
    return ETLProfile(
        name="profile-name",
        version="9",
        source_columns={"sku": ("product_id", "product_group_id")},
        required_source_columns=("sku",),
        defaults={"stock": "0"},
    )


def test_semantic_payload_contains_only_the_three_snapshot_fields_and_lists_targets():
    payload = build_profile_semantic_payload(_profile())

    assert payload == {
        "source_columns": {"sku": ["product_id", "product_group_id"]},
        "required_source_columns": ["sku"],
        "defaults": {"stock": "0"},
    }


def test_semantic_payload_is_mutation_isolated_from_profile():
    profile = _profile()
    payload = build_profile_semantic_payload(profile)
    profile.source_columns["sku"] = ("product_id",)
    profile.defaults["stock"] = "5"

    assert payload["source_columns"] == {"sku": ["product_id", "product_group_id"]}
    assert payload["defaults"] == {"stock": "0"}


def test_payload_hash_uses_the_existing_canonical_json_and_profile_wrapper():
    profile = _profile()
    payload = build_profile_semantic_payload(profile)
    canonical = canonicalize_profile_semantic_payload(payload)

    assert canonical == (
        '{"defaults":{"stock":"0"},"required_source_columns":["sku"],'
        '"source_columns":{"sku":["product_id","product_group_id"]}}'
    )
    assert compute_profile_definition_sha256_from_payload(payload) == hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    assert compute_profile_definition_sha256_from_payload(payload) == compute_profile_definition_sha256(profile)
