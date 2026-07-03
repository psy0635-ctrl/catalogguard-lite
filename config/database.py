# 역할: 데이터베이스 연결 문자열을 환경변수에서 읽고 검증합니다.
import os


# 환경변수 이름을 상수로 두면 테스트와 실제 코드가 같은 이름을 공유할 수 있습니다.
DATABASE_URL_ENV_VAR = "DATABASE_URL"
TEST_DATABASE_URL_ENV_VAR = "TEST_DATABASE_URL"


class DatabaseConfigurationError(RuntimeError):
    """Database settings are missing or invalid."""


def get_database_url(env_var: str = DATABASE_URL_ENV_VAR) -> str:
    # 실제 DB 연결이 필요한 순간에만 환경변수를 읽고, 없으면 명확히 실패시킵니다.
    database_url = os.environ.get(env_var, "").strip()
    if not database_url:
        raise DatabaseConfigurationError(
            f"{env_var} 환경변수가 설정되지 않았습니다. "
            "PostgreSQL 연결이 필요한 명령에서만 이 값을 설정해 주세요."
        )
    return database_url


def get_optional_database_url(env_var: str = TEST_DATABASE_URL_ENV_VAR) -> str | None:
    # 통합 테스트처럼 DB가 선택 사항인 곳에서는 None으로 건너뛸 수 있게 합니다.
    database_url = os.environ.get(env_var, "").strip()
    return database_url or None
