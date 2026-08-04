from __future__ import annotations

import random
import unittest
from collections import Counter

from cogs.werewolf_system.catalog import (
    BOARD_AUTO,
    BOARD_MERCHANT,
    BOARD_SPECS,
    BOARD_WOLF_KING,
)
from cogs.werewolf_system.game import WerewolfGame
from cogs.werewolf_system.roles import (
    AwakenedGargoyle,
    AwakenedLonelyGirl,
    Gargoyle,
    Player,
    Seer,
    Villager,
    Wolf,
    WolfKing,
)

from test_werewolf import FakeBot, FakeChannel, FakeUser
from werewolf_engine.ids import BoardId, PlayerStatus, RoleId, WinnerId, parse_role_id
from werewolf_engine.models import BoardConfiguration, GameSettings, GameState, PlayerState
from werewolf_engine.rules import (
    InvalidPlayerCount,
    active_wolves,
    assign_role_ids,
    assign_configured_role_ids,
    create_initial_role_state,
    determine_winner,
    get_action_targets,
    get_night_action_limit,
    is_player_count_valid,
)


def make_legacy_game(roles: list[type]) -> WerewolfGame:
    host = FakeUser(999)
    game = WerewolfGame(FakeBot(), FakeChannel(), host)
    game.players = [Player(FakeUser(index + 1), role()) for index, role in enumerate(roles)]
    return game


def engine_from_legacy(game: WerewolfGame) -> GameState:
    players: list[PlayerState] = []
    role_states = {}
    for seat, legacy_player in enumerate(game.players, start=1):
        role_id = parse_role_id(legacy_player.role.name)
        player_id = str(legacy_player.id)
        players.append(
            PlayerState(
                player_id,
                str(legacy_player.id),
                seat,
                legacy_player.display_name,
                PlayerStatus(legacy_player.status),
                role_id,
            )
        )
        role_state = create_initial_role_state(role_id)
        role_state.checked_target_ids = [str(target_id) for target_id in legacy_player.role.checked_targets]
        if legacy_player.role.last_target is not None:
            last_targets = legacy_player.role.last_target
            if not isinstance(last_targets, list):
                last_targets = [last_targets]
            role_state.last_target_ids = [str(target_id) for target_id in last_targets]
        role_states[player_id] = role_state
    return GameState(
        "game-1",
        "room-1",
        BoardId.STANDARD,
        GameSettings(reveal_roles_on_death=False),
        players=players,
        role_states=role_states,
    )


class AssignmentParityTests(unittest.TestCase):
    def test_fixed_board_assignments_match_legacy_shuffle(self) -> None:
        for board_id in BOARD_SPECS:
            with self.subTest(board=board_id):
                legacy = make_legacy_game([Villager] * 12)
                legacy.board_id = board_id
                random.seed(20260804)
                self.assertTrue(legacy.assign_roles())

                assigned = assign_role_ids(
                    BoardId(board_id),
                    [str(player.id) for player in legacy.players],
                    rng=random.Random(20260804),
                )
                self.assertEqual(
                    [assigned[str(player.id)] for player in legacy.players],
                    [parse_role_id(player.role.name) for player in legacy.players],
                )

    def test_flexible_board_counts_match_legacy(self) -> None:
        cases = {
            BOARD_AUTO: (3, 5, 6, 9, 10, 20),
            BOARD_WOLF_KING: (5, 12, 20),
            BOARD_MERCHANT: (7, 12, 20),
        }
        for board_id, counts in cases.items():
            for count in counts:
                with self.subTest(board=board_id, count=count):
                    legacy = make_legacy_game([Villager] * count)
                    legacy.board_id = board_id
                    random.seed(42)
                    self.assertTrue(legacy.assign_roles())
                    assigned = assign_role_ids(
                        BoardId(board_id),
                        [str(player.id) for player in legacy.players],
                        rng=random.Random(42),
                    )
                    self.assertEqual(
                        Counter(assigned.values()),
                        Counter(parse_role_id(player.role.name) for player in legacy.players),
                    )

    def test_invalid_player_counts_are_rejected(self) -> None:
        self.assertFalse(is_player_count_valid(BoardId.STANDARD, 11))
        self.assertFalse(is_player_count_valid(BoardId.AUTO, 21))
        with self.assertRaises(InvalidPlayerCount):
            assign_role_ids(BoardId.STANDARD, [str(index) for index in range(11)], rng=random.Random(1))

    def test_explicit_activity_configuration_requires_engine_flag_and_exact_count(self) -> None:
        configuration = BoardConfiguration(
            BoardId.STANDARD,
            (RoleId.WEREWOLF, RoleId.SEER, RoleId.VILLAGER),
            3,
            3,
            True,
            engine_enabled=True,
        )
        assigned = assign_configured_role_ids(
            configuration,
            ("p1", "p2", "p3"),
            rng=random.Random(3),
        )
        self.assertCountEqual(assigned.values(), configuration.role_ids)
        with self.assertRaises(InvalidPlayerCount):
            assign_configured_role_ids(configuration, ("p1", "p2"), rng=random.Random(3))


