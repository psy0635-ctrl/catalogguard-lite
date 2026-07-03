# 상품명에서 추정되는 카테고리와 현재 카테고리의 명확한 불일치를 찾습니다.
import re

from config.settings import CATEGORY_ALIASES, CATEGORY_KEYWORDS
from core.models import Product, ValidationIssue


SEPARATOR_PATTERN = re.compile(r"[-_/]+")
WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_product_name_for_category(value: object) -> str:
    """카테고리 키워드 검색을 위해 상품명을 정리합니다."""
    if not isinstance(value, str):
        return ""

    normalized_value = value.strip().casefold()
    normalized_value = SEPARATOR_PATTERN.sub(" ", normalized_value)
    return WHITESPACE_PATTERN.sub(" ", normalized_value).strip()


def normalize_category(value: object) -> str:
    """카테고리 비교를 위해 문자열을 정리합니다."""
    if not isinstance(value, str):
        return ""

    normalized_value = value.strip().casefold()
    if not normalized_value:
        return ""
    return CATEGORY_ALIASES.get(normalized_value, normalized_value)


def _compact(value: str) -> str:
    return value.replace(" ", "")


def _find_category_keyword_matches(product_name: object) -> dict[str, list[str]]:
    normalized_name = normalize_product_name_for_category(product_name)
    if not normalized_name:
        return {}

    compact_name = _compact(normalized_name)
    matches: dict[str, list[str]] = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            normalized_keyword = normalize_product_name_for_category(keyword)
            if not normalized_keyword:
                continue

            if (
                normalized_keyword in normalized_name
                or _compact(normalized_keyword) in compact_name
            ):
                matches.setdefault(category, []).append(keyword)

    return matches


def find_categories_from_product_name(product_name: object) -> set[str]:
    return set(_find_category_keyword_matches(product_name))


def find_category_mismatches(products: list[Product]) -> list[ValidationIssue]:
    issues = []

    for product in products:
        current_category = normalize_category(product.category)
        if not normalize_product_name_for_category(product.product_name):
            continue
        if not current_category:
            continue

        keyword_matches = _find_category_keyword_matches(product.product_name)
        inferred_categories = set(keyword_matches)
        if len(inferred_categories) != 1:
            continue

        inferred_category = next(iter(inferred_categories))
        if inferred_category == current_category:
            continue

        keyword = keyword_matches[inferred_category][0]
        issues.append(
            ValidationIssue(
                rule="product_category_mismatch",
                severity="warning",
                product_id=product.product_id,
                product_group_id=product.product_group_id,
                message=(
                    f"product_name keyword '{keyword}' implies category "
                    f"'{inferred_category}' but current category is "
                    f"'{current_category}'"
                ),
            )
        )

    return issues


def detect_category_mismatches(products: list[Product]) -> list[ValidationIssue]:
    return find_category_mismatches(products)
