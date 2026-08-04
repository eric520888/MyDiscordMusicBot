"""Selectable 3-12 player board compositions for the standalone Activity."""

from __future__ import annotations

from activity_backend.app.application.models import ActivityBoardId
from werewolf_engine.ids import BoardId, RoleId
from werewolf_engine.models import BoardConfiguration


_CLASSIC_ROLES: dict[int, tuple[RoleId, ...]] = {
    3: (RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.WITCH),
    4: (RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH),
    5: (RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH),
    6: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH),
    7: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    8: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    9: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    10: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    11: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    12: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
}

_BEGINNER_ROLES: dict[int, tuple[RoleId, ...]] = {
    3: (RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.WITCH),
    4: (RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.WITCH),
    5: (RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH),
    6: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH),
    7: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH),
    8: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    9: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    10: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    11: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    12: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
}

_POWER_ROLES: dict[int, tuple[RoleId, ...]] = {
    3: (RoleId.WEREWOLF, RoleId.WITCH, RoleId.HUNTER),
    4: (RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.WITCH, RoleId.HUNTER),
    5: (RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    6: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    7: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    8: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    9: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    10: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    11: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
    12: (RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER),
}

_BOARD_ROLES: dict[ActivityBoardId, dict[int, tuple[RoleId, ...]]] = {
    ActivityBoardId.CLASSIC: _CLASSIC_ROLES,
    ActivityBoardId.BEGINNER: _BEGINNER_ROLES,
    ActivityBoardId.POWER: _POWER_ROLES,
}


def build_mvp_board(
    player_count: int,
    board_id: ActivityBoardId | str = ActivityBoardId.CLASSIC,
) -> BoardConfiguration:
    try:
        parsed_board_id = ActivityBoardId(board_id)
        roles = _BOARD_ROLES[parsed_board_id][player_count]
    except (KeyError, ValueError) as exc:
        raise ValueError("狼人殺 Activity 需要 3 到 12 位玩家與有效板子") from exc
    return BoardConfiguration(
        board_id=BoardId.AUTO,
        role_ids=roles,
        min_players=player_count,
        max_players=player_count,
        fixed_composition=True,
        engine_enabled=True,
    )


def preview_mvp_boards(player_count: int) -> tuple[dict[str, object], ...]:
    preview_count = min(12, max(3, player_count))
    return tuple(
        {
            "board_id": board_id.value,
            "preview_player_count": preview_count,
            "role_ids": [role_id.value for role_id in _BOARD_ROLES[board_id][preview_count]],
        }
        for board_id in ActivityBoardId
    )