class TargetingParityTests(unittest.TestCase):
    def assert_targets_match(self, legacy: WerewolfGame, actor_index: int, action: str) -> None:
        actor = legacy.players[actor_index]
        legacy_targets = {str(player.id) for player in legacy.get_action_targets(actor, action)}
        engine = engine_from_legacy(legacy)
        engine_targets = {player.player_id for player in get_action_targets(engine, str(actor.id), action)}
        self.assertEqual(engine_targets, legacy_targets)

    def test_wolf_cannot_target_regular_wolf(self) -> None:
        game = make_legacy_game([Wolf, WolfKing, Villager])
        self.assert_targets_match(game, 0, "wolf_kill")

    def test_awakened_self_kill_role_remains_targetable(self) -> None:
        game = make_legacy_game([Wolf, AwakenedGargoyle, Villager])
        self.assert_targets_match(game, 0, "wolf_kill")

    def test_convert_only_targets_adjacent_seats(self) -> None:
        game = make_legacy_game([Villager, AwakenedGargoyle, Wolf, Seer])
        self.assert_targets_match(game, 1, "convert")

    def test_checked_and_previous_targets_are_excluded(self) -> None:
        check_game = make_legacy_game([Gargoyle, Villager, Seer])
        check_game.players[0].role.checked_targets.add(check_game.players[1].id)
        self.assert_targets_match(check_game, 0, "exact_check")

        guard_game = make_legacy_game([Villager, Villager, Villager])
        guard_game.players[0].role.last_target = guard_game.players[1].id
        self.assert_targets_match(guard_game, 0, "guard")

    def test_action_limits_preserve_legacy_rules(self) -> None:
        self.assertEqual(get_night_action_limit("double_check"), 2)
        self.assertEqual(get_night_action_limit("wolf_kill", has_extra_wolf_kill=True), 2)
        self.assertEqual(get_night_action_limit("seer_check", has_action_bonus=True), 2)
        self.assertEqual(get_night_action_limit("seer_check"), 1)


class PlayerAndVictoryParityTests(unittest.TestCase):
    def test_isolated_wolf_only_joins_after_regular_wolves_die(self) -> None:
        legacy = make_legacy_game([Wolf, Gargoyle, Villager])
        engine = engine_from_legacy(legacy)
        self.assertEqual([player.player_id for player in active_wolves(engine)], ["1"])
        engine.players[0].status = PlayerStatus.DEAD
        self.assertEqual([player.player_id for player in active_wolves(engine)], ["2"])

    def test_base_victory_boundaries_match_legacy(self) -> None:
        cases = [
            ([Villager, Seer], WinnerId.GOOD),
            ([Wolf, Villager], WinnerId.WOLF),
            ([Wolf, Seer], WinnerId.WOLF),
            ([Wolf, Villager, Seer], None),
            ([Wolf, Villager, Seer, AwakenedLonelyGirl], None),
        ]
        legacy_names = {WinnerId.GOOD: "好人陣營", WinnerId.WOLF: "狼人陣營", None: None}
        for roles, expected in cases:
            with self.subTest(roles=[role.__name__ for role in roles]):
                legacy = make_legacy_game(roles)
                self.assertEqual(legacy.check_winner(), legacy_names[expected])
                self.assertEqual(determine_winner(engine_from_legacy(legacy)), expected)


if __name__ == "__main__":
    unittest.main()
