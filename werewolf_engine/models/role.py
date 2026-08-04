"""Serializable per-game role state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Self

from ..ids import CampId, RoleId
from ..roles import get_role_definition
from .common import (
    JsonModel,
    JsonValue,
    assert_allowed_keys,
    require_bool,
    require_identifier,
    require_identifier_list,
    require_int,
    require_json_object,
)


REGISTERED_ROLE_RESOURCE_KEYS = frozenset(
    {
        "antidote_available",
        "poison_available",
        "hunter_shots",
        "poison_recipes",
        "awakened_claws",
        "cooldown_until",
        "last_guard_round",
        "wolf_reveal_round",
        "boost_used",
        "weaken_used",
        "mimic_witch_used",
        "illusion_used",
        "secret_body",
        "doomed",
        "self_destruct_attempted",
        "inherited_by_awakened_lonely_girl",
    }
)


@dataclass(frozen=True, slots=True)
class EffectState(JsonModel):
    effect_id: str
    source_player_id: str | None = None
    target_player_id: str | None = None
    expires_round: int | None = None
    data: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_id", require_identifier(self.effect_id, "effect_id"))
        if self.source_player_id is not None:
            object.__setattr__(self, "source_player_id", require_identifier(self.source_player_id, "source_player_id"))
        if self.target_player_id is not None:
            object.__setattr__(self, "target_player_id", require_identifier(self.target_player_id, "target_player_id"))
        if self.expires_round is not None:
            object.__setattr__(self, "expires_round", require_int(self.expires_round, "expires_round", minimum=1))
        object.__setattr__(self, "data", require_json_object(self.data, "data"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {"effect_id", "source_player_id", "target_player_id", "expires_round", "data"}
        assert_allowed_keys(data, allowed, required={"effect_id"})
        return cls(
            effect_id=data["effect_id"],
            source_player_id=data.get("source_player_id"),
            target_player_id=data.get("target_player_id"),
            expires_round=data.get("expires_round"),
            data=data.get("data", {}),
        )


@dataclass(slots=True)
class RoleState(JsonModel):
    role_id: RoleId
    camp: CampId
    disabled: bool = False
    used_abilities: set[str] = field(default_factory=set)
    resources: dict[str, int | bool] = field(default_factory=dict)
    last_target_ids: list[str] = field(default_factory=list)
    checked_target_ids: list[str] = field(default_factory=list)
    effects: list[EffectState] = field(default_factory=list)
    mimicked_role_id: RoleId | None = None

    def __post_init__(self) -> None:
        self.role_id = RoleId(self.role_id)
        self.camp = CampId(self.camp)
        expected_camp = get_role_definition(self.role_id).camp
        if self.camp is not expected_camp:
            raise ValueError(f"role {self.role_id.value} must use camp {expected_camp.value}")
        self.disabled = require_bool(self.disabled, "disabled")
        self.used_abilities = set(require_identifier_list(self.used_abilities, "used_abilities"))
        unknown_resources = set(self.resources) - REGISTERED_ROLE_RESOURCE_KEYS
        if unknown_resources:
            raise ValueError(f"unregistered role resources: {', '.join(sorted(unknown_resources))}")
        normalized_resources: dict[str, int | bool] = {}
        for key, value in self.resources.items():
            if isinstance(value, bool):
                normalized_resources[key] = value
            else:
                normalized_resources[key] = require_int(value, f"resources.{key}")
        self.resources = normalized_resources
        self.last_target_ids = require_identifier_list(self.last_target_ids, "last_target_ids")
        self.checked_target_ids = require_identifier_list(self.checked_target_ids, "checked_target_ids")
        self.effects = [effect if isinstance(effect, EffectState) else EffectState.from_dict(effect) for effect in self.effects]
        self.mimicked_role_id = RoleId(self.mimicked_role_id) if self.mimicked_role_id is not None else None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "role_id",
            "camp",
            "disabled",
            "used_abilities",
            "resources",
            "last_target_ids",
            "checked_target_ids",
            "effects",
            "mimicked_role_id",
        }
        assert_allowed_keys(data, allowed, required={"role_id", "camp"})
        effects = data.get("effects", [])
        if not isinstance(effects, list):
            raise TypeError("effects must be a list")
        return cls(
            role_id=RoleId(data["role_id"]),
            camp=CampId(data["camp"]),
            disabled=data.get("disabled", False),
            used_abilities=set(data.get("used_abilities", [])),
            resources=dict(data.get("resources", {})),
            last_target_ids=list(data.get("last_target_ids", [])),
            checked_target_ids=list(data.get("checked_target_ids", [])),
            effects=[EffectState.from_dict(item) for item in effects],
            mimicked_role_id=RoleId(data["mimicked_role_id"]) if data.get("mimicked_role_id") is not None else None,
        )
