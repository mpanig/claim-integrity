from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# Pool: 10 kept open + 20 overflow = 30 connections at most. The API never runs more request threads than
# that (see app.main: MAX_CONCURRENT_REQUESTS), so a burst of requests queues instead of timing out
# with "QueuePool limit ... reached".
POOL_SIZE, MAX_OVERFLOW = 10, 20
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=POOL_SIZE, max_overflow=MAX_OVERFLOW, pool_timeout=30)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """One session per request, always closed (and its connection returned) when the request ends."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
