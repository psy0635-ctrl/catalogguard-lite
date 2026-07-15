# 역할: 상품 목록에 적용할 핵심 검수 규칙들을 실행하고 문제 목록을 만듭니다.
import re

from config.settings import (
    BANK_ACCOUNT_CONTEXT_TERMS,
    CONTENT_SCAN_FIELDS,
    PROHIBITED_TERMS,
    REQUIRED_FIELDS,
    VALID_CATEGORIES,
)
from core.category_mismatch_detector import find_category_mismatches
from core.duplicate_detector import (
    find_duplicate_product_ids,
    find_duplicate_product_names,
)
from core.fashion_attribute_validator import (
    find_standard_color,
    find_standard_size,
)
from core.models import Product, ValidationIssue
from core.price_anomaly_detector import find_category_price_anomalies
from core.privacy import (
    EMAIL_PATTERN,
    extract_digits,
    find_phone_number_matches,
    find_resident_registration_number_matches,
    mask_email,
    mask_phone_number,
    mask_resident_registration_number,
)


BANK_ACCOUNT_PATTERN = re.compile(r"(?<![\d-])(?:\d[-\s]?){9,13}\d(?![-\s]?\d)")


def normalize_duplicate_text(value: str) -> str:
    """중복 비교를 위해 공백과 영문 대소문자를 정리합니다."""
    return " ".join(value.split()).casefold()


def normalize_content_text(value: str) -> str:
    """내용 검색을 위해 공백과 영문 대소문자를 정리합니다."""
    return " ".join(value.split()).casefold()


def iter_scannable_fields(product: Product):
    # 설정에 적힌 순서대로 필드를 돌려야 테스트와 화면 결과 순서가 안정적입니다.
    for field_name in CONTENT_SCAN_FIELDS:
        yield field_name, getattr(product, field_name, "")


def find_prohibited_terms(text: str) -> list[str]:
    normalized_text = normalize_content_text(text)
    found_terms = []

    for term in PROHIBITED_TERMS:
        normalized_term = normalize_content_text(term)
        if normalized_term and normalized_term in normalized_text:
            found_terms.append(term)

    return found_terms


def find_unique_pattern_values(pattern: re.Pattern[str], text: str) -> list[str]:
    # 같은 필드 안에서 같은 이메일이 반복되어도 문제는 한 번만 만들기 위한 함수입니다.
    values = []
    seen_values = set()

    for match in pattern.finditer(text):
        value = match.group()
        key = value.casefold()
        if key in seen_values:
            continue
        seen_values.add(key)
        values.append(value)

    return values


def find_unique_matches_by_key(matches: list[re.Match[str]], key_func) -> list[re.Match[str]]:
    # 같은 값을 다른 표기로 쓴 경우도 같은 문제로 보려고 비교용 key를 따로 받습니다.
    unique_matches = []
    seen_keys = set()
    for match in matches:
        key = key_func(match)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_matches.append(match)

    return unique_matches


def spans_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    # 두 정규식 결과가 같은 글자 구간을 가리키는지 확인합니다.
    return first[0] < second[1] and second[0] < first[1]


def has_bank_account_context(text: str) -> bool:
    # 긴 숫자만으로 계좌라고 판단하지 않도록, 주변 문맥어가 있는지 먼저 봅니다.
    normalized_text = normalize_content_text(text)
    return any(
        normalize_content_text(term) in normalized_text
        for term in BANK_ACCOUNT_CONTEXT_TERMS
    )


def find_suspected_bank_account_matches(
    text: str,
    occupied_spans: list[tuple[int, int]],
) -> list[re.Match[str]]:
    if not has_bank_account_context(text):
        return []

    matches = []
    seen_numbers = set()
    for match in BANK_ACCOUNT_PATTERN.finditer(text):
        # 이미 전화번호나 주민등록번호로 잡힌 숫자는 계좌번호로 중복 표시하지 않습니다.
        if any(spans_overlap(match.span(), occupied_span) for occupied_span in occupied_spans):
            continue

        digits = extract_digits(match.group())
        if not 10 <= len(digits) <= 14:
            continue
        if digits in seen_numbers:
            continue

        seen_numbers.add(digits)
        matches.append(match)

    return matches


def mask_account_number(value: str) -> str:
    digits = extract_digits(value)
    return f"{digits[:3]}-***-***{digits[-3:]}"


def check_duplicate_product_id(products: list[Product]) -> list[ValidationIssue]:
    return find_duplicate_product_ids(products)


def check_duplicate_product_name(products: list[Product]) -> list[ValidationIssue]:
    return find_duplicate_product_names(products)


