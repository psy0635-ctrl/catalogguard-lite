# 역할: 패션 상품의 색상과 사이즈 표기를 권장 표준값과 비교하기 위한 기준을 제공합니다.
from collections.abc import Callable

from config.settings import FASHION_CATEGORY_ATTRIBUTE_RULES


COLOR_ALIASES = {
    "black": "BLACK",
    "블랙": "BLACK",
    "검정": "BLACK",
    "검정색": "BLACK",
    "white": "WHITE",
    "화이트": "WHITE",
    "흰색": "WHITE",
    "gray": "GRAY",
    "grey": "GRAY",
    "그레이": "GRAY",
    "회색": "GRAY",
    "navy": "NAVY",
    "네이비": "NAVY",
    "남색": "NAVY",
    "beige": "BEIGE",
    "베이지": "BEIGE",
    "brown": "BROWN",
    "브라운": "BROWN",
    "갈색": "BROWN",
    "red": "RED",
    "레드": "RED",
    "빨강": "RED",
    "빨간색": "RED",
    "blue": "BLUE",
    "블루": "BLUE",
    "파랑": "BLUE",
    "파란색": "BLUE",
    "green": "GREEN",
    "그린": "GREEN",
    "초록": "GREEN",
    "초록색": "GREEN",
    "yellow": "YELLOW",
    "옐로": "YELLOW",
    "옐로우": "YELLOW",
    "노랑": "YELLOW",
    "노란색": "YELLOW",
    "pink": "PINK",
    "핑크": "PINK",
    "purple": "PURPLE",
    "퍼플": "PURPLE",
    "보라": "PURPLE",
    "보라색": "PURPLE",
    "orange": "ORANGE",
    "오렌지": "ORANGE",
    "주황": "ORANGE",
    "주황색": "ORANGE",
    "khaki": "KHAKI",
    "카키": "KHAKI",
    "ivory": "IVORY",
    "아이보리": "IVORY",
    "cream": "CREAM",
    "크림": "CREAM",
}

SIZE_ALIASES = {
    "xxs": "XXS",
    "xs": "XS",
    "extra small": "XS",
    "x-small": "XS",
    "xsmall": "XS",
    "s": "S",
    "small": "S",
    "m": "M",
    "medium": "M",
    "l": "L",
    "large": "L",
    "xl": "XL",
    "extra large": "XL",
    "x-large": "XL",
    "xlarge": "XL",
    "xxl": "XXL",
    "2xl": "XXL",
    "xx-large": "XXL",
    "xxlarge": "XXL",
    "xxxl": "XXXL",
    "3xl": "XXXL",
    "xxx-large": "XXXL",
    "xxxlarge": "XXXL",
    "free": "FREE",
    "f": "FREE",
    "free size": "FREE",
    "freesize": "FREE",
    "one size": "FREE",
    "one-size": "FREE",
    "onesize": "FREE",
    "프리": "FREE",
    "프리사이즈": "FREE",
}


# 사이즈 체계 이름입니다. 문자형(ALPHA)과 숫자형(NUMERIC)만 구분합니다.
SIZE_SYSTEM_ALPHA = "ALPHA"
SIZE_SYSTEM_NUMERIC = "NUMERIC"

# FREE는 어느 체계에도 속하지 않으므로 문자형 표준 사이즈에서 제외합니다.
ALPHA_STANDARD_SIZES = frozenset(SIZE_ALIASES.values()) - {"FREE"}


# 필수 값 검사 필드 이름과 카테고리 정책 key를 연결합니다.
# 여기에 없는 필드는 카테고리와 무관하게 기존처럼 항상 필수입니다.
CATEGORY_ATTRIBUTE_POLICY_KEYS = {"size": "size_required"}


def is_field_required_for_category(category: object, field_name: str) -> bool:
    """카테고리별 정책에서 그 필드가 필수 값인지 알려 줍니다."""
    policy_key = CATEGORY_ATTRIBUTE_POLICY_KEYS.get(field_name)
    if policy_key is None:
        return True

    # canonical 카테고리와 정확히 일치할 때만 정책을 적용합니다.
    # 빈 값이나 허용 목록에 없는 값은 어떤 패션 카테고리인지 추정하지 않고 기존 정책을 유지합니다.
    category_rules = FASHION_CATEGORY_ATTRIBUTE_RULES.get(category)
    if category_rules is None:
        return True

    return bool(category_rules.get(policy_key, True))


def _find_standard_value(
    value: object,
    aliases: dict[str, str],
) -> str | None:
    if not isinstance(value, str):
        return None

    normalized_value = value.strip().casefold()
    if not normalized_value:
        return None

    return aliases.get(normalized_value)


def find_standard_color(value: object) -> str | None:
    return _find_standard_value(value, COLOR_ALIASES)


def find_standard_size(value: object) -> str | None:
    return _find_standard_value(value, SIZE_ALIASES)


def find_size_system(value: object) -> str | None:
    """사이즈 값이 문자형인지 숫자형인지 알려 주고, 판단할 수 없으면 None을 돌려줍니다."""
    if not isinstance(value, str):
        return None

    if find_standard_size(value) in ALPHA_STANDARD_SIZES:
        return SIZE_SYSTEM_ALPHA

    # 공백을 없앤 값이 아스키 숫자로만 되어 있을 때만 숫자형으로 봅니다.
    digits_only_value = "".join(value.split())
    if digits_only_value.isascii() and digits_only_value.isdigit():
        return SIZE_SYSTEM_NUMERIC

    return None


def _build_comparison_key(
    value: object,
    standard_value_finder: Callable[[object], str | None],
) -> str | None:
    """원본을 바꾸지 않고 표준값 또는 대소문자 무시 비교 키를 만듭니다."""
    if not isinstance(value, str):
        return None

    normalized_value = value.strip()
    if not normalized_value:
        return None

    standard_value = standard_value_finder(normalized_value)
    if standard_value is not None:
        return standard_value
    return normalized_value.casefold()


def build_color_comparison_key(value: object) -> str | None:
    return _build_comparison_key(value, find_standard_color)


def build_size_comparison_key(value: object) -> str | None:
    return _build_comparison_key(value, find_standard_size)
