from __future__ import annotations

import time

import httpx

from ui.auth_service import AuthClient, AuthSession
from ui.dashboard import _document_identity, _format_citations


def test_auth_client_refreshes_once_and_centralizes_authorization_header():
    seen_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/refresh":
            return httpx.Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "token_type": "Bearer",
                    "expires_in": 900,
                    "refresh_expires_in": 3600,
                },
            )
        seen_headers.append(request.headers.get("Authorization", ""))
        return httpx.Response(200, json={"documents": []})

    client = AuthClient("http://testserver", httpx.Timeout(5))
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5)
    session = AuthSession(
        access_token="expired-access",
        refresh_token="old-refresh",
        access_expires_at=time.time() - 1,
        refresh_expires_at=time.time() + 3600,
        user={"username": "alice", "roles": ["user"]},
    )

    response = client.request("GET", "/api/v1/documents", session)

    assert response.status_code == 200
    assert seen_headers == ["Bearer new-access"]
    assert session.access_token == "new-access"
    assert session.refresh_token == "new-refresh"


def test_browser_state_restores_login_without_persisting_access_token():
    refresh_requests: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        refresh_requests.append(request.content)
        return httpx.Response(
            200,
            json={
                "access_token": "restored-access",
                "refresh_token": "rotated-refresh",
                "token_type": "Bearer",
                "expires_in": 900,
                "refresh_expires_in": 3600,
            },
        )

    client = AuthClient("http://testserver", httpx.Timeout(5))
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(handler), timeout=5)
    original = AuthSession(
        access_token="do-not-store-this",
        refresh_token="saved-refresh",
        access_expires_at=time.time() + 900,
        refresh_expires_at=time.time() + 3600,
        user={"username": "alice", "roles": ["user"]},
    )

    browser_state = original.to_browser_state()
    restored = client.restore(browser_state)

    assert "access_token" not in browser_state
    assert refresh_requests == [b'{"refresh_token":"saved-refresh"}']
    assert restored.access_token == "restored-access"
    assert restored.refresh_token == "rotated-refresh"
    assert restored.user == original.user


def test_document_names_and_answer_sources_use_current_api_fields():
    source, document_id = _document_identity(
        {"id": "doc-1", "title": "iKUN", "source_name": "iKUN.pdf"}
    )
    sources = _format_citations(
        [
            {"source": "iKUN.pdf", "locator": "第 2 页"},
            {"source": "iKUN.pdf", "locator": "第 2 页"},
        ]
    )

    assert source == "iKUN\\.pdf"
    assert document_id == "doc\\-1"
    assert sources.count("iKUN\\.pdf") == 1
    assert "第 2 页" in sources
