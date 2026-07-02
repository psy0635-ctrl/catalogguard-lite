import pytest

from core.loader import load_products
from config.settings import DEV_DATA_PATH


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
