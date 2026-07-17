# 역할: 같은 상품 그룹 안에서 서로 다른 카테고리가 함께 쓰였는지 탐지합니다.
import json

from core.category_mismatch_detector import normalize_category
from core.models import Product, ValidationIssue


GROUP_CATEGORY_MESSAGE_PREFIX = "inconsistent_group_category:"


def build_group_category_message(
    product_group_id: str,
    category_groups: list[dict[str, object]],
) -> str:
    """표시 계층이 손실 없이 읽을 수 있는 카테고리 불일치 메시지를 만듭니다."""
    payload = {
        "product_group_id": product_group_id,
        "categories": category_groups,
    }
    return GROUP_CATEGORY_MESSAGE_PREFIX + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_group_category_message(
    message: str,
) -> tuple[str, list[dict[str, object]]] | None:
    """구조화된 카테고리 불일치 메시지의 JSON과 필드 타입을 검증합니다."""
    if not isinstance(message, str) or not message.startswith(
        GROUP_CATEGORY_MESSAGE_PREFIX
    ):
        return None

    try:
        payload = json.loads(message.removeprefix(GROUP_CATEGORY_MESSAGE_PREFIX))
    except (json.JSONDecodeError, RecursionError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    product_group_id = payload.get("product_group_id")
    categories = payload.get("categories")
    if not isinstance(product_group_id, str) or not isinstance(categories, list):
        return None

    parsed_categories: list[dict[str, object]] = []
    for category in categories:
        if not isinstance(category, dict):
            return None

        display_value = category.get("display_value")
        product_ids = category.get("product_ids")
        if (
            not isinstance(display_value, str)
            or not isinstance(product_ids, list)
            or not all(isinstance(product_id, str) for product_id in product_ids)
        ):
            return None

        parsed_categories.append(
            {
                "display_value": display_value,
                "product_ids": product_ids,
            }
        )

    return product_group_id, parsed_categories


def find_inconsistent_group_categories(
    products: list[Product],
) -> list[ValidationIssue]:
    """같은 그룹의 비어 있지 않은 카테고리 비교값이 둘 이상인지 찾습니다."""
    products_by_group: dict[
        str,
        list[tuple[int, Product, str, str]],
    ] = {}

    for product_index, product in enumerate(products):
        product_group_id = (
            product.product_group_id.strip()
            if isinstance(product.product_group_id, str)
            else ""
        )
        category_key = normalize_category(product.category)
        if not product_group_id or not category_key:
            continue

        display_value = product.category.strip()
        products_by_group.setdefault(product_group_id, []).append(
            (product_index, product, category_key, display_value)
        )

    indexed_issues: list[tuple[int, ValidationIssue]] = []
    for product_group_id, group_entries in products_by_group.items():
        categories_by_key: dict[str, dict[str, object]] = {}
        for _, product, category_key, display_value in group_entries:
            category_group = categories_by_key.setdefault(
                category_key,
                {
                    "display_value": display_value,
                    "product_ids": [],
                },
            )
            product_ids = category_group["product_ids"]
            if isinstance(product_ids, list) and product.product_id not in product_ids:
                product_ids.append(product.product_id)

        if len(categories_by_key) < 2:
            continue

        message = build_group_category_message(
            product_group_id,
            list(categories_by_key.values()),
        )
        for product_index, product, _, _ in group_entries:
            indexed_issues.append(
                (
                    product_index,
                    ValidationIssue(
                        rule="inconsistent_group_category",
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
