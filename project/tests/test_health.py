import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from api import application as main


class ReadyStore:
    def list_documents(self):
        return []


class ReadySystem:
    initialized = True
    store = ReadyStore()

    def initialize(self):
        return self


class FailingSystem:
    initialized = False

    def initialize(self):
        raise ConnectionError("internal dependency detail")


class ReadyAuthService:
    async def readiness(self):
        return {"postgresql": "ok", "redis": "ok", "jwt_keys": "ok"}


READY_AUTH = SimpleNamespace(service=ReadyAuthService())


def test_liveness_does_not_initialize_dependencies():
    assert main.health_live()["status"] == "alive"


def test_root_redirects_to_gradio_ui():
    response = main.root()
    assert response.status_code == 307
    assert response.headers["location"] == "/ui/"


@pytest.mark.asyncio
async def test_readiness_checks_initialized_store(monkeypatch):
    monkeypatch.setattr(main, "system", ReadySystem())
    monkeypatch.setattr(main, "auth", READY_AUTH)
    payload = await main.health_ready()

    assert payload["status"] == "ready"
    assert payload["checks"] == {
        "postgresql": "ok",
        "redis": "ok",
        "jwt_keys": "ok",
        "milvus": "ok",
        "model_api": "configured",
    }


@pytest.mark.asyncio
async def test_readiness_fails_closed_without_leaking_internal_error(monkeypatch):
    monkeypatch.setattr(main, "system", FailingSystem())
    monkeypatch.setattr(main, "auth", READY_AUTH)

    with pytest.raises(HTTPException) as error:
        await main.health_ready()

    assert error.value.status_code == 503
    assert "internal dependency detail" not in error.value.detail
