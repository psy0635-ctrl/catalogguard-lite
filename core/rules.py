from config.settings import REQUIRED_FIELDS, VALID_CATEGORIES
from core.models import Product, ValidationIssue


def check_duplicate_product_id(products: list[Product]) -> list[ValidationIssue]:
    seen: dict[str, str] = {}
    issues = []
    for product in products:
        prior_group = seen.get(product.product_id)
        if prior_group is None:
            seen[product.product_id] = product.product_group_id
        elif prior_group != product.product_group_id:
            issues.append(
                ValidationIssue(
                    rule="duplicate_product_id",
                    severity="error",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message=(
                        f"product_id '{product.product_id}' is reused across "
                        f"groups '{prior_group}' and '{product.product_group_id}'"
                    ),
                )
            )
    return issues


def check_missing_required_fields(products: list[Product]) -> list[ValidationIssue]:
    issues = []
    for product in products:
        for field in REQUIRED_FIELDS:
            if not getattr(product, field):
                issues.append(
                    ValidationIssue(
                        rule="missing_required_field",
                        severity="error",
                        product_id=product.product_id,
                        product_group_id=product.product_group_id,
                        message=f"'{field}' is missing",
                    )
                )
    return issues


def check_invalid_category(products: list[Product]) -> list[ValidationIssue]:
    issues = []
    for product in products:
        if product.category and product.category not in VALID_CATEGORIES:
            issues.append(
                ValidationIssue(
                    rule="invalid_category",
                    severity="error",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message=f"category '{product.category}' is not one of {sorted(VALID_CATEGORIES)}",
                )
            )
    return issues


def check_stock(products: list[Product]) -> list[ValidationIssue]:
    issues = []
    for product in products:
        if product.stock is None:
            issues.append(
                ValidationIssue(
                    rule="invalid_stock",
                    severity="error",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message="stock is missing or not a number",
                )
            )
        elif product.stock < 0:
            issues.append(
                ValidationIssue(
                    rule="invalid_stock",
                    severity="error",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message=f"stock {product.stock} is negative",
                )
            )
        elif product.stock == 0:
            issues.append(
                ValidationIssue(
                    rule="out_of_stock",
                    severity="warning",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message="stock is 0",
                )
            )
    return issues


def check_price(products: list[Product]) -> list[ValidationIssue]:
    issues = []
    for product in products:
        if product.price is None:
            issues.append(
                ValidationIssue(
                    rule="invalid_price",
                    severity="error",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message="price is missing or not a number",
                )
            )
        elif product.price < 0:
            issues.append(
                ValidationIssue(
                    rule="invalid_price",
                    severity="error",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message=f"price {product.price} is negative",
                )
            )
        elif product.price == 0:
            issues.append(
                ValidationIssue(
                    rule="zero_price",
                    severity="warning",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message="price is 0",
                )
            )
    return issues


RULES = [
    check_duplicate_product_id,
    check_missing_required_fields,
    check_invalid_category,
    check_stock,
    check_price,
]


def run_all_rules(products: list[Product]) -> list[ValidationIssue]:
    issues = []
    for rule in RULES:
        issues.extend(rule(products))
    return issues
