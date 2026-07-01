import pandas as pd

from config.settings import REQUIRED_COLUMNS
from core.models import Product


def load_products(csv_path) -> list[Product]:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    products = []
    for row in df.to_dict(orient="records"):
        stock_raw = row["stock"].strip()
        stock = int(stock_raw) if stock_raw.lstrip("-").isdigit() else None
        price_raw = row["price"].strip()
        price = int(price_raw) if price_raw.lstrip("-").isdigit() else None
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
