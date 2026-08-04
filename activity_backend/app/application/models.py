"""Application-layer values that do not depend on FastAPI or Discord SDK objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Self

from werewolf_engine.models import GameEvent, GameState, PlayerState, RoomState
from werewolf_engine.models.common import (
    JsonModel,
    assert_allowed_keys,
    require_identifier,
    require_int,
    require_string,
)


@dataclass(frozen=True, slots=True)
class ActivityContext:
    discord_user_id: str
    display_name: str
    instance_id: str
    channel_id: str
    guild_id: str | None
    locale: str = "en-US"

    def __post_init__(self) -> None:
        object.__setattr__(self, "discord_user_id", require_identifier(self.discord_user_id, "discord_user_id"))
        object.__setattr__(self, "display_name", require_string(self.display_name, "display_name"))
        object.__setattr__(self, "instance_id", require_identifier(self.instance_id, "instance_id"))
        object.__setattr__(self, "channel_id", require_identifier(self.channel_id, "channel_id"))
        if self.guild_id is not None:
            object.__setattr__(self, "guild_id", require_identifier(self.guild_id, "guild_id"))
        object.__setattr__(self, "locale", require_string(self.locale, "locale", max_length=32))

    @property
    def binding_key(self) -> tuple[str, str, str | None]:
        return (self.instance_id, self.channel_id, self.guild_id)


@dataclass(slots=True)
class RoomAggregate(JsonModel):
    room: RoomState
    players: dict[str, PlayerState]
    game: GameState | None = None
    revision: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.room, RoomState):
            self.room = RoomState.from_dict(self.room)
        self.players = {
            player_id: player if isinstance(player, PlayerState) else PlayerState.from_dict(player)
            for player_id, player in self.players.items()
        }
        if set(self.players) != set(self.room.member_player_ids):
            raise ValueError("room members must match aggregate players")
        if self.game is not None and not isinstance(self.game, GameState):
            self.game = GameState.from_dict(self.game)
        self.revision = require_int(self.revision, "revision")

    def player_for_discord_user(self, discord_user_id: str) -> PlayerState | None:
        return next(
            (player for player in self.players.values() if player.discord_user_id == discord_user_id),
            None,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {"room", "players", "game", "revision"}
        assert_allowed_keys(data, allowed, required={"room", "players"})
        players = data["players"]
        if not isinstance(players, Mapping):
            raise TypeError("players must be an object")
        return cls(
            room=RoomState.from_dict(data["room"]),
            players={player_id: PlayerState.from_dict(player) for player_id, player in players.items()},
            game=GameState.from_dict(data["game"]) if data.get("game") is not None else None,
            revision=data.get("revision", 0),
        )


@dataclass(frozen=True, slots=True)
class RoomCommandResult:
    aggregate: RoomAggregate
    events: tuple[GameEvent, ...] = ()


IdFactory = Callable[[str], str]
