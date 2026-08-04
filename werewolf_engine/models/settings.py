"""Room-adjustable game settings."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Self

from ..ids import VoteVisibility
from .common import JsonModel, assert_allowed_keys, require_bool, require_int, require_string


@dataclass(frozen=True, slots=True)
class GameSettings(JsonModel):
    """Settings chosen in the lobby and locked when the game starts."""

    reveal_roles_on_death: bool
    default_locale: str = "zh-TW"
    reveal_all_roles_at_game_end: bool = True
    allow_spectators: bool = False
    vote_visibility: VoteVisibility = VoteVisibility.REVEAL_AFTER_RESULT
    night_seconds: int = 120
    day_discussion_seconds: int = 300
    vote_seconds: int = 60
    locked: bool = False

    def __post_init__(self) -> None:
        require_bool(self.reveal_roles_on_death, "reveal_roles_on_death")
        require_string(self.default_locale, "default_locale", max_length=32)
        if not self.default_locale:
            raise ValueError("default_locale cannot be empty")
        require_bool(self.reveal_all_roles_at_game_end, "reveal_all_roles_at_game_end")
        require_bool(self.allow_spectators, "allow_spectators")
        object.__setattr__(self, "vote_visibility", VoteVisibility(self.vote_visibility))
        require_int(self.night_seconds, "night_seconds", minimum=10)
        require_int(self.day_discussion_seconds, "day_discussion_seconds", minimum=10)
        require_int(self.vote_seconds, "vote_seconds", minimum=10)
        require_bool(self.locked, "locked")

    def with_updates(self, **changes: Any) -> Self:
        if self.locked:
            raise ValueError("game settings are locked after the game starts")
        if "locked" in changes:
            raise ValueError("use lock() to lock game settings")
        return replace(self, **changes)

    def lock(self) -> Self:
        return replace(self, locked=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "reveal_roles_on_death",
            "default_locale",
            "reveal_all_roles_at_game_end",
            "allow_spectators",
            "vote_visibility",
            "night_seconds",
            "day_discussion_seconds",
            "vote_seconds",
            "locked",
        }
        assert_allowed_keys(data, allowed, required={"reveal_roles_on_death"})
        return cls(
            reveal_roles_on_death=require_bool(data["reveal_roles_on_death"], "reveal_roles_on_death"),
            default_locale=data.get("default_locale", "zh-TW"),
            reveal_all_roles_at_game_end=data.get("reveal_all_roles_at_game_end", True),
            allow_spectators=data.get("allow_spectators", False),
            vote_visibility=VoteVisibility(data.get("vote_visibility", VoteVisibility.REVEAL_AFTER_RESULT)),
            night_seconds=data.get("night_seconds", 120),
            day_discussion_seconds=data.get("day_discussion_seconds", 300),
            vote_seconds=data.get("vote_seconds", 60),
            locked=data.get("locked", False),
        )
