"""Serializable player state without Discord SDK objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Self

from ..ids import PlayerStatus, RoleId
from .common import (
    JsonModel,
    assert_allowed_keys,
    require_bool,
    require_identifier,
    require_int,
    require_string,
)


@dataclass(slots=True)
class PlayerState(JsonModel):
    player_id: str
    discord_user_id: str
    seat: int
    display_name: str
    status: PlayerStatus = PlayerStatus.ALIVE
    role_id: RoleId | None = None
    connected: bool = True
    ready: bool = False
    spectator: bool = False
    vote_enabled: bool = True

    def __post_init__(self) -> None:
        self.player_id = require_identifier(self.player_id, "player_id")
        self.discord_user_id = require_identifier(self.discord_user_id, "discord_user_id")
        self.seat = require_int(self.seat, "seat", minimum=0)
        self.display_name = require_string(self.display_name, "display_name")
        self.status = PlayerStatus(self.status)
        self.role_id = RoleId(self.role_id) if self.role_id is not None else None
        self.connected = require_bool(self.connected, "connected")
        self.ready = require_bool(self.ready, "ready")
        self.spectator = require_bool(self.spectator, "spectator")
        self.vote_enabled = require_bool(self.vote_enabled, "vote_enabled")
        if self.spectator and self.role_id is not None:
            raise ValueError("spectators cannot have a role")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "player_id",
            "discord_user_id",
            "seat",
            "display_name",
            "status",
            "role_id",
            "connected",
            "ready",
            "spectator",
            "vote_enabled",
        }
        required = {"player_id", "discord_user_id", "seat", "display_name"}
        assert_allowed_keys(data, allowed, required=required)
        return cls(
            player_id=data["player_id"],
            discord_user_id=data["discord_user_id"],
            seat=data["seat"],
            display_name=data["display_name"],
            status=PlayerStatus(data.get("status", PlayerStatus.ALIVE)),
            role_id=RoleId(data["role_id"]) if data.get("role_id") is not None else None,
            connected=data.get("connected", True),
            ready=data.get("ready", False),
            spectator=data.get("spectator", False),
            vote_enabled=data.get("vote_enabled", True),
        )
