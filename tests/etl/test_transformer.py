import json

import pytest

from etl.models import ETLProfile
from etl.transformer import transform_rows


PROFILE = ETLProfile(
    name="sample_fashion_vendor",
    version="1",
    source_columns={
        "vendor_sku": "product_id",
        "item_name": "product_name",
        "main_category": "category",
        "colour": "color",
        "size_name": "size",
        "quantity": "stock",
        "list_price": "price",
        "discount_price": "sale_price",
        "image_link": "image_path",
        "description_text": "description",
        "brand_name": "seller",
    },
    required_source_columns=(
        "vendor_sku",
        "item_name",
        "main_category",
        "list_price",
        "colour",
        "size_name",
        "image_link",
    ),
    defaults={"product_group_id": "sample_fashion_vendor", "stock": "0"},
)


VALID_ROW = {
    "vendor_sku": " 000123 ",
    "item_name": "  기본  티셔츠  ",
    "main_category": " TOP ",
    "brand_name": " Sample Brand ",
    "list_price": "₩12,000",
    "discount_price": "15000",
    "colour": " 블랙 ",
    "size_name": " medium ",
    "quantity": " 10 ",
    "description_text": " 편안한 티셔츠 ",
    "image_link": " https://example.test/t-shirt.jpg ",
}


def test_transform_rows_trims_text_preserves_product_id_and_parses_numbers():
    result = transform_rows([VALID_ROW], PROFILE)

    assert result.rejected_rows == []
    assert result.loaded_rows == [
        {
            "product_group_id": "sample_fashion_vendor",
            "product_id": "000123",
            "product_name": "기본  티셔츠",
            "category": "TOP",
            "color": "블랙",
            "size": "medium",
            "stock": "10",
            "price": "12000",
            "sale_price": "15000",
            "image_path": "https://example.test/t-shirt.jpg",
            "description": "편안한 티셔츠",
            "seller": "Sample Brand",
        }
    ]


def test_transform_rows_uses_stock_default_for_blank_source_value():
    row = {**VALID_ROW, "quantity": " "}

    result = transform_rows([row], PROFILE)

    assert result.loaded_rows[0]["stock"] == "0"
    assert result.rejected_rows == []


def test_transform_rows_allows_blank_discount_price():
    row = {**VALID_ROW, "discount_price": " "}

    result = transform_rows([row], PROFILE)

    assert result.rejected_rows == []
    assert result.loaded_rows[0]["sale_price"] == ""


def test_transform_rows_rejects_unparseable_discount_price_with_existing_price_error_code():
    row = {**VALID_ROW, "discount_price": "무료"}

    result = transform_rows([row], PROFILE)

    assert result.loaded_rows == []
    assert json.loads(result.rejected_rows[0]["error_code"]) == ["INVALID_PRICE"]


def test_transform_rows_uses_vendor_sku_as_product_group_id_when_profile_maps_it_twice():
    profile = ETLProfile(
        **{
            **PROFILE.__dict__,
            "source_columns": {
                **PROFILE.source_columns,
                "vendor_sku": ("product_group_id", "product_id"),
            },
            "defaults": {"stock": "0"},
        }
    )

    result = transform_rows([VALID_ROW, {**VALID_ROW, "vendor_sku": "000124"}], profile)

    assert [row["product_group_id"] for row in result.loaded_rows] == ["000123", "000124"]


def test_transform_rows_collects_multiple_row_errors_with_source_line_number():
    row = {
        **VALID_ROW,
        "vendor_sku": " ",
        "list_price": "무료",
        "quantity": "1.5",
    }

    result = transform_rows([row], PROFILE)

    assert result.loaded_rows == []
    assert result.rejected_rows[0]["source_row_number"] == "2"
    assert json.loads(result.rejected_rows[0]["error_code"]) == [
        "MISSING_SOURCE_VALUE",
        "MISSING_PRODUCT_ID",
        "INVALID_PRICE",
        "INVALID_STOCK",
    ]
    assert all("Traceback" not in message for message in json.loads(result.rejected_rows[0]["error_message"]))


def test_transform_rows_identifies_each_missing_required_source_column_in_messages():
    row = {**VALID_ROW, "vendor_sku": "", "item_name": ""}

    result = transform_rows([row], PROFILE)

    messages = json.loads(result.rejected_rows[0]["error_message"])
    assert "vendor_sku" in messages[0]
    assert "item_name" in messages[1]


def test_transform_rows_rejects_negative_price_and_stock_without_rejecting_sale_price_quality_issue():
    invalid_row = {**VALID_ROW, "list_price": "-1000", "quantity": "-1"}
    sale_price_quality_row = {**VALID_ROW, "discount_price": "15000"}

    result = transform_rows([invalid_row, sale_price_quality_row], PROFILE)

    assert json.loads(result.rejected_rows[0]["error_code"]) == [
        "NEGATIVE_PRICE",
        "NEGATIVE_STOCK",
    ]
    assert result.loaded_rows[0]["price"] == "12000"


