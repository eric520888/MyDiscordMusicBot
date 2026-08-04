"""Strict JSON serialization helpers for durable engine state."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Mapping, Self, TypeAlias, cast


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class JsonModel:
    """Mixin for dataclasses that provide a strict ``from_dict`` method."""

    schema_version: ClassVar[int] = 1

    def to_dict(self) -> dict[str, JsonValue]:
        value = encode_json(self)
        if not isinstance(value, dict):
            raise TypeError("model did not encode to an object")
        return value

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, value: str) -> Self:
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError(f"{cls.__name__} JSON must contain an object")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        raise NotImplementedError


def encode_json(value: Any) -> JsonValue:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("non-finite floats are not JSON-safe")
        return value
    if isinstance(value, Enum):
        return cast(JsonScalar, value.value)
    if isinstance(value, datetime):
        return format_timestamp(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: encode_json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            result[key] = encode_json(item)
        return result
    if isinstance(value, (set, frozenset)):
        if not all(isinstance(item, (str, Enum)) for item in value):
            raise TypeError("JSON sets may only contain string identifiers")
        return sorted(cast(list[JsonValue], [encode_json(item) for item in value]))
    if isinstance(value, (list, tuple)):
        return [encode_json(item) for item in value]
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def assert_allowed_keys(
    data: Mapping[str, Any],
    allowed: set[str],
    *,
    required: set[str] | None = None,
) -> None:
    if not isinstance(data, Mapping):
        raise TypeError("model input must be a mapping")
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
    missing = (required or set()) - set(data)
    if missing:
        raise ValueError(f"missing fields: {', '.join(sorted(missing))}")


def require_identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value) > 128:
        raise ValueError(f"{field_name} is too long")
    return value


def require_string(value: Any, field_name: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if len(value) > max_length:
        raise ValueError(f"{field_name} is too long")
    return value


def require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean")
    return value


def require_int(value: Any, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    return value


def normalize_timestamp(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def format_timestamp(value: datetime) -> str:
    return normalize_timestamp(value, "timestamp").isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    return normalize_timestamp(parsed, field_name)


def require_json_object(value: Any, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    encoded = encode_json(value)
    if not isinstance(encoded, dict):
        raise TypeError(f"{field_name} must be an object")
    # A JSON round trip prevents callers from retaining mutable/non-JSON objects.
    return cast(dict[str, JsonValue], json.loads(json.dumps(encoded, allow_nan=False)))


def require_identifier_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise TypeError(f"{field_name} must be a list of identifiers")
    result = [require_identifier(item, field_name) for item in value]
    if len(set(result)) != len(result):
        raise ValueError(f"{field_name} cannot contain duplicates")
    return result
