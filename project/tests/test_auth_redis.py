from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

import pytest

from auth.errors import AuthDependencyError
from auth.models import RefreshTokenRecord
from auth.repository import AsyncRedisRefreshTokenRepository


@pytest.mark.asyncio
async def test_real_redis_refresh_token_ttl_and_atomic_consumption():
    prefix = f"refresh_token:test-{uuid.uuid4().hex}:"
    repository = AsyncRedisRefreshTokenRepository(
        "redis://127.0.0.1:6379/15",
        key_prefix=prefix,
    )
    try:
        await repository.ping()
    except AuthDependencyError:
        pytest.skip("local Redis integration service is not running")

    token = "integration-token"
    now = datetime.now(UTC)
    record = RefreshTokenRecord(
        user_id="user-1",
        device_info="pytest-redis",
        created_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=5)).isoformat(),
    )
    assert await repository.create(token, record, ttl_seconds=300) is True
    assert await repository.client.ttl(f"{prefix}{token}") > 0
    assert await repository.consume(token) == record
    assert await repository.consume(token) is None
    await repository.close()
