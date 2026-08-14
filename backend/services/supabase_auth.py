from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from backend.config import get_settings


class SupabaseAuthError(Exception):
    def __init__(self, status_code: int, code: str = "authentication_failed"):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True)
class ProviderSession:
    access_token: str
    refresh_token: str
    user_id: str
    email: str
    email_verified: bool
    identities: tuple[dict[str, Any], ...]
    user_metadata: dict[str, Any] = field(default_factory=dict)


class SupabaseAuthClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = f"{settings.SUPABASE_URL}/auth/v1"
        self.anon_key = settings.SUPABASE_ANON_KEY
        self.service_key = settings.SUPABASE_SERVICE_ROLE_KEY

    async def register(
        self,
        email: str,
        password: str,
        redirect_to: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/signup",
            json={"email": email, "password": password, "data": metadata or {}},
            params={"redirect_to": redirect_to},
        )

    async def password_login(self, email: str, password: str) -> ProviderSession:
        payload = await self._request(
            "POST",
            "/token",
            params={"grant_type": "password"},
            json={"email": email, "password": password},
        )
        return _provider_session(payload)

    async def exchange_pkce(self, auth_code: str, code_verifier: str) -> ProviderSession:
        payload = await self._request(
            "POST",
            "/token",
            params={"grant_type": "pkce"},
            json={"auth_code": auth_code, "code_verifier": code_verifier},
        )
        return _provider_session(payload)

    async def refresh(self, refresh_token: str) -> ProviderSession:
        payload = await self._request(
            "POST",
            "/token",
            params={"grant_type": "refresh_token"},
            json={"refresh_token": refresh_token},
        )
        return _provider_session(payload)

    async def verify_otp(self, token_hash: str, otp_type: str) -> ProviderSession | None:
        payload = await self._request(
            "POST", "/verify", json={"token_hash": token_hash, "type": otp_type}
        )
        if not payload.get("access_token"):
            return None
        return _provider_session(payload)

    async def send_recovery(self, email: str, redirect_to: str) -> None:
        await self._request(
            "POST",
            "/recover",
            json={"email": email},
            params={"redirect_to": redirect_to},
        )

    async def update_password(self, access_token: str, password: str) -> None:
        await self._request(
            "PUT", "/user", json={"password": password}, access_token=access_token
        )

    async def logout(self, access_token: str, scope: str = "global") -> None:
        await self._request(
            "POST",
            "/logout",
            params={"scope": scope},
            access_token=access_token,
        )

    async def get_user(self, access_token: str) -> dict[str, Any]:
        return await self._request("GET", "/user", access_token=access_token)

    async def unlink_identity(self, access_token: str, identity_id: str) -> None:
        await self._request(
            "DELETE", f"/user/identities/{identity_id}", access_token=access_token
        )

    async def delete_user(self, user_id: str) -> None:
        if not self.service_key:
            raise SupabaseAuthError(503, "account_deletion_unconfigured")
        await self._request(
            "DELETE",
            f"/admin/users/{user_id}",
            service_role=True,
        )

    def oauth_url(
        self,
        *,
        redirect_to: str,
        code_challenge: str,
        state: str,
        scopes: str = "openid email profile",
    ) -> str:
        callback = str(httpx.URL(redirect_to).copy_add_param("state", state))
        query = urlencode(
            {
                "provider": "google",
                "redirect_to": callback,
                "code_challenge": code_challenge,
                "code_challenge_method": "s256",
                "scopes": scopes,
            }
        )
        return f"{self.base_url}/authorize?{query}"

    async def identity_link_url(
        self,
        *,
        access_token: str,
        redirect_to: str,
        code_challenge: str,
        state: str,
        scopes: str = "openid email profile",
    ) -> str:
        callback = str(httpx.URL(redirect_to).copy_add_param("state", state))
        params = {
            "provider": "google",
            "redirect_to": callback,
            "code_challenge": code_challenge,
            "code_challenge_method": "s256",
            "scopes": scopes,
        }
        if not self.anon_key:
            raise SupabaseAuthError(503, "authentication_unconfigured")
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(12.0), follow_redirects=False
            ) as client:
                response = await client.get(
                    f"{self.base_url}/user/identities/authorize",
                    params=params,
                    headers={
                        "apikey": self.anon_key,
                        "Authorization": f"Bearer {access_token}",
                    },
                )
        except httpx.HTTPError as exc:
            raise SupabaseAuthError(
                503, "authentication_provider_unavailable"
            ) from exc
        if response.status_code not in {301, 302, 303, 307, 308}:
            raise SupabaseAuthError(response.status_code, "identity_link_failed")
        location = response.headers.get("location")
        if not location:
            raise SupabaseAuthError(502, "invalid_authentication_response")
        return location

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        access_token: str | None = None,
        service_role: bool = False,
    ) -> dict[str, Any]:
        api_key = self.service_key if service_role else self.anon_key
        if not api_key:
            raise SupabaseAuthError(503, "authentication_unconfigured")
        bearer = api_key if service_role else (access_token or api_key)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(12.0)) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json,
                    params=params,
                    headers={
                        "apikey": api_key,
                        "Authorization": f"Bearer {bearer}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError as exc:
            raise SupabaseAuthError(503, "authentication_provider_unavailable") from exc
        if response.status_code >= 400:
            code = "authentication_failed"
            try:
                body = response.json()
                code = body.get("error_code") or body.get("code") or code
            except ValueError:
                pass
            raise SupabaseAuthError(response.status_code, str(code))
        if not response.content:
            return {}
        return response.json()


def _provider_session(payload: dict[str, Any]) -> ProviderSession:
    user = payload.get("user") or {}
    email = str(user.get("email") or "")
    user_id = str(user.get("id") or "")
    if not user_id or not email:
        raise SupabaseAuthError(502, "invalid_authentication_response")
    verified = bool(user.get("email_confirmed_at") or user.get("confirmed_at"))
    return ProviderSession(
        access_token=str(payload.get("access_token") or ""),
        refresh_token=str(payload.get("refresh_token") or ""),
        user_id=user_id,
        email=email,
        email_verified=verified,
        identities=tuple(user.get("identities") or ()),
        user_metadata=dict(user.get("user_metadata") or {}),
    )
