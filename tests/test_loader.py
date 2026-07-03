# 역할: CSV와 DataFrame을 Product 객체로 변환하는 로더 동작을 테스트합니다.
import pandas as pd
import pytest

from config.settings import DEV_DATA_PATH
from core.loader import load_products, load_products_from_dataframe, parse_optional_int
from core.rules import run_all_rules


# CSV 파일을 Product 목록으로 읽는 로더 동작을 검증합니다.
def test_load_products_returns_expected_count():
    products = load_products(DEV_DATA_PATH)

    assert len(products) == 5


def test_load_products_parses_fields_correctly():
    products = load_products(DEV_DATA_PATH)

    first = products[0]
    assert first.product_group_id == "G001"
    assert first.product_id == "P001"
    assert first.product_name == "오버핏 반팔 티셔츠"
    assert first.category == "TOP"
    assert first.stock == 5


def test_load_products_treats_blank_field_as_empty_string():
    products = load_products(DEV_DATA_PATH)

    missing_color = next(p for p in products if p.product_id == "P004")
    assert missing_color.color == ""


def test_load_products_handles_missing_optional_content_columns():
    products = load_products(DEV_DATA_PATH)

    assert products[0].description == ""
    assert products[0].seller == ""


def test_load_products_from_dataframe_returns_expected_product():
    dataframe = pd.read_csv(DEV_DATA_PATH, dtype=str, keep_default_na=False)

    products = load_products_from_dataframe(dataframe)

    first = products[0]
    assert first.product_group_id == "G001"
    assert first.product_id == "P001"
    assert first.product_name == "오버핏 반팔 티셔츠"
    assert first.stock == 5
    assert first.price == 19000


def test_load_products_from_dataframe_matches_load_products_result():
    dataframe = pd.read_csv(DEV_DATA_PATH, dtype=str, keep_default_na=False)

    dataframe_products = load_products_from_dataframe(dataframe)
    file_products = load_products(DEV_DATA_PATH)

    assert dataframe_products == file_products


def test_load_products_from_dataframe_handles_missing_optional_content_columns():
    dataframe = pd.DataFrame(
        [
            {
                "product_group_id": "G001",
                "product_id": "P001",
                "product_name": "기본 상품",
                "category": "TOP",
                "color": "BLACK",
                "size": "M",
                "stock": "5",
                "price": "10000",
                "image_path": "a.jpg",
            }
        ]
    )

    products = load_products_from_dataframe(dataframe)

    assert products[0].description == ""
    assert products[0].seller == ""


def test_load_products_from_dataframe_does_not_change_original_dataframe():
    dataframe = pd.DataFrame(
        [
            {
                "product_group_id": " G001 ",
                "product_id": " P001 ",
                "product_name": " 기본 상품 ",
                "category": " TOP ",
                "color": " BLACK ",
                "size": " M ",
                "stock": " 5 ",
                "price": " 10000 ",
                "image_path": " a.jpg ",
            }
        ]
    )
    original_dataframe = dataframe.copy(deep=True)

    products = load_products_from_dataframe(dataframe)

    assert products[0].product_group_id == "G001"
    pd.testing.assert_frame_equal(dataframe, original_dataframe)


def test_load_products_reads_optional_content_columns(tmp_path):
    extended_csv = tmp_path / "extended.csv"
    extended_csv.write_text(
        (
            "product_group_id,product_id,product_name,category,color,size,"
            "stock,price,image_path,description,seller\n"
            "G001,P001,기본 상품,TOP,BLACK,M,5,10000,a.jpg,"
            "안전한 상품 설명,공식 판매자\n"
        ),
        encoding="utf-8",
    )

    products = load_products(extended_csv)

    assert products[0].description == "안전한 상품 설명"
    assert products[0].seller == "공식 판매자"


def test_load_products_strips_blank_optional_content_values(tmp_path):
    extended_csv = tmp_path / "blank_optional.csv"
    extended_csv.write_text(
        (
            "product_group_id,product_id,product_name,category,color,size,"
            "stock,price,image_path,description,seller\n"
            "G001,P001,기본 상품,TOP,BLACK,M,5,10000,a.jpg,   ,   \n"
        ),
        encoding="utf-8",
    )

    products = load_products(extended_csv)

    assert products[0].description == ""
    assert products[0].seller == ""


def test_load_products_raises_on_missing_column(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("product_group_id,product_id\nG001,P001\n", encoding="utf-8")

    try:
        load_products(bad_csv)
        assert False, "ValueError expected"
    except ValueError as exc:
        assert "product_name" in str(exc)


def test_load_products_raises_on_header_only_csv(tmp_path):
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text(
        (
            "product_group_id,product_id,product_name,category,color,size,"
            "stock,price,image_path\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="상품 데이터가 없습니다"):
        load_products(empty_csv)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5", 5),
        ("-5", -5),
        ("0", 0),
        (" 10 ", 10),
        ("+5", 5),
    ],
)
def test_parse_optional_int_parses_valid_integer_strings(value, expected):
    assert parse_optional_int(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "--5", "---10", "5.5", "1,000"])
def test_parse_optional_int_returns_none_for_invalid_integer_strings(value):
    assert parse_optional_int(value) is None


def test_load_products_keeps_invalid_numeric_strings_as_none(tmp_path):
    bad_number_csv = tmp_path / "bad_number.csv"
    bad_number_csv.write_text(
        (
            "product_group_id,product_id,product_name,category,color,size,"
            "stock,price,image_path\n"
            "G001,P001,상품A,TOP,BLACK,M,--5,--1000,a.jpg\n"
        ),
        encoding="utf-8",
    )

    products = load_products(bad_number_csv)
    issues = run_all_rules(products)
    issue_rules = {issue.rule for issue in issues}

    assert products[0].stock is None
    assert products[0].price is None
    assert "invalid_stock" in issue_rules
    assert "invalid_price" in issue_rules
