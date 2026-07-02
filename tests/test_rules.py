from core.models import Product
from core.rules import (
    check_duplicate_product_id,
    check_invalid_category,
    check_missing_required_fields,
    check_price,
    check_stock,
    run_all_rules,
)


def make_product(**overrides) -> Product:
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


def test_run_all_rules_aggregates_every_rule():
    products = [
        make_product(product_group_id="G001", product_id="P003", color="BLACK"),
        make_product(product_group_id="G002", product_id="P003", color=""),
    ]

    issues = run_all_rules(products)
    rules_triggered = {issue.rule for issue in issues}

    assert "duplicate_product_id" in rules_triggered
    assert "missing_required_field" in rules_triggered
