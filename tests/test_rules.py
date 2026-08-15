# 역할: 핵심 검수 규칙들이 상품 데이터 오류를 정확히 찾아내는지 테스트합니다.
import pytest

from config.settings import (
    DEV_DATA_PATH,
    FASHION_CATEGORY_ATTRIBUTE_RULES,
    VALID_CATEGORIES,
)
from core import rules
from core.duplicate_detector import parse_duplicate_variant_message
from core.loader import load_products
from core.models import Product
from core.rules import (
    RULES,
    check_duplicate_product_content,
    check_duplicate_product_id,
    check_inconsistent_group_category,
    check_inconsistent_group_size_system,
    check_invalid_category,
    check_missing_required_fields,
    check_non_standard_color,
    check_non_standard_size,
    check_price,
    check_price_outliers,
    check_sale_price,
    check_prohibited_and_personal_information,
    check_stock,
    run_all_rules,
)


# 각 검수 규칙이 어떤 상황에서 문제를 만들거나 무시하는지 확인하는 테스트입니다.
def make_product(**overrides) -> Product:
    # 테스트마다 필요한 값만 바꿀 수 있도록 기본 상품을 만들어 주는 helper입니다.
    defaults = dict(
        product_group_id="G001",
        product_id="P001",
        product_name="반팔 티셔츠",
        category="TOP",
        color="BLACK",
        size="M",
        stock=5,
        price=19000,
        image_path="data/dev/images/p001.jpg",
    )
    defaults.update(overrides)
    return Product(**defaults)


def test_check_duplicate_product_id_flags_reuse_across_groups():
    products = [
        make_product(product_group_id="G001", product_id="P003"),
        make_product(product_group_id="G002", product_id="P003"),
    ]

    issues = check_duplicate_product_id(products)

    assert len(issues) == 2
    assert all(issue.rule == "duplicate_product_id" for issue in issues)
    assert all(issue.product_id == "P003" for issue in issues)
    assert all("rows 2, 3" in issue.message for issue in issues)


def test_check_duplicate_product_id_flags_same_group_reuse():
    products = [
        make_product(product_group_id="G001", product_id="P001", size="M"),
        make_product(product_group_id="G001", product_id="P001", size="L"),
    ]

    issues = check_duplicate_product_id(products)

    assert len(issues) == 2
    assert all(issue.rule == "duplicate_product_id" for issue in issues)


def test_check_duplicate_product_id_ignores_blank_product_ids_across_groups():
    products = [
        make_product(product_group_id="G001", product_id=""),
        make_product(product_group_id="G002", product_id=""),
    ]

    duplicate_issues = check_duplicate_product_id(products)
    missing_issues = check_missing_required_fields(products)

    assert duplicate_issues == []
    assert len(missing_issues) == 2
    assert all(issue.rule == "missing_required_field" for issue in missing_issues)
    assert all("product_id" in issue.message for issue in missing_issues)


def test_check_duplicate_product_id_does_not_require_product_group_id():
    products = [
        make_product(product_group_id="", product_id="P777"),
        make_product(product_group_id="G002", product_id="P777"),
    ]

    duplicate_issues = check_duplicate_product_id(products)
    missing_issues = check_missing_required_fields(products)

    assert len(duplicate_issues) == 2
    assert all(issue.rule == "duplicate_product_id" for issue in duplicate_issues)
    assert len(missing_issues) == 1
    assert missing_issues[0].rule == "missing_required_field"
    assert "product_group_id" in missing_issues[0].message


def test_check_duplicate_product_content_flags_same_group_duplicate():
    products = [
        make_product(product_group_id="G001", product_id="P001", price=15000),
        make_product(product_group_id="G001", product_id="P002", price=15000),
    ]

    issues = check_duplicate_product_content(products)

    assert len(issues) == 1
    assert issues[0].rule == "duplicate_product_content"
    assert issues[0].severity == "error"
    assert issues[0].product_id == "P002"


def test_check_duplicate_product_content_flags_different_group_duplicate():
    products = [
        make_product(product_group_id="G001", product_id="P001", price=15000),
        make_product(product_group_id="G002", product_id="P002", price=15000),
    ]

    issues = check_duplicate_product_content(products)

    assert len(issues) == 1
    assert issues[0].rule == "duplicate_product_content"
    assert issues[0].product_id == "P002"


def test_check_duplicate_product_content_uses_first_product_as_base():
    products = [
        make_product(product_group_id="G001", product_id="P001", price=15000),
        make_product(product_group_id="G002", product_id="P002", price=15000),
        make_product(product_group_id="G003", product_id="P003", price=15000),
    ]

    issues = check_duplicate_product_content(products)

    assert len(issues) == 2
    assert [issue.product_id for issue in issues] == ["P002", "P003"]
    assert all("product_id 'P001' in group 'G001'" in issue.message for issue in issues)


@pytest.mark.parametrize(
    "overrides",
    [
        {"product_name": "긴팔 티셔츠"},
        {"category": "BOTTOM"},
        {"color": "WHITE"},
        {"size": "L"},
        {"price": 16000},
    ],
)
def test_check_duplicate_product_content_allows_different_core_fields(overrides):
    second_product_values = {
        "product_group_id": "G002",
        "product_id": "P002",
        "price": 15000,
    }
    second_product_values.update(overrides)
    products = [
        make_product(product_group_id="G001", product_id="P001", price=15000),
        make_product(**second_product_values),
    ]

    issues = check_duplicate_product_content(products)

    assert issues == []


def test_check_duplicate_product_content_ignores_stock_difference():
    products = [
        make_product(product_group_id="G001", product_id="P001", stock=10, price=15000),
        make_product(product_group_id="G002", product_id="P002", stock=3, price=15000),
    ]

    issues = check_duplicate_product_content(products)

    assert len(issues) == 1
    assert issues[0].product_id == "P002"


def test_check_duplicate_product_content_ignores_image_path_difference():
    products = [
        make_product(
            product_group_id="G001",
            product_id="P001",
            price=15000,
            image_path="image1.jpg",
        ),
        make_product(
            product_group_id="G002",
            product_id="P002",
            price=15000,
            image_path="image2.jpg",
        ),
    ]

    issues = check_duplicate_product_content(products)

    assert len(issues) == 1
    assert issues[0].product_id == "P002"


def test_check_duplicate_product_content_normalizes_whitespace():
    products = [
        make_product(product_group_id="G001", product_id="P001", product_name="기본 티셔츠"),
        make_product(product_group_id="G002", product_id="P002", product_name=" 기본  티셔츠 "),
    ]

    issues = check_duplicate_product_content(products)

    assert len(issues) == 1
    assert issues[0].product_id == "P002"


