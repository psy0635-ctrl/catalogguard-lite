# 역할: 패션 색상과 사이즈 별칭이 정확한 표준값으로만 변환되는지 테스트합니다.
import pytest

from core.fashion_attribute_validator import find_standard_color, find_standard_size


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
