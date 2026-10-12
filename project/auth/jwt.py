from __future__ import annotations

from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
import hashlib
import os
from pathlib import Path
from typing import Any
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from .errors import InvalidTokenError
from .models import UserContext, UserRecord


def _base64url_uint(value: int) -> str:
    width = max(1, (value.bit_length() + 7) // 8)
    return urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode("ascii")


class RSAKeyManager:
    """Owns the signing key and persists its public counterpart separately."""

    def __init__(
        self,
        private_key_path: str | Path,
        public_key_path: str | Path,
        *,
        configured_kid: str = "",
        key_size: int = 3072,
    ) -> None:
        self.private_key_path = Path(private_key_path)
        self.public_key_path = Path(public_key_path)
        self.private_key_path.parent.mkdir(parents=True, exist_ok=True)
        self.public_key_path.parent.mkdir(parents=True, exist_ok=True)
        self.private_key = self._load_or_create_private_key(key_size)
        self.public_key = self.private_key.public_key()
        self._persist_public_key()
        self.kid = configured_kid.strip() or self._derive_kid()

    def _load_or_create_private_key(self, key_size: int):
        if self.private_key_path.is_file():
            private_key = serialization.load_pem_private_key(
                self.private_key_path.read_bytes(),
                password=None,
            )
            if not isinstance(private_key, rsa.RSAPrivateKey):
                raise ValueError("AUTH_PRIVATE_KEY_PATH must contain an RSA private key")
            return private_key
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
        payload = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._atomic_write(self.private_key_path, payload, private=True)
        return private_key

    def _persist_public_key(self) -> None:
        payload = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if not self.public_key_path.is_file() or self.public_key_path.read_bytes() != payload:
            self._atomic_write(self.public_key_path, payload, private=False)

    @staticmethod
    def _atomic_write(path: Path, payload: bytes, *, private: bool) -> None:
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(payload)
        if private:
            try:
                os.chmod(temporary, 0o600)
            except OSError:
                pass
        temporary.replace(path)

    def _derive_kid(self) -> str:
        der = self.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return hashlib.sha256(der).hexdigest()[:16]


class JWTIssuer:
    def __init__(
        self,
        private_key: Any,
        *,
        kid: str,
        issuer: str,
        audience: str,
        ttl_seconds: int,
    ) -> None:
        self.private_key = private_key
        self.kid = kid
        self.issuer = issuer
        self.audience = audience
        self.ttl_seconds = ttl_seconds

    def issue_access_token(self, user: UserRecord) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": user.id,
            "user_id": user.id,
            "username": user.username,
            "role": user.primary_role,
            "tenant_id": user.tenant_id,
            "permissions": list(user.permissions),
            "iss": self.issuer,
            "aud": self.audience,
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.ttl_seconds)).timestamp()),
        }
        return jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.kid, "typ": "JWT"},
        )


class JWTVerifier:
    def __init__(
        self,
        public_key: Any,
        *,
        kid: str,
        issuer: str,
        audience: str,
        leeway_seconds: int = 5,
    ) -> None:
        self.public_key = public_key
        self.kid = kid
        self.issuer = issuer
        self.audience = audience
        self.leeway_seconds = leeway_seconds

    @classmethod
    def from_public_key_file(
        cls,
        path: str | Path,
        *,
        kid: str,
        issuer: str,
        audience: str,
        leeway_seconds: int = 5,
    ) -> "JWTVerifier":
        public_key = serialization.load_pem_public_key(Path(path).read_bytes())
        return cls(
            public_key,
            kid=kid,
            issuer=issuer,
            audience=audience,
            leeway_seconds=leeway_seconds,
        )

    def verify(self, token: str) -> UserContext:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or header.get("kid") != self.kid:
                raise InvalidTokenError()
            payload = jwt.decode(
                token,
                self.public_key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.leeway_seconds,
                options={
                    "require": [
                        "sub",
                        "user_id",
                        "username",
                        "role",
                        "tenant_id",
                        "iat",
                        "exp",
                    ]
                },
            )
        except InvalidTokenError:
            raise
        except jwt.PyJWTError as exc:
            raise InvalidTokenError() from exc

        permissions = payload.get("permissions", [])
        if not isinstance(permissions, list) or not all(isinstance(item, str) for item in permissions):
            raise InvalidTokenError()
        required_strings = ("user_id", "username", "role", "tenant_id")
        if any(not isinstance(payload.get(key), str) or not payload[key] for key in required_strings):
            raise InvalidTokenError()
        if payload["sub"] != payload["user_id"]:
            raise InvalidTokenError()
        return UserContext(
            user_id=payload["user_id"],
            username=payload["username"],
            role=payload["role"],
            tenant_id=payload["tenant_id"],
            permissions=tuple(permissions),
        )

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        numbers = self.public_key.public_numbers()
        return {
            "keys": [
                {
                    "kid": self.kid,
                    "kty": "RSA",
                    "alg": "RS256",
                    "use": "sig",
                    "n": _base64url_uint(numbers.n),
                    "e": _base64url_uint(numbers.e),
                }
            ]
        }