def test_check_duplicate_product_content_normalizes_case():
    products = [
        make_product(product_group_id="G001", product_id="P001", color="BLACK"),
        make_product(product_group_id="G002", product_id="P002", color="black"),
    ]

    issues = check_duplicate_product_content(products)

    assert len(issues) == 1
    assert issues[0].product_id == "P002"


@pytest.mark.parametrize(
    "field_name",
    ["product_group_id", "product_id", "product_name", "category", "color", "size"],
)
def test_check_duplicate_product_content_excludes_missing_required_fields(field_name):
    products = [
        make_product(product_group_id="G001", product_id="P001"),
        make_product(product_group_id="G002", product_id="P002"),
    ]
    for product in products:
        setattr(product, field_name, "")

    duplicate_issues = check_duplicate_product_content(products)
    missing_issues = check_missing_required_fields(products)

    assert duplicate_issues == []
    assert len(missing_issues) == 2
    assert all(field_name in issue.message for issue in missing_issues)


def test_check_duplicate_product_content_excludes_invalid_categories():
    products = [
        make_product(product_group_id="G001", product_id="P001", category="ACCESSORY"),
        make_product(product_group_id="G002", product_id="P002", category="ACCESSORY"),
    ]

    duplicate_issues = check_duplicate_product_content(products)
    category_issues = check_invalid_category(products)

    assert duplicate_issues == []
    assert len(category_issues) == 2
    assert all(issue.rule == "invalid_category" for issue in category_issues)


@pytest.mark.parametrize(
    ("price", "expected_rule"),
    [
        (None, "invalid_price"),
        (0, "invalid_non_positive_price"),
        (-1000, "invalid_non_positive_price"),
    ],
)
def test_check_duplicate_product_content_excludes_invalid_prices(price, expected_rule):
    products = [
        make_product(product_group_id="G001", product_id="P001", price=price),
        make_product(product_group_id="G002", product_id="P002", price=price),
    ]

    duplicate_issues = check_duplicate_product_content(products)
    price_issues = check_price(products)

    assert duplicate_issues == []
    assert len(price_issues) == 2
    assert all(issue.rule == expected_rule for issue in price_issues)


def test_check_duplicate_product_content_keeps_duplicate_product_id_rule():
    products = [
        make_product(product_group_id="G001", product_id="P777", product_name="반팔 티셔츠"),
        make_product(product_group_id="G002", product_id="P777", product_name="긴팔 티셔츠"),
    ]

    duplicate_id_issues = check_duplicate_product_id(products)
    duplicate_content_issues = check_duplicate_product_content(products)

    assert len(duplicate_id_issues) == 2
    assert all(issue.rule == "duplicate_product_id" for issue in duplicate_id_issues)
    assert duplicate_content_issues == []


def test_check_missing_required_fields_detects_blank_color():
    products = [make_product(color="")]

    issues = check_missing_required_fields(products)

    assert len(issues) == 1
    assert issues[0].rule == "missing_required_field"
    assert "color" in issues[0].message


def test_check_missing_required_fields_detects_blank_product_name():
    products = [make_product(product_name="")]

    issues = check_missing_required_fields(products)

    assert len(issues) == 1
    assert issues[0].rule == "missing_required_field"
    assert "product_name" in issues[0].message


def test_check_missing_required_fields_detects_blank_product_group_id():
    products = [make_product(product_group_id="")]

    issues = check_missing_required_fields(products)

    assert len(issues) == 1
    assert issues[0].rule == "missing_required_field"
    assert "product_group_id" in issues[0].message


def test_check_missing_required_fields_detects_blank_product_id():
    products = [make_product(product_id="")]

    issues = check_missing_required_fields(products)

    assert len(issues) == 1
    assert issues[0].rule == "missing_required_field"
    assert "product_id" in issues[0].message


def test_check_missing_required_fields_messages_name_missing_id_fields():
    products = [make_product(product_group_id="", product_id="")]

    issues = check_missing_required_fields(products)
    messages = [issue.message for issue in issues]

    assert len(issues) == 2
    assert any("product_group_id" in message for message in messages)
    assert any("product_id" in message for message in messages)


def test_check_missing_required_fields_allows_full_product():
    products = [make_product()]

    issues = check_missing_required_fields(products)

    assert issues == []


# 아래는 카테고리별 필수 패션 속성 정책(category-aware validation) 테스트입니다.
@pytest.mark.parametrize("category", ["TOP", "BOTTOM", "OUTER", "SHOES"])
def test_check_missing_required_fields_requires_size_for_apparel_categories(category):
    products = [make_product(category=category, product_name="테스트 상품", size="")]

    issues = check_missing_required_fields(products)

    assert len(issues) == 1
    assert issues[0].rule == "missing_required_field"
    assert issues[0].severity == "error"
    assert "size" in issues[0].message


def test_check_missing_required_fields_allows_blank_size_for_bag():
    products = [make_product(category="BAG", product_name="백팩", size="")]

    issues = check_missing_required_fields(products)

    assert issues == []


def test_check_missing_required_fields_still_checks_other_fields_for_bag():
    # size만 선택 값이며, 나머지 필수 값 정책은 BAG에서도 그대로 유지되어야 합니다.
    products = [make_product(category="BAG", product_name="백팩", size="", color="")]

    issues = check_missing_required_fields(products)

    assert len(issues) == 1
    assert "color" in issues[0].message


def test_check_missing_required_fields_requires_size_for_invalid_category():
    # 허용 목록에 없는 카테고리는 어떤 패션 카테고리인지 추정하지 않고 기존 정책을 유지합니다.
    products = [make_product(category="ACCESSORY", size="")]

    missing_issues = check_missing_required_fields(products)
    category_issues = check_invalid_category(products)

    assert len(missing_issues) == 1
    assert "size" in missing_issues[0].message
    assert len(category_issues) == 1
    assert category_issues[0].rule == "invalid_category"


def test_check_missing_required_fields_requires_size_for_blank_category():
    products = [make_product(category="", size="")]

    missing_issues = check_missing_required_fields(products)
    messages = [issue.message for issue in missing_issues]

    assert len(missing_issues) == 2
    assert any("category" in message for message in messages)
    assert any("size" in message for message in messages)
    # 빈 카테고리는 기존처럼 필수 값 누락만 처리하고 카테고리 오류는 만들지 않습니다.
    assert check_invalid_category(products) == []


def test_check_missing_required_fields_does_not_apply_bag_policy_to_lowercase_bag():
    # canonical 표기가 아닌 값은 기존과 같이 카테고리 오류이며 size도 계속 필수입니다.
    products = [make_product(category="bag", size="")]

    missing_issues = check_missing_required_fields(products)

    assert len(missing_issues) == 1
    assert "size" in missing_issues[0].message
    assert len(check_invalid_category(products)) == 1


