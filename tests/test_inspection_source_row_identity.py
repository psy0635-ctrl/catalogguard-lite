import pandas as pd

from api.routes.inspections import build_inspection_response
from core.inspection_service import inspect_dataframe
from core.loader import load_products_from_dataframe
from core.rules import (
    check_duplicate_product_id,
    check_inconsistent_group_category,
    check_missing_required_fields,
)
from core.upload_validator import validate_and_read_uploaded_csv
from db.persistence_service import build_result_create_items


CSV_COLUMNS = [
    "product_group_id",
    "product_id",
    "product_name",
    "category",
    "color",
    "size",
    "stock",
    "price",
    "image_path",
    "description",
    "seller",
]


def make_row(**overrides):
    row = {
        "product_group_id": "G001",
        "product_id": "P001",
        "product_name": "기본 상품",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": "5",
        "price": "10000",
        "image_path": "image.jpg",
        "description": "",
        "seller": "",
    }
    row.update(overrides)
    return row


def make_dataframe(rows):
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def test_loader_assigns_logical_source_rows_from_record_order_not_dataframe_index():
    dataframe = make_dataframe([make_row(product_id="P001"), make_row(product_id="P002")])
    dataframe.index = [100, 500]

    products = load_products_from_dataframe(dataframe)

    assert [product.source_row_number for product in products] == [2, 3]


def test_quoted_multiline_and_blank_physical_line_keep_logical_source_row_sequence():
    csv_text = "\n".join(
        [
            ",".join(CSV_COLUMNS),
            'G001,P001,상품 A,TOP,BLACK,M,5,10000,image.jpg,"첫째 줄',
            '둘째 줄",',
            "",
            "G002,P002,상품 B,SHOES,WHITE,260,3,20000,image2.jpg,,",
        ]
    )

    dataframe = validate_and_read_uploaded_csv("products.csv", csv_text.encode("utf-8-sig"))
    products = load_products_from_dataframe(dataframe)

    assert [product.source_row_number for product in products] == [2, 3]


def test_missing_business_ids_keep_distinct_source_rows_on_issues():
    products = load_products_from_dataframe(
        make_dataframe(
            [
                make_row(product_group_id="", product_id=""),
                make_row(product_group_id="", product_id=""),
            ]
        )
    )

    issues = check_missing_required_fields(products)

    assert [issue.source_row_number for issue in issues] == [2, 2, 3, 3]


def test_duplicate_product_id_issues_keep_each_record_source_row():
    products = load_products_from_dataframe(
        make_dataframe(
            [
                make_row(product_group_id="G001", product_id="P001"),
                make_row(product_group_id="G002", product_id="P001"),
                make_row(product_group_id="G003", product_id="P001"),
            ]
        )
    )

    issues = check_duplicate_product_id(products)

    assert [issue.source_row_number for issue in issues] == [2, 3, 4]


def test_group_rule_keeps_the_affected_products_source_rows():
    products = load_products_from_dataframe(
        make_dataframe(
            [
                make_row(product_group_id="G001", product_id="P001", category="TOP"),
                make_row(product_group_id="G001", product_id="P002", category="BOTTOM"),
            ]
        )
    )

    issues = check_inconsistent_group_category(products)

    assert [issue.source_row_number for issue in issues] == [2, 3]


def test_report_persistence_and_api_response_preserve_source_rows_without_changing_display_columns():
    report = inspect_dataframe(
        make_dataframe(
            [
                make_row(product_group_id="", product_id=""),
                make_row(product_group_id="", product_id=""),
            ]
        )
    )

    assert "source_row_number" not in report.result_dataframe.columns
    expected_source_rows = [
        record["source_row_number"] for record in report.result_records
    ]
    assert expected_source_rows == [2, 2, 3, 3, 2, 3]
    assert [item.source_row_number for item in build_result_create_items(report)] == expected_source_rows

    response = build_inspection_response(report, inspection_run_id=1).model_dump()
    assert [item["source_row_number"] for item in response["results"]] == expected_source_rows
