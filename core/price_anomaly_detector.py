# 역할: 카테고리별 가격 분포를 기준으로 지나치게 낮거나 높은 가격을 찾습니다.
from statistics import median

from core.models import Product, ValidationIssue


MIN_CATEGORY_SAMPLE_SIZE = 5
LOW_PRICE_RATIO = 0.25
HIGH_PRICE_RATIO = 4.0


def normalize_category(category: str) -> str:
    """카테고리 비교용 문자열을 정리합니다."""
    if not isinstance(category, str):
        return ""
    return category.strip().casefold()


def get_valid_price(price) -> int | None:
    """통계 계산에 사용할 수 있는 양수 가격을 반환합니다."""
    if isinstance(price, bool):
        return None
    if isinstance(price, int):
        return price if price > 0 else None
    if isinstance(price, str):
        stripped_price = price.strip()
        if not stripped_price:
            return None
        try:
            parsed_price = int(stripped_price)
        except ValueError:
            return None
        return parsed_price if parsed_price > 0 else None
    return None


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}"


def calculate_category_price_medians(products: list[Product]) -> dict[str, float]:
    """카테고리별 가격 중앙값을 계산합니다."""
    prices_by_category: dict[str, list[int]] = {}

    for product in products:
        category = normalize_category(product.category)
        price = get_valid_price(product.price)
        if not category or price is None:
            continue
        prices_by_category.setdefault(category, []).append(price)

    medians = {}
    for category, prices in prices_by_category.items():
        if len(prices) < MIN_CATEGORY_SAMPLE_SIZE:
            continue
        medians[category] = float(median(prices))

    return medians


def find_category_price_anomalies(products: list[Product]) -> list[ValidationIssue]:
    """카테고리 중앙값과 비교하여 가격 이상치를 찾습니다."""
    category_medians = calculate_category_price_medians(products)
    issues = []

    for product in products:
        category = normalize_category(product.category)
        price = get_valid_price(product.price)
        if not category or price is None:
            continue

        median_price = category_medians.get(category)
        if median_price is None:
            continue

        if not (
            price < median_price * LOW_PRICE_RATIO
            or price > median_price * HIGH_PRICE_RATIO
        ):
            continue

        ratio = price / median_price
        issues.append(
            ValidationIssue(
                rule="category_price_anomaly",
                severity="warning",
                product_id=product.product_id,
                product_group_id=product.product_group_id,
                message=(
                    f"price {price} in category '{product.category.strip()}' "
                    f"has median {_format_number(median_price)} "
                    f"and ratio {_format_number(ratio)}"
                ),
            )
        )

    return issues


def detect_price_anomalies(products: list[Product]) -> list[ValidationIssue]:
    return find_category_price_anomalies(products)
