from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
DEV_DATA_PATH = DATA_DIR / "dev" / "products_dev.csv"
TEST_DATA_PATH = DATA_DIR / "test"

REQUIRED_COLUMNS = [
    "product_group_id",
    "product_id",
    "product_name",
    "category",
    "color",
    "size",
    "stock",
    "image_path",
]

REQUIRED_FIELDS = [
    "product_name",
    "category",
    "color",
    "size",
    "image_path",
]

VALID_CATEGORIES = {"TOP", "BOTTOM", "OUTER"}
