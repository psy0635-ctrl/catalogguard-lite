import json

import pytest

from etl.profile_loader import ETLProfileValidationError, load_profile


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
