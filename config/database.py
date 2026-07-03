import os


DATABASE_URL_ENV_VAR = "DATABASE_URL"
TEST_DATABASE_URL_ENV_VAR = "TEST_DATABASE_URL"


class DatabaseConfigurationError(RuntimeError):
    """Database settings are missing or invalid."""


def get_database_url(env_var: str = DATABASE_URL_ENV_VAR) -> str:
    database_url = os.environ.get(env_var, "").strip()
    if not database_url:
        raise DatabaseConfigurationError(
            f"{env_var} 환경변수가 설정되지 않았습니다. "
            "PostgreSQL 연결이 필요한 명령에서만 이 값을 설정해 주세요."
        )
    return database_url


def get_optional_database_url(env_var: str = TEST_DATABASE_URL_ENV_VAR) -> str | None:
    database_url = os.environ.get(env_var, "").strip()
    return database_url or None
