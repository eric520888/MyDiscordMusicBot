"""Player-submitted night actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Self

from ..ids import ActionId
from .common import (
    JsonModel,
    assert_allowed_keys,
    normalize_timestamp,
    parse_timestamp,
    require_bool,
    require_identifier,
    require_identifier_list,
    require_int,
    require_string,
)


@dataclass(frozen=True, slots=True)
class NightAction(JsonModel):
    actor_player_id: str
    action_id: ActionId
    target_player_ids: tuple[str, ...]
    submitted_at: datetime
    request_id: str
    round_number: int
    mode: str = "default"
    resolved: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_player_id", require_identifier(self.actor_player_id, "actor_player_id"))
        object.__setattr__(self, "action_id", ActionId(self.action_id))
        targets = tuple(require_identifier_list(self.target_player_ids, "target_player_ids"))
        object.__setattr__(self, "target_player_ids", targets)
        object.__setattr__(self, "submitted_at", normalize_timestamp(self.submitted_at, "submitted_at"))
        object.__setattr__(self, "request_id", require_identifier(self.request_id, "request_id"))
        object.__setattr__(self, "round_number", require_int(self.round_number, "round_number", minimum=1))
        object.__setattr__(self, "mode", require_string(self.mode, "mode", max_length=64))
        object.__setattr__(self, "resolved", require_bool(self.resolved, "resolved"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "actor_player_id",
            "action_id",
            "target_player_ids",
            "submitted_at",
            "request_id",
            "round_number",
            "mode",
            "resolved",
        }
        required = {"actor_player_id", "action_id", "target_player_ids", "submitted_at", "request_id", "round_number"}
        assert_allowed_keys(data, allowed, required=required)
        return cls(
            actor_player_id=data["actor_player_id"],
            action_id=ActionId(data["action_id"]),
            target_player_ids=tuple(data["target_player_ids"]),
            submitted_at=parse_timestamp(data["submitted_at"], "submitted_at"),
            request_id=data["request_id"],
            round_number=data["round_number"],
            mode=data.get("mode", "default"),
            resolved=data.get("resolved", False),
        )
