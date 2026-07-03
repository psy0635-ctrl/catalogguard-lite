# 프로젝트의 규칙 설정 파일
from pathlib import Path

# 프로젝트 기준 경로입니다. 다른 파일에서 샘플 CSV 위치를 만들 때 사용합니다.
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
DEV_DATA_PATH = DATA_DIR / "dev" / "products_dev.csv"
TEST_DATA_PATH = DATA_DIR / "test"

# CSV에 반드시 있어야 하는 컬럼 목록입니다.
REQUIRED_COLUMNS = [
    "product_group_id",
    "product_id",
    "product_name",
    "category",
    "color",
    "size",
    "stock",
    "price",
    "image_path",
]

# 값이 비어 있으면 오류로 볼 필드입니다. stock, price는 전용 숫자 규칙에서 따로 봅니다.
REQUIRED_FIELDS = [
    "product_group_id",
    "product_id",
    "product_name",
    "category",
    "color",
    "size",
    "image_path",
]

VALID_CATEGORIES = {"TOP", "BOTTOM", "OUTER"}

CATEGORY_KEYWORDS = {
    "상의": (
        "티셔츠",
        "반팔티",
        "긴팔티",
        "셔츠",
        "블라우스",
        "후드티",
        "맨투맨",
        "니트",
        "스웨터",
    ),
    "하의": (
        "청바지",
        "데님팬츠",
        "바지",
        "팬츠",
        "슬랙스",
        "스커트",
        "치마",
        "레깅스",
        "반바지",
        "쇼츠",
    ),
    "아우터": (
        "후드집업",
        "집업",
        "자켓",
        "재킷",
        "코트",
        "점퍼",
        "패딩",
    ),
    "신발": (
        "운동화",
        "스니커즈",
        "러닝화",
        "구두",
        "로퍼",
        "부츠",
        "샌들",
        "슬리퍼",
    ),
    "가방": (
        "백팩",
        "크로스백",
        "숄더백",
        "토트백",
        "클러치백",
        "에코백",
        "파우치",
    ),
}

CATEGORY_ALIASES = {
    "top": "상의",
    "tops": "상의",
    "bottom": "하의",
    "bottoms": "하의",
    "outer": "아우터",
    "outers": "아우터",
    "shoe": "신발",
    "shoes": "신발",
    "bag": "가방",
    "bags": "가방",
}

# 금지어와 개인정보 형태를 검사할 텍스트 필드입니다.
CONTENT_SCAN_FIELDS = (
    "product_name",
    "description",
    "seller",
)

# MVP용 예시 금지어입니다. 실제 서비스에서는 운영 정책에 맞게 바꿔야 합니다.
PROHIBITED_TERMS = (
    "카카오톡",
    "카톡",
    "텔레그램",
    "외부결제",
    "외부 결제",
    "직거래",
    "현금거래",
)

# 계좌번호 의심은 숫자만으로 판단하지 않고, 아래 문맥어가 함께 있을 때만 봅니다.
BANK_ACCOUNT_CONTEXT_TERMS = (
    "계좌",
    "입금",
    "송금",
    "은행",
    "예금주",
)