def test_run_all_rules_reports_no_issue_for_bag_without_size():
    products = [make_product(category="BAG", product_name="백팩", size="")]

    assert run_all_rules(products) == []


def test_run_all_rules_reports_no_issue_for_bag_with_free_size():
    products = [make_product(category="BAG", product_name="백팩", size="FREE")]

    assert run_all_rules(products) == []


def test_run_all_rules_reports_no_issue_for_normal_top_product():
    products = [make_product(category="TOP", product_name="반팔 티셔츠", size="M")]

    assert run_all_rules(products) == []


def test_fashion_category_attribute_rules_cover_every_valid_category():
    # 정책 표와 허용 카테고리 목록이 따로 놀지 않도록 고정합니다.
    assert set(FASHION_CATEGORY_ATTRIBUTE_RULES) == VALID_CATEGORIES


def test_check_invalid_category_rejects_unknown_category():
    products = [make_product(category="ACCESSORY")]

    issues = check_invalid_category(products)

    assert len(issues) == 1
    assert issues[0].rule == "invalid_category"


def test_check_stock_flags_negative_as_error_and_zero_as_warning():
    products = [
        make_product(product_id="P010", stock=-1),
        make_product(product_id="P011", stock=0),
        make_product(product_id="P012", stock=3),
    ]

    issues = check_stock(products)

    assert len(issues) == 2
    assert issues[0].severity == "error"
    assert issues[1].severity == "warning"


def test_check_stock_flags_non_numeric_stock():
    products = [make_product(stock=None)]

    issues = check_stock(products)

    assert len(issues) == 1
    assert issues[0].message == "stock is missing or not a number"


def test_check_price_flags_non_positive_prices_as_errors():
    products = [
        make_product(product_id="P020", price=-1000),
        make_product(product_id="P021", price=0),
        make_product(product_id="P022", price=5000),
    ]

    issues = check_price(products)

    assert len(issues) == 2
    assert issues[0].severity == "error"
    assert issues[1].severity == "error"
    assert [issue.rule for issue in issues] == [
        "invalid_non_positive_price",
        "invalid_non_positive_price",
    ]


def test_check_price_flags_non_numeric_price():
    products = [make_product(price=None)]

    issues = check_price(products)

    assert len(issues) == 1
    assert issues[0].rule == "invalid_price"
    assert issues[0].message == "price is missing or not a number"


@pytest.mark.parametrize("sale_price", [39000, 50000, None])
def test_check_sale_price_allows_blank_or_non_greater_sale_prices(sale_price):
    products = [make_product(price=50000, sale_price=sale_price)]

    assert check_sale_price(products) == []


def test_check_sale_price_flags_sale_price_greater_than_price():
    products = [make_product(price=50000, sale_price=60000)]

    issues = check_sale_price(products)

    assert len(issues) == 1
    assert issues[0].rule == "sale_price_greater_than_price"
    assert issues[0].severity == "error"
    assert issues[0].product_id == "P001"
    assert issues[0].product_group_id == "G001"
    assert issues[0].message == "sale_price 60000 is greater than price 50000"


def test_check_sale_price_skips_comparison_when_price_is_invalid():
    products = [make_product(price=None, sale_price=60000)]

    assert check_sale_price(products) == []


def test_check_price_outliers_flags_high_price_by_category():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=11000),
        make_product(product_id="P003", price=12000),
        make_product(product_id="P004", price=13000),
        make_product(product_id="P005", price=100000),
    ]

    issues = check_price_outliers(products)

    assert len(issues) == 1
    assert issues[0].rule == "category_price_anomaly"
    assert issues[0].severity == "warning"
    assert issues[0].product_id == "P005"


def test_check_price_outliers_flags_low_price_by_category():
    products = [
        make_product(product_id="P001", price=1000),
        make_product(product_id="P002", price=10000),
        make_product(product_id="P003", price=11000),
        make_product(product_id="P004", price=12000),
        make_product(product_id="P005", price=13000),
    ]

    issues = check_price_outliers(products)

    assert len(issues) == 1
    assert issues[0].rule == "category_price_anomaly"
    assert issues[0].severity == "warning"
    assert issues[0].product_id == "P001"


def test_check_price_outliers_allows_similar_prices():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=10500),
        make_product(product_id="P003", price=11000),
        make_product(product_id="P004", price=11500),
        make_product(product_id="P005", price=12000),
    ]

    issues = check_price_outliers(products)

    assert issues == []


def test_check_price_outliers_skips_categories_below_minimum_size():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=11000),
        make_product(product_id="P003", price=12000),
        make_product(product_id="P004", price=100000),
    ]

    issues = check_price_outliers(products)

    assert issues == []


def test_check_price_outliers_uses_category_specific_price_ranges():
    products = [
        make_product(product_id="T001", category="TOP", price=10000),
        make_product(product_id="T002", category="TOP", price=11000),
        make_product(product_id="T003", category="TOP", price=12000),
        make_product(product_id="T004", category="TOP", price=13000),
        make_product(product_id="T005", category="TOP", price=100000),
        make_product(product_id="B001", category="BOTTOM", price=100000),
        make_product(product_id="B002", category="BOTTOM", price=110000),
        make_product(product_id="B003", category="BOTTOM", price=120000),
        make_product(product_id="B004", category="BOTTOM", price=130000),
        make_product(product_id="B005", category="BOTTOM", price=140000),
    ]

    issues = check_price_outliers(products)

    assert len(issues) == 1
    assert issues[0].product_id == "T005"


def test_check_price_outliers_excludes_invalid_prices():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=10000),
        make_product(product_id="P003", price=10000),
        make_product(product_id="P004", price=10000),
        make_product(product_id="P005", price=10000),
        make_product(product_id="P006", price=None),
        make_product(product_id="P007", price=0),
        make_product(product_id="P008", price=-1000),
    ]

    issues = run_all_rules(products)
    price_outlier_issues = [
        issue for issue in issues if issue.rule == "category_price_anomaly"
    ]
    price_issues = [
        issue
        for issue in issues
        if issue.rule in {"invalid_price", "invalid_non_positive_price"}
    ]

    assert price_outlier_issues == []
    assert len(price_issues) == 3


def test_check_price_outliers_excludes_invalid_categories():
    products = [
        make_product(product_id="P001", category="TOP", price=10000),
        make_product(product_id="P002", category="TOP", price=11000),
        make_product(product_id="P003", category="TOP", price=12000),
        make_product(product_id="P004", category="TOP", price=13000),
        make_product(product_id="P005", category="", price=100000),
        make_product(product_id="P006", category="SHOES", price=100000),
    ]

    issues = check_price_outliers(products)

    assert issues == []


