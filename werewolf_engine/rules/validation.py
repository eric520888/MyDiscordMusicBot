"""Board and lobby validation."""

from __future__ import annotations

from ..boards import get_board_definition
from ..ids import BoardId


def is_player_count_valid(board_id: BoardId | str, player_count: int) -> bool:
    if isinstance(player_count, bool) or not isinstance(player_count, int):
        return False
    board = get_board_definition(board_id)
    if board.fixed_composition:
        return player_count == len(board.roles)
    return board.min_players <= player_count <= board.max_players
