# 역할: 카테고리별 가격 이상치 탐지 로직이 경계값과 예외를 올바르게 처리하는지 테스트합니다.
from dataclasses import asdict

from core.duplicate_detector import find_duplicate_product_ids
from core.models import Product
from core.price_anomaly_detector import (
    calculate_category_price_medians,
    find_category_price_anomalies,
    get_valid_price,
    normalize_category,
)
from core.privacy import mask_personal_information
from core.rules import check_price, run_all_rules


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


def test_check_price_flags_zero_as_non_positive_error():
    issues = check_price([make_product(price=0)])

    assert len(issues) == 1
    assert issues[0].rule == "invalid_non_positive_price"
    assert issues[0].severity == "error"
    assert issues[0].message == "price 0 is not positive"


def test_check_price_flags_negative_as_non_positive_error():
    issues = check_price([make_product(price=-1000)])

    assert len(issues) == 1
    assert issues[0].rule == "invalid_non_positive_price"
    assert issues[0].severity == "error"
    assert issues[0].message == "price -1000 is not positive"


def test_check_price_allows_positive_price():
    assert check_price([make_product(price=1)]) == []


def test_run_all_rules_does_not_duplicate_non_positive_price_errors():
    products = [
        make_product(product_id="P001", price=0),
        make_product(product_id="P002", price=-1000),
    ]

    issues = run_all_rules(products)
    price_issues = [
        issue
        for issue in issues
        if issue.rule in {"invalid_non_positive_price", "category_price_anomaly"}
    ]

    assert [issue.rule for issue in price_issues] == [
        "invalid_non_positive_price",
        "invalid_non_positive_price",
    ]


def test_calculate_category_price_medians_handles_odd_count():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=12000),
        make_product(product_id="P003", price=15000),
        make_product(product_id="P004", price=18000),
        make_product(product_id="P005", price=20000),
    ]

    medians = calculate_category_price_medians(products)

    assert medians["top"] == 15000


def test_calculate_category_price_medians_handles_even_count():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=12000),
        make_product(product_id="P003", price=18000),
        make_product(product_id="P004", price=20000),
        make_product(product_id="P005", price=22000),
        make_product(product_id="P006", price=24000),
    ]

    medians = calculate_category_price_medians(products)

    assert medians["top"] == 19000


def test_calculate_category_price_medians_excludes_non_positive_prices():
    products = [
        make_product(product_id="P001", price=0),
        make_product(product_id="P002", price=-1000),
        make_product(product_id="P003", price=10000),
        make_product(product_id="P004", price=12000),
        make_product(product_id="P005", price=15000),
        make_product(product_id="P006", price=18000),
        make_product(product_id="P007", price=20000),
    ]

    medians = calculate_category_price_medians(products)

    assert medians["top"] == 15000


def test_get_valid_price_excludes_invalid_values():
    assert get_valid_price(None) is None
    assert get_valid_price("") is None
    assert get_valid_price("abc") is None
    assert get_valid_price(0) is None
    assert get_valid_price(-1) is None
    assert get_valid_price("1000") == 1000


def test_calculate_category_price_medians_excludes_blank_categories():
    products = [
        make_product(product_id="P001", category="", price=10000),
        make_product(product_id="P002", category="   ", price=12000),
        make_product(product_id="P003", category="TOP", price=10000),
        make_product(product_id="P004", category="TOP", price=12000),
        make_product(product_id="P005", category="TOP", price=15000),
        make_product(product_id="P006", category="TOP", price=18000),
        make_product(product_id="P007", category="TOP", price=20000),
    ]

    medians = calculate_category_price_medians(products)

    assert "" not in medians
    assert medians["top"] == 15000


def test_normalize_category_strips_spaces_and_casefolds_english():
    assert normalize_category(" TOP ") == "top"
    assert normalize_category("shoes") == "shoes"
    assert normalize_category("SHOES") == "shoes"
    assert normalize_category("") == ""


def test_find_category_price_anomalies_flags_low_price_below_ratio():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=12000),
        make_product(product_id="P003", price=15000),
        make_product(product_id="P004", price=18000),
        make_product(product_id="P005", price=20000),
        make_product(product_id="P006", price=1000),
    ]

    issues = find_category_price_anomalies(products)

    assert len(issues) == 1
    assert issues[0].rule == "category_price_anomaly"
    assert issues[0].severity == "warning"
    assert issues[0].product_id == "P006"


