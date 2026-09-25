from dataclasses import asdict

import pytest

from core.group_product_name_consistency_detector import (
    build_group_product_name_message,
    find_inconsistent_group_product_names,
    parse_group_product_name_message,
)
from core.models import Product


def make_product(**overrides):
    values = dict(product_group_id="G001", product_id="P001", product_name="Basic T-Shirt",
                  category="TOP", color="BLACK", size="M", stock=5, price=10000,
                  image_path="image.jpg", source_row_number=2)
    values.update(overrides)
    return Product(**values)


@pytest.mark.parametrize("other_name", ["Basic T-Shirt", " Basic T-Shirt ",
    "basic t-shirt", "Basic   T-Shirt", "\tBASIC  T-SHIRT\n"])
def test_equivalent_names_have_no_issue(other_name):
    assert find_inconsistent_group_product_names([
        make_product(), make_product(product_id="P002", product_name=other_name)
    ]) == []


def test_mismatch_warns_every_named_row_with_source_rows_and_stable_message():
    products = [
        make_product(product_id="P001", product_name=" 베이직 티셔츠 ", source_row_number=4),
        make_product(product_id="P002", product_name="베이직 티셔츠", source_row_number=7),
        make_product(product_id="P003", product_name="프리미엄 티셔츠", source_row_number=9),
    ]
    issues = find_inconsistent_group_product_names(products)
    assert [issue.product_id for issue in issues] == ["P001", "P002", "P003"]
    assert [issue.source_row_number for issue in issues] == [4, 7, 9]
    assert all(issue.rule == "inconsistent_group_product_name" and issue.severity == "warning"
               and issue.related_source_rows == [] for issue in issues)
    assert len({issue.message for issue in issues}) == 1
    assert parse_group_product_name_message(issues[0].message) == ("G001", [
        {"display_value": "베이직 티셔츠", "product_ids": ["P001", "P002"]},
        {"display_value": "프리미엄 티셔츠", "product_ids": ["P003"]},
    ])


def test_different_groups_and_blank_ids_do_not_compare():
    products = [make_product(product_group_id="G001"),
                make_product(product_group_id="G002", product_name="Other"),
                make_product(product_group_id="", product_name="One"),
                make_product(product_group_id="   ", product_name="Two")]
    assert find_inconsistent_group_product_names(products) == []


@pytest.mark.parametrize("blank_name", ["", "   ", None])
def test_blank_name_is_excluded_from_mismatch(blank_name):
    products = [make_product(product_id="P001"),
                make_product(product_id="P002", product_name="Different"),
                make_product(product_id="P003", product_name=blank_name)]
    assert [issue.product_id for issue in find_inconsistent_group_product_names(products)] == ["P001", "P002"]
    assert find_inconsistent_group_product_names([products[0], products[2]]) == []


def test_global_order_and_original_products_are_preserved():
    products = [make_product(product_group_id="G1", product_id="P1", product_name=" One "),
                make_product(product_group_id="G2", product_id="P2", product_name="Two"),
                make_product(product_group_id="G1", product_id="P3", product_name="Three"),
                make_product(product_group_id="G2", product_id="P4", product_name="Four")]
    before = [asdict(product) for product in products]
    identities = [id(product) for product in products]
    assert [issue.product_id for issue in find_inconsistent_group_product_names(products)] == ["P1", "P2", "P3", "P4"]
    assert [asdict(product) for product in products] == before
    assert [id(product) for product in products] == identities


def test_message_round_trip_with_special_characters():
    names = [{"display_value": "한글, '한정' \"판\"", "product_ids": ["P'1", 'P"2']},
             {"display_value": "다른 상품", "product_ids": ["P3"]}]
    assert parse_group_product_name_message(build_group_product_name_message('G"한글', names)) == ('G"한글', names)


@pytest.mark.parametrize("message", ["wrong", "inconsistent_group_product_name:{broken",
    "inconsistent_group_product_name:[]",
    'inconsistent_group_product_name:{"product_group_id":1,"product_names":[]}',
    'inconsistent_group_product_name:{"product_group_id":"G","product_names":{}}',
    'inconsistent_group_product_name:{"product_group_id":"G","product_names":[1]}',
    'inconsistent_group_product_name:{"product_group_id":"G","product_names":[{"display_value":1,"product_ids":[]}]}',
    'inconsistent_group_product_name:{"product_group_id":"G","product_names":[{"display_value":"A","product_ids":[1]}]}'])
def test_parser_rejects_malformed_messages(message):
    assert parse_group_product_name_message(message) is None