# 아래는 카테고리별 필수 속성 정책(category-aware validation)을 ETL에 적용한 뒤의 동작입니다.
# 정책의 단일 기준은 검수와 같은 config.settings.FASHION_CATEGORY_ATTRIBUTE_RULES입니다.
MARKETPLACE_PROFILE = ETLProfile(
    name="sample_marketplace_vendor",
    version="2",
    source_columns={
        "style_id": "product_group_id",
        "sku_code": "product_id",
        "title": "product_name",
        "category_code": "category",
        "tone": "color",
        "fit_size": "size",
        "regular_price": "price",
        "photo": "image_path",
    },
    required_source_columns=(
        "style_id",
        "sku_code",
        "title",
        "category_code",
        "tone",
        "fit_size",
        "photo",
    ),
    defaults={"stock": "0"},
)

MARKETPLACE_VALID_ROW = {
    "style_id": "G001",
    "sku_code": "SKU-1",
    "title": "레더 토트백",
    "category_code": "BAG",
    "tone": "BLACK",
    "fit_size": "FREE",
    "regular_price": "59000",
    "photo": "https://example.test/bag.jpg",
}


@pytest.mark.parametrize("category", ["TOP", "BOTTOM", "OUTER", "SHOES"])
def test_transform_rows_still_rejects_blank_size_for_apparel_categories(category):
    row = {**VALID_ROW, "main_category": category, "size_name": ""}

    result = transform_rows([row], PROFILE)

    assert result.loaded_rows == []
    assert json.loads(result.rejected_rows[0]["error_code"]) == ["MISSING_SOURCE_VALUE"]
    assert "size_name" in json.loads(result.rejected_rows[0]["error_message"])[0]


def test_transform_rows_allows_blank_size_for_bag():
    row = {**VALID_ROW, "main_category": "BAG", "item_name": "레더 토트백", "size_name": ""}

    result = transform_rows([row], PROFILE)

    assert result.rejected_rows == []
    assert len(result.loaded_rows) == 1
    assert result.loaded_rows[0]["category"] == "BAG"
    assert result.loaded_rows[0]["size"] == ""


def test_transform_rows_allows_blank_size_for_bag_on_marketplace_profile():
    row = {**MARKETPLACE_VALID_ROW, "fit_size": ""}

    result = transform_rows([row], MARKETPLACE_PROFILE)

    assert result.rejected_rows == []
    assert result.loaded_rows[0]["size"] == ""
    assert result.loaded_rows[0]["category"] == "BAG"


@pytest.mark.parametrize("blank_column", ["colour", "image_link", "item_name"])
def test_transform_rows_still_rejects_other_blank_required_values_for_bag(blank_column):
    # size만 선택 값이며, BAG에서도 나머지 필수 공급사 값 정책은 그대로입니다.
    row = {**VALID_ROW, "main_category": "BAG", blank_column: ""}

    result = transform_rows([row], PROFILE)

    assert result.loaded_rows == []
    assert blank_column in json.loads(result.rejected_rows[0]["error_message"])[0]


def test_transform_rows_rejects_blank_size_for_invalid_category():
    # 허용 목록에 없는 카테고리는 BAG로 추정하지 않고 기존 정책을 유지합니다.
    row = {**VALID_ROW, "main_category": "ACCESSORY", "size_name": ""}

    result = transform_rows([row], PROFILE)

    assert result.loaded_rows == []
    assert "size_name" in json.loads(result.rejected_rows[0]["error_message"])[0]


def test_transform_rows_rejects_blank_size_for_lowercase_bag():
    # canonical 표기가 아닌 값은 별칭으로 정규화하지 않으므로 size가 계속 필수입니다.
    row = {**VALID_ROW, "main_category": "bag", "size_name": ""}

    result = transform_rows([row], PROFILE)

    assert result.loaded_rows == []
    assert "size_name" in json.loads(result.rejected_rows[0]["error_message"])[0]


def test_transform_rows_rejects_blank_size_when_category_is_also_blank():
    row = {**VALID_ROW, "main_category": "", "size_name": ""}

    result = transform_rows([row], PROFILE)

    assert result.loaded_rows == []
    messages = json.loads(result.rejected_rows[0]["error_message"])
    assert any("main_category" in message for message in messages)
    assert any("size_name" in message for message in messages)


def test_transform_rows_applies_bag_policy_after_existing_whitespace_trimming():
    # 기존 표준 행 생성이 모든 값을 trim하므로 ' BAG '는 검수와 동일하게 canonical BAG가 됩니다.
    # 별칭 정규화를 새로 추가한 것이 아니라, 원래 있던 trim 결과에 정책을 적용하는 것입니다.
    row = {**VALID_ROW, "main_category": " BAG ", "size_name": ""}

    result = transform_rows([row], PROFILE)

    assert result.rejected_rows == []
    assert result.loaded_rows[0]["category"] == "BAG"


def test_transform_rows_keeps_unmapped_required_source_column_always_required():
    # 표준 컬럼에 매핑되지 않은 필수 컬럼은 카테고리 정책과 무관하게 필수로 남습니다.
    profile = ETLProfile(
        name="unmapped_required",
        version="1",
        source_columns=PROFILE.source_columns,
        required_source_columns=(*PROFILE.required_source_columns, "audit_note"),
        defaults=PROFILE.defaults,
    )
    row = {**VALID_ROW, "main_category": "BAG", "audit_note": ""}

    result = transform_rows([row], profile)

    assert result.loaded_rows == []
    assert "audit_note" in json.loads(result.rejected_rows[0]["error_message"])[0]
