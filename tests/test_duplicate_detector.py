from dataclasses import asdict

from core.duplicate_detector import (
    detect_duplicate_products,
    find_duplicate_product_ids,
    find_duplicate_product_names,
    normalize_product_name,
)
from core.models import Product
from core.privacy import mask_personal_information
from core.rules import check_missing_required_fields, run_all_rules


def make_product(**overrides) -> Product:
    defaults = dict(
        product_group_id="G001",
        product_id="P001",
        product_name="테스트 상품",
        category="TOP",
        color="BLACK",
        size="M",
        stock=5,
        price=10000,
        image_path="fake/image.jpg",
    )
    defaults.update(overrides)
    return Product(**defaults)


def test_find_duplicate_product_ids_flags_two_matching_ids():
    products = [
        make_product(product_group_id="G001", product_id="P001"),
        make_product(product_group_id="G002", product_id="P001", product_name="다른 상품"),
    ]

    issues = find_duplicate_product_ids(products)

    assert len(issues) == 2
    assert {issue.severity for issue in issues} == {"error"}
    assert all(issue.rule == "duplicate_product_id" for issue in issues)
    assert all("rows 2, 3" in issue.message for issue in issues)


def test_find_duplicate_product_ids_flags_every_product_in_large_group():
    products = [
        make_product(product_group_id="G001", product_id="P001"),
        make_product(product_group_id="G002", product_id="P001"),
        make_product(product_group_id="G003", product_id="P001"),
    ]

    issues = find_duplicate_product_ids(products)

    assert len(issues) == 3
    assert [issue.product_group_id for issue in issues] == ["G001", "G002", "G003"]
    assert all("rows 2, 3, 4" in issue.message for issue in issues)


def test_find_duplicate_product_ids_allows_different_ids():
    products = [
        make_product(product_id="P001"),
        make_product(product_id="P002"),
    ]

    assert find_duplicate_product_ids(products) == []


def test_find_duplicate_product_ids_ignores_blank_ids():
    products = [
        make_product(product_id=""),
        make_product(product_id=""),
    ]

    assert find_duplicate_product_ids(products) == []


def test_find_duplicate_product_ids_ignores_whitespace_only_ids():
    products = [
        make_product(product_id="   "),
        make_product(product_id=" "),
    ]

    assert find_duplicate_product_ids(products) == []


def test_normalize_product_name_keeps_korean_english_and_numbers():
    assert normalize_product_name(" 가짜-Product_123 / 테스트! ") == "가짜product123테스트"


def test_normalize_product_name_handles_missing_or_blank_values():
    assert normalize_product_name(None) == ""
    assert normalize_product_name("") == ""
    assert normalize_product_name("   ") == ""


def test_find_duplicate_product_names_flags_exact_match():
    products = [
        make_product(product_id="P001", product_name="가짜 상품"),
        make_product(product_id="P002", product_name="가짜 상품"),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2
    assert all(issue.rule == "duplicate_product_name" for issue in issues)
    assert all(issue.severity == "warning" for issue in issues)


def test_find_duplicate_product_names_flags_whitespace_only_difference():
    products = [
        make_product(product_id="P001", product_name="가짜 테스트 1"),
        make_product(product_id="P002", product_name="가짜테스트1"),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2
    assert all("product_ids 'P001, P002'" in issue.message for issue in issues)


def test_find_duplicate_product_names_flags_separator_only_difference():
    products = [
        make_product(product_id="P001", product_name="무지-반팔-티셔츠"),
        make_product(product_id="P002", product_name="무지_반팔/티셔츠"),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2


def test_find_duplicate_product_names_flags_case_only_difference():
    products = [
        make_product(product_id="P001", product_name="Fake Test Item 1"),
        make_product(product_id="P002", product_name="FAKE_TEST_ITEM_1"),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2
    assert all("faketestitem1" in issue.message for issue in issues)


def test_find_duplicate_product_names_ignores_blank_names():
    products = [
        make_product(product_id="P001", product_name=""),
        make_product(product_id="P002", product_name="   "),
    ]

    assert find_duplicate_product_names(products) == []


def test_find_duplicate_product_names_allows_different_names():
    products = [
        make_product(product_id="P001", product_name="가짜 상의"),
        make_product(product_id="P002", product_name="가짜 하의"),
    ]

    assert find_duplicate_product_names(products) == []


def test_detect_duplicate_products_does_not_modify_original_products():
    products = [
        make_product(product_id="P001", product_name="가짜 상품"),
        make_product(product_id="P001", product_name="가짜상품"),
    ]
    before_products = [asdict(product) for product in products]

    detect_duplicate_products(products)

    assert [asdict(product) for product in products] == before_products


def test_run_all_rules_keeps_existing_missing_field_check():
    products = [make_product(product_id="", product_name="")]

    issues = run_all_rules(products)
    missing_rules = [issue.rule for issue in issues if issue.rule == "missing_required_field"]

    assert missing_rules == ["missing_required_field", "missing_required_field"]
    assert check_missing_required_fields(products)


def test_personal_information_masking_still_masks_sentence_values():
    masked_text = mask_personal_information("문의 010-1234-5678 seller@test.com")

    assert masked_text == "문의 010-****-5678 se****@test.com"
