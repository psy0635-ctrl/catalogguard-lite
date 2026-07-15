# 역할: 패션 상품의 색상과 사이즈 표기를 권장 표준값과 비교하기 위한 기준을 제공합니다.


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
