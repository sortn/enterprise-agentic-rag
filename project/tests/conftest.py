import sys
import os
from pathlib import Path
import uuid

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config import Settings


@pytest_asyncio.fixture
async def postgres_settings(tmp_path):
    database_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://enterprise_rag:enterprise_rag@127.0.0.1:5432/enterprise_rag",
    )
    schema = f"test_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(database_url)
    async with admin_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    await admin_engine.dispose()

    settings = Settings(
        database_url=database_url,
        database_schema=schema,
        auto_create_schema=True,
        auth_private_key_path=tmp_path / "keys" / "private.pem",
        auth_public_key_path=tmp_path / "keys" / "public.pem",
        auth_rsa_key_size=2048,
    )
    try:
        yield settings
    finally:
        cleanup_engine = create_async_engine(database_url)
        async with cleanup_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await cleanup_engine.dispose()
