# 역할: 상품 ID와 상품명 중복 탐지 유틸의 다양한 비교 조건을 테스트합니다.
from dataclasses import asdict

import pytest

from core import duplicate_detector
from core.duplicate_detector import (
    build_duplicate_product_content_key,
    detect_duplicate_products,
    find_duplicate_product_content,
    find_duplicate_product_ids,
    find_duplicate_product_names,
    find_duplicate_variant_combinations,
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


# 아래는 size가 선택 값인 카테고리(BAG)의 빈 size도 완전 중복 비교에 포함되는지 확인합니다.
# 정책의 단일 기준은 검수·ETL과 같은 config.settings.FASHION_CATEGORY_ATTRIBUTE_RULES입니다.
def bag_product(**overrides) -> Product:
    defaults = dict(
        product_group_id="G001",
        product_id="P001",
        product_name="클래식 숄더백",
        category="BAG",
        color="BLACK",
        size="",
        stock=5,
        price=50000,
        image_path="fake/bag.jpg",
    )
    defaults.update(overrides)
    return Product(**defaults)


def test_build_duplicate_product_content_key_accepts_blank_size_for_bag():
    key = build_duplicate_product_content_key(bag_product())

    assert key is not None
    # 빈 size는 정규화 결과 ""로 그대로 키에 들어갑니다.
    assert key[3] == ""


@pytest.mark.parametrize("category", ["TOP", "BOTTOM", "OUTER", "SHOES"])
def test_build_duplicate_product_content_key_rejects_blank_size_for_apparel(category):
    product = bag_product(category=category, product_name="반팔 티셔츠")

    assert build_duplicate_product_content_key(product) is None


@pytest.mark.parametrize("blank_field", ["color", "product_name", "product_group_id", "product_id"])
def test_build_duplicate_product_content_key_still_rejects_other_blank_fields_for_bag(blank_field):
    product = bag_product(**{blank_field: ""})

    assert build_duplicate_product_content_key(product) is None


@pytest.mark.parametrize("category", ["ACCESSORY", "bag", ""])
def test_build_duplicate_product_content_key_rejects_blank_size_for_non_canonical_category(category):
    # 허용 목록에 없거나 canonical이 아닌 카테고리는 BAG로 추정하지 않습니다.
    assert build_duplicate_product_content_key(bag_product(category=category)) is None


@pytest.mark.parametrize("price", [None, 0, -1000])
def test_build_duplicate_product_content_key_still_rejects_invalid_price_for_bag(price):
    assert build_duplicate_product_content_key(bag_product(price=price)) is None


def test_find_duplicate_product_content_flags_two_blank_size_bags():
    products = [
        bag_product(product_group_id="G001", product_id="P001"),
        bag_product(product_group_id="G002", product_id="P002"),
    ]

    issues = find_duplicate_product_content(products)

    assert [issue.product_id for issue in issues] == ["P002"]
    assert issues[0].rule == "duplicate_product_content"
    assert issues[0].severity == "error"


def test_find_duplicate_product_content_treats_blank_size_and_free_as_different():
    # 빈 size를 FREE와 같은 값으로 보지 않습니다.
    products = [
        bag_product(product_group_id="G001", product_id="P001", size=""),
        bag_product(product_group_id="G002", product_id="P002", size="FREE"),
    ]

    assert find_duplicate_product_content(products) == []


@pytest.mark.parametrize(
    ("field", "value"),
    [("color", "WHITE"), ("price", 60000), ("product_name", "다른 가방")],
)
def test_find_duplicate_product_content_keeps_other_fields_significant_for_bag(field, value):
    products = [
        bag_product(product_group_id="G001", product_id="P001"),
        bag_product(product_group_id="G002", product_id="P002", **{field: value}),
    ]

    assert find_duplicate_product_content(products) == []


def test_find_duplicate_product_content_does_not_flag_blank_size_apparel():
    # TOP의 빈 size는 완전 중복이 아니라 기존 필수 값 누락 규칙이 처리합니다.
    products = [
        make_product(product_group_id="G001", product_id="P001", size=""),
        make_product(product_group_id="G002", product_id="P002", size=""),
    ]

    assert find_duplicate_product_content(products) == []
    missing_issues = check_missing_required_fields(products)
    assert len(missing_issues) == 2
    assert all("size" in issue.message for issue in missing_issues)


def test_find_duplicate_product_content_keeps_existing_behaviour_for_sized_products():
    products = [
        make_product(product_group_id="G001", product_id="P001", size="M"),
        make_product(product_group_id="G002", product_id="P002", size="M"),
    ]

    issues = find_duplicate_product_content(products)

    assert [issue.product_id for issue in issues] == ["P002"]


def test_find_duplicate_product_content_does_not_modify_products():
    products = [
        bag_product(product_group_id="G001", product_id="P001"),
        bag_product(product_group_id="G002", product_id="P002"),
    ]
    before = [asdict(product) for product in products]

    find_duplicate_product_content(products)

    assert [asdict(product) for product in products] == before


def test_find_duplicate_variant_combinations_detects_blank_size_bags():
    # size가 선택 값인 카테고리에서 빈 size는 정상 옵션 상태이므로 옵션 중복 비교 대상입니다.
    products = [
        bag_product(product_group_id="G001", product_id="P001"),
        bag_product(
            product_group_id="G001",
            product_id="P002",
            product_name="데일리 숄더백",
            price=52000,
        ),
    ]

    issues = find_duplicate_variant_combinations(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002"]
    assert all(issue.rule == "duplicate_variant_combination" for issue in issues)
    assert all(issue.severity == "error" for issue in issues)
    # 비교값은 빈 문자열 그대로 유지하며 FREE 같은 다른 값으로 바꾸지 않습니다.
    assert all(
        duplicate_detector.parse_duplicate_variant_message(issue.message)
        == ("G001", "BLACK", "", ["P001", "P002"])
        for issue in issues
    )


def test_find_duplicate_variant_combinations_skips_complete_duplicate_blank_size_bags():
    # 완전 중복 관계는 기존처럼 완전 중복 규칙이 우선하므로 옵션 중복으로 다시 표시하지 않습니다.
    products = [
        bag_product(product_group_id="G001", product_id="P001"),
        bag_product(product_group_id="G001", product_id="P002"),
    ]

    assert find_duplicate_variant_combinations(products) == []
    assert [issue.product_id for issue in find_duplicate_product_content(products)] == ["P002"]


def test_find_duplicate_variant_combinations_treats_blank_size_and_free_as_different_for_bag():
    # 빈 size를 FREE와 같은 값으로 보지 않는 기존 정책을 옵션 중복에서도 유지합니다.
    products = [
        bag_product(product_group_id="G001", product_id="P001", size=""),
        bag_product(product_group_id="G001", product_id="P002", size="FREE"),
    ]

    assert find_duplicate_variant_combinations(products) == []


# 아래는 별칭 의미 비교가 공백 표기 차이 때문에 빠지지 않는지 확인합니다.
# 완전 중복은 계속 엄격 비교이므로 두 규칙의 결과가 서로 달라야 정상입니다.
@pytest.mark.parametrize(
    "size",
    ["free size", "free  size", " free   size ", "free\tsize", "one  size"],
)
def test_find_duplicate_variant_combinations_matches_free_size_alias_spacing(size):
    products = [
        bag_product(product_group_id="G001", product_id="P001", size="FREE"),
        bag_product(product_group_id="G001", product_id="P002", size=size),
    ]

    issues = find_duplicate_variant_combinations(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002"]
    assert all(
        duplicate_detector.parse_duplicate_variant_message(issue.message)
        == ("G001", "BLACK", "FREE", ["P001", "P002"])
        for issue in issues
    )


@pytest.mark.parametrize("size", ["free size", "free  size", "one size", "프리사이즈"])
def test_find_duplicate_product_content_keeps_strict_size_comparison_for_aliases(size):
    # 완전 중복은 별칭을 적용하지 않으므로 표기가 다르면 계속 다른 상품입니다.
    products = [
        bag_product(product_group_id="G001", product_id="P001", size="FREE"),
        bag_product(product_group_id="G002", product_id="P002", size=size),
    ]

    assert find_duplicate_product_content(products) == []


def test_find_duplicate_product_content_still_matches_case_and_outer_space_only():
    # 대소문자와 앞뒤 공백만 다른 값은 기존처럼 완전 중복으로 봅니다.
    products = [
        bag_product(product_group_id="G001", product_id="P001", size="FREE"),
        bag_product(product_group_id="G002", product_id="P002", size=" free "),
    ]

    assert [issue.product_id for issue in find_duplicate_product_content(products)] == ["P002"]


def test_find_duplicate_variant_combinations_allows_different_colors_with_blank_size():
    products = [
        bag_product(product_group_id="G001", product_id="P001", color="BLACK"),
        bag_product(product_group_id="G001", product_id="P002", color="RED"),
    ]

    assert find_duplicate_variant_combinations(products) == []


def test_find_duplicate_variant_combinations_ignores_blank_size_bags_in_different_groups():
    # 옵션 중복은 같은 상품 그룹 안에서만 판단하는 기존 기준을 유지합니다.
    products = [
        bag_product(product_group_id="G001", product_id="P001"),
        bag_product(
            product_group_id="G002",
            product_id="P002",
            product_name="데일리 숄더백",
            price=52000,
        ),
    ]

    assert find_duplicate_variant_combinations(products) == []


@pytest.mark.parametrize("category", ["TOP", "BOTTOM", "OUTER", "SHOES"])
def test_find_duplicate_variant_combinations_skips_blank_size_for_required_categories(category):
    # size가 필수인 카테고리의 빈 size는 기존처럼 필수 값 누락 규칙이 처리합니다.
    products = [
        bag_product(
            product_group_id="G001",
            product_id="P001",
            category=category,
            product_name="반팔 티셔츠",
        ),
        bag_product(
            product_group_id="G001",
            product_id="P002",
            category=category,
            product_name="기본 반팔",
            price=52000,
        ),
    ]

    assert find_duplicate_variant_combinations(products) == []
    assert len(check_missing_required_fields(products)) == 2


@pytest.mark.parametrize("category", ["ACCESSORY", "bag", ""])
def test_find_duplicate_variant_combinations_skips_blank_size_for_non_canonical_category(category):
    # 허용 목록에 없거나 canonical이 아닌 카테고리는 BAG로 추정하지 않고 기존 정책을 유지합니다.
    products = [
        bag_product(product_group_id="G001", product_id="P001", category=category),
        bag_product(
            product_group_id="G001",
            product_id="P002",
            category=category,
            product_name="데일리 숄더백",
            price=52000,
        ),
    ]

    assert find_duplicate_variant_combinations(products) == []


def test_find_duplicate_variant_combinations_keeps_non_complete_relations_for_blank_size_bags():
    # 사이즈가 있는 상품과 같은 방식으로, 완전 중복인 관계만 빼고 실제 옵션 중복은 유지합니다.
    products = [
        bag_product(product_group_id="G001", product_id="P001"),
        bag_product(product_group_id="G001", product_id="P002"),
        bag_product(product_group_id="G001", product_id="P003", price=52000),
    ]

    issues = find_duplicate_variant_combinations(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002", "P003"]
    assert all(
        duplicate_detector.parse_duplicate_variant_message(issue.message)
        == ("G001", "BLACK", "", ["P001", "P002", "P003"])
        for issue in issues
    )


def test_find_duplicate_variant_combinations_unchanged_for_sized_complete_duplicates():
    # 사이즈가 있는 완전 중복 관계는 기존처럼 옵션 중복으로 다시 표시하지 않습니다.
    products = [
        make_product(product_group_id="G001", product_id="P001", size="M"),
        make_product(product_group_id="G001", product_id="P002", size="M"),
    ]

    assert find_duplicate_variant_combinations(products) == []
    assert [issue.product_id for issue in find_duplicate_product_content(products)] == ["P002"]


def test_run_all_rules_reports_complete_duplicate_for_blank_size_bags():
    products = [
        bag_product(product_group_id="G001", product_id="P001"),
        bag_product(product_group_id="G002", product_id="P002"),
    ]

    issues = run_all_rules(products)
    rules_by_product = {}
    for issue in issues:
        rules_by_product.setdefault(issue.product_id, []).append(issue.rule)

    assert "duplicate_product_content" in rules_by_product["P002"]
    # 빈 size가 정상인 카테고리이므로 size 누락 오류는 생기지 않습니다.
    assert "missing_required_field" not in rules_by_product.get("P001", [])
    assert "missing_required_field" not in rules_by_product["P002"]
