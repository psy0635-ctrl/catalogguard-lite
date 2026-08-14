import json
from pathlib import Path

import pytest

from etl.profile_loader import (
    ETL_PROFILE_DIR,
    ETLProfileNotFoundError,
    ETLProfileValidationError,
    get_profile_path,
    list_etl_profiles,
    load_profile,
)


VALID_PROFILE = {
    "profile_name": "sample_fashion_vendor",
    "profile_version": "1",
    "source_columns": {
        "vendor_sku": "product_id",
        "item_name": "product_name",
        "main_category": "category",
        "colour": "color",
        "size_name": "size",
        "quantity": "stock",
        "list_price": "price",
        "image_link": "image_path",
        "description_text": "description",
        "brand_name": "seller",
    },
    "required_source_columns": [
        "vendor_sku",
        "item_name",
        "main_category",
        "list_price",
        "colour",
        "size_name",
        "image_link",
    ],
    "defaults": {"product_group_id": "sample_fashion_vendor"},
}


def write_profile(tmp_path, profile):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    return profile_path


def test_load_profile_returns_validated_mapping_and_defaults(tmp_path):
    profile = load_profile(write_profile(tmp_path, VALID_PROFILE))

    assert profile.name == "sample_fashion_vendor"
    assert profile.version == "1"
    assert profile.source_columns["vendor_sku"] == ("product_id",)
    assert profile.defaults == {"product_group_id": "sample_fashion_vendor"}


def test_load_profile_allows_one_source_column_to_populate_product_group_and_id(tmp_path):
    profile_data = json.loads(json.dumps(VALID_PROFILE))
    profile_data["source_columns"]["vendor_sku"] = [
        "product_group_id",
        "product_id",
    ]
    profile_data["defaults"].pop("product_group_id")

    profile = load_profile(write_profile(tmp_path, profile_data))

    assert profile.source_columns["vendor_sku"] == (
        "product_group_id",
        "product_id",
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda profile: profile.pop("profile_name"), "profile_name"),
        (lambda profile: profile.__setitem__("source_columns", []), "source_columns"),
        (
            lambda profile: profile["source_columns"].__setitem__(
                "vendor_sku", "unknown_column"
            ),
            "unknown_column",
        ),
        (
            lambda profile: profile["source_columns"].__setitem__(
                "second_sku", "product_id"
            ),
            "product_id",
        ),
        (
            lambda profile: (
                profile["source_columns"].pop("image_link"),
                profile["required_source_columns"].remove("image_link"),
            ),
            "image_path",
        ),
        (
            lambda profile: profile.__setitem__("defaults", {"unknown_column": "x"}),
            "unknown_column",
        ),
    ],
)
def test_load_profile_rejects_invalid_schema(tmp_path, change, message):
    profile_data = json.loads(json.dumps(VALID_PROFILE))
    change(profile_data)

    with pytest.raises(ETLProfileValidationError, match=message):
        load_profile(write_profile(tmp_path, profile_data))


def test_load_profile_rejects_malformed_json(tmp_path):
    profile_path = tmp_path / "profile.json"
    profile_path.write_text("{", encoding="utf-8")

    with pytest.raises(ETLProfileValidationError, match="JSON"):
        load_profile(profile_path)


def test_list_etl_profiles_returns_known_allowlisted_profiles():
    profiles = list_etl_profiles()

    ids = {profile["id"] for profile in profiles}
    assert ids == {"sample_fashion_vendor_v1", "sample_marketplace_vendor_v1"}
    for profile in profiles:
        assert set(profile) == {"id", "display_name"}
        assert isinstance(profile["display_name"], str) and profile["display_name"]


def test_list_etl_profiles_display_names_do_not_claim_a_profile_version():
    # profile_id의 '_v1'은 고정된 API 식별자이고 실제 버전은 profile_version입니다.
    # display_name이 실제 버전과 다른 값을 주장하지 않도록 고정합니다.
    for profile in list_etl_profiles():
        assert "v1" not in profile["display_name"]
        assert "v2" not in profile["display_name"]


def test_allowlisted_profile_ids_keep_loading_their_current_profile_version():
    # id와 파일명은 그대로 두고 실제 profile_version만 올렸는지 확인합니다.
    expected_names = {
        "sample_fashion_vendor_v1": "sample_fashion_vendor",
        "sample_marketplace_vendor_v1": "sample_marketplace_vendor",
    }

    for profile_id, expected_name in expected_names.items():
        profile = load_profile(get_profile_path(profile_id))

        assert profile.name == expected_name
        assert profile.version == "2"


def test_get_profile_path_resolves_known_id_to_a_loadable_profile():
    path = get_profile_path("sample_fashion_vendor_v1")

    assert path.parent.resolve() == ETL_PROFILE_DIR.resolve()
    profile = load_profile(path)
    assert profile.name == "sample_fashion_vendor"


@pytest.mark.parametrize(
    "profile_id",
    [
        "unknown_profile",
        "",
        "../../config/etl/sample_fashion_vendor_v1.json",
        "..\\..\\config\\etl\\sample_fashion_vendor_v1.json",
        str(Path(__file__).resolve()),
        "sample_fashion_vendor_v1.json",
        "sample_fashion_vendor_v1/../../../etc/passwd",
    ],
)
def test_get_profile_path_rejects_ids_outside_the_allowlist(profile_id):
    with pytest.raises(ETLProfileNotFoundError):
        get_profile_path(profile_id)
