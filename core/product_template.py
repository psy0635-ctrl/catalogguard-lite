# 역할: 사용자가 내려받을 수 있는 상품 입력 CSV 템플릿을 생성합니다.
import pandas as pd

from config.settings import CSV_TEMPLATE_COLUMNS
from core.models import Product


PRODUCT_TEMPLATE_FILENAME = "catalogguard_product_template.csv"

EXAMPLE_TEMPLATE_PRODUCT = Product(
    product_group_id="G001",
    product_id="P001",
    product_name="오버핏 반팔 티셔츠",
    category="TOP",
    color="BLACK",
    size="M",
    stock=10,
    price=19900,
    image_path="data/images/sample_product.jpg",
    description="템플릿 작성용 가짜 예시 상품입니다.",
    seller="SAMPLE_SELLER",
)


def build_product_template_dataframe() -> pd.DataFrame:
    """현재 CSV 구조에 맞는 예시 상품 템플릿 DataFrame을 만듭니다."""
    row = {
        column: getattr(EXAMPLE_TEMPLATE_PRODUCT, column)
        for column in CSV_TEMPLATE_COLUMNS
    }
    return pd.DataFrame([row], columns=CSV_TEMPLATE_COLUMNS)


def build_product_template_csv() -> bytes:
    """상품 입력 템플릿을 UTF-8 BOM CSV bytes로 만듭니다."""
    csv_text = build_product_template_dataframe().to_csv(index=False)
    return csv_text.encode("utf-8-sig")


def get_product_template_filename() -> str:
    """템플릿 다운로드 파일명을 반환합니다."""
    return PRODUCT_TEMPLATE_FILENAME
