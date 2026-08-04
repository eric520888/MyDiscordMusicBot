"""Minimal Discord OAuth exchange and signed server sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx


class AuthError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DiscordIdentity:
    user_id: str
    display_name: str


def _encode_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_part(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class DiscordAuth:
    def __init__(self, *, client_id: str, client_secret: str, session_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self._session_secret = session_secret.encode("utf-8")

    async def exchange_code(self, code: str) -> tuple[str, int, DiscordIdentity]:
        if not self.client_id or not self.client_secret:
            raise AuthError("Discord OAuth 尚未設定")
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_response.status_code >= 400:
                raise AuthError("Discord 授權碼無效或已過期")
            token_data = token_response.json()
            access_token = str(token_data.get("access_token", ""))
            expires_in = int(token_data.get("expires_in", 3600))
            if not access_token:
                raise AuthError("Discord 未回傳存取權杖")
            user_response = await client.get(
                "https://discord.com/api/v10/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_response.status_code >= 400:
                raise AuthError("無法驗證 Discord 玩家")
            user = user_response.json()
        user_id = str(user.get("id", ""))
        display_name = str(user.get("global_name") or user.get("username") or "Discord 玩家")[:64]
        if not user_id:
            raise AuthError("Discord 玩家資料不完整")
        return access_token, expires_in, DiscordIdentity(user_id, display_name)

    def issue_session(self, identity: DiscordIdentity, *, ttl_seconds: int = 3600) -> str:
        now = int(time.time())
        header = _encode_part(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
        payload = _encode_part(
            json.dumps(
                {
                    "iss": "discord-werewolf-activity",
                    "sub": identity.user_id,
                    "name": identity.display_name,
                    "iat": now,
                    "exp": now + min(max(ttl_seconds, 60), 86400),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        unsigned = f"{header}.{payload}".encode("ascii")
        signature = _encode_part(hmac.new(self._session_secret, unsigned, hashlib.sha256).digest())
        return f"{header}.{payload}.{signature}"

    def verify_session(self, token: str) -> DiscordIdentity:
        try:
            header, payload, signature = token.split(".")
            unsigned = f"{header}.{payload}".encode("ascii")
            expected = hmac.new(self._session_secret, unsigned, hashlib.sha256).digest()
            if not hmac.compare_digest(expected, _decode_part(signature)):
                raise AuthError("工作階段簽章無效")
            data: dict[str, Any] = json.loads(_decode_part(payload))
            if data.get("iss") != "discord-werewolf-activity":
                raise AuthError("工作階段來源無效")
            if int(data.get("exp", 0)) <= int(time.time()):
                raise AuthError("工作階段已過期")
            return DiscordIdentity(str(data["sub"]), str(data.get("name") or "Discord 玩家")[:64])
        except AuthError:
            raise
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise AuthError("工作階段格式無效") from exc
