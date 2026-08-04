"""Activity room state and trusted Discord context binding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Self

from .common import (
    JsonModel,
    assert_allowed_keys,
    normalize_timestamp,
    parse_timestamp,
    require_bool,
    require_identifier,
    require_identifier_list,
)
from .settings import GameSettings


@dataclass(slots=True)
class RoomState(JsonModel):
    room_id: str
    discord_instance_id: str
    discord_channel_id: str
    discord_guild_id: str | None
    host_player_id: str
    member_player_ids: list[str]
    settings: GameSettings
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    game_id: str | None = None
    closed: bool = False

    def __post_init__(self) -> None:
        self.room_id = require_identifier(self.room_id, "room_id")
        self.discord_instance_id = require_identifier(self.discord_instance_id, "discord_instance_id")
        self.discord_channel_id = require_identifier(self.discord_channel_id, "discord_channel_id")
        if self.discord_guild_id is not None:
            self.discord_guild_id = require_identifier(self.discord_guild_id, "discord_guild_id")
        self.host_player_id = require_identifier(self.host_player_id, "host_player_id")
        self.member_player_ids = require_identifier_list(self.member_player_ids, "member_player_ids")
        if self.host_player_id not in self.member_player_ids:
            raise ValueError("host_player_id must be a room member")
        if not isinstance(self.settings, GameSettings):
            self.settings = GameSettings.from_dict(self.settings)
        self.created_at = normalize_timestamp(self.created_at, "created_at")
        self.updated_at = normalize_timestamp(self.updated_at, "updated_at")
        self.expires_at = normalize_timestamp(self.expires_at, "expires_at")
        if not self.created_at <= self.updated_at <= self.expires_at:
            raise ValueError("room timestamps must be ordered")
        if self.game_id is not None:
            self.game_id = require_identifier(self.game_id, "game_id")
        self.closed = require_bool(self.closed, "closed")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "room_id",
            "discord_instance_id",
            "discord_channel_id",
            "discord_guild_id",
            "host_player_id",
            "member_player_ids",
            "settings",
            "created_at",
            "updated_at",
            "expires_at",
            "game_id",
            "closed",
        }
        required = allowed - {"discord_guild_id", "game_id", "closed"}
        assert_allowed_keys(data, allowed, required=required)
        return cls(
            room_id=data["room_id"],
            discord_instance_id=data["discord_instance_id"],
            discord_channel_id=data["discord_channel_id"],
            discord_guild_id=data.get("discord_guild_id"),
            host_player_id=data["host_player_id"],
            member_player_ids=list(data["member_player_ids"]),
            settings=GameSettings.from_dict(data["settings"]),
            created_at=parse_timestamp(data["created_at"], "created_at"),
            updated_at=parse_timestamp(data["updated_at"], "updated_at"),
            expires_at=parse_timestamp(data["expires_at"], "expires_at"),
            game_id=data.get("game_id"),
            closed=data.get("closed", False),
        )
