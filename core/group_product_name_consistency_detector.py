# 역할: 같은 상품 그룹 안에서 서로 다른 상품명이 함께 쓰였는지 탐지합니다.
import json

from core.models import Product, ValidationIssue


GROUP_PRODUCT_NAME_MESSAGE_PREFIX = "inconsistent_group_product_name:"


def build_group_product_name_message(
    product_group_id: str, product_name_groups: list[dict[str, object]]
) -> str:
    payload = {"product_group_id": product_group_id, "product_names": product_name_groups}
    return GROUP_PRODUCT_NAME_MESSAGE_PREFIX + json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    )


def parse_group_product_name_message(
    message: str,
) -> tuple[str, list[dict[str, object]]] | None:
    if not isinstance(message, str) or not message.startswith(GROUP_PRODUCT_NAME_MESSAGE_PREFIX):
        return None
    try:
        payload = json.loads(message.removeprefix(GROUP_PRODUCT_NAME_MESSAGE_PREFIX))
    except (json.JSONDecodeError, RecursionError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    product_group_id = payload.get("product_group_id")
    product_names = payload.get("product_names")
    if not isinstance(product_group_id, str) or not isinstance(product_names, list):
        return None
    parsed_names: list[dict[str, object]] = []
    for name in product_names:
        if not isinstance(name, dict):
            return None
        display_value = name.get("display_value")
        product_ids = name.get("product_ids")
        if (
            not isinstance(display_value, str)
            or not isinstance(product_ids, list)
            or not all(isinstance(product_id, str) for product_id in product_ids)
        ):
            return None
        parsed_names.append({"display_value": display_value, "product_ids": product_ids})
    return product_group_id, parsed_names


def find_inconsistent_group_product_names(products: list[Product]) -> list[ValidationIssue]:
    """비어 있지 않은 그룹과 상품명만 비교하고 참여한 모든 행을 알립니다."""
    products_by_group: dict[str, list[tuple[int, Product, str, str]]] = {}
    for index, product in enumerate(products):
        group_id = product.product_group_id.strip() if isinstance(product.product_group_id, str) else ""
        display_name = product.product_name.strip() if isinstance(product.product_name, str) else ""
        if group_id and display_name:
            products_by_group.setdefault(group_id, []).append(
                (index, product, " ".join(display_name.split()).casefold(), display_name)
            )

    indexed_issues: list[tuple[int, ValidationIssue]] = []
    for group_id, entries in products_by_group.items():
        names_by_key: dict[str, dict[str, object]] = {}
        for _, product, key, display_name in entries:
            name_group = names_by_key.setdefault(
                key, {"display_value": display_name, "product_ids": []}
            )
            product_ids = name_group["product_ids"]
            if isinstance(product_ids, list) and product.product_id not in product_ids:
                product_ids.append(product.product_id)
        if len(names_by_key) < 2:
            continue
        message = build_group_product_name_message(group_id, list(names_by_key.values()))
        for index, product, _, _ in entries:
            indexed_issues.append((index, ValidationIssue(
                rule="inconsistent_group_product_name",
                severity="warning",
                product_id=product.product_id,
                product_group_id=product.product_group_id,
                message=message,
                source_row_number=product.source_row_number,
            )))
    return [issue for _, issue in sorted(indexed_issues, key=lambda item: item[0])]
