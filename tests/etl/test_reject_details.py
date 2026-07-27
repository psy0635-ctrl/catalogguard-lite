import csv
import io
import json

import pytest

from etl.models import ETLProfile
from etl.reject_parser import RejectFileValidationError, parse_reject_csv
from etl.reject_sanitizer import mask_rejected_source_data
from etl.transformer import transform_rows


PROFILE = ETLProfile(
    name="vendor",
    version="1",
    source_columns={
        "sku": "product_id",
        "name": "product_name",
        "price_text": "price",
        "stock_text": "stock",
    },
    required_source_columns=("sku", "name", "price_text", "stock_text"),
    defaults={"product_group_id": "vendor"},
)


def test_transform_rejects_include_error_fields_aligned_with_error_codes():
    result = transform_rows(
        [
            {
                "sku": "SKU-1",
                "name": "Item",
                "price_text": "invalid",
                "stock_text": "-1",
            }
        ],
        PROFILE,
    )

    rejected = result.rejected_rows[0]
    assert json.loads(rejected["error_code"]) == ["INVALID_PRICE", "NEGATIVE_STOCK"]
    assert json.loads(rejected["error_field"]) == ["price", "stock"]
    assert len(json.loads(rejected["error_message"])) == 2


def test_mask_rejected_source_data_masks_all_sensitive_values_without_mutating_input():
    source_data = {
        "name": "문의 seller@example.com",
        "description": "전화 010-1234-5678, 계좌 123-456-789012",
        "note": "주민 000000-1234567",
        "sku": "SKU-1",
    }

    masked = mask_rejected_source_data(source_data)

    assert source_data["name"] == "문의 seller@example.com"
    assert masked["name"] == "문의 se****@example.com"
    assert masked["description"] == "전화 010-****-5678, 계좌 123-***-***012"
    assert masked["note"] == "주민 000000-*******"
    assert masked["sku"] == "SKU-1"
    assert all(isinstance(value, str) for value in masked.values())


def _reject_csv(rows: list[list[str]], *, headers: list[str] | None = None) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        headers
        or [
            "source_row_number",
            "error_code",
            "error_field",
            "error_message",
            "sku",
            "description",
        ]
    )
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def test_parse_reject_csv_builds_structured_errors_and_masked_source_data():
    parsed = parse_reject_csv(
        _reject_csv(
            [
                [
                    "4",
                    '["INVALID_PRICE", "NEGATIVE_STOCK"]',
                    '["price", "stock"]',
                    '["bad price", "negative stock"]',
                    "SKU-1",
                    "문의 010-1234-5678",
                ]
            ]
        ),
        filename="rejected_rows.csv",
        expected_row_count=1,
    )

    assert len(parsed) == 1
    assert parsed[0].source_row_number == 4
    assert [error.code for error in parsed[0].errors] == [
        "INVALID_PRICE",
        "NEGATIVE_STOCK",
    ]
    assert [error.field for error in parsed[0].errors] == ["price", "stock"]
    assert parsed[0].masked_source_data["description"] == "문의 010-****-5678"


@pytest.mark.parametrize(
    "rows",
    [
        [["1", '["INVALID_PRICE"]', '["price"]', '["bad"]', "SKU-1", ""]],
        [["4", '["INVALID_PRICE"]', '["price", "stock"]', '["bad"]', "SKU-1", ""]],
        [["4", "[]", "[]", "[]", "SKU-1", ""]],
        [["4", '["invalid_price"]', '["price"]', '["bad"]', "SKU-1", ""]],
        [["4", '["INVALID_PRICE"]', '["price"]', '[" "]', "SKU-1", ""]],
    ],
)
def test_parse_reject_csv_rejects_invalid_structure(rows):
    with pytest.raises(RejectFileValidationError):
        parse_reject_csv(
            _reject_csv(rows),
            filename="rejected_rows.csv",
            expected_row_count=1,
        )
