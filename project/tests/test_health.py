import pytest
from fastapi import HTTPException

from api import main


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


def test_liveness_does_not_initialize_dependencies():
    assert main.health_live()["status"] == "alive"


def test_readiness_checks_initialized_store(monkeypatch):
    monkeypatch.setattr(main, "system", ReadySystem())
    payload = main.health_ready()

    assert payload["status"] == "ready"
    assert payload["checks"] == {"milvus": "ok", "model_api": "configured"}


def test_readiness_fails_closed_without_leaking_internal_error(monkeypatch):
    monkeypatch.setattr(main, "system", FailingSystem())

    with pytest.raises(HTTPException) as error:
        main.health_ready()

    assert error.value.status_code == 503
    assert "internal dependency detail" not in error.value.detail
