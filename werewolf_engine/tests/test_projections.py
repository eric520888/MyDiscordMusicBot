from __future__ import annotations

import unittest
from datetime import datetime, timezone

from werewolf_engine.events import build_player_died_event, project_state_for_player
from werewolf_engine.ids import (
    BoardId,
    DeathCause,
    EventType,
    EventVisibility,
    GamePhase,
    PlayerStatus,
    RoleId,
)
from werewolf_engine.models import GameEvent, GameSettings, GameState, PlayerProjection, PlayerState
from werewolf_engine.rules import create_initial_role_state


NOW = datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)


def make_game(*, reveal_roles_on_death: bool, ended: bool = False) -> GameState:
    settings = GameSettings(
        reveal_roles_on_death=reveal_roles_on_death,
        reveal_all_roles_at_game_end=True,
    ).lock()
    players = [
        PlayerState("p1", "1001", 1, "Wolf 1", PlayerStatus.ALIVE, RoleId.WEREWOLF),
        PlayerState("p2", "1002", 2, "Wolf 2", PlayerStatus.ALIVE, RoleId.WEREWOLF),
        PlayerState("p3", "1003", 3, "Seer", PlayerStatus.DEAD, RoleId.SEER),
        PlayerState("p4", "1004", 4, "Villager", PlayerStatus.ALIVE, RoleId.VILLAGER),
    ]
    return GameState(
        "game-1",
        "room-1",
        BoardId.STANDARD,
        settings,
        phase=GamePhase.ENDED if ended else GamePhase.DAY,
        round_number=1,
        players=players,
        role_states={player.player_id: create_initial_role_state(player.role_id) for player in players},
        ended_reason="normal" if ended else None,
        event_sequence=4,
    )


class DeathRevealProjectionTests(unittest.TestCase):
    def test_hidden_death_omits_role_from_event_and_other_players(self) -> None:
        game = make_game(reveal_roles_on_death=False)
        event = build_player_died_event(game, "p3", DeathCause.WOLF_ATTACK, event_id="e5", occurred_at=NOW)
        projection = project_state_for_player(game, "p4", events=[event])
        dead_player = next(player for player in projection.players if player.player_id == "p3")

        self.assertNotIn("role_id", event.payload)
        self.assertIsNone(dead_player.revealed_role_id)
        self.assertEqual(projection.events[0].payload, {"player_id": "p3", "cause": "wolf_attack"})

    def test_enabled_death_reveals_role(self) -> None:
        game = make_game(reveal_roles_on_death=True)
        event = build_player_died_event(game, "p3", DeathCause.EXILE, event_id="e5", occurred_at=NOW)
        projection = project_state_for_player(game, "p4", events=[event])
        dead_player = next(player for player in projection.players if player.player_id == "p3")

        self.assertEqual(event.payload["role_id"], "seer")
        self.assertIs(dead_player.revealed_role_id, RoleId.SEER)

    def test_special_role_can_force_reveal_explicitly(self) -> None:
        game = make_game(reveal_roles_on_death=False)
        event = build_player_died_event(
            game,
            "p3",
            DeathCause.ABILITY,
            event_id="e5",
            occurred_at=NOW,
            force_reveal=True,
        )
        self.assertEqual(event.payload["role_id"], "seer")

    def test_game_end_reveal_is_separate_from_death_setting(self) -> None:
        game = make_game(reveal_roles_on_death=False, ended=True)
        projection = project_state_for_player(game, "p4")
        self.assertEqual(
            {player.revealed_role_id for player in projection.players},
            {RoleId.WEREWOLF, RoleId.SEER, RoleId.VILLAGER},
        )


class PrivateProjectionTests(unittest.TestCase):
    def test_each_player_receives_only_their_role_state(self) -> None:
        game = make_game(reveal_roles_on_death=False)
        projection = project_state_for_player(game, "p4")
        self.assertIs(projection.self_role_state.role_id, RoleId.VILLAGER)
        self.assertIsNone(next(player for player in projection.players if player.player_id == "p1").revealed_role_id)

    def test_regular_wolves_know_pack_but_good_players_do_not(self) -> None:
        game = make_game(reveal_roles_on_death=False)
        self.assertEqual(project_state_for_player(game, "p1").wolf_team_player_ids, ("p1", "p2"))
        self.assertEqual(project_state_for_player(game, "p4").wolf_team_player_ids, ())

    def test_private_event_is_only_projected_to_recipient(self) -> None:
        game = make_game(reveal_roles_on_death=False)
        event = GameEvent(
            "e5",
            5,
            EventType.SEER_RESULT,
            EventVisibility.PLAYER_ONLY,
            NOW,
            payload={"target_player_id": "p1", "alignment": "wolf"},
            recipient_player_ids=frozenset({"p3"}),
        )
        self.assertEqual(len(project_state_for_player(game, "p3", events=[event]).events), 1)
        self.assertEqual(len(project_state_for_player(game, "p4", events=[event]).events), 0)

    def test_projection_round_trips_without_authoritative_state(self) -> None:
        game = make_game(reveal_roles_on_death=False)
        projection = project_state_for_player(game, "p4")
        restored = PlayerProjection.from_json(projection.to_json())
        self.assertEqual(restored, projection)
        self.assertNotIn("role_states", projection.to_dict())
        self.assertIsNot(projection.self_role_state, game.role_states["p4"])


if __name__ == "__main__":
    unittest.main()
