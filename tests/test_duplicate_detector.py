# 역할: 상품 ID와 상품명 중복 탐지 유틸의 다양한 비교 조건을 테스트합니다.
from dataclasses import asdict

from core import duplicate_detector
from core.duplicate_detector import (
    detect_duplicate_products,
    find_duplicate_product_ids,
    find_duplicate_product_names,
    has_explicit_option_difference,
    normalize_product_name,
    normalize_option_value,
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


def test_normalize_option_value_strips_casefolds_and_handles_none():
    assert normalize_option_value(None) == ""
    assert normalize_option_value(" BLACK ") == "black"
    assert normalize_option_value(" M ") == "m"


def test_has_explicit_option_difference_detects_different_color():
    first = make_product(color="BLACK", size="")
    second = make_product(color="NAVY", size="")

    assert has_explicit_option_difference(first, second)


def test_has_explicit_option_difference_detects_different_size():
    first = make_product(color="BLACK", size="M")
    second = make_product(color="BLACK", size="L")

    assert has_explicit_option_difference(first, second)


def test_has_explicit_option_difference_requires_both_values_present():
    first = make_product(color="BLACK", size="M")
    second = make_product(color="", size="M")

    assert not has_explicit_option_difference(first, second)


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


def test_find_duplicate_product_names_ignores_same_group_different_color_option():
    products = [
        make_product(product_id="P001", product_name="기본 티셔츠", color="BLACK", size="M"),
        make_product(product_id="P002", product_name="기본 티셔츠", color="NAVY", size="M"),
    ]

    assert find_duplicate_product_names(products) == []


def test_find_duplicate_product_names_ignores_same_group_different_size_option():
    products = [
        make_product(product_id="P001", product_name="기본 티셔츠", color="BLACK", size="M"),
        make_product(product_id="P002", product_name="기본 티셔츠", color="BLACK", size="L"),
    ]

    assert find_duplicate_product_names(products) == []


def test_find_duplicate_product_names_ignores_same_group_different_color_and_size_option():
    products = [
        make_product(product_id="P001", product_name="기본 티셔츠", color="BLACK", size="M"),
        make_product(product_id="P002", product_name="기본 티셔츠", color="NAVY", size="L"),
    ]

    assert find_duplicate_product_names(products) == []


def test_find_duplicate_product_names_flags_same_group_same_option():
    products = [
        make_product(product_id="P001", product_name="기본 티셔츠", color="BLACK", size="M"),
        make_product(product_id="P002", product_name="기본 티셔츠", color="BLACK", size="M"),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2
    assert {issue.product_id for issue in issues} == {"P001", "P002"}
    assert all(issue.rule == "duplicate_product_name" for issue in issues)


def test_find_duplicate_product_names_flags_different_groups_even_with_different_options():
    products = [
        make_product(
            product_group_id="G001",
            product_id="P001",
            product_name="기본 티셔츠",
            color="BLACK",
            size="M",
        ),
        make_product(
            product_group_id="G002",
            product_id="P002",
            product_name="기본 티셔츠",
            color="NAVY",
            size="L",
        ),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2
    assert {issue.product_group_id for issue in issues} == {"G001", "G002"}


def test_find_duplicate_product_names_flags_blank_group_ids():
    products = [
        make_product(
            product_group_id="",
            product_id="P001",
            product_name="기본 티셔츠",
            color="BLACK",
            size="M",
        ),
        make_product(
            product_group_id="",
            product_id="P002",
            product_name="기본 티셔츠",
            color="NAVY",
            size="L",
        ),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2


def test_find_duplicate_product_names_flags_when_one_color_is_blank():
    products = [
        make_product(product_id="P001", product_name="기본 티셔츠", color="BLACK", size="M"),
        make_product(product_id="P002", product_name="기본 티셔츠", color="", size="M"),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2


def test_find_duplicate_product_names_flags_when_one_size_is_blank():
    products = [
        make_product(product_id="P001", product_name="기본 티셔츠", color="BLACK", size="M"),
        make_product(product_id="P002", product_name="기본 티셔츠", color="BLACK", size=""),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2


def test_find_duplicate_product_names_normalizes_option_case_and_spaces():
    products = [
        make_product(
            product_id="P001",
            product_name="기본 티셔츠",
            color=" BLACK ",
            size=" M ",
        ),
        make_product(
            product_id="P002",
            product_name="기본 티셔츠",
            color="black",
            size="m",
        ),
    ]

    issues = find_duplicate_product_names(products)

    assert len(issues) == 2


def test_find_duplicate_product_names_handles_multiple_products_pairwise():
    products = [
        make_product(product_id="P001", product_name="기본 티셔츠", color="BLACK", size="M"),
        make_product(product_id="P002", product_name="기본 티셔츠", color="NAVY", size="M"),
        make_product(product_id="P003", product_name="기본 티셔츠", color="BLACK", size="M"),
    ]

    issues = find_duplicate_product_names(products)

    assert {issue.product_id for issue in issues} == {"P001", "P003"}
    assert all("rows 2, 4" in issue.message for issue in issues)


def test_find_duplicate_product_ids_still_flags_duplicate_id_with_different_options():
    products = [
        make_product(
            product_group_id="G001",
            product_id="P001",
            product_name="기본 티셔츠",
            color="BLACK",
            size="M",
        ),
        make_product(
            product_group_id="G002",
            product_id="P001",
            product_name="후드 집업",
            color="GRAY",
            size="L",
        ),
    ]

    issues = find_duplicate_product_ids(products)

    assert len(issues) == 2
    assert all(issue.rule == "duplicate_product_id" for issue in issues)
    assert all(issue.severity == "error" for issue in issues)


def test_detect_duplicate_products_does_not_modify_original_products():
    products = [
        make_product(product_id="P001", product_name="가짜 상품"),
        make_product(product_id="P001", product_name="가짜상품"),
    ]
    before_products = [asdict(product) for product in products]

    detect_duplicate_products(products)

    assert [asdict(product) for product in products] == before_products


def test_find_duplicate_product_names_does_not_modify_original_option_values():
    products = [
        make_product(
            product_group_id=" G001 ",
            product_id=" P001 ",
            product_name="기본 티셔츠",
            color=" BLACK ",
            size=" M ",
        ),
        make_product(
            product_group_id=" G001 ",
            product_id=" P002 ",
            product_name="기본 티셔츠",
            color="black",
            size="m",
        ),
    ]
    before_products = [asdict(product) for product in products]

    find_duplicate_product_names(products)

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


def test_find_duplicate_variant_combinations_flags_all_rows_with_standardized_options():
    products = [
        make_product(product_id="P001", product_name="상품 A", color="BLACK", size="M"),
        make_product(product_id="P002", product_name="상품 B", color="black", size="medium"),
    ]

    issues = duplicate_detector.find_duplicate_variant_combinations(products)

    assert len(issues) == 2
    assert [issue.product_id for issue in issues] == ["P001", "P002"]
    assert all(issue.rule == "duplicate_variant_combination" for issue in issues)
    assert all(issue.severity == "error" for issue in issues)
    assert all(
        duplicate_detector.parse_duplicate_variant_message(issue.message)
        == ("G001", "BLACK", "M", ["P001", "P002"])
        for issue in issues
    )


def test_find_duplicate_variant_combinations_flags_custom_color_and_numeric_size():
    products = [
        make_product(product_id="P001", color="MELANGE GRAY", size="95"),
        make_product(
            product_id="P002",
            color="melange gray",
            size=" 95 ",
            price=11000,
        ),
    ]

    issues = duplicate_detector.find_duplicate_variant_combinations(products)

    assert len(issues) == 2
    assert all(
        duplicate_detector.parse_duplicate_variant_message(issue.message)
        == ("G001", "melange gray", "95", ["P001", "P002"])
        for issue in issues
    )


def test_find_duplicate_variant_combinations_ignores_different_options_or_groups():
    products = [
        make_product(product_group_id="G001", product_id="P001", color="BLACK", size="M"),
        make_product(product_group_id="G001", product_id="P002", color="BLACK", size="L"),
        make_product(product_group_id="G001", product_id="P003", color="WHITE", size="M"),
        make_product(product_group_id="G002", product_id="P004", color="BLACK", size="M"),
    ]

    assert duplicate_detector.find_duplicate_variant_combinations(products) == []


def test_find_duplicate_variant_combinations_ignores_blank_color_or_size():
    products = [
        make_product(product_id="P001", color="BLACK", size=""),
        make_product(product_id="P002", color="BLACK", size=""),
        make_product(product_id="P003", color="", size="M"),
        make_product(product_id="P004", color="", size="M"),
    ]

    assert duplicate_detector.find_duplicate_variant_combinations(products) == []


def test_find_duplicate_variant_combinations_leaves_same_product_id_to_existing_rule():
    products = [
        make_product(product_id="P001", color="BLACK", size="M"),
        make_product(product_id="P001", color="black", size="medium"),
    ]

    assert duplicate_detector.find_duplicate_variant_combinations(products) == []
    assert len(find_duplicate_product_ids(products)) == 2


def test_find_duplicate_variant_combinations_keeps_input_order_for_three_rows():
    products = [
        make_product(product_id="P003", color="BLACK", size="M"),
        make_product(product_id="P001", color="black", size="medium"),
        make_product(product_id="P002", color="블랙", size="M"),
    ]

    first_run = duplicate_detector.find_duplicate_variant_combinations(products)
    second_run = duplicate_detector.find_duplicate_variant_combinations(products)

    assert [issue.product_id for issue in first_run] == ["P003", "P001", "P002"]
    assert [issue.message for issue in first_run] == [issue.message for issue in second_run]
    assert all(
        duplicate_detector.parse_duplicate_variant_message(issue.message)
        == ("G001", "BLACK", "M", ["P003", "P001", "P002"])
        for issue in first_run
    )


def test_find_duplicate_variant_combinations_keeps_global_input_order_across_buckets():
    products = [
        make_product(
            product_group_id="G001",
            product_id="P001",
            product_name="상품 A1",
            color="BLACK",
            size="M",
        ),
        make_product(
            product_group_id="G002",
            product_id="P002",
            product_name="상품 B1",
            color="WHITE",
            size="L",
        ),
        make_product(
            product_group_id="G002",
            product_id="P003",
            product_name="상품 B2",
            color="white",
            size="large",
        ),
        make_product(
            product_group_id="G001",
            product_id="P004",
            product_name="상품 A2",
            color="black",
            size="medium",
        ),
    ]

    issues = duplicate_detector.find_duplicate_variant_combinations(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002", "P003", "P004"]


def test_find_duplicate_variant_combinations_does_not_modify_products():
    products = [
        make_product(product_id="P001", color=" 블랙 ", size=" medium "),
        make_product(product_id="P002", color="BLACK", size="M"),
    ]
    before_products = [asdict(product) for product in products]

    duplicate_detector.find_duplicate_variant_combinations(products)

    assert [asdict(product) for product in products] == before_products
