# 역할: 상품 ID·상품명과 상품 그룹 내 옵션 조합 기준으로 중복 상품 후보를 탐지합니다.
import json
import re

from config.settings import VALID_CATEGORIES
from core.fashion_attribute_validator import (
    build_color_comparison_key,
    build_size_comparison_key,
)
from core.models import Product, ValidationIssue


PRODUCT_NAME_ALLOWED_PATTERN = re.compile(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]")
DUPLICATE_VARIANT_MESSAGE_PREFIX = "duplicate_variant_combination:"


def normalize_product_name(product_name: str) -> str:
    """중복 비교를 위해 상품명을 정리합니다."""
    if not isinstance(product_name, str):
        return ""

    normalized_name = product_name.strip().casefold()
    return PRODUCT_NAME_ALLOWED_PATTERN.sub("", normalized_name)


def normalize_option_value(value: object) -> str:
    """상품 옵션 비교를 위해 값을 정리합니다."""
    if value is None:
        return ""
    return str(value).strip().casefold()


def normalize_duplicate_content_text(value: str) -> str:
    """완전 중복 비교를 위해 공백과 영문 대소문자를 정리합니다."""
    return " ".join(value.split()).casefold()


def build_duplicate_variant_message(
    product_group_id: str,
    color_key: str,
    size_key: str,
    product_ids: list[str],
) -> str:
    """표시 계층이 손실 없이 읽을 수 있는 중복 옵션 메시지를 만듭니다."""
    payload = {
        "product_group_id": product_group_id,
        "color": color_key,
        "size": size_key,
        "product_ids": product_ids,
    }
    return DUPLICATE_VARIANT_MESSAGE_PREFIX + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_duplicate_variant_message(
    message: str,
) -> tuple[str, str, str, list[str]] | None:
    """구조화된 중복 옵션 메시지를 검증해 표시용 값으로 되돌립니다."""
    if not message.startswith(DUPLICATE_VARIANT_MESSAGE_PREFIX):
        return None

    try:
        payload = json.loads(message.removeprefix(DUPLICATE_VARIANT_MESSAGE_PREFIX))
    except (json.JSONDecodeError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    product_group_id = payload.get("product_group_id")
    color = payload.get("color")
    size = payload.get("size")
    product_ids = payload.get("product_ids")
    if (
        not isinstance(product_group_id, str)
        or not isinstance(color, str)
        or not isinstance(size, str)
        or not isinstance(product_ids, list)
        or not all(isinstance(product_id, str) for product_id in product_ids)
    ):
        return None

    return product_group_id, color, size, product_ids


def build_duplicate_product_content_key(
    product: Product,
) -> tuple[str, str, str, str, int] | None:
    """비교 가능한 상품이면 기존 완전 중복 판정 키를 반환합니다."""
    if not product.product_group_id or not product.product_id:
        return None
    if not product.product_name or not product.category:
        return None
    if product.category not in VALID_CATEGORIES:
        return None
    if not product.color or not product.size:
        return None
    if product.price is None or product.price <= 0:
        return None

    return (
        normalize_duplicate_content_text(product.product_name),
        normalize_duplicate_content_text(product.category),
        normalize_duplicate_content_text(product.color),
        normalize_duplicate_content_text(product.size),
        product.price,
    )


def has_explicit_option_difference(first: Product, second: Product) -> bool:
    # 같은 상품 그룹 안에서 색상이나 사이즈가 명확히 다르면 정상 옵션으로 볼 수 있습니다.
    first_color = normalize_option_value(first.color)
    second_color = normalize_option_value(second.color)
    first_size = normalize_option_value(first.size)
    second_size = normalize_option_value(second.size)

    color_is_different = first_color and second_color and first_color != second_color
    size_is_different = first_size and second_size and first_size != second_size
    return bool(color_is_different or size_is_different)


def is_same_group_normal_option(first: Product, second: Product) -> bool:
    first_group_id = normalize_option_value(first.product_group_id)
    second_group_id = normalize_option_value(second.product_group_id)
    first_product_id = normalize_option_value(first.product_id)
    second_product_id = normalize_option_value(second.product_id)

    if not first_group_id or first_group_id != second_group_id:
        return False
    if not first_product_id or not second_product_id:
        return False
    if first_product_id == second_product_id:
        return False
    return has_explicit_option_difference(first, second)


def _format_row_numbers(rows: list[int]) -> str:
    return ", ".join(str(row) for row in rows)


def _format_product_ids(products: list[Product]) -> str:
    product_ids = [product.product_id.strip() for product in products if product.product_id.strip()]
    return ", ".join(product_ids) if product_ids else "없음"


def find_duplicate_product_ids(products: list[Product]) -> list[ValidationIssue]:
    products_by_id: dict[str, list[tuple[int, Product]]] = {}

    # CSV의 1행은 헤더이므로 사용자에게 보여 줄 데이터 행 번호는 2부터 시작합니다.
    for row_number, product in enumerate(products, start=2):
        product_id = product.product_id.strip()
        if not product_id:
            continue
        products_by_id.setdefault(product_id, []).append((row_number, product))

    issues = []
    for product_id, duplicate_rows in products_by_id.items():
        if len(duplicate_rows) < 2:
            continue

        row_numbers = [row_number for row_number, _ in duplicate_rows]
        row_text = _format_row_numbers(row_numbers)
        for _, product in duplicate_rows:
            issues.append(
                ValidationIssue(
                    rule="duplicate_product_id",
                    severity="error",
                    product_id=product_id,
                    product_group_id=product.product_group_id,
                    message=f"product_id '{product_id}' is duplicated in rows {row_text}",
                )
            )

    return issues


def find_duplicate_product_names(products: list[Product]) -> list[ValidationIssue]:
    products_by_name: dict[str, list[tuple[int, Product]]] = {}

    # 상품명은 공백, 특수문자, 대소문자를 정리한 뒤 비교해야 눈에 보이는 중복을 잡기 쉽습니다.
    for row_number, product in enumerate(products, start=2):
        normalized_name = normalize_product_name(product.product_name)
        if not normalized_name:
            continue
        products_by_name.setdefault(normalized_name, []).append((row_number, product))

    issues = []
    for normalized_name, duplicate_rows in products_by_name.items():
        if len(duplicate_rows) < 2:
            continue

        duplicate_indexes: set[int] = set()
        for first_index, (_, first_product) in enumerate(duplicate_rows):
            for second_index in range(first_index + 1, len(duplicate_rows)):
                _, second_product = duplicate_rows[second_index]
                if is_same_group_normal_option(first_product, second_product):
                    continue
                duplicate_indexes.add(first_index)
                duplicate_indexes.add(second_index)

        if len(duplicate_indexes) < 2:
            continue

        candidate_rows = [
            duplicate_rows[index] for index in sorted(duplicate_indexes)
        ]
        row_numbers = [row_number for row_number, _ in candidate_rows]
        duplicate_products = [product for _, product in candidate_rows]
        row_text = _format_row_numbers(row_numbers)
        product_id_text = _format_product_ids(duplicate_products)

        for _, product in candidate_rows:
            issues.append(
                ValidationIssue(
                    rule="duplicate_product_name",
                    severity="warning",
                    product_id=product.product_id,
                    product_group_id=product.product_group_id,
                    message=(
                        f"product_name '{product.product_name}' normalized to "
                        f"'{normalized_name}' duplicates rows {row_text} "
                        f"with product_ids '{product_id_text}'"
                    ),
                )
            )

    return issues


def find_duplicate_product_content(
    products: list[Product],
) -> list[ValidationIssue]:
    """완전 중복 비교 키가 같은 상품을 찾습니다."""
    seen: dict[tuple[str, str, str, str, int], Product] = {}
    issues = []

    for product in products:
        duplicate_key = build_duplicate_product_content_key(product)
        if duplicate_key is None:
            continue

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


def find_duplicate_variant_combinations(
    products: list[Product],
) -> list[ValidationIssue]:
    """같은 그룹에서 서로 다른 상품 ID가 공유하는 색상·사이즈 조합을 찾습니다."""
    products_by_variant: dict[tuple[str, str, str], list[tuple[int, Product]]] = {}

    for product_index, product in enumerate(products):
        product_group_id = product.product_group_id.strip()
        product_id = product.product_id.strip()
        color_key = build_color_comparison_key(product.color)
        size_key = build_size_comparison_key(product.size)

        # 비어 있는 값은 기존 필수값 누락 규칙이 담당합니다.
        if (
            not product_group_id
            or not product_id
            or color_key is None
            or size_key is None
        ):
            continue

        variant_key = (product_group_id, color_key, size_key)
        products_by_variant.setdefault(variant_key, []).append(
            (product_index, product)
        )

    indexed_issues: list[tuple[int, ValidationIssue]] = []
    for (product_group_id, color_key, size_key), duplicate_entries in (
        products_by_variant.items()
    ):
        duplicate_products = [product for _, product in duplicate_entries]
        product_ids = list(
            dict.fromkeys(product.product_id.strip() for product in duplicate_products)
        )
        if len(product_ids) < 2:
            continue

        complete_content_keys = [
            build_duplicate_product_content_key(product)
            for product in duplicate_products
        ]
        variant_indexes: set[int] = set()
        for first_index, first_product in enumerate(duplicate_products):
            for second_index in range(first_index + 1, len(duplicate_products)):
                second_product = duplicate_products[second_index]
                if (
                    first_product.product_id.strip()
                    == second_product.product_id.strip()
                ):
                    continue

                first_content_key = complete_content_keys[first_index]
                second_content_key = complete_content_keys[second_index]
                if (
                    first_content_key is not None
                    and first_content_key == second_content_key
                ):
                    continue

                variant_indexes.add(first_index)
                variant_indexes.add(second_index)

        if len(variant_indexes) < 2:
            continue

        duplicate_entries = [
            entry
            for index, entry in enumerate(duplicate_entries)
            if index in variant_indexes
        ]
        duplicate_products = [product for _, product in duplicate_entries]
        product_ids = list(
            dict.fromkeys(product.product_id.strip() for product in duplicate_products)
        )

        message = build_duplicate_variant_message(
            product_group_id,
            color_key,
            size_key,
            product_ids,
        )
        for product_index, product in duplicate_entries:
            indexed_issues.append(
                (
                    product_index,
                    ValidationIssue(
                        rule="duplicate_variant_combination",
                        severity="error",
                        product_id=product.product_id,
                        product_group_id=product.product_group_id,
                        message=message,
                    ),
                )
            )

    return [
        issue
        for _, issue in sorted(indexed_issues, key=lambda indexed_issue: indexed_issue[0])
    ]


def detect_duplicate_products(products: list[Product]) -> list[ValidationIssue]:
    return [
        *find_duplicate_product_ids(products),
        *find_duplicate_product_names(products),
    ]
