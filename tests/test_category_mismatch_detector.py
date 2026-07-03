# 역할: 상품명 기반 카테고리 불일치 탐지 로직과 기존 규칙 연동을 테스트합니다.
from dataclasses import asdict

import pandas as pd

from core.category_mismatch_detector import (
    detect_category_mismatches,
    find_categories_from_product_name,
    find_category_mismatches,
    normalize_category,
    normalize_product_name_for_category,
)
from core.duplicate_detector import find_duplicate_product_ids, find_duplicate_product_names
from core.models import Product
from core.price_anomaly_detector import find_category_price_anomalies
from core.privacy import create_masked_preview, mask_personal_information
from core.rules import check_missing_required_fields, check_price, run_all_rules


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


def test_normalize_product_name_for_category_handles_safe_values():
    assert normalize_product_name_for_category(None) == ""
    assert normalize_product_name_for_category(123) == ""
    assert normalize_product_name_for_category("  남성-러닝_운동화/세트  ") == "남성 러닝 운동화 세트"


def test_normalize_category_handles_aliases_and_blank_values():
    assert normalize_category(None) == ""
    assert normalize_category("") == ""
    assert normalize_category(" TOP ") == "상의"
    assert normalize_category("shoes") == "신발"
    assert normalize_category("신발") == "신발"


def test_find_category_mismatches_allows_matching_shoes_category():
    products = [make_product(product_name="남성 러닝 운동화", category="신발")]

    assert find_category_mismatches(products) == []


def test_find_category_mismatches_flags_clear_shoes_mismatch():
    products = [make_product(product_name="여성 앵클 부츠", category="상의")]

    issues = find_category_mismatches(products)

    assert len(issues) == 1
    assert issues[0].rule == "product_category_mismatch"
    assert issues[0].severity == "warning"
    assert "keyword '부츠'" in issues[0].message
    assert "category '신발'" in issues[0].message
    assert "current category is '상의'" in issues[0].message


def test_find_category_mismatches_flags_top_item_in_shoes_category():
    products = [make_product(product_name="오버핏 반팔 티셔츠", category="신발")]

    issues = find_category_mismatches(products)

    assert len(issues) == 1
    assert "category '상의'" in issues[0].message
    assert "current category is '신발'" in issues[0].message


def test_find_category_mismatches_flags_bottom_item_in_bag_category():
    products = [make_product(product_name="데님 청바지", category="가방")]

    issues = find_category_mismatches(products)

    assert len(issues) == 1
    assert "keyword '청바지'" in issues[0].message
    assert "category '하의'" in issues[0].message
    assert "current category is '가방'" in issues[0].message


def test_find_category_mismatches_skips_blank_product_names():
    products = [
        make_product(product_name=None, category="신발"),
        make_product(product_name="", category="신발"),
        make_product(product_name="   ", category="신발"),
    ]

    assert find_category_mismatches(products) == []
    assert check_missing_required_fields([make_product(product_name="")])


def test_find_category_mismatches_skips_blank_categories():
    products = [
        make_product(product_name="여성 운동화", category=None),
        make_product(product_name="여성 운동화", category=""),
        make_product(product_name="여성 운동화", category="   "),
    ]

    assert find_category_mismatches(products) == []
    assert check_missing_required_fields([make_product(category="")])


def test_find_category_mismatches_skips_names_without_keywords():
    products = [make_product(product_name="데일리 패션 상품", category="기타")]

    assert find_category_mismatches(products) == []


def test_find_category_mismatches_skips_multiple_detected_categories():
    products = [make_product(product_name="운동화 티셔츠 세트", category="세트상품")]

    assert find_categories_from_product_name("운동화 티셔츠 세트") == {"신발", "상의"}
    assert find_category_mismatches(products) == []


def test_find_category_mismatches_treats_multiple_keywords_in_same_category_as_one():
    products = [make_product(product_name="러닝 운동화 스니커즈", category="신발")]

    assert find_categories_from_product_name("러닝 운동화 스니커즈") == {"신발"}
    assert find_category_mismatches(products) == []


def test_find_category_mismatches_handles_english_category_aliases():
    products = [
        make_product(product_name="남성 러닝 운동화", category=" SHOES "),
        make_product(product_name="남성 러닝 운동화", category="shoes"),
    ]

    assert find_category_mismatches(products) == []


def test_find_category_mismatches_allows_current_project_top_alias():
    products = [make_product(product_name="오버핏 반팔 티셔츠", category="TOP")]

    assert find_category_mismatches(products) == []


def test_detect_category_mismatches_does_not_modify_original_products():
    products = [
        make_product(product_name="여성 앵클 부츠", category="상의"),
        make_product(product_name="오버핏 반팔 티셔츠", category="TOP"),
    ]
    before_products = [asdict(product) for product in products]

    detect_category_mismatches(products)

    assert [asdict(product) for product in products] == before_products


def test_run_all_rules_includes_product_category_mismatch():
    products = [make_product(product_name="여성 앵클 부츠", category="TOP")]

    issues = run_all_rules(products)
    mismatch_issues = [
        issue for issue in issues if issue.rule == "product_category_mismatch"
    ]

    assert len(mismatch_issues) == 1
    assert mismatch_issues[0].severity == "warning"


def test_existing_personal_information_detection_and_preview_masking_still_work():
    assert mask_personal_information("문의 010-1234-5678 seller@test.com") == (
        "문의 010-****-5678 se****@test.com"
    )

    preview_df = pd.DataFrame({"description": ["문의 010-1234-5678"]})
    masked_df = create_masked_preview(preview_df)

    assert masked_df.loc[0, "description"] == "문의 010-****-5678"
    assert preview_df.loc[0, "description"] == "문의 010-1234-5678"


def test_existing_duplicate_detection_still_works():
    products = [
        make_product(product_id="P001", product_name="가짜 상품"),
        make_product(product_id="P001", product_name="가짜상품"),
    ]

    assert len(find_duplicate_product_ids(products)) == 2
    assert len(find_duplicate_product_names(products)) == 2


def test_existing_price_checks_still_work():
    assert check_price([make_product(price=0)])[0].rule == "invalid_non_positive_price"

    products = [
        make_product(product_id="P001", product_name="테스트 상품", price=10000),
        make_product(product_id="P002", product_name="테스트 상품", price=10000),
        make_product(product_id="P003", product_name="테스트 상품", price=10000),
        make_product(product_id="P004", product_name="테스트 상품", price=10000),
        make_product(product_id="P005", product_name="테스트 상품", price=100000),
    ]

    issues = find_category_price_anomalies(products)

    assert len(issues) == 1
    assert issues[0].rule == "category_price_anomaly"
