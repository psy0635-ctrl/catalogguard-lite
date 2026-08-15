# 역할: CSV 컬럼, 허용 카테고리, 금칙어처럼 검수 전반에서 쓰는 설정값을 모읍니다.
import os
from pathlib import Path

# 프로젝트 기준 경로입니다. 다른 파일에서 샘플 CSV 위치를 만들 때 사용합니다.
BASE_DIR = Path(__file__).resolve().parent.parent

CATALOGGUARD_API_BASE_URL_ENV_VAR = "CATALOGGUARD_API_BASE_URL"
CATALOGGUARD_API_TIMEOUT_SECONDS_ENV_VAR = "CATALOGGUARD_API_TIMEOUT_SECONDS"
CATALOGGUARD_ETL_S3_BUCKET_ENV_VAR = "CATALOGGUARD_ETL_S3_BUCKET"
CATALOGGUARD_ETL_S3_PREFIX_ENV_VAR = "CATALOGGUARD_ETL_S3_PREFIX"
# 서버 운영자가 지정하는 신뢰 공급사 HTTP feed입니다. API 사용자는 URL을 선택할 수 없습니다.
CATALOGGUARD_ETL_HTTP_FEED_URL_ENV_VAR = "CATALOGGUARD_ETL_HTTP_FEED_URL"
CATALOGGUARD_ETL_HTTP_FEED_FILENAME_ENV_VAR = "CATALOGGUARD_ETL_HTTP_FEED_FILENAME"
CATALOGGUARD_API_DEFAULT_TIMEOUT_SECONDS = 5.0
CELERY_BROKER_URL_ENV_VAR = "CELERY_BROKER_URL"
REDIS_JOB_URL_ENV_VAR = "REDIS_JOB_URL"
INSPECTION_JOB_DIR_ENV_VAR = "INSPECTION_JOB_DIR"
INSPECTION_JOB_TTL_SECONDS_ENV_VAR = "INSPECTION_JOB_TTL_SECONDS"
DEFAULT_CELERY_BROKER_URL = "redis://localhost:6379/0"
DEFAULT_REDIS_JOB_URL = "redis://localhost:6379/1"
DEFAULT_INSPECTION_JOB_DIR = BASE_DIR / "var" / "inspection_jobs"
DEFAULT_INSPECTION_JOB_TTL_SECONDS = 24 * 60 * 60
# HTTP feed에서 받은 CSV를 기존 ETL에 넘길 때 사용할 안전한 기본 파일명입니다.
DEFAULT_ETL_HTTP_FEED_FILENAME = "supplier_feed.csv"

# ETL 배치를 "최초로" 만든 입력 경로입니다. dedup identity는
# (input_file_sha256, profile_name, profile_version)이므로 같은 bytes가 다른 경로로 다시 들어오면
# 기존 배치를 재사용합니다. 따라서 한 배치가 기록할 수 있는 것은 모든 유입 경로가 아니라
# 최초 경로 하나뿐이고, 그래서 이름이 initial_* 입니다.
ETL_INITIAL_SOURCE_TYPE_UNKNOWN = "unknown"
ETL_INITIAL_SOURCE_TYPES = (
    # migration 이전 row입니다. 과거 출처를 추측하지 않고 정직하게 unknown으로 둡니다.
    ETL_INITIAL_SOURCE_TYPE_UNKNOWN,
    "upload",
    "s3",
    "http_feed",
    "cli",
)
ETL_INITIAL_SOURCE_TYPE_MAX_LENGTH = 20
ETL_INITIAL_SOURCE_REF_MAX_LENGTH = 255
# HTTP feed는 URL 원문에 token/credential이 들어갈 수 있으므로 저장하지 않고,
# 비밀이 없는 고정 식별자만 남깁니다.
ETL_HTTP_FEED_SOURCE_REF = "configured_http_feed"

# JWT access token 서명 키입니다. 서버 설정으로 고정하며 요청에서 선택할 수 없습니다.
CATALOGGUARD_JWT_SECRET_ENV_VAR = "CATALOGGUARD_JWT_SECRET"
CATALOGGUARD_JWT_ALGORITHM = "HS256"
CATALOGGUARD_JWT_ACCESS_TOKEN_TTL_SECONDS_ENV_VAR = (
    "CATALOGGUARD_JWT_ACCESS_TOKEN_TTL_SECONDS"
)
DEFAULT_JWT_ACCESS_TOKEN_TTL_SECONDS = 60 * 60
# 검수 규칙 버전입니다. 규칙이 바뀌어 같은 CSV도 다시 저장해야 하면 이 값을 올립니다.
INSPECTION_VERSION = "11"

DATA_DIR = BASE_DIR / "data"
DEV_DATA_PATH = DATA_DIR / "dev" / "products_dev.csv"
TEST_DATA_PATH = DATA_DIR / "test"

MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 10_000
SUPPORTED_CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp949")

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

OPTIONAL_COLUMNS = [
    "sale_price",
    "description",
    "seller",
]

CSV_TEMPLATE_COLUMNS = [*REQUIRED_COLUMNS, *OPTIONAL_COLUMNS]

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

VALID_CATEGORIES = {"TOP", "BOTTOM", "OUTER", "SHOES", "BAG"}