def test_check_price_outliers_handles_equal_baseline_prices():
    products_with_outlier = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=10000),
        make_product(product_id="P003", price=10000),
        make_product(product_id="P004", price=10000),
        make_product(product_id="P005", price=100000),
    ]
    products_without_outlier = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=10000),
        make_product(product_id="P003", price=10000),
        make_product(product_id="P004", price=10000),
        make_product(product_id="P005", price=10000),
    ]

    outlier_issues = check_price_outliers(products_with_outlier)
    normal_issues = check_price_outliers(products_without_outlier)

    assert len(outlier_issues) == 1
    assert outlier_issues[0].product_id == "P005"
    assert normal_issues == []


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("product_name", "카톡 문의 상품"),
        ("description", "텔레그램으로 문의하세요"),
        ("seller", "직거래 가능 판매자"),
    ],
)
def test_check_content_safety_flags_prohibited_terms_in_scanned_fields(
    field_name,
    value,
):
    products = [make_product(**{field_name: value})]

    issues = check_prohibited_and_personal_information(products)

    assert len(issues) == 1
    assert issues[0].rule == "prohibited_term"
    assert issues[0].severity == "error"
    assert f"field '{field_name}' contains prohibited term" in issues[0].message


def test_check_content_safety_normalizes_whitespace_for_prohibited_terms():
    products = [make_product(description="외부   결제로 구매 가능")]

    issues = check_prohibited_and_personal_information(products)

    assert len(issues) == 1
    assert issues[0].message == "field 'description' contains prohibited term '외부 결제'"


def test_check_content_safety_does_not_repeat_same_prohibited_term_in_field():
    products = [make_product(product_name="카톡 문의 후 카톡 연락")]

    issues = check_prohibited_and_personal_information(products)

    assert [issue.rule for issue in issues] == ["prohibited_term"]


def test_check_content_safety_flags_different_prohibited_terms_separately():
    products = [make_product(product_name="카톡 또는 텔레그램 문의")]

    issues = check_prohibited_and_personal_information(products)

    assert [issue.rule for issue in issues] == ["prohibited_term", "prohibited_term"]
    assert "카톡" in issues[0].message
    assert "텔레그램" in issues[1].message


@pytest.mark.parametrize(
    ("email_address", "masked_email"),
    [
        ("test@example.com", "te**@example.com"),
        ("user.name+shop@example.co.kr", "us************@example.co.kr"),
        ("a@example.com", "a*@example.com"),
    ],
    ids=["basic_email", "subdomain_email", "short_local_email"],
)
def test_check_content_safety_masks_email_addresses(email_address, masked_email):
    products = [make_product(description=f"문의 {email_address}")]

    issues = check_prohibited_and_personal_information(products)

    assert len(issues) == 1
    assert issues[0].rule == "email_address"
    assert issues[0].message == (
        f"field 'description' contains email address '{masked_email}'"
    )
    assert email_address not in issues[0].message


@pytest.mark.parametrize("text", ["example", "test@", "@example.com"])
def test_check_content_safety_ignores_invalid_email_text(text):
    products = [make_product(description=f"문의 {text}")]

    issues = check_prohibited_and_personal_information(products)

    assert issues == []


@pytest.mark.parametrize(
    ("phone_number", "masked_phone"),
    [
        ("010-1234-5678", "010-****-5678"),
        ("01012345678", "010****5678"),
        ("010 1234 5678", "010-****-5678"),
        ("02-123-4567", "02-****-4567"),
        ("031-1234-5678", "031-****-5678"),
    ],
    ids=[
        "mobile_hyphen",
        "mobile_plain",
        "mobile_spaces",
        "seoul_landline",
        "regional_landline",
    ],
)
def test_check_content_safety_masks_phone_numbers(phone_number, masked_phone):
    products = [make_product(seller=f"문의 {phone_number}")]

    issues = check_prohibited_and_personal_information(products)

    assert len(issues) == 1
    assert issues[0].rule == "phone_number"
    assert issues[0].message == f"field 'seller' contains phone number '{masked_phone}'"
    assert phone_number not in issues[0].message


def test_check_content_safety_ignores_general_product_numbers_as_phone_numbers():
    products = [make_product(description="상품 코드 12345678901")]

    issues = check_prohibited_and_personal_information(products)

    assert issues == []


def test_check_content_safety_masks_resident_registration_numbers():
    rrn = "000000-1234567"
    products = [make_product(description=f"테스트 값 {rrn}")]

    issues = check_prohibited_and_personal_information(products)

    assert len(issues) == 1
    assert issues[0].rule == "resident_registration_number"
    assert issues[0].message == (
        "field 'description' contains resident registration number '000000-*******'"
    )
    assert rrn not in issues[0].message


@pytest.mark.parametrize(
    "text",
    ["0000001234567", "바코드 8801234567890"],
    ids=["plain_rrn_like_number", "barcode_number"],
)
def test_check_content_safety_ignores_non_hyphenated_rrn_like_numbers(text):
    products = [make_product(description=text)]

    issues = check_prohibited_and_personal_information(products)

    assert issues == []


@pytest.mark.parametrize("context_term", ["계좌", "입금", "은행"])
def test_check_content_safety_flags_suspected_bank_account_with_context(context_term):
    products = [make_product(description=f"{context_term} 123-456-789012")]

    issues = check_prohibited_and_personal_information(products)

    assert len(issues) == 1
    assert issues[0].rule == "suspected_bank_account"
    assert issues[0].severity == "warning"
    assert issues[0].message == (
        "field 'description' contains suspected bank account '123-***-***012'"
    )
    assert "123-456-789012" not in issues[0].message


def test_check_content_safety_ignores_bank_account_like_number_without_context():
    products = [make_product(description="상품 코드 123-456-789012")]

    issues = check_prohibited_and_personal_information(products)

    assert issues == []


def test_check_content_safety_does_not_duplicate_phone_as_bank_account():
    products = [make_product(description="입금 문의 010-1234-5678")]

    issues = check_prohibited_and_personal_information(products)

    assert [issue.rule for issue in issues] == ["phone_number"]


def test_check_content_safety_uses_all_phone_spans_to_avoid_bank_duplicates():
    products = [make_product(description="입금 문의 010-1234-5678 01012345678")]

    issues = check_prohibited_and_personal_information(products)

    assert [issue.rule for issue in issues] == ["phone_number"]


def test_check_content_safety_does_not_duplicate_rrn_as_bank_account():
    products = [make_product(description="입금 확인 000000-1234567")]

    issues = check_prohibited_and_personal_information(products)

    assert [issue.rule for issue in issues] == ["resident_registration_number"]


def test_check_content_safety_uses_all_rrn_spans_to_avoid_bank_duplicates():
    products = [make_product(description="입금 확인 000000-1234567 000000-1234567")]

    issues = check_prohibited_and_personal_information(products)

    assert [issue.rule for issue in issues] == ["resident_registration_number"]


