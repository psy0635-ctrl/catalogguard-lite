# 역할: 패션 색상과 사이즈 별칭이 정확한 표준값으로만 변환되는지 테스트합니다.
import pytest

from core import fashion_attribute_validator
from core.fashion_attribute_validator import (
    COLOR_ALIASES,
    SIZE_ALIASES,
    SIZE_SYSTEM_ALPHA,
    SIZE_SYSTEM_NUMERIC,
    build_alias_lookup_key,
    build_alias_lookup_table,
    build_color_comparison_key,
    build_size_comparison_key,
    build_variant_size_comparison_key,
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


@pytest.mark.parametrize(
    ("category", "size"),
    [
        ("BAG", "FREE"),
        ("BAG", "free size"),
        ("BAG", "M"),
        ("BAG", " 95 "),
        ("TOP", "medium"),
        ("ACCESSORY", "MELANGE"),
    ],
)
def test_build_variant_size_comparison_key_keeps_existing_key_for_filled_sizes(category, size):
    # 값이 있는 사이즈는 카테고리와 무관하게 기존 비교 키를 그대로 사용합니다.
    assert build_variant_size_comparison_key(category, size) == build_size_comparison_key(size)


@pytest.mark.parametrize("size", ["", " ", "   "])
def test_build_variant_size_comparison_key_accepts_blank_size_for_optional_category(size):
    # size가 선택 값인 canonical 카테고리는 빈 사이즈 자체를 정상 비교값으로 사용합니다.
    assert build_variant_size_comparison_key("BAG", size) == ""


def test_build_variant_size_comparison_key_keeps_blank_size_different_from_free():
    assert build_variant_size_comparison_key("BAG", "") != build_variant_size_comparison_key(
        "BAG", "FREE"
    )


@pytest.mark.parametrize("category", ["TOP", "BOTTOM", "OUTER", "SHOES"])
def test_build_variant_size_comparison_key_rejects_blank_size_for_required_category(category):
    assert build_variant_size_comparison_key(category, "") is None


@pytest.mark.parametrize("category", ["ACCESSORY", "bag", " BAG ", "", None])
def test_build_variant_size_comparison_key_rejects_blank_size_for_non_canonical_category(category):
    # 허용 목록에 없거나 canonical이 아닌 카테고리는 BAG로 추정하지 않습니다.
    assert build_variant_size_comparison_key(category, "") is None


@pytest.mark.parametrize("size", [None, 95])
def test_build_variant_size_comparison_key_rejects_non_string_size(size):
    assert build_variant_size_comparison_key("BAG", size) is None


# 아래는 의미 비교에서 내부 연속 공백을 의미 차이로 보지 않는지 확인합니다.
# 완전 중복 규칙의 엄격 비교 정책은 그대로 두고, 별칭 비교만 공백에 견디게 합니다.
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("free size", "FREE"),
        ("free  size", "FREE"),
        (" free   size ", "FREE"),
        ("free\tsize", "FREE"),
        ("free\nsize", "FREE"),
        ("FREE  SIZE", "FREE"),
        ("one size", "FREE"),
        ("one  size", "FREE"),
        ("extra large", "XL"),
        ("extra  large", "XL"),
        ("extra small", "XS"),
        ("extra\tsmall", "XS"),
    ],
)
def test_find_standard_size_ignores_internal_whitespace_differences(value, expected):
    assert find_standard_size(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("free  size", "FREE"),
        (" free   size ", "FREE"),
        ("free\tsize", "FREE"),
        ("one  size", "FREE"),
        ("extra  large", "XL"),
    ],
)
def test_build_size_comparison_key_ignores_internal_whitespace_differences(value, expected):
    assert build_size_comparison_key(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # 별칭 사전에 없는 사용자 정의 값도 같은 기준으로 공백만 정리합니다.
        ("MELANGE GRAY", "melange gray"),
        ("melange  gray", "melange gray"),
        ("dark\tblue", "dark blue"),
    ],
)
def test_build_color_comparison_key_ignores_internal_whitespace_differences(value, expected):
    assert build_color_comparison_key(value) == expected


