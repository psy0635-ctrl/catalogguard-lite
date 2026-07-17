# 역할: 상품 그룹 안의 카테고리 비교와 구조화 메시지 계약을 검증합니다.
from dataclasses import asdict

from core.group_category_consistency_detector import (
    build_group_category_message,
    find_inconsistent_group_categories,
    parse_group_category_message,
)
from core.models import Product


def make_product(**overrides) -> Product:
    defaults = {
        "product_group_id": "G001",
        "product_id": "P001",
        "product_name": "테스트 상품",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 5,
        "price": 10000,
        "image_path": "image.jpg",
    }
    defaults.update(overrides)
    return Product(**defaults)


def test_find_inconsistent_group_categories_allows_same_category():
    products = [
        make_product(product_id="P001", category="TOP"),
        make_product(product_id="P002", category="TOP"),
    ]

    assert find_inconsistent_group_categories(products) == []


def test_find_inconsistent_group_categories_allows_whitespace_case_and_aliases():
    products = [
        make_product(product_id="P001", category="TOP"),
        make_product(product_id="P002", category=" top "),
        make_product(product_id="P003", category="상의"),
    ]

    assert find_inconsistent_group_categories(products) == []


def test_find_inconsistent_group_categories_flags_all_nonblank_rows():
    products = [
        make_product(product_id="P001", category="TOP"),
        make_product(product_id="P002", category="SHOES"),
    ]

    issues = find_inconsistent_group_categories(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002"]
    assert all(issue.rule == "inconsistent_group_category" for issue in issues)
    assert all(issue.severity == "error" for issue in issues)
    assert all(issue.product_group_id == "G001" for issue in issues)
    assert all(
        parse_group_category_message(issue.message)
        == (
            "G001",
            [
                {"display_value": "TOP", "product_ids": ["P001"]},
                {"display_value": "SHOES", "product_ids": ["P002"]},
            ],
        )
        for issue in issues
    )


def test_find_inconsistent_group_categories_ignores_different_groups():
    products = [
        make_product(product_group_id="G001", product_id="P001", category="TOP"),
        make_product(product_group_id="G002", product_id="P002", category="SHOES"),
    ]

    assert find_inconsistent_group_categories(products) == []


def test_find_inconsistent_group_categories_ignores_blank_category():
    products = [
        make_product(product_id="P001", category="TOP"),
        make_product(product_id="P002", category="   "),
        make_product(product_id="P003", category=None),
    ]

    assert find_inconsistent_group_categories(products) == []


def test_find_inconsistent_group_categories_excludes_blank_row_from_mismatch():
    products = [
        make_product(product_id="P001", category="TOP"),
        make_product(product_id="P002", category="SHOES"),
        make_product(product_id="P003", category=""),
    ]

    issues = find_inconsistent_group_categories(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002"]


def test_find_inconsistent_group_categories_keeps_first_display_values_in_input_order():
    products = [
        make_product(product_id="P001", category=" top "),
        make_product(product_id="P002", category="상의"),
        make_product(product_id="P003", category="BOTTOM"),
        make_product(product_id="P004", category="SHOES"),
    ]

    first_run = find_inconsistent_group_categories(products)
    second_run = find_inconsistent_group_categories(products)
    parsed_message = parse_group_category_message(first_run[0].message)

    assert [issue.product_id for issue in first_run] == [
        "P001",
        "P002",
        "P003",
        "P004",
    ]
    assert parsed_message == (
        "G001",
        [
            {"display_value": "top", "product_ids": ["P001", "P002"]},
            {"display_value": "BOTTOM", "product_ids": ["P003"]},
            {"display_value": "SHOES", "product_ids": ["P004"]},
        ],
    )
    assert [issue.message for issue in first_run] == [
        issue.message for issue in second_run
    ]


def test_find_inconsistent_group_categories_keeps_global_input_order():
    products = [
        make_product(product_group_id="G001", product_id="P001", category="TOP"),
        make_product(product_group_id="G002", product_id="P002", category="SHOES"),
        make_product(product_group_id="G001", product_id="P003", category="BOTTOM"),
        make_product(product_group_id="G002", product_id="P004", category="BAG"),
    ]

    issues = find_inconsistent_group_categories(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002", "P003", "P004"]


def test_group_category_message_round_trips_special_characters():
    category_groups = [
        {"display_value": "TOP, PREMIUM", "product_ids": ["P'001", 'P"002']},
        {"display_value": "가방, 한정판", "product_ids": ["상품 003"]},
    ]

    message = build_group_category_message('G"한글, 001', category_groups)

    assert parse_group_category_message(message) == ('G"한글, 001', category_groups)


def test_parse_group_category_message_rejects_malformed_payloads():
    assert parse_group_category_message("not-a-group-category-message") is None
    assert parse_group_category_message("inconsistent_group_category:{broken") is None
    assert (
        parse_group_category_message(
            'inconsistent_group_category:{"product_group_id":"G001","categories":[1]}'
        )
        is None
    )


def test_find_inconsistent_group_categories_does_not_modify_products_or_order():
    products = [
        make_product(product_id="P001", category=" top "),
        make_product(product_id="P002", category=" SHOES "),
    ]
    before_products = [asdict(product) for product in products]
    before_identities = [id(product) for product in products]

    find_inconsistent_group_categories(products)

    assert [asdict(product) for product in products] == before_products
    assert [id(product) for product in products] == before_identities


def test_find_inconsistent_group_categories_allows_same_invalid_category():
    products = [
        make_product(product_id="P001", category="UNKNOWN_CATEGORY"),
        make_product(product_id="P002", category=" unknown_category "),
    ]

    assert find_inconsistent_group_categories(products) == []


def test_find_inconsistent_group_categories_ignores_blank_group_id():
    products = [
        make_product(product_group_id="", product_id="P001", category="TOP"),
        make_product(product_group_id="   ", product_id="P002", category="SHOES"),
    ]

    assert find_inconsistent_group_categories(products) == []
