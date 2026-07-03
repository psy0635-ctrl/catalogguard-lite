# 역할: SQLAlchemy 엔진과 세션 팩토리를 생성하고 요청 후 세션을 닫습니다.
from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.database import get_database_url


# 앱에서 기본으로 사용할 엔진과 세션 팩토리는 필요해지는 순간에만 만듭니다.
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def create_database_engine(database_url: str | None = None) -> Engine:
    # pool_pre_ping=True는 오래된 DB 연결을 쓰기 전에 살아 있는지 확인하게 해 줍니다.
    return create_engine(
        database_url or get_database_url(),
        pool_pre_ping=True,
    )


def create_session_factory(
    engine: Engine | None = None,
    database_url: str | None = None,
) -> sessionmaker[Session]:
    # commit/rollback은 호출하는 Service가 결정하도록 자동 커밋을 끕니다.
    return sessionmaker(
        bind=engine or create_database_engine(database_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_engine() -> Engine:
    global _engine

    # DATABASE_URL이 필요한 시점까지 import만으로는 DB 설정을 읽지 않습니다.
    if _engine is None:
        _engine = create_database_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory

    # 같은 프로세스 안에서는 세션 팩토리를 재사용합니다.
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        # FastAPI 의존성으로 사용할 때 요청이 끝나면 세션을 반드시 닫습니다.
        session.close()
