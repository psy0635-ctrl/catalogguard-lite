# 역할: 패션 색상과 사이즈 별칭이 정확한 표준값으로만 변환되는지 테스트합니다.
import pytest

from core import fashion_attribute_validator
from core.fashion_attribute_validator import (
    SIZE_SYSTEM_ALPHA,
    SIZE_SYSTEM_NUMERIC,
    find_size_system,
    find_standard_color,
    find_standard_size,
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
