# 역할: 패션 색상과 사이즈 별칭이 정확한 표준값으로만 변환되는지 테스트합니다.
import pytest

from core import fashion_attribute_validator
from core.fashion_attribute_validator import (
    SIZE_SYSTEM_ALPHA,
    SIZE_SYSTEM_NUMERIC,
    find_size_system,
    find_standard_color,
    find_standard_size,
    is_field_required_for_category,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("BLACK", "BLACK"),
        ("black", "BLACK"),
        ("Black", "BLACK"),
        ("블랙", "BLACK"),
        ("검정색", "BLACK"),
        ("grey", "GRAY"),
        (" 블랙 ", "BLACK"),
        ("MELANGE GRAY", None),
        ("DUSTY PINK", None),
        ("", None),
        ("   ", None),
        (None, None),
        (123, None),
    ],
)
def test_find_standard_color_returns_only_known_exact_aliases(value, expected):
    assert find_standard_color(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("M", "M"),
        ("m", "M"),
        ("medium", "M"),
        ("2XL", "XXL"),
        ("xx-large", "XXL"),
        ("프리사이즈", "FREE"),
        ("one size", "FREE"),
        ("95", None),
        ("", None),
        ("   ", None),
        (None, None),
        (95, None),
    ],
)
def test_find_standard_size_returns_only_known_exact_aliases(value, expected):
    assert find_standard_size(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("BLACK", "BLACK"),
        ("black", "BLACK"),
        (" 블랙 ", "BLACK"),
        ("MELANGE GRAY", "melange gray"),
        (" melange gray ", "melange gray"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_build_color_comparison_key_uses_standard_or_casefolded_value(
    value,
    expected,
):
    assert fashion_attribute_validator.build_color_comparison_key(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("M", "M"),
        ("medium", "M"),
        (" 2XL ", "XXL"),
        ("95", "95"),
        (" 95 ", "95"),
        ("custom size", "custom size"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_build_size_comparison_key_uses_standard_or_casefolded_value(
    value,
    expected,
):
    assert fashion_attribute_validator.build_size_comparison_key(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("M", SIZE_SYSTEM_ALPHA),
        ("m", SIZE_SYSTEM_ALPHA),
        ("medium", SIZE_SYSTEM_ALPHA),
        ("2XL", SIZE_SYSTEM_ALPHA),
        ("xx-large", SIZE_SYSTEM_ALPHA),
        (" L ", SIZE_SYSTEM_ALPHA),
        ("95", SIZE_SYSTEM_NUMERIC),
        ("100", SIZE_SYSTEM_NUMERIC),
        ("270", SIZE_SYSTEM_NUMERIC),
        ("30", SIZE_SYSTEM_NUMERIC),
        (" 95 ", SIZE_SYSTEM_NUMERIC),
        ("FREE", None),
        ("free", None),
        ("F", None),
        ("one size", None),
        ("프리", None),
        ("프리사이즈", None),
        ("", None),
        ("   ", None),
        (None, None),
        ("OS", None),
        ("1호", None),
        ("여성용", None),
        ("custom size", None),
        ("M-L", None),
        ("95-100", None),
        (95, None),
    ],
)
def test_find_size_system_classifies_only_alpha_and_numeric_sizes(value, expected):
    assert find_size_system(value) == expected


def test_find_size_system_ignores_non_ascii_digit_characters():
    # 전각 숫자나 위첨자는 숫자 사이즈 체계로 단정하지 않습니다.
    assert find_size_system("９５") is None
    assert find_size_system("²") is None


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("TOP", True),
        ("BOTTOM", True),
        ("OUTER", True),
        ("SHOES", True),
        ("BAG", False),
        # 정책 표에 없는 값은 카테고리를 추정하지 않고 기존처럼 필수로 봅니다.
        ("bag", True),
        (" BAG ", True),
        ("ACCESSORY", True),
        ("", True),
        (None, True),
    ],
)
def test_is_field_required_for_category_applies_size_policy(category, expected):
    assert is_field_required_for_category(category, "size") is expected


@pytest.mark.parametrize("field_name", ["color", "product_name", "image_path"])
def test_is_field_required_for_category_keeps_other_fields_always_required(field_name):
    # 정책이 없는 필드는 BAG에서도 기존 필수 값 정책을 그대로 따릅니다.
    assert is_field_required_for_category("BAG", field_name) is True
