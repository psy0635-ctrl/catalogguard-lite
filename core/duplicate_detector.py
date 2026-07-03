# 상품 목록 전체를 비교하는 중복 탐지 유틸입니다.
import re

from core.models import Product, ValidationIssue


PRODUCT_NAME_ALLOWED_PATTERN = re.compile(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]")


def normalize_product_name(product_name: str) -> str:
    """중복 비교를 위해 상품명을 정리합니다."""
    if not isinstance(product_name, str):
        return ""

    normalized_name = product_name.strip().casefold()
    return PRODUCT_NAME_ALLOWED_PATTERN.sub("", normalized_name)


def _format_row_numbers(rows: list[int]) -> str:
    return ", ".join(str(row) for row in rows)


def _format_product_ids(products: list[Product]) -> str:
    product_ids = [product.product_id.strip() for product in products if product.product_id.strip()]
    return ", ".join(product_ids) if product_ids else "없음"


def find_duplicate_product_ids(products: list[Product]) -> list[ValidationIssue]:
    products_by_id: dict[str, list[tuple[int, Product]]] = {}

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

    for row_number, product in enumerate(products, start=2):
        normalized_name = normalize_product_name(product.product_name)
        if not normalized_name:
            continue
        products_by_name.setdefault(normalized_name, []).append((row_number, product))

    issues = []
    for normalized_name, duplicate_rows in products_by_name.items():
        if len(duplicate_rows) < 2:
            continue

        row_numbers = [row_number for row_number, _ in duplicate_rows]
        duplicate_products = [product for _, product in duplicate_rows]
        row_text = _format_row_numbers(row_numbers)
        product_id_text = _format_product_ids(duplicate_products)

        for _, product in duplicate_rows:
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


def detect_duplicate_products(products: list[Product]) -> list[ValidationIssue]:
    return [
        *find_duplicate_product_ids(products),
        *find_duplicate_product_names(products),
    ]
