from __future__ import annotations

import unittest
from datetime import datetime, timezone

from werewolf_engine.ids import (
    BoardId,
    DeathCause,
    EventType,
    GamePhase,
    PlayerStatus,
    RoleId,
    WinnerId,
)
from werewolf_engine.models import GameSettings, GameState, PlayerState
from werewolf_engine.rules import DeathRequest, create_initial_role_state, resolve_deaths


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def make_game(
    roles: tuple[RoleId, ...],
    *,
    reveal_roles_on_death: bool = False,
    phase: GamePhase = GamePhase.NIGHT_WITCH,
) -> GameState:
    players = [
        PlayerState(f"p{index}", str(1000 + index), index, f"Player {index}", role_id=role_id)
        for index, role_id in enumerate(roles, start=1)
    ]
    return GameState(
        "game-1",
        "room-1",
        BoardId.STANDARD,
        GameSettings(reveal_roles_on_death=reveal_roles_on_death).lock(),
        phase=phase,
        round_number=1,
        players=players,
        role_states={player.player_id: create_initial_role_state(player.role_id) for player in players},
        event_sequence=10,
    )


class DeathResolutionTests(unittest.TestCase):
    def test_resolution_clones_state_and_hides_role_when_disabled(self) -> None:
        original = make_game((RoleId.WEREWOLF, RoleId.SEER, RoleId.HUNTER, RoleId.VILLAGER))
        result = resolve_deaths(
            original,
            (DeathRequest("p2", DeathCause.WOLF_ATTACK),),
            occurred_at=NOW,
            event_id_prefix="event",
            continue_phase=GamePhase.DAY,
        )
        self.assertIs(original.players[1].status, PlayerStatus.ALIVE)
        self.assertIs(result.game.players[1].status, PlayerStatus.DEAD)
        self.assertIs(result.game.phase, GamePhase.DAY)
        self.assertNotIn("role_id", result.events[0].payload)

    def test_enabled_setting_reveals_role_in_death_event(self) -> None:
        game = make_game(
            (RoleId.WEREWOLF, RoleId.SEER, RoleId.VILLAGER),
            reveal_roles_on_death=True,
        )
        result = resolve_deaths(
            game,
            (DeathRequest("p2", DeathCause.WOLF_ATTACK),),
            occurred_at=NOW,
            event_id_prefix="event",
            continue_phase=GamePhase.DAY,
        )
        self.assertEqual(result.events[0].payload["role_id"], "seer")

    def test_non_poisoned_hunter_creates_shoot_decision_before_victory(self) -> None:
        game = make_game((RoleId.WEREWOLF, RoleId.HUNTER, RoleId.VILLAGER))
        result = resolve_deaths(
            game,
            (DeathRequest("p2", DeathCause.WOLF_ATTACK),),
            occurred_at=NOW,
            event_id_prefix="event",
            continue_phase=GamePhase.DAY,
        )
        self.assertIs(result.game.phase, GamePhase.ROLE_SHOOT)
        self.assertEqual(result.pending_shooter_player_ids, ("p2",))
        self.assertIsNone(result.game.winner)
        self.assertEqual(result.game.pending_decisions[0]["action_id"], "hunter_shoot")

    def test_poisoned_hunter_cannot_shoot(self) -> None:
        game = make_game((RoleId.WEREWOLF, RoleId.HUNTER, RoleId.VILLAGER))
        result = resolve_deaths(
            game,
            (DeathRequest("p2", DeathCause.POISON),),
            occurred_at=NOW,
            event_id_prefix="event",
            continue_phase=GamePhase.DAY,
        )
        self.assertEqual(result.pending_shooter_player_ids, ())
        self.assertIs(result.game.phase, GamePhase.ENDED)
        self.assertIs(result.game.winner, WinnerId.WOLF)

    def test_victory_appends_game_ended_event(self) -> None:
        game = make_game((RoleId.WEREWOLF, RoleId.SEER, RoleId.VILLAGER), phase=GamePhase.DAY)
        result = resolve_deaths(
            game,
            (DeathRequest("p1", DeathCause.EXILE),),
            occurred_at=NOW,
            event_id_prefix="event",
            continue_phase=GamePhase.NIGHT_ACTIONS,
        )
        self.assertIs(result.game.phase, GamePhase.ENDED)
        self.assertIs(result.game.winner, WinnerId.GOOD)
        self.assertEqual([event.event_type for event in result.events], [EventType.PLAYER_DIED, EventType.GAME_ENDED])
        self.assertEqual(result.events[-1].payload, {"winner": "good"})

    def test_duplicate_or_dead_death_requests_are_rejected(self) -> None:
        game = make_game((RoleId.WEREWOLF, RoleId.SEER, RoleId.VILLAGER))
        duplicate = (
            DeathRequest("p2", DeathCause.WOLF_ATTACK),
            DeathRequest("p2", DeathCause.POISON),
        )
        with self.assertRaisesRegex(ValueError, "twice"):
            resolve_deaths(
                game,
                duplicate,
                occurred_at=NOW,
                event_id_prefix="event",
                continue_phase=GamePhase.DAY,
            )


if __name__ == "__main__":
    unittest.main()
