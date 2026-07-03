# 역할: 데이터베이스 URL 읽기, 엔진 생성, 세션 종료, 실제 연결을 테스트합니다.
import pytest
from sqlalchemy import text

from config.database import (
    DatabaseConfigurationError,
    get_database_url,
    get_optional_database_url,
)
import db.session as db_session
from db.session import (
    create_database_engine,
    create_session_factory,
)


def test_get_database_url_reads_environment(monkeypatch):
    # 실제 DB 접속 문자열은 DATABASE_URL 환경변수에서 읽습니다.
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:pass@localhost:5432/catalogguard_lite",
    )

    assert (
        get_database_url()
        == "postgresql+psycopg://user:pass@localhost:5432/catalogguard_lite"
    )


def test_get_database_url_raises_clear_error_when_missing(monkeypatch):
    # 필수 DB URL이 없을 때는 나중에 모호하게 실패하지 않고 즉시 알려 줍니다.
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(DatabaseConfigurationError, match="DATABASE_URL"):
        get_database_url()


def test_get_optional_database_url_returns_none_when_missing(monkeypatch):
    # 테스트 DB URL은 선택 사항이므로 없으면 None을 돌려 통합 테스트를 건너뜁니다.
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    assert get_optional_database_url() is None


def test_create_database_engine_is_lazy_and_uses_pool_pre_ping():
    # 엔진 생성 자체는 연결을 열지 않고, 오래된 연결 확인 옵션을 켭니다.
    engine = create_database_engine(
        "postgresql+psycopg://user:pass@localhost:5432/catalogguard_lite"
    )
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.pool._pre_ping is True
    finally:
        engine.dispose()


def test_create_session_factory_binds_to_engine_without_connecting():
    engine = create_database_engine(
        "postgresql+psycopg://user:pass@localhost:5432/catalogguard_lite"
    )
    try:
        session_factory = create_session_factory(engine)
        session = session_factory()
        try:
            assert session.bind is engine
        finally:
            session.close()
    finally:
        engine.dispose()


def test_get_session_closes_session(monkeypatch):
    # get_session()은 요청이 끝났을 때 세션 close()를 호출해야 합니다.
    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    fake_session = FakeSession()
    monkeypatch.setattr(
        db_session,
        "get_session_factory",
        lambda: lambda: fake_session,
    )

    session_generator = db_session.get_session()
    session = next(session_generator)

    assert session is fake_session
    with pytest.raises(StopIteration):
        next(session_generator)
    assert fake_session.closed is True


def test_postgresql_select_one_when_test_database_url_is_configured():
    # TEST_DATABASE_URL이 있는 환경에서는 실제 PostgreSQL 연결까지 확인합니다.
    test_database_url = get_optional_database_url()
    if test_database_url is None:
        pytest.skip("TEST_DATABASE_URL이 설정되지 않아 실제 PostgreSQL 연결 테스트를 건너뜁니다.")

    engine = create_database_engine(test_database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()
