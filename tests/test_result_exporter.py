import io

import pandas as pd
import pytest

from config.settings import DEV_DATA_PATH
from core.loader import load_products
from core.models import ValidationIssue
from core.presentation import (
    PRICE_RECOMMENDATION,
    RESULT_COLUMNS,
    build_result_dataframe,
)
from core.result_exporter import (
    DEFAULT_RESULT_FILENAME,
    MAX_FILENAME_STEM_LENGTH,
    build_result_filename,
    build_validation_result_csv,
    prepare_export_dataframe,
    sanitize_csv_cell,
)
from core.rules import run_all_rules


def read_exported_csv(csv_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(
        io.BytesIO(csv_bytes),
        encoding="utf-8-sig",
        dtype=object,
        keep_default_na=False,
    )


def make_result_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "검수 상태": "주의",
                "오류 항목": "가격 이상치",
                "상품 그룹 ID": "G002",
                "상품 ID": "P002",
                "오류 이유": "같은 카테고리의 일반적인 가격 범위와 큰 차이가 있습니다.",
                "수정 권장사항": "가격 단위와 할인 가격 입력 여부를 확인하십시오.",
                "위험 수준": "중간",
            },
            {
                "검수 상태": "오류",
                "오류 항목": "필수 값 누락",
                "상품 그룹 ID": "G001",
                "상품 ID": "P001",
                "오류 이유": "필수 항목 'color' 값이 누락되었습니다.",
                "수정 권장사항": "누락된 필수 값을 입력하세요.",
                "위험 수준": "높음",
            },
        ],
        columns=RESULT_COLUMNS,
    )


def make_issue(rule: str, message: str) -> ValidationIssue:
    return ValidationIssue(
        rule=rule,
        severity="error",
        product_group_id="G001",
        product_id="P001",
        message=message,
    )


def test_build_validation_result_csv_uses_utf8_bom_and_preserves_display_data():
    result_df = make_result_dataframe()

    csv_bytes = build_validation_result_csv(result_df)
    exported_df = read_exported_csv(csv_bytes)

    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert list(exported_df.columns) == RESULT_COLUMNS
    assert exported_df["상품 ID"].tolist() == ["P002", "P001"]
    assert exported_df["오류 이유"].tolist() == result_df["오류 이유"].tolist()


def test_prepare_export_dataframe_does_not_change_original_dataframe():
    result_df = make_result_dataframe()
    result_df.loc[0, "오류 이유"] = "=SUM(1,1)"
    original_df = result_df.copy(deep=True)

    export_df = prepare_export_dataframe(result_df)

    pd.testing.assert_frame_equal(result_df, original_df)
    assert export_df.loc[0, "오류 이유"] == "'=SUM(1,1)"
    assert result_df.loc[0, "오류 이유"] == "=SUM(1,1)"


def test_build_validation_result_csv_handles_empty_dataframe():
    result_df = pd.DataFrame(columns=RESULT_COLUMNS)

    csv_bytes = build_validation_result_csv(result_df)
    exported_df = read_exported_csv(csv_bytes)

    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert exported_df.empty
    assert list(exported_df.columns) == RESULT_COLUMNS


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=SUM(1,1)", "'=SUM(1,1)"),
        ("+SUM(1,1)", "'+SUM(1,1)"),
        ("-HYPERLINK('x','y')", "'-HYPERLINK('x','y')"),
        ("@SUM(1,1)", "'@SUM(1,1)"),
        ("'=SUM(1,1)", "'=SUM(1,1)"),
    ],
)
def test_sanitize_csv_cell_protects_formula_like_strings(value, expected):
    assert sanitize_csv_cell(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "P001",
        "상품명 오류",
        "010-****-0000",
        "",
    ],
)
def test_sanitize_csv_cell_keeps_safe_strings(value):
    assert sanitize_csv_cell(value) == value


def test_sanitize_csv_cell_keeps_non_string_values_unchanged():
    values = [1000, 0, -5000, None, pd.NA, ["=SUM(1,1)"]]

    for value in values:
        assert sanitize_csv_cell(value) is value


def test_prepare_export_dataframe_keeps_numeric_and_missing_values_safe():
    result_df = pd.DataFrame(
        {
            "text": pd.Series(["=SUM(1,1)", "", None, pd.NA], dtype=object),
            "price": pd.Series([1000, 0, -5000, None], dtype=object),
            "stock": pd.Series([10, 0, None, pd.NA], dtype=object),
        }
    )

    export_df = prepare_export_dataframe(result_df)

    assert export_df.loc[0, "text"] == "'=SUM(1,1)"
    assert export_df.loc[1, "text"] == ""
    assert pd.isna(export_df.loc[2, "text"])
    assert pd.isna(export_df.loc[3, "text"])
    assert export_df["price"].tolist() == [1000, 0, -5000, None]
    assert export_df.loc[0, "stock"] == 10
    assert export_df.loc[1, "stock"] == 0
    assert pd.isna(export_df.loc[2, "stock"])
    assert pd.isna(export_df.loc[3, "stock"])


@pytest.mark.parametrize(
    ("uploaded_filename", "expected"),
    [
        ("products.csv", "products_validation_results.csv"),
        ("상품목록.CSV", "상품목록_validation_results.csv"),
        (None, DEFAULT_RESULT_FILENAME),
        ("", DEFAULT_RESULT_FILENAME),
        ("../../products.csv", "products_validation_results.csv"),
        (r"..\products.csv", "products_validation_results.csv"),
        ("상품:목록?.csv", "상품_목록__validation_results.csv"),
    ],
)
def test_build_result_filename_uses_uploaded_file_stem_safely(
    uploaded_filename,
    expected,
):
    assert build_result_filename(uploaded_filename) == expected


def test_build_result_filename_limits_long_file_stem():
    filename = build_result_filename(f"{'a' * 200}.csv")

    assert filename == f"{'a' * MAX_FILENAME_STEM_LENGTH}_validation_results.csv"


def test_csv_export_does_not_expose_raw_personal_information_when_results_are_masked():
    issues = [
        make_issue(
            rule="phone_number",
            message="field 'seller' contains phone number '010-****-0000'",
        ),
        make_issue(
            rule="email_address",
            message="field 'description' contains email address 'se****@example.test'",
        ),
        make_issue(
            rule="resident_registration_number",
            message=(
                "field 'description' contains resident registration number "
                "'000000-*******'"
            ),
        ),
    ]
    result_df = build_result_dataframe(issues)

    csv_text = build_validation_result_csv(result_df).decode("utf-8-sig")

    assert "010-0000-0000" not in csv_text
    assert "seller@example.test" not in csv_text
    assert "000000-1000000" not in csv_text
    assert "010-****-0000" in csv_text
    assert "se****@example.test" in csv_text
    assert "000000-*******" in csv_text


def test_products_dev_export_matches_filtered_validation_results_after_option_filter():
    products = load_products(DEV_DATA_PATH)
    issues = run_all_rules(products)
    result_df = build_result_dataframe(issues)

    csv_bytes = build_validation_result_csv(result_df)
    exported_df = read_exported_csv(csv_bytes)

    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    assert len(exported_df) == 6
    assert set(exported_df["검수 상태"]) == {"오류"}
    assert "상품명 중복" not in set(exported_df["오류 항목"])
    assert "P001" not in set(exported_df["상품 ID"])
    assert "P002" not in set(exported_df["상품 ID"])
    assert PRICE_RECOMMENDATION in set(exported_df["수정 권장사항"])
