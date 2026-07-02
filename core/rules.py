# 실제 오류를 찾는 핵심 파일
import re
from statistics import quantiles

from config.settings import (
    BANK_ACCOUNT_CONTEXT_TERMS,
    CONTENT_SCAN_FIELDS,
    PRICE_OUTLIER_IQR_MULTIPLIER,
    PRICE_OUTLIER_MIN_CATEGORY_SIZE,
    PROHIBITED_TERMS,
    REQUIRED_FIELDS,
    VALID_CATEGORIES,
)
from core.models import Product, ValidationIssue


# 자주 쓰는 정규식은 매번 새로 만들지 않도록 파일이 로드될 때 한 번만 준비합니다.
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MOBILE_PHONE_PATTERN = re.compile(r"(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
LANDLINE_PHONE_PATTERN = re.compile(r"(?<!\d)0(?:2|[3-6]\d)[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
RESIDENT_REGISTRATION_NUMBER_PATTERN = re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)")
BANK_ACCOUNT_PATTERN = re.compile(r"(?<![\d-])(?:\d[-\s]?){9,13}\d(?![-\s]?\d)")


def normalize_duplicate_text(value: str) -> str:
    """중복 비교를 위해 공백과 영문 대소문자를 정리합니다."""
    return " ".join(value.split()).casefold()


def normalize_content_text(value: str) -> str:
    """내용 검색을 위해 공백과 영문 대소문자를 정리합니다."""
    return " ".join(value.split()).casefold()


def extract_digits(value: str) -> str:
    # 전화번호나 계좌번호처럼 구분자가 섞인 값에서 숫자만 비교할 때 사용합니다.
    return re.sub(r"\D", "", value)


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


def find_phone_number_matches(text: str) -> list[re.Match[str]]:
    matches = [
        *MOBILE_PHONE_PATTERN.finditer(text),
        *LANDLINE_PHONE_PATTERN.finditer(text),
    ]
    matches.sort(key=lambda match: (match.start(), match.end()))
    return matches


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


def find_resident_registration_number_matches(text: str) -> list[re.Match[str]]:
    return list(RESIDENT_REGISTRATION_NUMBER_PATTERN.finditer(text))


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


def mask_email(value: str) -> str:
    # 결과 메시지에는 개인정보 원문을 남기지 않고 일부만 보여줍니다.
    local_part, domain = value.split("@", 1)
    visible_local_part = local_part[:2] if len(local_part) >= 2 else local_part[:1]
    return f"{visible_local_part}***@{domain}"


def mask_phone_number(value: str) -> str:
    digits = extract_digits(value)
    separated_parts = [part for part in re.split(r"[-\s]+", value.strip()) if part]

    if len(separated_parts) >= 3:
        return f"{separated_parts[0]}-****-{separated_parts[-1]}"

    prefix_length = 2 if digits.startswith("02") else 3
    return f"{digits[:prefix_length]}****{digits[-4:]}"


def mask_resident_registration_number(value: str) -> str:
    return f"{value[:8]}******"


def mask_account_number(value: str) -> str:
    digits = extract_digits(value)
    return f"{digits[:3]}-***-***{digits[-3:]}"


def check_duplicate_product_id(products: list[Product]) -> list[ValidationIssue]:
    seen: dict[str, str] = {}
    issues = []
    for product in products:
        # ID가 비어 있으면 중복 검사가 아니라 필수값 누락 규칙에서 처리합니다.
        if not product.product_id or not product.product_group_id:
            continue

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


def check_price_outliers(products: list[Product]) -> list[ValidationIssue]:
    """카테고리별 가격 분포를 기준으로 지나치게 높거나 낮은 가격을 찾습니다."""
    products_by_category: dict[str, list[Product]] = {}

    for product in products:
        # 이상치 계산은 유효한 카테고리와 양수 가격만 대상으로 합니다.
        if not product.category or product.category not in VALID_CATEGORIES:
            continue
        if product.price is None or product.price <= 0:
            continue

        products_by_category.setdefault(product.category, []).append(product)

    issues = []
    for category, category_products in products_by_category.items():
        # 데이터가 너무 적으면 이상치 기준이 불안정하므로 계산하지 않습니다.
        if len(category_products) < PRICE_OUTLIER_MIN_CATEGORY_SIZE:
            continue

        prices = sorted(product.price for product in category_products if product.price)
        # IQR은 가운데 50% 가격 범위를 이용해 너무 튀는 값을 찾는 방식입니다.
        q1, _, q3 = quantiles(prices, n=4, method="inclusive")
        iqr = q3 - q1
        lower_bound = q1 - PRICE_OUTLIER_IQR_MULTIPLIER * iqr
        upper_bound = q3 + PRICE_OUTLIER_IQR_MULTIPLIER * iqr
        lower_display = round(lower_bound)
        upper_display = round(upper_bound)

        for product in category_products:
            if product.price < lower_bound or product.price > upper_bound:
                issues.append(
                    ValidationIssue(
                        rule="price_outlier",
                        severity="warning",
                        product_id=product.product_id,
                        product_group_id=product.product_group_id,
                        message=(
                            f"price {product.price} is outside category "
                            f"'{category}' expected range {lower_display} "
                            f"to {upper_display}"
                        ),
                    )
                )

    return issues


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
    check_duplicate_product_content,
    check_missing_required_fields,
    check_invalid_category,
    check_stock,
    check_price,
    check_price_outliers,
    check_prohibited_and_personal_information,
]


def run_all_rules(products: list[Product]) -> list[ValidationIssue]:
    issues = []
    for rule in RULES:
        issues.extend(rule(products))
    return issues
