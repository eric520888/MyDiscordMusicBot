"""Serializable board configuration used by a game instance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Self

from ..boards.catalog import BoardDefinition, get_board_definition
from ..ids import BoardId, RoleId
from .common import JsonModel, assert_allowed_keys, require_bool, require_int


@dataclass(frozen=True, slots=True)
class BoardConfiguration(JsonModel):
    board_id: BoardId
    role_ids: tuple[RoleId, ...]
    min_players: int
    max_players: int
    fixed_composition: bool
    engine_enabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "board_id", BoardId(self.board_id))
        object.__setattr__(self, "role_ids", tuple(RoleId(role_id) for role_id in self.role_ids))
        object.__setattr__(self, "min_players", require_int(self.min_players, "min_players", minimum=1))
        object.__setattr__(self, "max_players", require_int(self.max_players, "max_players", minimum=1))
        object.__setattr__(self, "fixed_composition", require_bool(self.fixed_composition, "fixed_composition"))
        object.__setattr__(self, "engine_enabled", require_bool(self.engine_enabled, "engine_enabled"))
        if self.max_players < self.min_players:
            raise ValueError("max_players cannot be less than min_players")
        if self.fixed_composition and len(self.role_ids) != self.min_players:
            raise ValueError("fixed board role count must match min_players")

    @classmethod
    def from_definition(cls, definition: BoardDefinition | BoardId | str) -> Self:
        board = definition if isinstance(definition, BoardDefinition) else get_board_definition(definition)
        return cls(
            board_id=board.board_id,
            role_ids=board.roles,
            min_players=board.min_players,
            max_players=board.max_players,
            fixed_composition=board.fixed_composition,
            engine_enabled=board.activity_enabled,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {"board_id", "role_ids", "min_players", "max_players", "fixed_composition", "engine_enabled"}
        required = allowed - {"engine_enabled"}
        assert_allowed_keys(data, allowed, required=required)
        return cls(
            board_id=BoardId(data["board_id"]),
            role_ids=tuple(RoleId(role_id) for role_id in data["role_ids"]),
            min_players=data["min_players"],
            max_players=data["max_players"],
            fixed_composition=data["fixed_composition"],
            engine_enabled=data.get("engine_enabled", False),
        )
