"""Centralized authentication state and token-aware HTTP client for Gradio."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import time
from typing import Any, Iterator

import httpx


@dataclass
class AuthSession:
    access_token: str = ""
    refresh_token: str = ""
    access_expires_at: float = 0.0
    refresh_expires_at: float = 0.0
    user: dict[str, Any] = field(default_factory=dict)

    @property
    def authenticated(self) -> bool:
        return bool(self.access_token and self.refresh_token and self.user)

    @property
    def is_admin(self) -> bool:
        return "admin" in self.user.get("roles", [])

    def to_browser_state(self) -> dict[str, Any]:
        """Return the minimum session data needed to restore a login."""
        if not self.refresh_token or not self.user:
            return {}
        return {
            "refresh_token": self.refresh_token,
            "refresh_expires_at": self.refresh_expires_at,
            "user": self.user,
        }


class AuthClientError(RuntimeError):
    pass


class AuthClient:
    def __init__(self, api_base_url: str, timeout: httpx.Timeout) -> None:
        self.api_base_url = api_base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)

    def register(self, username: str, email: str, password: str) -> AuthSession:
        response = self.client.post(
            f"{self.api_base_url}/api/v1/auth/register",
            json={
                "username": username,
                "email": email,
                "password": password,
                "device_info": "gradio-web",
            },
        )
        return self._session_from_response(response)

    def login(self, username: str, password: str) -> AuthSession:
        response = self.client.post(
            f"{self.api_base_url}/api/v1/auth/login",
            json={
                "username": username,
                "password": password,
                "device_info": "gradio-web",
            },
        )
        return self._session_from_response(response)

    def logout(self, session: AuthSession) -> AuthSession:
        if session.refresh_token:
            try:
                self.client.post(
                    f"{self.api_base_url}/api/v1/auth/logout",
                    json={"refresh_token": session.refresh_token},
                )
            except httpx.HTTPError:
                pass
        return AuthSession()

    def restore(self, browser_state: Any) -> AuthSession:
        """Restore a browser session by rotating its saved refresh token."""
        if not isinstance(browser_state, dict):
            raise AuthClientError("保存的登录状态无效，请重新登录。")

        refresh_token = str(browser_state.get("refresh_token") or "")
        user = browser_state.get("user")
        try:
            refresh_expires_at = float(browser_state.get("refresh_expires_at") or 0)
        except (TypeError, ValueError):
            refresh_expires_at = 0.0

        if not refresh_token or not isinstance(user, dict) or not user:
            raise AuthClientError("没有可恢复的登录状态。")
        if refresh_expires_at and refresh_expires_at <= time.time():
            raise AuthClientError("登录已过期，请重新登录。")

        session = AuthSession(
            refresh_token=refresh_token,
            refresh_expires_at=refresh_expires_at,
            user=dict(user),
        )
        self._refresh(session)
        return session

    def request(
        self,
        method: str,
        path: str,
        session: AuthSession,
        **kwargs: Any,
    ) -> httpx.Response:
        self._ensure_access_token(session)
        response = self.client.request(
            method,
            f"{self.api_base_url}{path}",
            headers=self._authorization_header(session),
            **kwargs,
        )
        if response.status_code == 401 and session.refresh_token:
            self._refresh(session)
            response = self.client.request(
                method,
                f"{self.api_base_url}{path}",
                headers=self._authorization_header(session),
                **kwargs,
            )
        return response

    @contextmanager
    def stream(
        self,
        method: str,
        path: str,
        session: AuthSession,
        **kwargs: Any,
    ) -> Iterator[httpx.Response]:
        self._ensure_access_token(session)
        response = self.client.send(
            self.client.build_request(
                method,
                f"{self.api_base_url}{path}",
                headers=self._authorization_header(session),
                **kwargs,
            ),
            stream=True,
        )
        if response.status_code == 401 and session.refresh_token:
            response.close()
            self._refresh(session)
            response = self.client.send(
                self.client.build_request(
                    method,
                    f"{self.api_base_url}{path}",
                    headers=self._authorization_header(session),
                    **kwargs,
                ),
                stream=True,
            )
        try:
            yield response
        finally:
            response.close()

    def _ensure_access_token(self, session: AuthSession) -> None:
        if not session.authenticated:
            raise AuthClientError("请先登录")
        if session.access_expires_at <= time.time() + 15:
            self._refresh(session)

    def _refresh(self, session: AuthSession) -> None:
        if not session.refresh_token or session.refresh_expires_at <= time.time():
            raise AuthClientError("登录状态已过期，请重新登录")
        try:
            response = self.client.post(
                f"{self.api_base_url}/api/v1/auth/refresh",
                json={"refresh_token": session.refresh_token},
            )
        except httpx.HTTPError as exc:
            raise AuthClientError("认证服务暂时不可用") from exc
        if response.is_error:
            raise AuthClientError(self._error_detail(response))
        payload = response.json()
        now = time.time()
        session.access_token = payload["access_token"]
        session.refresh_token = payload["refresh_token"]
        session.access_expires_at = now + int(payload["expires_in"])
        session.refresh_expires_at = now + int(payload["refresh_expires_in"])

    def _session_from_response(self, response: httpx.Response) -> AuthSession:
        if response.is_error:
            raise AuthClientError(self._error_detail(response))
        payload = response.json()
        now = time.time()
        return AuthSession(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            access_expires_at=now + int(payload["expires_in"]),
            refresh_expires_at=now + int(payload["refresh_expires_in"]),
            user=payload["user"],
        )

    @staticmethod
    def _authorization_header(session: AuthSession) -> dict[str, str]:
        return {"Authorization": f"Bearer {session.access_token}"}

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
            detail = payload.get("detail")
            if isinstance(detail, list):
                return "提交的信息格式不正确"
            if isinstance(detail, str):
                return detail
        except (ValueError, TypeError):
            pass
        return f"请求失败（HTTP {response.status_code}）"
