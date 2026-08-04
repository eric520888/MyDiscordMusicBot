"""Explicit 6-12 player board compositions for the standalone Activity MVP."""

from __future__ import annotations

from werewolf_engine.ids import BoardId, RoleId
from werewolf_engine.models import BoardConfiguration


_MVP_ROLES: dict[int, tuple[RoleId, ...]] = {
    6: (
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.SEER,
        RoleId.WITCH,
    ),
    7: (
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.SEER,
        RoleId.WITCH,
        RoleId.HUNTER,
    ),
    8: (
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.SEER,
        RoleId.WITCH,
        RoleId.HUNTER,
    ),
    9: (
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.SEER,
        RoleId.WITCH,
        RoleId.HUNTER,
    ),
    10: (
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.SEER,
        RoleId.WITCH,
        RoleId.HUNTER,
    ),
    11: (
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.SEER,
        RoleId.WITCH,
        RoleId.HUNTER,
    ),
    12: (
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.VILLAGER,
        RoleId.SEER,
        RoleId.WITCH,
        RoleId.HUNTER,
    ),
}


def build_mvp_board(player_count: int) -> BoardConfiguration:
    try:
        roles = _MVP_ROLES[player_count]
    except KeyError as exc:
        raise ValueError("狼人殺 Activity 需要 6 到 12 位玩家") from exc
    return BoardConfiguration(
        board_id=BoardId.AUTO,
        role_ids=roles,
        min_players=player_count,
        max_players=player_count,
        fixed_composition=True,
        engine_enabled=True,
    )
