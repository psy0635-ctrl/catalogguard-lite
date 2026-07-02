# 데이터 모양을 정하는 파일
from dataclasses import dataclass


@dataclass
class Product:
    """CSV 한 줄을 프로그램 안에서 다루기 쉽게 만든 상품 데이터입니다."""

    product_group_id: str
    product_id: str
    product_name: str
    category: str
    color: str
    size: str
    stock: int | None
    price: int | None
    image_path: str
    description: str = ""
    seller: str = ""


@dataclass
class ValidationIssue:
    """검수 규칙이 발견한 문제 한 건을 담는 데이터입니다."""

    rule: str
    severity: str  # "error" | "warning"
    product_id: str
    product_group_id: str
    message: str
