# 역할: 상품 그룹 안에서 문자형·숫자형 사이즈 체계가 섞였는지 판단하는 규칙을 검증합니다.
from dataclasses import asdict

from core.group_size_consistency_detector import (
    GROUP_SIZE_SYSTEM_MESSAGE,
    find_inconsistent_group_size_systems,
)
from core.models import Product


def make_product(**overrides) -> Product:
    defaults = {
        "product_group_id": "G001",
        "product_id": "P001",
        "product_name": "테스트 상품",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 5,
        "price": 10000,
        "image_path": "image.jpg",
    }
    defaults.update(overrides)
    return Product(**defaults)


def make_group(sizes: list[str], product_group_id: str = "G001") -> list[Product]:
    return [
        make_product(
            product_group_id=product_group_id,
            product_id=f"P{index:03d}",
            size=size,
        )
        for index, size in enumerate(sizes, start=1)
    ]


def test_find_inconsistent_group_size_systems_allows_alpha_only_group():
    products = make_group(["S", "M", "L", "XL"])

    assert find_inconsistent_group_size_systems(products) == []


def test_find_inconsistent_group_size_systems_allows_numeric_only_group():
    products = make_group(["95", "100", "105"])

    assert find_inconsistent_group_size_systems(products) == []


def test_find_inconsistent_group_size_systems_flags_mixed_alpha_and_numeric():
    products = make_group(["M", "L", "100"])

    issues = find_inconsistent_group_size_systems(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002", "P003"]
    assert all(issue.rule == "inconsistent_group_size_system" for issue in issues)
    assert all(issue.severity == "warning" for issue in issues)
    assert all(issue.product_group_id == "G001" for issue in issues)
    assert all(issue.message == GROUP_SIZE_SYSTEM_MESSAGE for issue in issues)


def test_find_inconsistent_group_size_systems_recognizes_alias_as_alpha():
    products = make_group(["medium", "L", "100"])

    issues = find_inconsistent_group_size_systems(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002", "P003"]


def test_find_inconsistent_group_size_systems_ignores_free_size():
    products = make_group(["M", "L", "FREE"])

    assert find_inconsistent_group_size_systems(products) == []


def test_find_inconsistent_group_size_systems_ignores_custom_size():
    products = make_group(["M", "L", "custom size"])

    assert find_inconsistent_group_size_systems(products) == []


def test_find_inconsistent_group_size_systems_ignores_blank_size():
    products = make_group(["M", "L", ""])

    assert find_inconsistent_group_size_systems(products) == []


def test_find_inconsistent_group_size_systems_ignores_different_groups():
    products = [
        *make_group(["M", "L"], product_group_id="G001"),
        *make_group(["95", "100"], product_group_id="G002"),
    ]

    assert find_inconsistent_group_size_systems(products) == []


def test_find_inconsistent_group_size_systems_flags_only_classified_products():
    products = [
        make_product(product_id="P001", size="M"),
        make_product(product_id="P002", size="100"),
        make_product(product_id="P003", size="FREE"),
        make_product(product_id="P004", size="custom size"),
    ]

    issues = find_inconsistent_group_size_systems(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002"]


def test_find_inconsistent_group_size_systems_ignores_blank_group_id():
    products = [
        make_product(product_group_id="", product_id="P001", size="M"),
        make_product(product_group_id="   ", product_id="P002", size="100"),
    ]

    assert find_inconsistent_group_size_systems(products) == []


def test_find_inconsistent_group_size_systems_keeps_global_input_order():
    products = [
        make_product(product_group_id="G001", product_id="P001", size="M"),
        make_product(product_group_id="G002", product_id="P002", size="L"),
        make_product(product_group_id="G001", product_id="P003", size="100"),
        make_product(product_group_id="G002", product_id="P004", size="105"),
    ]

    issues = find_inconsistent_group_size_systems(products)

    assert [issue.product_id for issue in issues] == ["P001", "P002", "P003", "P004"]


def test_find_inconsistent_group_size_systems_does_not_modify_products_or_order():
    products = make_group(["M", " 100 "])
    before_products = [asdict(product) for product in products]
    before_identities = [id(product) for product in products]

    find_inconsistent_group_size_systems(products)

    assert [asdict(product) for product in products] == before_products
    assert [id(product) for product in products] == before_identities