def check_duplicate_product_content(products: list[Product]) -> list[ValidationIssue]:
    """상품 핵심 정보가 모두 같은 중복 상품을 찾습니다."""
    seen: dict[tuple[str, str, str, str, int], Product] = {}
    issues = []

    for product in products:
        # 비교 기준이 부족하거나 잘못된 상품은 중복 판단에서 제외합니다.
        if not product.product_group_id or not product.product_id:
            continue
        if not product.product_name or not product.category:
            continue
        if product.category not in VALID_CATEGORIES:
            continue
        if not product.color or not product.size:
            continue
        if product.price is None or product.price <= 0:
            continue

        # 상품명/카테고리/색상/사이즈/가격이 모두 같으면 같은 상품으로 봅니다.
        duplicate_key = (
            normalize_duplicate_text(product.product_name),
            normalize_duplicate_text(product.category),
            normalize_duplicate_text(product.color),
            normalize_duplicate_text(product.size),
            product.price,
        )
        first_product = seen.get(duplicate_key)
        if first_product is None:
            seen[duplicate_key] = product
            continue

        issues.append(
            ValidationIssue(
                rule="duplicate_product_content",
                severity="error",
                product_id=product.product_id,
                product_group_id=product.product_group_id,
                message=(
                    f"product_id '{product.product_id}' in group "
                    f"'{product.product_group_id}' duplicates product_id "
                    f"'{first_product.product_id}' in group "
                    f"'{first_product.product_group_id}' with same product_name, "
                    "category, color, size, and price"
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


def check_non_standard_color(
    products: list[Product],
) -> list[ValidationIssue]:
    issues = []
    for product in products:
        if not product.color:
            continue

        standard_color = find_standard_color(product.color)
        if standard_color is None or product.color == standard_color:
            continue

        issues.append(
            ValidationIssue(
                rule="non_standard_color",
                severity="warning",
                product_id=product.product_id,
                product_group_id=product.product_group_id,
                message=(
                    f"color '{product.color}' should be standardized to "
                    f"'{standard_color}'"
                ),
            )
        )
    return issues


def check_non_standard_size(
    products: list[Product],
) -> list[ValidationIssue]:
    issues = []
    for product in products:
        if not product.size:
            continue

        standard_size = find_standard_size(product.size)
        if standard_size is None or product.size == standard_size:
            continue

        issues.append(
            ValidationIssue(
                rule="non_standard_size",
                severity="warning",
                product_id=product.product_id,
                product_group_id=product.product_group_id,
                message=(
                    f"size '{product.size}' should be standardized to "
                    f"'{standard_size}'"
                ),
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
        elif product.price <= 0:
            issues.append(
                ValidationIssue(
                    rule="invalid_non_positive_price",
                    severity="error",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message=f"price {product.price} is not positive",
                )
            )
    return issues


def check_price_outliers(products: list[Product]) -> list[ValidationIssue]:
    """카테고리별 가격 중앙값을 기준으로 지나치게 높거나 낮은 가격을 찾습니다."""
    return find_category_price_anomalies(products)


def check_product_category_mismatch(products: list[Product]) -> list[ValidationIssue]:
    return find_category_mismatches(products)


def check_prohibited_and_personal_information(
    products: list[Product],
) -> list[ValidationIssue]:
    """상품 텍스트에서 금지어와 개인정보 형태를 찾습니다."""
    issues = []

    for product in products:
        for field_name, value in iter_scannable_fields(product):
            if not value:
                continue

            # 한 필드 안에서는 금지어 -> 이메일 -> 전화번호 -> 주민번호 -> 계좌 의심 순서로 검사합니다.
            for term in find_prohibited_terms(value):
                issues.append(
                    ValidationIssue(
                        rule="prohibited_term",
                        severity="error",
                        product_id=product.product_id,
                        product_group_id=product.product_group_id,
                        message=(
                            f"field '{field_name}' contains prohibited term '{term}'"
                        ),
                    )
                )

            for email_address in find_unique_pattern_values(EMAIL_PATTERN, value):
                issues.append(
                    ValidationIssue(
                        rule="email_address",
                        severity="error",
                        product_id=product.product_id,
                        product_group_id=product.product_group_id,
                        message=(
                            f"field '{field_name}' contains email address "
                            f"'{mask_email(email_address)}'"
                        ),
                    )
                )

            phone_matches = find_phone_number_matches(value)
            resident_registration_number_matches = (
                find_resident_registration_number_matches(value)
            )
            # 문제 메시지는 중복 없이 만들지만, 계좌번호 중복 방지를 위해 원래 span은 따로 보관합니다.
            unique_phone_matches = find_unique_matches_by_key(
                phone_matches,
                lambda match: extract_digits(match.group()),
            )
            unique_rrn_matches = find_unique_matches_by_key(
                resident_registration_number_matches,
                lambda match: match.group(),
            )

            for phone_match in unique_phone_matches:
                issues.append(
                    ValidationIssue(
                        rule="phone_number",
                        severity="error",
                        product_id=product.product_id,
                        product_group_id=product.product_group_id,
                        message=(
                            f"field '{field_name}' contains phone number "
                            f"'{mask_phone_number(phone_match.group())}'"
                        ),
                    )
                )

            for rrn_match in unique_rrn_matches:
                issues.append(
                    ValidationIssue(
                        rule="resident_registration_number",
                        severity="error",
                        product_id=product.product_id,
                        product_group_id=product.product_group_id,
                        message=(
                            f"field '{field_name}' contains resident registration "
                            f"number '{mask_resident_registration_number(rrn_match.group())}'"
                        ),
                    )
                )

            occupied_spans = [
                match.span()
                for match in [
                    *phone_matches,
                    *resident_registration_number_matches,
                ]
            ]
            for account_match in find_suspected_bank_account_matches(
                value,
                occupied_spans,
            ):
                issues.append(
                    ValidationIssue(
                        rule="suspected_bank_account",
                        severity="warning",
                        product_id=product.product_id,
                        product_group_id=product.product_group_id,
                        message=(
                            f"field '{field_name}' contains suspected bank account "
                            f"'{mask_account_number(account_match.group())}'"
                        ),
                    )
                )

    return issues


RULES = [
    # 이 순서대로 실행되므로, 새 규칙을 추가할 때 결과 순서도 함께 고려해야 합니다.
    check_duplicate_product_id,
    check_duplicate_product_name,
    check_duplicate_product_content,
    check_missing_required_fields,
    check_non_standard_color,
    check_non_standard_size,
    check_invalid_category,
    check_stock,
    check_price,
    check_price_outliers,
    check_product_category_mismatch,
    check_prohibited_and_personal_information,
]


def run_all_rules(products: list[Product]) -> list[ValidationIssue]:
    issues = []
    for rule in RULES:
        issues.extend(rule(products))
    return issues