@pytest.mark.parametrize(
    "value",
    ["OS", "ONE", "UNI", "ONESIZE123", "one size fits all", "one  size  fits  all", "1호"],
)
def test_find_standard_size_does_not_invent_new_aliases(value):
    # 공백만 정리할 뿐 별칭 사전에 없는 표현을 새로 표준화하지는 않습니다.
    assert find_standard_size(value) is None


@pytest.mark.parametrize("value", ["", " ", "   ", "\t", "\n", "  \t \n "])
def test_comparison_keys_still_treat_whitespace_only_values_as_blank(value):
    # 공백만 있는 값은 기존처럼 비교 불가로 두어야 "" != "FREE" 정책이 유지됩니다.
    assert find_standard_size(value) is None
    assert build_size_comparison_key(value) is None
    assert build_color_comparison_key(value) is None
    assert build_variant_size_comparison_key("BAG", value) == ""
    assert build_variant_size_comparison_key("BAG", value) != build_variant_size_comparison_key(
        "BAG", "FREE"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [("extra large", SIZE_SYSTEM_ALPHA), ("extra  large", SIZE_SYSTEM_ALPHA)],
)
def test_find_size_system_classifies_whitespace_variants_of_alpha_aliases(value, expected):
    assert find_size_system(value) == expected


# 아래는 별칭 조회에서만 구분자 표기 차이를 무시하는 정책을 확인합니다.
# 사전 안에서는 관대하게, 사전 밖에서는 보수적으로 비교하는 것이 기준입니다.
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("free-size", "FREE"),
        ("free_size", "FREE"),
        ("FREE_SIZE", "FREE"),
        ("one_size", "FREE"),
        ("one - size", "FREE"),
        ("extra-large", "XL"),
        ("extra_large", "XL"),
        ("x_large", "XL"),
        ("extra-small", "XS"),
        ("extra_small", "XS"),
        ("x_small", "XS"),
        ("xx_large", "XXL"),
        ("xxx_large", "XXXL"),
    ],
)
def test_find_standard_size_ignores_separator_differences_inside_registered_aliases(
    value,
    expected,
):
    assert find_standard_size(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("free-size", "FREE"),
        ("free_size", "FREE"),
        ("extra_large", "XL"),
        ("xx_large", "XXL"),
    ],
)
def test_build_size_comparison_key_ignores_separator_differences(value, expected):
    assert build_size_comparison_key(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Policy A처럼 구분자를 공백으로 바꾸면 아래 별칭들이 깨지므로 기존 결과를 고정합니다.
        ("x-large", "XL"),
        ("x-small", "XS"),
        ("xx-large", "XXL"),
        ("xxx-large", "XXXL"),
        ("one-size", "FREE"),
        ("medium", "M"),
        ("2XL", "XXL"),
        ("free size", "FREE"),
        ("free  size", "FREE"),
        ("free\tsize", "FREE"),
        ("extra  large", "XL"),
        ("프리사이즈", "FREE"),
    ],
)
def test_find_standard_size_keeps_existing_alias_results(value, expected):
    assert find_standard_size(value) == expected


@pytest.mark.parametrize("value", ["free/size", "FREE.SIZE", "S/M", "36/38", "10.5"])
def test_find_standard_size_keeps_slash_and_dot_as_meaningful(value):
    # '/'와 '.'는 BLACK/WHITE, 10.5처럼 값 자체의 의미일 수 있어 제거하지 않습니다.
    assert find_standard_size(value) is None


@pytest.mark.parametrize("value", ["S-M", "M-L", "36-38", "95-100", "270-280", "S_M"])
def test_find_standard_size_does_not_canonicalize_meaningful_hyphen_values(value):
    # 구분자를 무시해도 사전에 없는 표현이면 표준값으로 만들지 않습니다.
    assert find_standard_size(value) is None


