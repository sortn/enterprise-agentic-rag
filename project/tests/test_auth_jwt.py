from __future__ import annotations

import jwt
import pytest

from auth.errors import InvalidTokenError
from auth.jwt import JWTIssuer, JWTVerifier, RSAKeyManager
from auth.models import UserRecord


def _user() -> UserRecord:
    return UserRecord(
        id="10000000-0000-0000-0000-000000000001",
        tenant_id="20000000-0000-0000-0000-000000000001",
        username="alice",
        email="alice@example.com",
        password_hash="not-returned",
        status="active",
        created_at="2026-09-01T00:00:00+00:00",
        updated_at="2026-09-01T00:00:00+00:00",
        roles=("user",),
        permissions=("agent:execute", "documents:read"),
    )


def test_rs256_access_token_contains_required_claims_and_kid(tmp_path):
    keys = RSAKeyManager(
        tmp_path / "private.pem",
        tmp_path / "public.pem",
        configured_kid="test-key-v1",
        key_size=2048,
    )
    issuer = JWTIssuer(
        keys.private_key,
        kid=keys.kid,
        issuer="test-issuer",
        audience="test-api",
        ttl_seconds=900,
    )
    verifier = JWTVerifier(
        keys.public_key,
        kid=keys.kid,
        issuer="test-issuer",
        audience="test-api",
    )

    token = issuer.issue_access_token(_user())
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, options={"verify_signature": False})
    context = verifier.verify(token)

    assert header == {"alg": "RS256", "kid": "test-key-v1", "typ": "JWT"}
    assert {"user_id", "username", "role", "tenant_id", "exp", "iat"} <= payload.keys()
    assert context.user_id == _user().id
    assert context.tenant_id == _user().tenant_id
    assert context.permissions == ("agent:execute", "documents:read")
    assert (tmp_path / "private.pem").is_file()
    assert (tmp_path / "public.pem").is_file()
    public_only_verifier = JWTVerifier.from_public_key_file(
        tmp_path / "public.pem",
        kid=keys.kid,
        issuer="test-issuer",
        audience="test-api",
    )
    assert public_only_verifier.verify(token).user_id == _user().id

    jwk = verifier.jwks()["keys"][0]
    assert jwk["kid"] == "test-key-v1"
    assert jwk["kty"] == "RSA"
    assert jwk["alg"] == "RS256"
    assert jwk["n"] and jwk["e"]


def test_verifier_rejects_an_unknown_kid(tmp_path):
    keys = RSAKeyManager(tmp_path / "private.pem", tmp_path / "public.pem", key_size=2048)
    token = JWTIssuer(
        keys.private_key,
        kid="retired-key",
        issuer="issuer",
        audience="api",
        ttl_seconds=900,
    ).issue_access_token(_user())
    verifier = JWTVerifier(
        keys.public_key,
        kid="active-key",
        issuer="issuer",
        audience="api",
    )

    with pytest.raises(InvalidTokenError):
        verifier.verify(token)
