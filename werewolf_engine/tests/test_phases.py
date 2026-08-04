from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from werewolf_engine.ids import BoardId, GamePhase, PlayerStatus, RoleId
from werewolf_engine.models import GameSettings, GameState, PlayerState
from werewolf_engine.phases import start_day, start_night
from werewolf_engine.rules import create_initial_role_state


NOW = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)


def make_game(phase: GamePhase) -> GameState:
    players = [
        PlayerState("p1", "1", 1, "Wolf", PlayerStatus.ALIVE, RoleId.WEREWOLF),
        PlayerState("p2", "2", 2, "Seer", PlayerStatus.ALIVE, RoleId.SEER),
        PlayerState("p3", "3", 3, "Dead", PlayerStatus.DEAD, RoleId.VILLAGER),
    ]
    return GameState(
        "game-1",
        "room-1",
        BoardId.STANDARD,
        GameSettings(reveal_roles_on_death=False, night_seconds=90, day_discussion_seconds=120, vote_seconds=30).lock(),
        phase=phase,
        round_number=1,
        players=players,
        role_states={player.player_id: create_initial_role_state(player.role_id) for player in players},
    )


class PhaseTransitionTests(unittest.TestCase):
    def test_start_night_uses_server_deadline_and_resets_round_data(self) -> None:
        game = make_game(GamePhase.DAY)
        result = start_night(game, occurred_at=NOW, event_id_prefix="event")
        self.assertIs(result.game.phase, GamePhase.NIGHT_ACTIONS)
        self.assertEqual(result.game.round_number, 2)
        self.assertEqual(result.game.phase_ends_at, NOW + timedelta(seconds=90))
        self.assertIsNone(result.game.vote_state)
        self.assertIs(game.phase, GamePhase.DAY)

    def test_start_day_builds_vote_state_from_living_voters(self) -> None:
        game = make_game(GamePhase.NIGHT_ACTIONS)
        result = start_day(game, occurred_at=NOW, event_id_prefix="event")
        self.assertIs(result.game.phase, GamePhase.DAY)
        self.assertEqual(result.game.vote_state.eligible_voter_ids, {"p1", "p2"})
        self.assertEqual(result.game.phase_ends_at, NOW + timedelta(seconds=150))
        self.assertEqual(result.event.payload, {"phase": "day", "round_number": 1})

    def test_invalid_transition_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot start night"):
            start_night(make_game(GamePhase.NIGHT_ACTIONS), occurred_at=NOW, event_id_prefix="event")


if __name__ == "__main__":
    unittest.main()
