"""Async engine and session factory (SQLAlchemy 2, psycopg 3)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create the async engine. Every connection runs in UTC."""
    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args={"options": "-c TimeZone=UTC"},
    )


def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