def test_find_category_price_anomalies_allows_exact_low_boundary():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=10000),
        make_product(product_id="P003", price=10000),
        make_product(product_id="P004", price=10000),
        make_product(product_id="P005", price=10000),
        make_product(product_id="P006", price=2500),
    ]

    assert find_category_price_anomalies(products) == []


def test_find_category_price_anomalies_flags_high_price_above_ratio():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=12000),
        make_product(product_id="P003", price=15000),
        make_product(product_id="P004", price=18000),
        make_product(product_id="P005", price=20000),
        make_product(product_id="P006", price=100000),
    ]

    issues = find_category_price_anomalies(products)

    assert len(issues) == 1
    assert issues[0].product_id == "P006"
    assert "median 16500" in issues[0].message


def test_find_category_price_anomalies_allows_exact_high_boundary():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=10000),
        make_product(product_id="P003", price=10000),
        make_product(product_id="P004", price=10000),
        make_product(product_id="P005", price=10000),
        make_product(product_id="P006", price=40000),
    ]

    assert find_category_price_anomalies(products) == []


def test_find_category_price_anomalies_allows_normal_range_prices():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=12000),
        make_product(product_id="P003", price=15000),
        make_product(product_id="P004", price=18000),
        make_product(product_id="P005", price=20000),
        make_product(product_id="P006", price=50000),
    ]

    assert find_category_price_anomalies(products) == []


def test_find_category_price_anomalies_skips_categories_below_minimum_size():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=12000),
        make_product(product_id="P003", price=15000),
        make_product(product_id="P004", price=100000),
    ]

    assert find_category_price_anomalies(products) == []


def test_find_category_price_anomalies_runs_at_minimum_size():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=10000),
        make_product(product_id="P003", price=10000),
        make_product(product_id="P004", price=10000),
        make_product(product_id="P005", price=100000),
    ]

    issues = find_category_price_anomalies(products)

    assert len(issues) == 1
    assert issues[0].product_id == "P005"


def test_find_category_price_anomalies_uses_separate_category_medians():
    products = [
        make_product(product_id="T001", category="TOP", price=10000),
        make_product(product_id="T002", category="TOP", price=10000),
        make_product(product_id="T003", category="TOP", price=10000),
        make_product(product_id="T004", category="TOP", price=10000),
        make_product(product_id="T005", category="TOP", price=100000),
        make_product(product_id="B001", category="BOTTOM", price=100000),
        make_product(product_id="B002", category="BOTTOM", price=110000),
        make_product(product_id="B003", category="BOTTOM", price=120000),
        make_product(product_id="B004", category="BOTTOM", price=130000),
        make_product(product_id="B005", category="BOTTOM", price=140000),
    ]

    issues = find_category_price_anomalies(products)

    assert [issue.product_id for issue in issues] == ["T005"]


def test_find_category_price_anomalies_skips_non_positive_price_products():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=10000),
        make_product(product_id="P003", price=10000),
        make_product(product_id="P004", price=10000),
        make_product(product_id="P005", price=10000),
        make_product(product_id="P006", price=0),
        make_product(product_id="P007", price=-1000),
    ]

    assert find_category_price_anomalies(products) == []


def test_find_category_price_anomalies_does_not_modify_original_products():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=10000),
        make_product(product_id="P003", price=10000),
        make_product(product_id="P004", price=10000),
        make_product(product_id="P005", price=100000),
    ]
    before_products = [asdict(product) for product in products]

    find_category_price_anomalies(products)

    assert [asdict(product) for product in products] == before_products


def test_duplicate_detection_still_works():
    products = [
        make_product(product_id="P001"),
        make_product(product_id="P001", product_name="다른 테스트 상품"),
    ]

    issues = find_duplicate_product_ids(products)

    assert len(issues) == 2


def test_personal_information_masking_still_works():
    masked_text = mask_personal_information("문의 010-1234-5678 seller@test.com")

    assert masked_text == "문의 010-****-5678 se****@test.com"


def test_run_all_rules_keeps_existing_non_numeric_price_result():
    issues = run_all_rules([make_product(price=None)])

    assert any(issue.rule == "invalid_price" for issue in issues)