@pytest.mark.parametrize(
    "value",
    ["OS", "ONE", "UNI", "ONESIZE123", "one size fits all", "one-size-fits-all", "1호"],
)
def test_find_standard_size_does_not_invent_aliases_from_separators(value):
    assert find_standard_size(value) is None


@pytest.mark.parametrize("value", ["-", "_", "_-", " - _ ", "--__", "\t-\n_"])
def test_separator_only_values_are_not_matched_to_any_alias(value):
    # 구분자만 남은 값은 조회 키가 비어 표준값을 찾지 않아야 합니다.
    assert build_alias_lookup_key(value) == ""
    assert find_standard_size(value) is None
    assert find_standard_color(value) is None
    assert build_variant_size_comparison_key("BAG", value) != build_variant_size_comparison_key(
        "BAG", "FREE"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("free size", "freesize"),
        ("free-size", "freesize"),
        ("free_size", "freesize"),
        ("free  size", "freesize"),
        ("free\tsize", "freesize"),
        ("FREE SIZE", "freesize"),
        ("free/size", "free/size"),
        ("FREE.SIZE", "free.size"),
    ],
)
def test_build_alias_lookup_key_removes_only_ignored_separators(value, expected):
    assert build_alias_lookup_key(value) == expected


@pytest.mark.parametrize(
    ("aliases", "label"),
    [(SIZE_ALIASES, "size"), (COLOR_ALIASES, "color")],
)
def test_alias_tables_have_no_lookup_key_collisions(aliases, label):
    # 구분자 제거 정책 때문에 앞으로 별칭을 추가할 때
    # 서로 다른 표준값이 같은 조회 키로 합쳐지는 회귀를 막습니다.
    canonical_values_by_key: dict[str, set[str]] = {}
    for alias, standard_value in aliases.items():
        canonical_values_by_key.setdefault(build_alias_lookup_key(alias), set()).add(
            standard_value
        )

    collisions = {
        key: values for key, values in canonical_values_by_key.items() if len(values) > 1
    }
    assert collisions == {}, f"{label} alias lookup key collision: {collisions}"


def test_build_alias_lookup_table_rejects_conflicting_standard_values():
    with pytest.raises(ValueError, match="alias lookup key"):
        build_alias_lookup_table({"one size": "FREE", "one-size": "XL"})


def test_build_alias_lookup_table_allows_same_standard_value_for_separator_variants():
    table = build_alias_lookup_table({"one size": "FREE", "one-size": "FREE"})

    assert table == {"onesize": "FREE"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [("extra-large", SIZE_SYSTEM_ALPHA), ("extra_large", SIZE_SYSTEM_ALPHA), ("M-L", None)],
)
def test_find_size_system_follows_separator_policy(value, expected):
    assert find_size_system(value) == expected


@pytest.mark.parametrize("value", ["BLACK", "black", "블랙", "검정", " BLACK ", "grey"])
def test_find_standard_color_keeps_existing_alias_results(value):
    # COLOR_ALIASES에는 구분자를 포함한 별칭이 없어 기존 결과가 그대로 유지되어야 합니다.
    assert find_standard_color(value) == COLOR_ALIASES[value.strip().casefold()]


@pytest.mark.parametrize(
    "value",
    ["MELANGE-GRAY", "MELANGE GRAY", "MELANGE_GRAY", "BLUE-GRAY", "BLUE GRAY", "BLUE_GRAY"],
)
def test_custom_color_values_keep_separators_in_comparison_key(value):
    # 사전 밖 사용자 정의 색상은 구분자를 그대로 두어 임의로 같은 값이 되지 않게 합니다.
    assert find_standard_color(value) is None
    assert build_color_comparison_key(value) == " ".join(value.split()).casefold()


def test_custom_color_separator_variants_stay_different():
    assert build_color_comparison_key("BLUE-GRAY") != build_color_comparison_key("BLUE GRAY")
    assert build_color_comparison_key("BLUE_GRAY") != build_color_comparison_key("BLUE GRAY")
