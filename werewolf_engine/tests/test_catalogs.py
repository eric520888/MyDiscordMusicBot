from __future__ import annotations

import unittest

from cogs.werewolf_system.catalog import BOARD_SPECS as LEGACY_BOARD_SPECS
from cogs.werewolf_system.catalog import ROLE_CATALOG as LEGACY_ROLE_CATALOG

from werewolf_engine.boards import BOARD_CATALOG, get_board_definition
from werewolf_engine.ids import (
    BoardId,
    CampId,
    LEGACY_ROLE_ALIASES,
    RoleId,
    parse_camp_id,
    parse_role_id,
)
from werewolf_engine.roles import ROLE_CATALOG, get_role_definition


class StableIdTests(unittest.TestCase):
    def test_every_legacy_role_has_one_stable_alias(self) -> None:
        self.assertEqual(set(LEGACY_ROLE_ALIASES), set(LEGACY_ROLE_CATALOG))
        self.assertEqual(set(LEGACY_ROLE_ALIASES.values()), set(RoleId))
        self.assertEqual(len(RoleId), 57)

    def test_parsers_accept_stable_and_legacy_values(self) -> None:
        self.assertIs(parse_role_id("werewolf"), RoleId.WEREWOLF)
        self.assertIs(parse_role_id("狼人"), RoleId.WEREWOLF)
        self.assertIs(parse_camp_id("wolf"), CampId.WOLF)
        self.assertIs(parse_camp_id("狼人陣營"), CampId.WOLF)
        with self.assertRaises(ValueError):
            parse_role_id("not-a-role")


class RoleCatalogTests(unittest.TestCase):
    def test_catalog_has_every_stable_role(self) -> None:
        self.assertEqual(set(ROLE_CATALOG), set(RoleId))
        self.assertEqual(sum(role.implemented_in_legacy for role in ROLE_CATALOG.values()), 46)

    def test_legacy_role_camps_match_new_catalog(self) -> None:
        for legacy_name, legacy_info in LEGACY_ROLE_CATALOG.items():
            with self.subTest(role=legacy_name):
                role_id = parse_role_id(legacy_name)
                self.assertEqual(
                    get_role_definition(role_id).camp,
                    parse_camp_id(legacy_info.camp),
                )

    def test_catalog_uses_localization_keys(self) -> None:
        role = get_role_definition(RoleId.SEER)
        self.assertEqual(role.name_key, "role.seer.name")
        self.assertEqual(role.description_key, "role.seer.description")
        self.assertNotIn("預言家", role.name_key)

    def test_only_mvp_roles_are_marked_ready(self) -> None:
        ready = {role.role_id for role in ROLE_CATALOG.values() if role.activity_mvp}
        self.assertEqual(
            ready,
            {RoleId.WEREWOLF, RoleId.VILLAGER, RoleId.SEER, RoleId.WITCH, RoleId.HUNTER},
        )


class BoardCatalogTests(unittest.TestCase):
    def test_catalog_preserves_all_legacy_board_ids(self) -> None:
        self.assertEqual(len(BOARD_CATALOG), 26)
        self.assertEqual({BoardId(board_id) for board_id in LEGACY_BOARD_SPECS}, set(BoardId) - {BoardId.AUTO, BoardId.WOLF_KING, BoardId.MERCHANT})

    def test_fixed_compositions_match_legacy_catalog(self) -> None:
        for legacy_board_id, legacy_spec in LEGACY_BOARD_SPECS.items():
            with self.subTest(board=legacy_board_id):
                board = get_board_definition(legacy_board_id)
                expected = tuple(parse_role_id(role_name) for role_name in legacy_spec.roles)
                self.assertEqual(board.roles, expected)
                self.assertEqual(board.min_players, 12)
                self.assertEqual(board.max_players, 12)
                self.assertTrue(board.fixed_composition)

    def test_flexible_boards_preserve_legacy_player_limits(self) -> None:
        expected = {
            BoardId.AUTO: (3, 20),
            BoardId.WOLF_KING: (5, 20),
            BoardId.MERCHANT: (7, 20),
        }
        for board_id, limits in expected.items():
            with self.subTest(board=board_id):
                board = get_board_definition(board_id)
                self.assertEqual((board.min_players, board.max_players), limits)
                self.assertFalse(board.fixed_composition)
                self.assertFalse(board.roles)


if __name__ == "__main__":
    unittest.main()
