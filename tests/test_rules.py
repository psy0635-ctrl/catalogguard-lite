import pytest

from core.models import Product
from core.rules import (
    check_duplicate_product_content,
    check_duplicate_product_id,
    check_invalid_category,
    check_missing_required_fields,
    check_price,
    check_price_outliers,
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

    assert len(issues) == 1
    assert issues[0].rule == "duplicate_product_id"
    assert issues[0].product_id == "P003"


def test_check_duplicate_product_id_allows_same_group_reuse():
    products = [
        make_product(product_group_id="G001", product_id="P001", size="M"),
        make_product(product_group_id="G001", product_id="P001", size="L"),
    ]

    issues = check_duplicate_product_id(products)

    assert issues == []


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


def test_check_duplicate_product_id_ignores_blank_product_group_id():
    products = [
        make_product(product_group_id="", product_id="P777"),
        make_product(product_group_id="G002", product_id="P777"),
    ]

    duplicate_issues = check_duplicate_product_id(products)
    missing_issues = check_missing_required_fields(products)

    assert duplicate_issues == []
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
        make_product(product_group_id="G001", product_id="P001", category="SHOES"),
        make_product(product_group_id="G002", product_id="P002", category="SHOES"),
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
        (0, "zero_price"),
        (-1000, "invalid_price"),
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

    assert len(duplicate_id_issues) == 1
    assert duplicate_id_issues[0].rule == "duplicate_product_id"
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


def test_check_invalid_category_rejects_unknown_category():
    products = [make_product(category="SHOES")]

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


def test_check_price_flags_negative_as_error_and_zero_as_warning():
    products = [
        make_product(product_id="P020", price=-1000),
        make_product(product_id="P021", price=0),
        make_product(product_id="P022", price=5000),
    ]

    issues = check_price(products)

    assert len(issues) == 2
    assert issues[0].severity == "error"
    assert issues[1].severity == "warning"


def test_check_price_flags_non_numeric_price():
    products = [make_product(price=None)]

    issues = check_price(products)

    assert len(issues) == 1
    assert issues[0].rule == "invalid_price"
    assert issues[0].message == "price is missing or not a number"


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
    assert issues[0].rule == "price_outlier"
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
    assert issues[0].rule == "price_outlier"
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
    price_outlier_issues = [issue for issue in issues if issue.rule == "price_outlier"]
    price_issues = [issue for issue in issues if issue.rule in {"invalid_price", "zero_price"}]

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


def test_check_price_outliers_handles_zero_iqr():
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
        ("test@example.com", "te***@example.com"),
        ("user.name+shop@example.co.kr", "us***@example.co.kr"),
        ("a@example.com", "a***@example.com"),
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
    rrn = "990101-1234567"
    products = [make_product(description=f"테스트 값 {rrn}")]

    issues = check_prohibited_and_personal_information(products)

    assert len(issues) == 1
    assert issues[0].rule == "resident_registration_number"
    assert issues[0].message == (
        "field 'description' contains resident registration number '990101-1******'"
    )
    assert rrn not in issues[0].message


@pytest.mark.parametrize(
    "text",
    ["9901011234567", "바코드 8801234567890"],
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
    products = [make_product(description="입금 확인 990101-1234567")]

    issues = check_prohibited_and_personal_information(products)

    assert [issue.rule for issue in issues] == ["resident_registration_number"]


def test_check_content_safety_uses_all_rrn_spans_to_avoid_bank_duplicates():
    products = [make_product(description="입금 확인 990101-1234567 990101-1234567")]

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
        "field 'description' contains email address 'te***@example.com'"
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
    price_outlier_issues = [issue for issue in issues if issue.rule == "price_outlier"]

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
