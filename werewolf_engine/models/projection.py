"""JSON-safe state sent to one authenticated Activity player."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Self

from ..ids import BoardId, EventType, GamePhase, PlayerStatus, RoleId
from .common import (
    JsonModel,
    JsonValue,
    assert_allowed_keys,
    normalize_timestamp,
    parse_timestamp,
    require_bool,
    require_identifier,
    require_identifier_list,
    require_int,
    require_json_object,
    require_string,
)
from .role import RoleState
from .settings import GameSettings


@dataclass(frozen=True, slots=True)
class ProjectedPlayer(JsonModel):
    player_id: str
    seat: int
    display_name: str
    status: PlayerStatus
    connected: bool
    ready: bool
    spectator: bool
    vote_enabled: bool
    revealed_role_id: RoleId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "player_id", require_identifier(self.player_id, "player_id"))
        object.__setattr__(self, "seat", require_int(self.seat, "seat"))
        object.__setattr__(self, "display_name", require_string(self.display_name, "display_name"))
        object.__setattr__(self, "status", PlayerStatus(self.status))
        object.__setattr__(self, "connected", require_bool(self.connected, "connected"))
        object.__setattr__(self, "ready", require_bool(self.ready, "ready"))
        object.__setattr__(self, "spectator", require_bool(self.spectator, "spectator"))
        object.__setattr__(self, "vote_enabled", require_bool(self.vote_enabled, "vote_enabled"))
        if self.revealed_role_id is not None:
            object.__setattr__(self, "revealed_role_id", RoleId(self.revealed_role_id))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "player_id",
            "seat",
            "display_name",
            "status",
            "connected",
            "ready",
            "spectator",
            "vote_enabled",
            "revealed_role_id",
        }
        assert_allowed_keys(data, allowed, required=allowed - {"revealed_role_id"})
        return cls(
            player_id=data["player_id"],
            seat=data["seat"],
            display_name=data["display_name"],
            status=PlayerStatus(data["status"]),
            connected=data["connected"],
            ready=data["ready"],
            spectator=data["spectator"],
            vote_enabled=data["vote_enabled"],
            revealed_role_id=RoleId(data["revealed_role_id"]) if data.get("revealed_role_id") else None,
        )


@dataclass(frozen=True, slots=True)
class ProjectedEvent(JsonModel):
    sequence: int
    event_type: EventType
    occurred_at: datetime
    payload: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", require_int(self.sequence, "sequence", minimum=1))
        object.__setattr__(self, "event_type", EventType(self.event_type))
        object.__setattr__(self, "occurred_at", normalize_timestamp(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "payload", require_json_object(self.payload, "payload"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {"sequence", "event_type", "occurred_at", "payload"}
        assert_allowed_keys(data, allowed, required=allowed - {"payload"})
        return cls(
            sequence=data["sequence"],
            event_type=EventType(data["event_type"]),
            occurred_at=parse_timestamp(data["occurred_at"], "occurred_at"),
            payload=data.get("payload", {}),
        )


@dataclass(frozen=True, slots=True)
class PlayerProjection(JsonModel):
    game_id: str
    viewer_player_id: str
    board_id: BoardId
    phase: GamePhase
    round_number: int
    revision: int
    settings: GameSettings
    players: tuple[ProjectedPlayer, ...]
    self_role_state: RoleState | None = None
    wolf_team_player_ids: tuple[str, ...] = ()
    pending_decisions: tuple[dict[str, JsonValue], ...] = ()
    events: tuple[ProjectedEvent, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "game_id", require_identifier(self.game_id, "game_id"))
        object.__setattr__(self, "viewer_player_id", require_identifier(self.viewer_player_id, "viewer_player_id"))
        object.__setattr__(self, "board_id", BoardId(self.board_id))
        object.__setattr__(self, "phase", GamePhase(self.phase))
        object.__setattr__(self, "round_number", require_int(self.round_number, "round_number"))
        object.__setattr__(self, "revision", require_int(self.revision, "revision"))
        if not isinstance(self.settings, GameSettings):
            object.__setattr__(self, "settings", GameSettings.from_dict(self.settings))
        players = tuple(
            player if isinstance(player, ProjectedPlayer) else ProjectedPlayer.from_dict(player)
            for player in self.players
        )
        object.__setattr__(self, "players", players)
        if self.self_role_state is not None and not isinstance(self.self_role_state, RoleState):
            object.__setattr__(self, "self_role_state", RoleState.from_dict(self.self_role_state))
        object.__setattr__(
            self,
            "wolf_team_player_ids",
            tuple(require_identifier_list(self.wolf_team_player_ids, "wolf_team_player_ids")),
        )
        object.__setattr__(
            self,
            "pending_decisions",
            tuple(require_json_object(decision, "pending_decision") for decision in self.pending_decisions),
        )
        object.__setattr__(
            self,
            "events",
            tuple(event if isinstance(event, ProjectedEvent) else ProjectedEvent.from_dict(event) for event in self.events),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "game_id",
            "viewer_player_id",
            "board_id",
            "phase",
            "round_number",
            "revision",
            "settings",
            "players",
            "self_role_state",
            "wolf_team_player_ids",
            "pending_decisions",
            "events",
        }
        required = allowed - {"self_role_state", "wolf_team_player_ids", "pending_decisions", "events"}
        assert_allowed_keys(data, allowed, required=required)
        return cls(
            game_id=data["game_id"],
            viewer_player_id=data["viewer_player_id"],
            board_id=BoardId(data["board_id"]),
            phase=GamePhase(data["phase"]),
            round_number=data["round_number"],
            revision=data["revision"],
            settings=GameSettings.from_dict(data["settings"]),
            players=tuple(ProjectedPlayer.from_dict(player) for player in data["players"]),
            self_role_state=RoleState.from_dict(data["self_role_state"]) if data.get("self_role_state") else None,
            wolf_team_player_ids=tuple(data.get("wolf_team_player_ids", [])),
            pending_decisions=tuple(data.get("pending_decisions", [])),
            events=tuple(ProjectedEvent.from_dict(event) for event in data.get("events", [])),
        )
