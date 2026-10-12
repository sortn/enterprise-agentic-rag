from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from auth.dependencies import require_roles
from auth.jwt import JWTIssuer, JWTVerifier, RSAKeyManager
from auth.middleware import JWTAuthenticationMiddleware
from auth.models import UserContext, UserRecord


def test_middleware_injects_user_context_and_rbac_denies_user_role(tmp_path):
    keys = RSAKeyManager(tmp_path / "private.pem", tmp_path / "public.pem", key_size=2048)
    issuer = JWTIssuer(
        keys.private_key,
        kid="key-v1",
        issuer="issuer",
        audience="api",
        ttl_seconds=900,
    )
    verifier = JWTVerifier(
        keys.public_key,
        kid="key-v1",
        issuer="issuer",
        audience="api",
    )
    user = UserRecord(
        id="user-1",
        tenant_id="tenant-1",
        username="alice",
        email="alice@example.com",
        password_hash="hash",
        status="active",
        created_at="2026-09-01T00:00:00+00:00",
        updated_at="2026-09-01T00:00:00+00:00",
        roles=("user",),
        permissions=("agent:execute",),
    )
    token = issuer.issue_access_token(user)

    app = FastAPI()
    app.add_middleware(JWTAuthenticationMiddleware, verifier=verifier)

    @app.get("/api/v1/context")
    def context(request: Request):
        current: UserContext = request.state.user
        return current.to_agent_context()

    @app.get("/api/v1/admin")
    def admin(_context: UserContext = Depends(require_roles("admin"))):
        return {"ok": True}

    @app.get("/api/v1/health/live")
    def live():
        return {"status": "alive"}

    client = TestClient(app)
    assert client.get("/api/v1/context").status_code == 401
    response = client.get(
        "/api/v1/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"
    assert response.json()["tenant_id"] == "tenant-1"
    assert client.get(
        "/api/v1/admin",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 403
    assert client.get("/api/v1/health/live").status_code == 200
    assert client.get("/api/v1/health-private").status_code == 401
