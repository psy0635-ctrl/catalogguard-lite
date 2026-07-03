# CSV를 읽어서 상품 객체로 바꾸는 파일
import pandas as pd

from config.settings import REQUIRED_COLUMNS
from core.models import Product


def parse_optional_int(value: str) -> int | None:
    """문자열을 정수로 변환하고, 변환할 수 없으면 None을 반환합니다."""
    cleaned_value = value.strip()

    # 빈 값은 숫자가 없는 상태로 보고, 이후 규칙에서 오류 여부를 판단합니다.
    if not cleaned_value:
        return None

    try:
        return int(cleaned_value)
    except ValueError:
        return None


def clean_text(value: object) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def clean_optional_text(row: dict[str, object], field_name: str) -> str:
    # description, seller처럼 없어도 되는 컬럼은 없으면 빈 문자열로 채웁니다.
    return clean_text(row.get(field_name, ""))


def load_products(csv_path) -> list[Product]:
    # 모든 값을 문자열로 읽어야 공백, 잘못된 숫자도 검수 규칙에서 직접 판단할 수 있습니다.
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    return load_products_from_dataframe(df)


def load_products_from_dataframe(dataframe: pd.DataFrame) -> list[Product]:
    """검증된 DataFrame을 Product 목록으로 변환합니다."""
    df = dataframe.copy(deep=True)
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
        # stock과 price는 비어 있거나 잘못된 숫자일 수 있으므로 안전하게 파싱합니다.
        stock = parse_optional_int(clean_text(row["stock"]))
        price = parse_optional_int(clean_text(row["price"]))
        products.append(
            Product(
                product_group_id=clean_text(row["product_group_id"]),
                product_id=clean_text(row["product_id"]),
                product_name=clean_text(row["product_name"]),
                category=clean_text(row["category"]),
                color=clean_text(row["color"]),
                size=clean_text(row["size"]),
                stock=stock,
                price=price,
                image_path=clean_text(row["image_path"]),
                description=clean_optional_text(row, "description"),
                seller=clean_optional_text(row, "seller"),
            )
        )
    return products
