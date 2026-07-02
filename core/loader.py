import pandas as pd

from config.settings import REQUIRED_COLUMNS
from core.models import Product


def parse_optional_int(value: str) -> int | None:
    """문자열을 정수로 변환하고, 변환할 수 없으면 None을 반환합니다."""
    cleaned_value = value.strip()

    if not cleaned_value:
        return None

    try:
        return int(cleaned_value)
    except ValueError:
        return None


def load_products(csv_path) -> list[Product]:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    if df.empty:
        raise ValueError(
            "CSV 파일에 상품 데이터가 없습니다. "
            "헤더 아래에 상품 정보를 한 줄 이상 입력해 주세요."
        )

    products = []
    for row in df.to_dict(orient="records"):
        stock = parse_optional_int(row["stock"])
        price = parse_optional_int(row["price"])
        products.append(
            Product(
                product_group_id=row["product_group_id"].strip(),
                product_id=row["product_id"].strip(),
                product_name=row["product_name"].strip(),
                category=row["category"].strip(),
                color=row["color"].strip(),
                size=row["size"].strip(),
                stock=stock,
                price=price,
                image_path=row["image_path"].strip(),
            )
        )
    return products
