from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.database import get_database_url


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def create_database_engine(database_url: str | None = None) -> Engine:
    return create_engine(
        database_url or get_database_url(),
        pool_pre_ping=True,
    )


def create_session_factory(
    engine: Engine | None = None,
    database_url: str | None = None,
) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine or create_database_engine(database_url),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_engine() -> Engine:
    global _engine

    if _engine is None:
        _engine = create_database_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory

    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
