from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from src.infrastructure.db.base import get_session_factory


def get_db_session() -> Generator[Session, None, None]:
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_request_actor(request: Request):
    return getattr(request.state, "actor", None)
