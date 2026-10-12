from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import Settings
from .base import Base


class DatabaseManager:
    """Owns the async engine and provides request-scoped SQLAlchemy sessions."""

    def __init__(self, settings: Settings) -> None:
        engine_kwargs: dict[str, object] = {
            "echo": settings.database_echo,
            "pool_pre_ping": True,
            "pool_size": settings.database_pool_size,
            "max_overflow": settings.database_max_overflow,
        }
        if settings.database_schema:
            engine_kwargs["connect_args"] = {
                "server_settings": {
                    "search_path": settings.database_schema
                }
            }
        self.engine: AsyncEngine = create_async_engine(settings.database_url, **engine_kwargs)
        self.sessions = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self.auto_create_schema = settings.auto_create_schema

    async def initialize(self) -> None:
        # Production and Docker use Alembic. AUTO_CREATE_SCHEMA is useful for
        # isolated development and integration-test databases only.
        if self.auto_create_schema:
            async with self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

    async def ping(self) -> bool:
        async with self.sessions() as session:
            return (await session.execute(text("SELECT 1"))).scalar_one() == 1

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
