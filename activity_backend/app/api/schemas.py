"""Validated HTTP and WebSocket request payloads."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OAuthCodeRequest(StrictModel):
    code: str = Field(min_length=1, max_length=512)


class ConnectRequest(StrictModel):
    instance_id: str = Field(min_length=1, max_length=128)
    channel_id: str = Field(min_length=1, max_length=128)
    guild_id: str | None = Field(default=None, max_length=128)
    locale: str = Field(default="zh-TW", min_length=2, max_length=32)


class SocketEnvelope(StrictModel):
    type: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=1, max_length=128)
    payload: dict = Field(default_factory=dict)
