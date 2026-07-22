import json

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
