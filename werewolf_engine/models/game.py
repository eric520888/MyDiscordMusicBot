"""Durable, server-authoritative game state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Self

from ..ids import BoardId, GamePhase, WinnerId
from .action import NightAction
from .common import (
    JsonModel,
    JsonValue,
    assert_allowed_keys,
    normalize_timestamp,
    parse_timestamp,
    require_identifier,
    require_int,
    require_json_object,
    require_string,
)
from .player import PlayerState
from .role import EffectState, RoleState
from .settings import GameSettings
from .vote import VoteState


@dataclass(slots=True)
class GameState(JsonModel):
    game_id: str
    room_id: str
    board_id: BoardId
    settings: GameSettings
    phase: GamePhase = GamePhase.WAITING
    round_number: int = 0
    revision: int = 0
    phase_started_at: datetime | None = None
    phase_ends_at: datetime | None = None
    players: list[PlayerState] = field(default_factory=list)
    role_states: dict[str, RoleState] = field(default_factory=dict)
    night_actions: list[NightAction] = field(default_factory=list)
    vote_state: VoteState | None = None
    pending_effects: list[EffectState] = field(default_factory=list)
    pending_decisions: list[dict[str, JsonValue]] = field(default_factory=list)
    winner: WinnerId | None = None
    ended_reason: str | None = None
    event_sequence: int = 0

    def __post_init__(self) -> None:
        self.game_id = require_identifier(self.game_id, "game_id")
        self.room_id = require_identifier(self.room_id, "room_id")
        self.board_id = BoardId(self.board_id)
        if not isinstance(self.settings, GameSettings):
            self.settings = GameSettings.from_dict(self.settings)
        self.phase = GamePhase(self.phase)
        self.round_number = require_int(self.round_number, "round_number")
        self.revision = require_int(self.revision, "revision")
        if self.phase is not GamePhase.WAITING and not self.settings.locked:
            raise ValueError("settings must be locked before the game starts")
        if self.phase_started_at is not None:
            self.phase_started_at = normalize_timestamp(self.phase_started_at, "phase_started_at")
        if self.phase_ends_at is not None:
            self.phase_ends_at = normalize_timestamp(self.phase_ends_at, "phase_ends_at")
        if self.phase_ends_at is not None and self.phase_started_at is None:
            raise ValueError("phase_ends_at requires phase_started_at")
        if self.phase_started_at is not None and self.phase_ends_at is not None and self.phase_ends_at < self.phase_started_at:
            raise ValueError("phase_ends_at cannot precede phase_started_at")
        self.players = [player if isinstance(player, PlayerState) else PlayerState.from_dict(player) for player in self.players]
        player_ids = [player.player_id for player in self.players]
        if len(set(player_ids)) != len(player_ids):
            raise ValueError("player IDs must be unique")
        seats = [player.seat for player in self.players]
        if len(set(seats)) != len(seats):
            raise ValueError("player seats must be unique")
        self.role_states = {
            require_identifier(player_id, "role state player ID"): state if isinstance(state, RoleState) else RoleState.from_dict(state)
            for player_id, state in self.role_states.items()
        }
        if not set(self.role_states).issubset(player_ids):
            raise ValueError("role_states contains a player not present in players")
        players_by_id = {player.player_id: player for player in self.players}
        for player_id, role_state in self.role_states.items():
            if players_by_id[player_id].role_id is not role_state.role_id:
                raise ValueError("player role_id must match its role state")
        self.night_actions = [action if isinstance(action, NightAction) else NightAction.from_dict(action) for action in self.night_actions]
        if self.vote_state is not None and not isinstance(self.vote_state, VoteState):
            self.vote_state = VoteState.from_dict(self.vote_state)
        self.pending_effects = [effect if isinstance(effect, EffectState) else EffectState.from_dict(effect) for effect in self.pending_effects]
        self.pending_decisions = [require_json_object(decision, "pending_decision") for decision in self.pending_decisions]
        self.winner = WinnerId(self.winner) if self.winner is not None else None
        if self.ended_reason is not None:
            self.ended_reason = require_string(self.ended_reason, "ended_reason", max_length=128)
        self.event_sequence = require_int(self.event_sequence, "event_sequence")
        if self.phase is GamePhase.ENDED and self.ended_reason is None:
            raise ValueError("ended games require ended_reason")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "game_id",
            "room_id",
            "board_id",
            "settings",
            "phase",
            "round_number",
            "revision",
            "phase_started_at",
            "phase_ends_at",
            "players",
            "role_states",
            "night_actions",
            "vote_state",
            "pending_effects",
            "pending_decisions",
            "winner",
            "ended_reason",
            "event_sequence",
        }
        required = {"game_id", "room_id", "board_id", "settings"}
        assert_allowed_keys(data, allowed, required=required)
        role_states = data.get("role_states", {})
        if not isinstance(role_states, Mapping):
            raise TypeError("role_states must be an object")
        return cls(
            game_id=data["game_id"],
            room_id=data["room_id"],
            board_id=BoardId(data["board_id"]),
            settings=GameSettings.from_dict(data["settings"]),
            phase=GamePhase(data.get("phase", GamePhase.WAITING)),
            round_number=data.get("round_number", 0),
            revision=data.get("revision", 0),
            phase_started_at=parse_timestamp(data["phase_started_at"], "phase_started_at") if data.get("phase_started_at") is not None else None,
            phase_ends_at=parse_timestamp(data["phase_ends_at"], "phase_ends_at") if data.get("phase_ends_at") is not None else None,
            players=[PlayerState.from_dict(player) for player in data.get("players", [])],
            role_states={player_id: RoleState.from_dict(state) for player_id, state in role_states.items()},
            night_actions=[NightAction.from_dict(action) for action in data.get("night_actions", [])],
            vote_state=VoteState.from_dict(data["vote_state"]) if data.get("vote_state") is not None else None,
            pending_effects=[EffectState.from_dict(effect) for effect in data.get("pending_effects", [])],
            pending_decisions=list(data.get("pending_decisions", [])),
            winner=WinnerId(data["winner"]) if data.get("winner") is not None else None,
            ended_reason=data.get("ended_reason"),
            event_sequence=data.get("event_sequence", 0),
        )
