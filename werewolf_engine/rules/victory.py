"""Base legacy-compatible victory check."""

from __future__ import annotations

from ..ids import CampId, WinnerId
from ..models import GameState
from .players import players_in_camp


def determine_winner(game: GameState) -> WinnerId | None:
    wolves = players_in_camp(game, CampId.WOLF, alive_only=True)
    gods = players_in_camp(game, CampId.GOD, alive_only=True)
    villagers = players_in_camp(game, CampId.VILLAGER, alive_only=True)

    if not wolves:
        return WinnerId.GOOD
    if not gods or not villagers:
        return WinnerId.WOLF
    if len(wolves) >= len(gods) + len(villagers):
        return WinnerId.WOLF
    return None