def test_check_content_safety_deduplicates_repeated_personal_information_in_field():
    products = [
        make_product(
            description=(
                "문의 test@example.com test@example.com "
                "010-1234-5678 01012345678"
            )
        )
    ]

    issues = check_prohibited_and_personal_information(products)

    assert [issue.rule for issue in issues] == ["email_address", "phone_number"]


def test_check_content_safety_skips_blank_scanned_fields():
    products = [make_product(product_name="", description="", seller="")]

    issues = check_prohibited_and_personal_information(products)

    assert issues == []


def test_check_content_safety_uses_deterministic_field_and_rule_order():
    products = [
        make_product(
            product_name="카톡 문의 상품",
            description="문의 test@example.com",
            seller="010-1234-5678",
        )
    ]

    issues = check_prohibited_and_personal_information(products)

    assert [issue.rule for issue in issues] == [
        "prohibited_term",
        "email_address",
        "phone_number",
    ]
    assert "field 'product_name'" in issues[0].message
    assert "field 'description'" in issues[1].message
    assert "field 'seller'" in issues[2].message


def test_check_content_safety_preserves_product_and_group_ids():
    products = [
        make_product(
            product_group_id="G777",
            product_id="P777",
            description="문의 test@example.com",
        )
    ]

    issues = check_prohibited_and_personal_information(products)

    assert len(issues) == 1
    assert issues[0].product_group_id == "G777"
    assert issues[0].product_id == "P777"


def test_run_all_rules_includes_content_safety_issues():
    products = [make_product(description="문의 test@example.com")]

    issues = run_all_rules(products)
    content_issues = [issue for issue in issues if issue.rule == "email_address"]

    assert len(content_issues) == 1
    assert content_issues[0].message == (
        "field 'description' contains email address 'te**@example.com'"
    )


def test_run_all_rules_includes_price_outlier_issues():
    products = [
        make_product(product_id="P001", price=10000),
        make_product(product_id="P002", price=11000),
        make_product(product_id="P003", price=12000),
        make_product(product_id="P004", price=13000),
        make_product(product_id="P005", price=100000),
    ]

    issues = run_all_rules(products)
    price_outlier_issues = [
        issue for issue in issues if issue.rule == "category_price_anomaly"
    ]

    assert len(price_outlier_issues) == 1
    assert price_outlier_issues[0].product_id == "P005"


def test_run_all_rules_includes_duplicate_product_content_issues():
    products = [
        make_product(product_group_id="G001", product_id="P001", price=15000),
        make_product(product_group_id="G002", product_id="P002", price=15000),
    ]

    issues = run_all_rules(products)
    duplicate_content_issues = [
        issue for issue in issues if issue.rule == "duplicate_product_content"
    ]

    assert len(duplicate_content_issues) == 1
    assert duplicate_content_issues[0].product_id == "P002"


def test_run_all_rules_aggregates_every_rule():
    products = [
        make_product(product_group_id="G001", product_id="P003", color="BLACK"),
        make_product(product_group_id="G002", product_id="P003", color=""),
    ]

    issues = run_all_rules(products)
    rules_triggered = {issue.rule for issue in issues}

    assert "duplicate_product_id" in rules_triggered
    assert "missing_required_field" in rules_triggered


def test_run_all_rules_products_dev_has_expected_issue_counts_after_option_filter():
    products = load_products(DEV_DATA_PATH)

    issues = run_all_rules(products)

    assert len(issues) == 6
    assert sum(issue.severity == "error" for issue in issues) == 6
    assert sum(issue.severity == "warning" for issue in issues) == 0
    assert "duplicate_product_name" not in {issue.rule for issue in issues}


def test_check_non_standard_color_allows_exact_standard_value():
    issues = check_non_standard_color([make_product(color="BLACK")])

    assert issues == []


@pytest.mark.parametrize("color", ["black", "Black", "블랙"])
def test_check_non_standard_color_warns_for_known_aliases(color):
    issues = check_non_standard_color([make_product(color=color)])

    assert len(issues) == 1
    assert issues[0].rule == "non_standard_color"
    assert issues[0].severity == "warning"
    assert color in issues[0].message
    assert "BLACK" in issues[0].message


def test_check_non_standard_color_ignores_custom_and_blank_values():
    assert check_non_standard_color([make_product(color="MELANGE GRAY")]) == []
    assert check_non_standard_color([make_product(color="")]) == []


def test_blank_color_only_creates_existing_missing_required_field_issue():
    issues = run_all_rules([make_product(color="")])
    relevant_issues = [
        issue
        for issue in issues
        if issue.rule in {"missing_required_field", "non_standard_color"}
    ]

    assert [issue.rule for issue in relevant_issues] == ["missing_required_field"]
    assert "color" in relevant_issues[0].message


def test_run_all_rules_creates_non_standard_color_warning_once():
    issues = run_all_rules([make_product(color="black")])

    assert sum(issue.rule == "non_standard_color" for issue in issues) == 1


def test_color_rule_is_registered_once():
    assert RULES.count(check_non_standard_color) == 1


def test_check_non_standard_size_allows_exact_standard_value():
    issues = check_non_standard_size([make_product(size="M")])

    assert issues == []


@pytest.mark.parametrize(
    ("size", "expected_standard"),
    [("m", "M"), ("medium", "M"), ("2XL", "XXL")],
)
def test_check_non_standard_size_warns_for_known_aliases(size, expected_standard):
    issues = check_non_standard_size([make_product(size=size)])

    assert len(issues) == 1
    assert issues[0].rule == "non_standard_size"
    assert issues[0].severity == "warning"
    assert size in issues[0].message
    assert expected_standard in issues[0].message


def test_check_non_standard_size_ignores_numeric_and_blank_values():
    assert check_non_standard_size([make_product(size="95")]) == []
    assert check_non_standard_size([make_product(size="")]) == []


def test_blank_size_only_creates_existing_missing_required_field_issue():
    issues = run_all_rules([make_product(size="")])
    relevant_issues = [
        issue
        for issue in issues
        if issue.rule in {"missing_required_field", "non_standard_size"}
    ]

    assert [issue.rule for issue in relevant_issues] == ["missing_required_field"]
    assert "size" in relevant_issues[0].message


def test_run_all_rules_creates_non_standard_size_warning_once():
    issues = run_all_rules([make_product(size="medium")])

    assert sum(issue.rule == "non_standard_size" for issue in issues) == 1


def test_size_rule_is_registered_once():
    assert RULES.count(check_non_standard_size) == 1


def test_products_dev_standard_fashion_values_do_not_create_new_warnings():
    issues = run_all_rules(load_products(DEV_DATA_PATH))
    issue_rules = {issue.rule for issue in issues}

    assert "non_standard_color" not in issue_rules
    assert "non_standard_size" not in issue_rules


