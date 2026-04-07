from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from src.core.config import get_settings
from src.infrastructure.db.models import Base


def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        connect_args=_connect_args(settings.database_url),
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)


def init_database() -> None:
    Base.metadata.create_all(bind=get_engine())


def reset_database_cache() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
