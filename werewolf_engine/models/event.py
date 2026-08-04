"""Visibility-scoped domain events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Self

from ..ids import EventType, EventVisibility
from .common import (
    JsonModel,
    JsonValue,
    assert_allowed_keys,
    normalize_timestamp,
    parse_timestamp,
    require_identifier,
    require_identifier_list,
    require_int,
    require_json_object,
)


@dataclass(frozen=True, slots=True)
class GameEvent(JsonModel):
    event_id: str
    sequence: int
    event_type: EventType
    visibility: EventVisibility
    occurred_at: datetime
    payload: dict[str, JsonValue] = field(default_factory=dict)
    recipient_player_ids: frozenset[str] = field(default_factory=frozenset)
    schema_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", require_identifier(self.event_id, "event_id"))
        object.__setattr__(self, "sequence", require_int(self.sequence, "sequence", minimum=1))
        object.__setattr__(self, "event_type", EventType(self.event_type))
        object.__setattr__(self, "visibility", EventVisibility(self.visibility))
        object.__setattr__(self, "occurred_at", normalize_timestamp(self.occurred_at, "occurred_at"))
        object.__setattr__(self, "payload", require_json_object(self.payload, "payload"))
        recipients = frozenset(require_identifier_list(self.recipient_player_ids, "recipient_player_ids"))
        object.__setattr__(self, "recipient_player_ids", recipients)
        object.__setattr__(self, "schema_version", require_int(self.schema_version, "schema_version", minimum=1))
        if self.visibility in {EventVisibility.PLAYER_ONLY, EventVisibility.HOST_ONLY} and not recipients:
            raise ValueError("private events require at least one recipient")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "event_id",
            "sequence",
            "event_type",
            "visibility",
            "occurred_at",
            "payload",
            "recipient_player_ids",
            "schema_version",
        }
        required = {"event_id", "sequence", "event_type", "visibility", "occurred_at"}
        assert_allowed_keys(data, allowed, required=required)
        return cls(
            event_id=data["event_id"],
            sequence=data["sequence"],
            event_type=EventType(data["event_type"]),
            visibility=EventVisibility(data["visibility"]),
            occurred_at=parse_timestamp(data["occurred_at"], "occurred_at"),
            payload=data.get("payload", {}),
            recipient_player_ids=frozenset(data.get("recipient_player_ids", [])),
            schema_version=data.get("schema_version", 1),
        )
