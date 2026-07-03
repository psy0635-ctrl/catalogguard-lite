# 역할: 상품 입력 CSV 템플릿 생성 결과가 업로드와 검수를 통과하는지 테스트합니다.
import io
from dataclasses import asdict

import pandas as pd

from config.settings import CSV_TEMPLATE_COLUMNS, OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from core.loader import load_products_from_dataframe
from core.privacy import (
    EMAIL_PATTERN,
    find_phone_number_matches,
    find_resident_registration_number_matches,
)
from core.product_template import (
    EXAMPLE_TEMPLATE_PRODUCT,
    build_product_template_csv,
    build_product_template_dataframe,
    get_product_template_filename,
)
from core.result_exporter import CSV_FORMULA_PREFIXES
from core.rules import run_all_rules
from core.upload_validator import validate_and_read_uploaded_csv


def read_template_csv(csv_bytes: bytes) -> pd.DataFrame:
    return pd.read_csv(
        io.BytesIO(csv_bytes),
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )


def test_build_product_template_dataframe_returns_one_row_dataframe():
    template_df = build_product_template_dataframe()

    assert isinstance(template_df, pd.DataFrame)
    assert len(template_df) == 1
    assert len(template_df.columns) > 0


def test_product_template_columns_match_supported_columns_in_order():
    template_df = build_product_template_dataframe()
    expected_columns = [*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS]

    assert list(template_df.columns) == expected_columns
    assert list(template_df.columns) == CSV_TEMPLATE_COLUMNS
    assert len(template_df.columns) == len(set(template_df.columns))


def test_product_template_required_values_are_not_blank():
    template_df = build_product_template_dataframe()
    row = template_df.iloc[0]

    for column in REQUIRED_COLUMNS:
        assert str(row[column]).strip()


def test_product_template_numeric_values_are_valid():
    template_df = build_product_template_dataframe()
    row = template_df.iloc[0]

    stock = int(row["stock"])
    price = int(row["price"])

    assert stock >= 0
    assert price > 0


def test_build_product_template_csv_uses_utf8_bom():
    csv_bytes = build_product_template_csv()

    assert csv_bytes.startswith(b"\xef\xbb\xbf")


def test_product_template_csv_keeps_korean_text():
    template_df = read_template_csv(build_product_template_csv())

    assert template_df.loc[0, "product_name"] == "오버핏 반팔 티셔츠"
    assert template_df.loc[0, "description"] == "템플릿 작성용 가짜 예시 상품입니다."


def test_product_template_csv_round_trips_columns_and_values():
    template_df = build_product_template_dataframe()
    reparsed_df = read_template_csv(build_product_template_csv())

    assert list(reparsed_df.columns) == list(template_df.columns)
    assert reparsed_df.loc[0, "product_group_id"] == "G001"
    assert reparsed_df.loc[0, "product_id"] == "P001"
    assert reparsed_df.loc[0, "stock"] == "10"
    assert reparsed_df.loc[0, "price"] == "19900"


def test_product_template_upload_validation_passes():
    validated_df = validate_and_read_uploaded_csv(
        get_product_template_filename(),
        build_product_template_csv(),
    )

    assert len(validated_df) == 1
    assert list(validated_df.columns) == CSV_TEMPLATE_COLUMNS


def test_product_template_converts_to_product():
    validated_df = validate_and_read_uploaded_csv(
        get_product_template_filename(),
        build_product_template_csv(),
    )

    products = load_products_from_dataframe(validated_df)

    assert len(products) == 1
    assert asdict(products[0]) == asdict(EXAMPLE_TEMPLATE_PRODUCT)


def test_product_template_example_product_passes_all_rules():
    validated_df = validate_and_read_uploaded_csv(
        get_product_template_filename(),
        build_product_template_csv(),
    )
    products = load_products_from_dataframe(validated_df)

    assert run_all_rules(products) == []


def test_product_template_does_not_contain_personal_information_patterns():
    csv_text = build_product_template_csv().decode("utf-8-sig")

    assert EMAIL_PATTERN.search(csv_text) is None
    assert find_phone_number_matches(csv_text) == []
    assert find_resident_registration_number_matches(csv_text) == []


def test_product_template_does_not_contain_formula_risk_strings():
    template_df = build_product_template_dataframe()

    for value in template_df.iloc[0].tolist():
        if not isinstance(value, str):
            continue
        assert not value.startswith(CSV_FORMULA_PREFIXES)


def test_product_template_does_not_change_column_settings():
    original_required_columns = tuple(REQUIRED_COLUMNS)
    original_optional_columns = tuple(OPTIONAL_COLUMNS)
    original_template_columns = tuple(CSV_TEMPLATE_COLUMNS)

    build_product_template_dataframe()
    build_product_template_csv()

    assert tuple(REQUIRED_COLUMNS) == original_required_columns
    assert tuple(OPTIONAL_COLUMNS) == original_optional_columns
    assert tuple(CSV_TEMPLATE_COLUMNS) == original_template_columns


def test_get_product_template_filename_returns_expected_filename():
    assert get_product_template_filename() == "catalogguard_product_template.csv"