def test_group_category_rule_is_registered_once_after_duplicate_product_id():
    assert RULES.count(check_inconsistent_group_category) == 1
    assert (
        RULES.index(check_inconsistent_group_category)
        == RULES.index(check_duplicate_product_id) + 1
    )


def test_group_size_system_rule_is_registered_once_after_group_category_rule():
    assert RULES.count(check_inconsistent_group_size_system) == 1
    assert (
        RULES.index(check_inconsistent_group_size_system)
        == RULES.index(check_inconsistent_group_category) + 1
    )


def test_duplicate_variant_rule_is_registered_once_after_group_size_system_rule():
    duplicate_variant_rule = rules.check_duplicate_variant_combination

    assert RULES.count(duplicate_variant_rule) == 1
    assert (
        RULES.index(duplicate_variant_rule)
        == RULES.index(check_inconsistent_group_size_system) + 1
    )


def test_check_inconsistent_group_size_system_flags_mixed_size_systems():
    products = [
        make_product(product_id="P001", size="M"),
        make_product(product_id="P002", size="L"),
        make_product(product_id="P003", size="100"),
    ]

    issues = check_inconsistent_group_size_system(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002", "P003"]
    assert all(issue.rule == "inconsistent_group_size_system" for issue in issues)
    assert all(issue.severity == "warning" for issue in issues)


@pytest.mark.parametrize(
    "sizes",
    [
        ["S", "M", "L", "XL"],
        ["95", "100", "105"],
        ["M", "L", "FREE"],
        ["M", "L", "custom size"],
    ],
)
def test_run_all_rules_allows_consistent_or_unclassified_size_groups(sizes):
    products = [
        make_product(product_id=f"P{index:03d}", color=f"COLOR{index}", size=size)
        for index, size in enumerate(sizes, start=1)
    ]

    issues = run_all_rules(products)

    assert [
        issue for issue in issues if issue.rule == "inconsistent_group_size_system"
    ] == []


def test_run_all_rules_creates_group_size_warning_with_alias_size_once():
    products = [
        make_product(product_id="P001", size="medium"),
        make_product(product_id="P002", size="L"),
        make_product(product_id="P003", size="100"),
    ]

    issues = run_all_rules(products)

    assert [
        issue.product_id
        for issue in issues
        if issue.rule == "inconsistent_group_size_system"
    ] == ["P001", "P002", "P003"]
    assert sum(issue.rule == "non_standard_size" for issue in issues) == 1


def test_blank_size_keeps_missing_required_field_without_group_size_warning():
    products = [
        make_product(product_id="P001", size="M"),
        make_product(product_id="P002", size="L"),
        make_product(product_id="P003", size=""),
    ]

    issues = run_all_rules(products)
    relevant_issues = [
        issue
        for issue in issues
        if issue.rule in {"missing_required_field", "inconsistent_group_size_system"}
    ]

    assert [issue.rule for issue in relevant_issues] == ["missing_required_field"]
    assert relevant_issues[0].product_id == "P003"
    assert "size" in relevant_issues[0].message


def test_blank_group_id_products_are_not_grouped_into_one_size_system_group():
    # product_group_id가 비어 있는 상품들을 같은 그룹으로 묶어 경고하면 안 됩니다.
    products = [
        make_product(product_group_id="", product_id="P001", size="M"),
        make_product(product_group_id="", product_id="P002", size="100"),
    ]

    issues = run_all_rules(products)
    group_id_issues = [
        issue
        for issue in issues
        if issue.rule == "missing_required_field" and "product_group_id" in issue.message
    ]

    assert [
        issue for issue in issues if issue.rule == "inconsistent_group_size_system"
    ] == []
    assert [issue.product_id for issue in group_id_issues] == ["P001", "P002"]


def test_run_all_rules_keeps_group_size_warning_separate_from_other_group_rules():
    products = [
        make_product(product_id="P001", size="M"),
        make_product(product_id="P002", size="100"),
    ]

    issues = run_all_rules(products)
    issue_rules = [issue.rule for issue in issues]

    assert issue_rules.count("inconsistent_group_size_system") == 2
    assert "inconsistent_group_category" not in issue_rules
    assert "duplicate_variant_combination" not in issue_rules
    assert "duplicate_product_content" not in issue_rules


def test_check_inconsistent_group_category_returns_all_participating_products():
    products = [
        make_product(product_id="P001", product_name="상품 A", category="TOP"),
        make_product(product_id="P002", product_name="상품 B", category="BOTTOM"),
    ]

    issues = check_inconsistent_group_category(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002"]
    assert all(issue.rule == "inconsistent_group_category" for issue in issues)


def test_run_all_rules_keeps_missing_category_separate_from_group_mismatch():
    products = [
        make_product(product_id="P001", product_name="상품 A", category="TOP"),
        make_product(product_id="P002", product_name="상품 B", category="BOTTOM"),
        make_product(product_id="P003", product_name="상품 C", category=""),
    ]

    issues = run_all_rules(products)
    group_issues = [
        issue for issue in issues if issue.rule == "inconsistent_group_category"
    ]
    missing_issues = [
        issue
        for issue in issues
        if issue.rule == "missing_required_field" and "category" in issue.message
    ]

    assert [issue.product_id for issue in group_issues] == ["P001", "P002"]
    assert [issue.product_id for issue in missing_issues] == ["P003"]


def test_run_all_rules_keeps_invalid_and_group_category_issues_distinct():
    products = [
        make_product(product_id="P001", product_name="상품 A", category="ACCESSORY"),
        make_product(product_id="P002", product_name="상품 B", category="STATIONERY"),
    ]

    issues = run_all_rules(products)

    assert [
        issue.product_id
        for issue in issues
        if issue.rule == "inconsistent_group_category"
    ] == ["P001", "P002"]
    assert [
        issue.product_id for issue in issues if issue.rule == "invalid_category"
    ] == ["P001", "P002"]


def test_run_all_rules_allows_shoes_product_without_category_issues():
    products = [
        make_product(
            product_name="남성 러닝 운동화",
            category="SHOES",
            size="270",
        )
    ]

    issues = run_all_rules(products)

    assert issues == []


def test_run_all_rules_allows_bag_product_with_free_size():
    products = [
        make_product(
            product_name="레더 토트백",
            category="BAG",
            color="BLACK",
            size="FREE",
        )
    ]

    issues = run_all_rules(products)

    assert issues == []


@pytest.mark.parametrize(
    ("product_name", "category"),
    [
        ("오버핏 반팔 티셔츠", "SHOES"),
        ("데님 청바지", "BAG"),
    ],
)
def test_run_all_rules_keeps_name_mismatch_for_allowed_shoes_and_bag(
    product_name,
    category,
):
    # SHOES/BAG는 허용 카테고리지만 상품명과 의미가 다르면 기존 경고는 그대로 나옵니다.
    products = [make_product(product_name=product_name, category=category)]

    issues = run_all_rules(products)

    assert [issue.rule for issue in issues] == ["product_category_mismatch"]
    assert issues[0].severity == "warning"


@pytest.mark.parametrize("category", ["ACCESSORY", "shoes", "신발", "bag", "가방"])
def test_check_invalid_category_still_rejects_non_canonical_values(category):
    # 정식 입력은 대문자 canonical 값뿐이며 alias는 비교용으로만 유지합니다.
    issues = check_invalid_category([make_product(category=category)])

    assert [issue.rule for issue in issues] == ["invalid_category"]
    assert issues[0].severity == "error"


@pytest.mark.parametrize(
    ("category", "size"),
    [("SHOES", "270"), ("BAG", "FREE")],
)
def test_check_duplicate_product_content_includes_shoes_and_bag(category, size):
    products = [
        make_product(
            product_group_id="G001",
            product_id="P001",
            product_name="공식 지원 상품",
            category=category,
            size=size,
            price=59000,
        ),
        make_product(
            product_group_id="G002",
            product_id="P002",
            product_name="공식 지원 상품",
            category=category,
            size=size,
            price=59000,
        ),
    ]

    issues = check_duplicate_product_content(products)

    assert [issue.product_id for issue in issues] == ["P002"]
    assert issues[0].rule == "duplicate_product_content"
    assert check_invalid_category(products) == []


def test_blank_bag_size_is_allowed_but_blank_apparel_size_is_not():
    # BAG은 size가 선택 값이지만, 다른 패션 카테고리는 기존처럼 필수 값입니다.
    bag_products = [make_product(product_name="레더 토트백", category="BAG", size="")]
    apparel_products = [
        make_product(product_name="레더 토트백", category="OUTER", size="")
    ]

    assert run_all_rules(bag_products) == []

    apparel_issues = [
        issue
        for issue in run_all_rules(apparel_products)
        if issue.rule == "missing_required_field"
    ]
    assert len(apparel_issues) == 1
    assert "size" in apparel_issues[0].message


def test_run_all_rules_flags_group_category_mismatch_between_allowed_categories():
    products = [
        make_product(
            product_id="P001",
            product_name="남성 러닝 운동화",
            category="SHOES",
            size="270",
        ),
        make_product(
            product_id="P002",
            product_name="오버핏 반팔 티셔츠",
            category="TOP",
            color="NAVY",
        ),
    ]

    issues = run_all_rules(products)

    assert [
        issue.product_id
        for issue in issues
        if issue.rule == "inconsistent_group_category"
    ] == ["P001", "P002"]
    assert [issue for issue in issues if issue.rule == "invalid_category"] == []


def test_group_category_comparison_still_treats_alias_as_same_category():
    # 그룹 비교는 alias를 같은 값으로 보지만, canonical이 아닌 입력 자체는 오류입니다.
    products = [
        make_product(
            product_id="P001",
            product_name="남성 러닝 운동화",
            category="SHOES",
            size="270",
        ),
        make_product(
            product_id="P002",
            product_name="남성 러닝 운동화",
            category="shoes",
            color="NAVY",
            size="280",
        ),
    ]

    issues = run_all_rules(products)

    assert [
        issue for issue in issues if issue.rule == "inconsistent_group_category"
    ] == []
    assert [
        issue.product_id for issue in issues if issue.rule == "invalid_category"
    ] == ["P002"]


def test_shoes_group_with_numeric_sizes_only_has_no_size_system_warning():
    products = [
        make_product(
            product_id=f"P00{index}",
            product_name="남성 러닝 운동화",
            category="SHOES",
            color=f"COLOR{index}",
            size=size,
        )
        for index, size in enumerate(["250", "260", "270"], start=1)
    ]

    issues = run_all_rules(products)

    assert issues == []


def test_shoes_group_with_mixed_size_systems_keeps_group_size_warning():
    # 카테고리별 사이즈 판정은 하지 않으므로 SHOES에서도 체계 혼재는 그대로 경고합니다.
    products = [
        make_product(
            product_id="P001",
            product_name="남성 러닝 운동화",
            category="SHOES",
            color="BLACK",
            size="M",
        ),
        make_product(
            product_id="P002",
            product_name="남성 러닝 운동화",
            category="SHOES",
            color="WHITE",
            size="270",
        ),
    ]

    issues = run_all_rules(products)

    assert [
        issue.product_id
        for issue in issues
        if issue.rule == "inconsistent_group_size_system"
    ] == ["P001", "P002"]
    assert [issue for issue in issues if issue.rule == "invalid_category"] == []


def test_run_all_rules_keeps_name_mismatch_and_group_category_issues_distinct():
    products = [
        make_product(
            product_id="P001",
            product_name="러닝 운동화 A",
            category="TOP",
            color="BLACK",
            size="M",
        ),
        make_product(
            product_id="P002",
            product_name="러닝 운동화 B",
            category="SHOES",
            color="WHITE",
            size="L",
        ),
    ]

    issues = run_all_rules(products)

    assert [
        issue.product_id
        for issue in issues
        if issue.rule == "inconsistent_group_category"
    ] == ["P001", "P002"]
    assert [
        issue.product_id
        for issue in issues
        if issue.rule == "product_category_mismatch"
    ] == ["P001"]


def test_run_all_rules_flags_custom_duplicate_variant_without_standardization_warnings():
    products = [
        make_product(product_id="P001", product_name="상품 A", color="MELANGE GRAY", size="95"),
        make_product(product_id="P002", product_name="상품 B", color="melange gray", size="95"),
    ]

    issues = run_all_rules(products)
    relevant_issues = [
        issue
        for issue in issues
        if issue.rule
        in {
            "duplicate_variant_combination",
            "non_standard_color",
            "non_standard_size",
        }
    ]

    assert [issue.rule for issue in relevant_issues] == [
        "duplicate_variant_combination",
        "duplicate_variant_combination",
    ]


def test_products_dev_does_not_create_duplicate_variant_regression():
    issues = run_all_rules(load_products(DEV_DATA_PATH))

    assert "duplicate_variant_combination" not in {issue.rule for issue in issues}


def test_run_all_rules_prefers_complete_duplicate_over_same_variant_pair():
    products = [
        make_product(product_id="P001", color="BLACK", size="M"),
        make_product(product_id="P002", color="black", size="m"),
    ]

    issues = run_all_rules(products)
    complete_issues = [
        issue for issue in issues if issue.rule == "duplicate_product_content"
    ]
    variant_issues = [
        issue for issue in issues if issue.rule == "duplicate_variant_combination"
    ]

    assert [issue.product_id for issue in complete_issues] == ["P002"]
    assert variant_issues == []
    assert any(
        issue.rule == "non_standard_color" and issue.product_id == "P002"
        for issue in issues
    )
    assert any(
        issue.rule == "non_standard_size" and issue.product_id == "P002"
        for issue in issues
    )


def test_run_all_rules_keeps_variant_when_complete_content_does_not_match():
    products = [
        make_product(product_id="P001", color="BLACK", size="M", price=19000),
        make_product(product_id="P002", color="black", size="medium", price=20000),
    ]

    issues = run_all_rules(products)

    assert [
        issue.product_id
        for issue in issues
        if issue.rule == "duplicate_variant_combination"
    ] == ["P001", "P002"]
    assert not any(issue.rule == "duplicate_product_content" for issue in issues)


def test_run_all_rules_keeps_non_complete_relations_in_three_product_variant():
    products = [
        make_product(product_id="P001", color="BLACK", size="M", price=19000),
        make_product(product_id="P002", color="black", size="m", price=19000),
        make_product(product_id="P003", color="black", size="medium", price=20000),
    ]

    issues = run_all_rules(products)
    complete_issues = [
        issue for issue in issues if issue.rule == "duplicate_product_content"
    ]
    variant_issues = [
        issue for issue in issues if issue.rule == "duplicate_variant_combination"
    ]

    assert [issue.product_id for issue in complete_issues] == ["P002"]
    assert [issue.product_id for issue in variant_issues] == ["P001", "P002", "P003"]
    assert all(
        parse_duplicate_variant_message(issue.message)
        == ("G001", "BLACK", "M", ["P001", "P002", "P003"])
        for issue in variant_issues
    )


def test_run_all_rules_flags_complete_duplicate_for_blank_size_bags():
    # size가 선택 값인 BAG도 빈 size끼리 완전 중복 비교 대상입니다.
    products = [
        make_product(
            product_group_id="G001",
            product_id="P001",
            product_name="클래식 숄더백",
            category="BAG",
            size="",
            price=50000,
        ),
        make_product(
            product_group_id="G002",
            product_id="P002",
            product_name="클래식 숄더백",
            category="BAG",
            size="",
            price=50000,
        ),
    ]

    issues = run_all_rules(products)
    content_issues = [
        issue for issue in issues if issue.rule == "duplicate_product_content"
    ]

    assert [issue.product_id for issue in content_issues] == ["P002"]
    assert content_issues[0].severity == "error"
    # 빈 size가 정상인 카테고리이므로 size 누락 오류는 생기지 않습니다.
    assert [issue for issue in issues if issue.rule == "missing_required_field"] == []


def test_run_all_rules_keeps_product_name_warning_beside_complete_duplicate_for_bags():
    # 상품명 중복 주의와 완전 중복 오류가 함께 나오는 것은 사이즈가 있는 상품과 같은
    # 기존 동작입니다. 이번 변경으로 한쪽을 숨기는 정책을 만들지 않습니다.
    def bag(product_group_id: str, product_id: str):
        return make_product(
            product_group_id=product_group_id,
            product_id=product_id,
            product_name="클래식 숄더백",
            category="BAG",
            size="",
            price=50000,
        )

    blank_size_rules = sorted(
        {issue.rule for issue in run_all_rules([bag("G001", "P001"), bag("G002", "P002")])}
    )
    sized_rules = sorted(
        {
            issue.rule
            for issue in run_all_rules(
                [
                    make_product(product_group_id="G001", product_id="P001", size="M"),
                    make_product(product_group_id="G002", product_id="P002", size="M"),
                ]
            )
        }
    )

    assert blank_size_rules == ["duplicate_product_content", "duplicate_product_name"]
    assert blank_size_rules == sized_rules


def test_run_all_rules_flags_duplicate_variant_for_blank_size_bags():
    # 같은 그룹, 같은 색상, 빈 size가 반복되면 완전 중복이 아니어도 옵션 중복입니다.
    products = [
        make_product(
            product_group_id="G001",
            product_id="P001",
            product_name="클래식 숄더백",
            category="BAG",
            size="",
            price=50000,
        ),
        make_product(
            product_group_id="G001",
            product_id="P002",
            product_name="데일리 숄더백",
            category="BAG",
            size="",
            price=52000,
        ),
    ]

    issues = run_all_rules(products)
    variant_issues = [
        issue for issue in issues if issue.rule == "duplicate_variant_combination"
    ]

    assert [issue.product_id for issue in variant_issues] == ["P001", "P002"]
    assert all(issue.severity == "error" for issue in variant_issues)
    assert all(
        parse_duplicate_variant_message(issue.message)
        == ("G001", "BLACK", "", ["P001", "P002"])
        for issue in variant_issues
    )
    # 빈 size가 정상인 카테고리이므로 size 누락 오류는 생기지 않습니다.
    assert [issue for issue in issues if issue.rule == "missing_required_field"] == []


def test_run_all_rules_keeps_complete_duplicate_priority_for_blank_size_bags():
    # 완전 중복 관계에는 옵션 중복을 다시 붙이지 않는 기존 우선순위를 유지합니다.
    products = [
        make_product(
            product_group_id="G001",
            product_id="P001",
            product_name="클래식 숄더백",
            category="BAG",
            size="",
            price=50000,
        ),
        make_product(
            product_group_id="G001",
            product_id="P002",
            product_name="클래식 숄더백",
            category="BAG",
            size="",
            price=50000,
        ),
    ]

    issues = run_all_rules(products)

    assert [
        issue.product_id
        for issue in issues
        if issue.rule == "duplicate_product_content"
    ] == ["P002"]
    assert [
        issue for issue in issues if issue.rule == "duplicate_variant_combination"
    ] == []


@pytest.mark.parametrize("category", ["TOP", "BOTTOM", "OUTER", "SHOES"])
def test_run_all_rules_keeps_missing_size_error_without_variant_issue(category):
    # size가 필수인 카테고리의 빈 size는 기존처럼 필수 값 누락 오류만 만듭니다.
    products = [
        make_product(product_group_id="G001", product_id="P001", category=category, size=""),
        make_product(
            product_group_id="G001",
            product_id="P002",
            product_name="기본 반팔",
            category=category,
            size="",
            price=12000,
        ),
    ]

    issues = run_all_rules(products)
    missing_issues = [
        issue for issue in issues if issue.rule == "missing_required_field"
    ]

    assert [issue.product_id for issue in missing_issues] == ["P001", "P002"]
    assert all("size" in issue.message for issue in missing_issues)
    assert [
        issue for issue in issues if issue.rule == "duplicate_variant_combination"
    ] == []
