# 역할: 상품 ID와 상품명 기준으로 중복 상품 후보를 탐지합니다.
import re

from core.models import Product, ValidationIssue


PRODUCT_NAME_ALLOWED_PATTERN = re.compile(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ]")


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


def detect_duplicate_products(products: list[Product]) -> list[ValidationIssue]:
    return [
        *find_duplicate_product_ids(products),
        *find_duplicate_product_names(products),
    ]