# 카테고리마다 다른 필수 패션 속성 정책입니다. 정책의 기준은 이 표 하나뿐입니다.
# key는 VALID_CATEGORIES의 canonical 표기와 정확히 같아야 합니다.
# 여기에 없는 카테고리(빈 값, 허용 목록에 없는 값 포함)는 카테고리를 추정하지 않고
# REQUIRED_FIELDS 기본 정책을 그대로 적용합니다.
FASHION_CATEGORY_ATTRIBUTE_RULES = {
    "TOP": {"size_required": True},
    "BOTTOM": {"size_required": True},
    "OUTER": {"size_required": True},
    "SHOES": {"size_required": True},
    # 가방은 의류 사이즈 체계가 없는 단일 사이즈 상품이 많아 size를 선택 값으로 둡니다.
    "BAG": {"size_required": False},
}

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


def get_catalogguard_api_base_url() -> str | None:
    api_base_url = os.environ.get(CATALOGGUARD_API_BASE_URL_ENV_VAR, "").strip()
    if not api_base_url:
        return None

    normalized_url = api_base_url.rstrip("/")
    return normalized_url or None


def get_catalogguard_etl_s3_bucket() -> str | None:
    value = os.environ.get(CATALOGGUARD_ETL_S3_BUCKET_ENV_VAR, "").strip()
    return value or None


def get_catalogguard_etl_s3_prefix() -> str | None:
    value = os.environ.get(CATALOGGUARD_ETL_S3_PREFIX_ENV_VAR, "").strip().strip("/")
    return f"{value}/" if value else None


def get_catalogguard_etl_http_feed_url() -> str | None:
    value = os.environ.get(CATALOGGUARD_ETL_HTTP_FEED_URL_ENV_VAR, "").strip()
    return value or None


def get_catalogguard_etl_http_feed_filename() -> str:
    # 파일명을 응답 헤더에서 추출하지 않고 서버 설정으로만 정합니다.
    value = os.environ.get(CATALOGGUARD_ETL_HTTP_FEED_FILENAME_ENV_VAR, "").strip()
    return value or DEFAULT_ETL_HTTP_FEED_FILENAME


def get_catalogguard_api_timeout_seconds() -> float:
    timeout_text = os.environ.get(CATALOGGUARD_API_TIMEOUT_SECONDS_ENV_VAR, "").strip()
    if not timeout_text:
        return CATALOGGUARD_API_DEFAULT_TIMEOUT_SECONDS

    try:
        timeout_seconds = float(timeout_text)
    except ValueError:
        return CATALOGGUARD_API_DEFAULT_TIMEOUT_SECONDS

    if timeout_seconds <= 0:
        return CATALOGGUARD_API_DEFAULT_TIMEOUT_SECONDS
    return timeout_seconds


def _get_non_empty_environment_value(
    environment_name: str,
    default_value: str,
) -> str:
    value = os.environ.get(environment_name, "").strip()
    return value or default_value


def get_celery_broker_url() -> str:
    return _get_non_empty_environment_value(
        CELERY_BROKER_URL_ENV_VAR,
        DEFAULT_CELERY_BROKER_URL,
    )


def get_redis_job_url() -> str:
    return _get_non_empty_environment_value(
        REDIS_JOB_URL_ENV_VAR,
        DEFAULT_REDIS_JOB_URL,
    )


def get_inspection_job_dir() -> Path:
    configured_directory = os.environ.get(INSPECTION_JOB_DIR_ENV_VAR, "").strip()
    return Path(configured_directory) if configured_directory else DEFAULT_INSPECTION_JOB_DIR


def get_inspection_job_ttl_seconds() -> int:
    value = os.environ.get(INSPECTION_JOB_TTL_SECONDS_ENV_VAR, "").strip()
    if not value:
        return DEFAULT_INSPECTION_JOB_TTL_SECONDS

    try:
        ttl_seconds = int(value)
    except ValueError:
        return DEFAULT_INSPECTION_JOB_TTL_SECONDS

    return ttl_seconds if ttl_seconds > 0 else DEFAULT_INSPECTION_JOB_TTL_SECONDS


class JWTConfigurationError(RuntimeError):
    """Raised when CATALOGGUARD_JWT_SECRET is missing where a token must be signed or verified."""


def get_jwt_secret() -> str:
    # 로그인/토큰 검증이 실제로 필요한 순간에만 읽습니다.
    # /health, CLI ETL, migration 명령은 이 값을 요구하지 않습니다.
    secret = os.environ.get(CATALOGGUARD_JWT_SECRET_ENV_VAR, "").strip()
    if not secret:
        raise JWTConfigurationError(
            f"{CATALOGGUARD_JWT_SECRET_ENV_VAR} 환경변수가 설정되지 않았습니다. "
            "로그인/토큰 검증이 필요한 명령에서만 이 값을 설정해 주세요."
        )
    return secret


def get_jwt_access_token_ttl_seconds() -> int:
    value = os.environ.get(
        CATALOGGUARD_JWT_ACCESS_TOKEN_TTL_SECONDS_ENV_VAR, ""
    ).strip()
    if not value:
        return DEFAULT_JWT_ACCESS_TOKEN_TTL_SECONDS

    try:
        ttl_seconds = int(value)
    except ValueError:
        return DEFAULT_JWT_ACCESS_TOKEN_TTL_SECONDS

    return ttl_seconds if ttl_seconds > 0 else DEFAULT_JWT_ACCESS_TOKEN_TTL_SECONDS
