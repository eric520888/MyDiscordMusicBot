"""Deterministic role assignment with injected randomness."""

from __future__ import annotations

import random
from collections.abc import Sequence

from ..boards import get_board_definition
from ..ids import BoardId, RoleId
from ..models import RoleState
from ..roles import get_role_definition
from .validation import is_player_count_valid


class InvalidPlayerCount(ValueError):
    pass


def _flexible_roles(board_id: BoardId, player_count: int) -> list[RoleId]:
    wolves_count = max(1, player_count // 3)
    werewolves = wolf_kings = seers = witches = hunters = merchants = 0

    if board_id is BoardId.AUTO:
        if player_count < 6:
            werewolves, seers = 1, 1
        elif player_count < 10:
            werewolves, wolf_kings, seers, witches, hunters = wolves_count - 1, 1, 1, 1, 1
        else:
            werewolves, wolf_kings, seers, witches, hunters, merchants = wolves_count - 1, 1, 1, 1, 1, 1
    elif board_id is BoardId.WOLF_KING:
        seers, witches, hunters, wolf_kings = 1, 1, 1, 1
        werewolves = max(0, wolves_count - 1)
    elif board_id is BoardId.MERCHANT:
        seers, witches, hunters, merchants, wolf_kings = 1, 1, 1, 1, 1
        werewolves = max(0, wolves_count - 1)
    else:
        raise ValueError(f"board {board_id.value} has no flexible assignment rule")

    roles = (
        [RoleId.WEREWOLF] * werewolves
        + [RoleId.WOLF_KING] * wolf_kings
        + [RoleId.SEER] * seers
        + [RoleId.WITCH] * witches
        + [RoleId.HUNTER] * hunters
        + [RoleId.MERCHANT] * merchants
    )
    roles.extend([RoleId.VILLAGER] * (player_count - len(roles)))
    return roles


def assign_role_ids(
    board_id: BoardId | str,
    player_ids: Sequence[str],
    *,
    rng: random.Random,
) -> dict[str, RoleId]:
    """Return a shuffled role mapping without mutating player state."""

    parsed_board_id = BoardId(board_id)
    if len(set(player_ids)) != len(player_ids):
        raise ValueError("player_ids must be unique")
    if not is_player_count_valid(parsed_board_id, len(player_ids)):
        raise InvalidPlayerCount(
            f"board {parsed_board_id.value} does not support {len(player_ids)} players"
        )

    board = get_board_definition(parsed_board_id)
    role_ids = list(board.roles) if board.fixed_composition else _flexible_roles(parsed_board_id, len(player_ids))
    rng.shuffle(role_ids)
    return dict(zip(player_ids, role_ids, strict=True))


def create_initial_role_state(role_id: RoleId | str) -> RoleState:
    parsed_role_id = RoleId(role_id)
    definition = get_role_definition(parsed_role_id)
    resources: dict[str, int | bool] = {}
    if parsed_role_id in {RoleId.WITCH, RoleId.AWAKENED_WITCH}:
        resources.update(antidote_available=True, poison_available=True)
    if parsed_role_id is RoleId.AWAKENED_WITCH:
        resources["poison_recipes"] = 3
    if definition.shoot_count:
        resources["hunter_shots"] = definition.shoot_count
    if parsed_role_id is RoleId.AWAKENED_FOOL:
        resources["secret_body"] = True
    return RoleState(role_id=parsed_role_id, camp=definition.camp, resources=resources)
