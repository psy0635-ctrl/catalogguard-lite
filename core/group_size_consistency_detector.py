# 역할: 같은 상품 그룹 안에서 문자형과 숫자형 사이즈 체계가 함께 쓰였는지 탐지합니다.
from core.fashion_attribute_validator import find_size_system
from core.models import Product, ValidationIssue


# 이 규칙은 문자형·숫자형이 함께 있을 때만 만들어지므로 메시지에 추가 값이 필요하지 않습니다.
GROUP_SIZE_SYSTEM_MESSAGE = "product group mixes alpha and numeric size systems"


def find_inconsistent_group_size_systems(
    products: list[Product],
) -> list[ValidationIssue]:
    """같은 그룹에서 분류 가능한 사이즈 체계가 둘 다 쓰였는지 찾습니다."""
    products_by_group: dict[str, list[tuple[int, Product, str]]] = {}

    for product_index, product in enumerate(products):
        product_group_id = (
            product.product_group_id.strip()
            if isinstance(product.product_group_id, str)
            else ""
        )
        # FREE, custom, 빈 값은 체계를 단정할 수 없으므로 비교에서 제외합니다.
        size_system = find_size_system(product.size)
        if not product_group_id or size_system is None:
            continue

        products_by_group.setdefault(product_group_id, []).append(
            (product_index, product, size_system)
        )

    indexed_issues: list[tuple[int, ValidationIssue]] = []
    for group_entries in products_by_group.values():
        size_systems = {size_system for _, _, size_system in group_entries}
        if len(size_systems) < 2:
            continue

        for product_index, product, _ in group_entries:
            indexed_issues.append(
                (
                    product_index,
                    ValidationIssue(
                        rule="inconsistent_group_size_system",
                        severity="warning",
                        product_id=product.product_id,
                        product_group_id=product.product_group_id,
                        message=GROUP_SIZE_SYSTEM_MESSAGE,
                    ),
                )
            )

    return [
        issue
        for _, issue in sorted(indexed_issues, key=lambda indexed_issue: indexed_issue[0])
    ]
