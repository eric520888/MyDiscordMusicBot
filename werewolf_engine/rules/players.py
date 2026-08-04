"""Pure player and camp queries."""

from __future__ import annotations

from ..ids import CampId, PlayerStatus
from ..models import GameState, PlayerState
from ..roles import get_role_definition


def alive_players(game: GameState) -> list[PlayerState]:
    return [player for player in game.players if player.status is PlayerStatus.ALIVE and not player.spectator]


def players_in_camp(game: GameState, camp: CampId | str, *, alive_only: bool = False) -> list[PlayerState]:
    parsed_camp = CampId(camp)
    candidates = alive_players(game) if alive_only else [player for player in game.players if not player.spectator]
    return [
        player
        for player in candidates
        if player.role_id is not None and get_role_definition(player.role_id).camp is parsed_camp
    ]


def active_wolves(game: GameState) -> list[PlayerState]:
    wolves = players_in_camp(game, CampId.WOLF, alive_only=True)
    regular = [
        player
        for player in wolves
        if get_role_definition(player.role_id).joins_wolf_vote
        and not get_role_definition(player.role_id).isolated_wolf
    ]
    if regular:
        return regular
    return [player for player in wolves if get_role_definition(player.role_id).isolated_wolf]
