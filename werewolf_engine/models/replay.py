"""Replay references derived from domain events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Self

from ..ids import EventType, EventVisibility, GamePhase
from .common import (
    JsonModel,
    JsonValue,
    assert_allowed_keys,
    normalize_timestamp,
    parse_timestamp,
    require_identifier,
    require_int,
    require_json_object,
)


@dataclass(frozen=True, slots=True)
class ReplayEntry(JsonModel):
    event_id: str
    sequence: int
    round_number: int
    phase: GamePhase
    event_type: EventType
    visibility: EventVisibility
    occurred_at: datetime
    payload: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", require_identifier(self.event_id, "event_id"))
        object.__setattr__(self, "sequence", require_int(self.sequence, "sequence", minimum=1))
        object.__setattr__(self, "round_number", require_int(self.round_number, "round_number"))
        object.__setattr__(self, "phase", GamePhase(self.phase))
        object.__setattr__(self, "event_type", EventType(self.event_type))
        object.__setattr__(self, "visibility", EventVisibility(self.visibility))
        object.__setattr__(self, "occurred_at", normalize_timestamp(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "payload", require_json_object(self.payload, "payload"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {"event_id", "sequence", "round_number", "phase", "event_type", "visibility", "occurred_at", "payload"}
        required = allowed - {"payload"}
        assert_allowed_keys(data, allowed, required=required)
        return cls(
            event_id=data["event_id"],
            sequence=data["sequence"],
            round_number=data["round_number"],
            phase=GamePhase(data["phase"]),
            event_type=EventType(data["event_type"]),
            visibility=EventVisibility(data["visibility"]),
            occurred_at=parse_timestamp(data["occurred_at"], "occurred_at"),
            payload=data.get("payload", {}),
        )
