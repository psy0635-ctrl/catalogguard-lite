from dataclasses import dataclass


@dataclass
class Product:
    product_group_id: str
    product_id: str
    product_name: str
    category: str
    color: str
    size: str
    stock: int
    image_path: str


@dataclass
class ValidationIssue:
    rule: str
    severity: str  # "error" | "warning"
    product_id: str
    product_group_id: str
    message: str
