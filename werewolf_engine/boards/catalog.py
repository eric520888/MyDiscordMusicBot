"""Immutable board compositions extracted from the legacy game."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from ..ids import BoardId, RoleId, localization_key


@dataclass(frozen=True, slots=True)
class BoardDefinition:
    board_id: BoardId
    roles: tuple[RoleId, ...]
    min_players: int
    max_players: int
    official: bool
    fixed_composition: bool
    activity_enabled: bool = False

    def __post_init__(self) -> None:
        if self.min_players < 1 or self.max_players < self.min_players:
            raise ValueError("invalid player limits")
        if self.fixed_composition and len(self.roles) != self.min_players:
            raise ValueError("fixed board role count must match player count")
        if not self.fixed_composition and self.roles:
            raise ValueError("flexible boards cannot declare a fixed composition")

    @property
    def name_key(self) -> str:
        return localization_key("board", self.board_id, "name")

    @property
    def description_key(self) -> str:
        return localization_key("board", self.board_id, "description")


def _roles(*items: tuple[RoleId, int]) -> tuple[RoleId, ...]:
    result: list[RoleId] = []
    for role_id, count in items:
        result.extend([role_id] * count)
    return tuple(result)


def _fixed(board_id: BoardId, roles: tuple[RoleId, ...], *, activity_enabled: bool = False) -> BoardDefinition:
    return BoardDefinition(board_id, roles, len(roles), len(roles), True, True, activity_enabled)


_CATALOG = {
    BoardId.AUTO: BoardDefinition(BoardId.AUTO, (), 3, 20, False, False),
    BoardId.STANDARD: _fixed(BoardId.STANDARD, _roles((RoleId.WEREWOLF, 4), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.FOOL, 1))),
    BoardId.WOLF_BEAUTY_KNIGHT: _fixed(BoardId.WOLF_BEAUTY_KNIGHT, _roles((RoleId.WEREWOLF, 3), (RoleId.WOLF_BEAUTY, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.KNIGHT, 1), (RoleId.GUARD, 1))),
    BoardId.WOLF_KING_GUARD: _fixed(BoardId.WOLF_KING_GUARD, _roles((RoleId.WEREWOLF, 3), (RoleId.WOLF_KING, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.GUARD, 1))),
    BoardId.WOLF_KING_DREAMER: _fixed(BoardId.WOLF_KING_DREAMER, _roles((RoleId.WEREWOLF, 3), (RoleId.WOLF_KING, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.DREAMER, 1))),
    BoardId.EVIL_KNIGHT: _fixed(BoardId.EVIL_KNIGHT, _roles((RoleId.WEREWOLF, 3), (RoleId.EVIL_KNIGHT, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.GUARD, 1))),
    BoardId.GARGOYLE_GRAVEKEEPER: _fixed(BoardId.GARGOYLE_GRAVEKEEPER, _roles((RoleId.WEREWOLF, 3), (RoleId.GARGOYLE, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.GRAVEKEEPER, 1))),
    BoardId.CRIMSON_DEMON_HUNTER: _fixed(BoardId.CRIMSON_DEMON_HUNTER, _roles((RoleId.WEREWOLF, 3), (RoleId.CRIMSON_APOSTLE, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.DEMON_HUNTER, 1), (RoleId.FOOL, 1))),
    BoardId.NIGHTMARE: _fixed(BoardId.NIGHTMARE, _roles((RoleId.WEREWOLF, 3), (RoleId.NIGHTMARE, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.DREAMER, 1))),
    BoardId.ETERNAL_ORDER: _fixed(BoardId.ETERNAL_ORDER, _roles((RoleId.WEREWOLF, 3), (RoleId.TIME_WOLF, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.GUARD, 1), (RoleId.ORDER_PRINCE, 1))),
    BoardId.PURE_WHITE: _fixed(BoardId.PURE_WHITE, _roles((RoleId.WEREWOLF, 3), (RoleId.WOLF_WITCH, 1), (RoleId.VILLAGER, 4), (RoleId.PURE_WHITE, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.GUARD, 1))),
    BoardId.TIME_WAVE: _fixed(BoardId.TIME_WAVE, _roles((RoleId.WEREWOLF, 3), (RoleId.NIGHT_MENTOR, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.GUARD, 1), (RoleId.DAY_SCHOLAR, 1))),
    BoardId.ANIMAL_DREAM: _fixed(BoardId.ANIMAL_DREAM, _roles((RoleId.WEREWOLF, 3), (RoleId.WOLF_BEAUTY, 1), (RoleId.ALPACA, 4), (RoleId.WHITE_CAT, 1), (RoleId.YOUNG_FOX, 1), (RoleId.BEAR, 1), (RoleId.PUFFERFISH, 1))),
    BoardId.HUNTER_SUN: _fixed(BoardId.HUNTER_SUN, _roles((RoleId.WEREWOLF, 3), (RoleId.ECLIPSE_MAID, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.DREAMER, 1), (RoleId.LIGHT_EARL, 1))),
    BoardId.AWAKENED_NIGHT: _fixed(BoardId.AWAKENED_NIGHT, _roles((RoleId.WEREWOLF, 3), (RoleId.NIGHT_NOBLE, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.DEMON_HUNTER, 1), (RoleId.AWAKENED_FOOL, 1))),
    BoardId.FRAGRANCE_FATE: _fixed(BoardId.FRAGRANCE_FATE, _roles((RoleId.WEREWOLF, 3), (RoleId.FRAGRANCE_PHANTOM, 1), (RoleId.VILLAGER, 4), (RoleId.AWAKENED_SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.GUARD, 1))),
    BoardId.AWAKENED_WOLF_KING: _fixed(BoardId.AWAKENED_WOLF_KING, _roles((RoleId.WEREWOLF, 3), (RoleId.AWAKENED_WOLF_KING, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.MERCHANT, 1), (RoleId.DREAMER, 1))),
    BoardId.MIRROR_MAZE: _fixed(BoardId.MIRROR_MAZE, _roles((RoleId.WEREWOLF, 3), (RoleId.AWAKENED_HIDDEN_WOLF, 1), (RoleId.VILLAGER, 4), (RoleId.MIRROR_GIRL, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.GUARD, 1))),
    BoardId.AWAKENED_WITCH: _fixed(BoardId.AWAKENED_WITCH, _roles((RoleId.WEREWOLF, 3), (RoleId.AWAKENED_WOLF_KING, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.AWAKENED_WITCH, 1), (RoleId.HUNTER, 1), (RoleId.GUARD, 1))),
    BoardId.DARK_NIGHT_STARS: _fixed(BoardId.DARK_NIGHT_STARS, _roles((RoleId.WEREWOLF, 3), (RoleId.AWAKENED_WOLF_BEAUTY, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.GUARD, 1), (RoleId.AWAKENED_HUNTER, 1))),
    BoardId.AWAKENED_LONELY_GIRL: _fixed(BoardId.AWAKENED_LONELY_GIRL, _roles((RoleId.WEREWOLF, 4), (RoleId.VILLAGER, 3), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.DREAMER, 1), (RoleId.HUNTER, 1), (RoleId.AWAKENED_LONELY_GIRL, 1))),
    BoardId.AWAKENED_GARGOYLE: _fixed(BoardId.AWAKENED_GARGOYLE, _roles((RoleId.WEREWOLF, 2), (RoleId.AWAKENED_GARGOYLE, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.GUARD, 1), (RoleId.GRAVEKEEPER, 1))),
    BoardId.MOONFALL_ABYSS: _fixed(BoardId.MOONFALL_ABYSS, _roles((RoleId.WEREWOLF, 3), (RoleId.AWAKENED_WHITE_WOLF_KING, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.AWAKENED_GUARD, 1))),
    BoardId.AWAKENED_DREAMER: _fixed(BoardId.AWAKENED_DREAMER, _roles((RoleId.AWAKENED_GARGOYLE, 1), (RoleId.WOLF_KING, 1), (RoleId.WEREWOLF, 1), (RoleId.VILLAGER, 4), (RoleId.SEER, 1), (RoleId.WITCH, 1), (RoleId.HUNTER, 1), (RoleId.GRAVEKEEPER, 1), (RoleId.AWAKENED_DREAMER, 1))),
    BoardId.WOLF_KING: BoardDefinition(BoardId.WOLF_KING, (), 5, 20, False, False),
    BoardId.MERCHANT: BoardDefinition(BoardId.MERCHANT, (), 7, 20, False, False),
}

BOARD_CATALOG: Mapping[BoardId, BoardDefinition] = MappingProxyType(_CATALOG)


def get_board_definition(board_id: BoardId | str) -> BoardDefinition:
    try:
        return BOARD_CATALOG[BoardId(board_id)]
    except (KeyError, ValueError) as exc:
        raise ValueError(f"unknown BoardId: {board_id}") from exc
