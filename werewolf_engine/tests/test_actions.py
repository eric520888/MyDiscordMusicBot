from __future__ import annotations

import random
import unittest
from datetime import datetime, timezone

from werewolf_engine.actions import (
    GameRuleError,
    resolve_day_vote,
    resolve_night_actions,
    submit_day_vote,
    submit_hunter_decision,
    submit_night_action,
    submit_witch_action,
)
from werewolf_engine.events import project_state_for_player
from werewolf_engine.ids import (
    ActionId,
    BoardId,
    EventType,
    GamePhase,
    PlayerStatus,
    RoleId,
    VoteVisibility,
    WinnerId,
)
from werewolf_engine.models import GameSettings, GameState, PlayerState
from werewolf_engine.phases import start_day
from werewolf_engine.rules import create_initial_role_state
from werewolf_engine.rules import DeathRequest, resolve_deaths
from werewolf_engine.ids import DeathCause


NOW = datetime(2026, 8, 4, 16, 0, tzinfo=timezone.utc)


def make_game(
    phase: GamePhase = GamePhase.NIGHT_ACTIONS,
    *,
    reveal_roles_on_death: bool = False,
    vote_visibility: VoteVisibility = VoteVisibility.REVEAL_AFTER_RESULT,
) -> GameState:
    roles = (
        RoleId.WEREWOLF,
        RoleId.SEER,
        RoleId.WITCH,
        RoleId.HUNTER,
        RoleId.VILLAGER,
    )
    players = [
        PlayerState(f"p{index}", str(index), index, f"Player {index}", role_id=role_id)
        for index, role_id in enumerate(roles, start=1)
    ]
    return GameState(
        "game-1",
        "room-1",
        BoardId.STANDARD,
        GameSettings(
            reveal_roles_on_death=reveal_roles_on_death,
            vote_visibility=vote_visibility,
        ).lock(),
        phase=phase,
        round_number=1,
        players=players,
        role_states={player.player_id: create_initial_role_state(player.role_id) for player in players},
    )


def submit_required_night_actions(game: GameState, wolf_target: str = "p4") -> GameState:
    wolf = submit_night_action(
        game,
        actor_player_id="p1",
        action_id=ActionId.WOLF_KILL,
        target_player_ids=(wolf_target,),
        request_id="wolf-request",
        expected_revision=game.revision,
        submitted_at=NOW,
        event_id_prefix="event",
    ).game
    return submit_night_action(
        wolf,
        actor_player_id="p2",
        action_id=ActionId.SEER_CHECK,
        target_player_ids=("p1",),
        request_id="seer-request",
        expected_revision=wolf.revision,
        submitted_at=NOW,
        event_id_prefix="event",
    ).game


class NightActionTests(unittest.TestCase):
    def test_wrong_role_illegal_target_and_dead_actor_are_rejected(self) -> None:
        game = make_game()
        with self.assertRaisesRegex(GameRuleError, "cannot submit a wolf vote") as wrong_role:
            submit_night_action(
                game,
                actor_player_id="p2",
                action_id=ActionId.WOLF_KILL,
                target_player_ids=("p4",),
                request_id="r1",
                expected_revision=0,
                submitted_at=NOW,
                event_id_prefix="event",
            )
        self.assertEqual(wrong_role.exception.code, "ACTION_NOT_ALLOWED")

        with self.assertRaises(GameRuleError) as teammate:
            submit_night_action(
                game,
                actor_player_id="p1",
                action_id=ActionId.WOLF_KILL,
                target_player_ids=("p1",),
                request_id="r2",
                expected_revision=0,
                submitted_at=NOW,
                event_id_prefix="event",
            )
        self.assertEqual(teammate.exception.code, "INVALID_TARGET")

        game.players[0].status = PlayerStatus.DEAD
        with self.assertRaises(GameRuleError) as dead:
            submit_night_action(
                game,
                actor_player_id="p1",
                action_id=ActionId.WOLF_KILL,
                target_player_ids=("p4",),
                request_id="r3",
                expected_revision=0,
                submitted_at=NOW,
                event_id_prefix="event",
            )
        self.assertEqual(dead.exception.code, "PLAYER_DEAD")

    def test_request_id_is_idempotent_before_revision_check(self) -> None:
        game = make_game()
        first = submit_night_action(
            game,
            actor_player_id="p1",
            action_id=ActionId.WOLF_KILL,
            target_player_ids=("p4",),
            request_id="same-request",
            expected_revision=0,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        duplicate = submit_night_action(
            first.game,
            actor_player_id="p1",
            action_id=ActionId.WOLF_KILL,
            target_player_ids=("p5",),
            request_id="same-request",
            expected_revision=0,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(len(duplicate.game.night_actions), 1)

    def test_new_request_cannot_submit_same_action_twice(self) -> None:
        game = make_game()
        first = submit_night_action(
            game,
            actor_player_id="p1",
            action_id=ActionId.WOLF_KILL,
            target_player_ids=("p4",),
            request_id="r1",
            expected_revision=0,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        with self.assertRaises(GameRuleError) as duplicate_action:
            submit_night_action(
                first.game,
                actor_player_id="p1",
                action_id=ActionId.WOLF_KILL,
                target_player_ids=("p5",),
                request_id="r2",
                expected_revision=first.game.revision,
                submitted_at=NOW,
                event_id_prefix="event",
            )
        self.assertEqual(duplicate_action.exception.code, "ACTION_ALREADY_SUBMITTED")

    def test_resolution_waits_for_required_actions(self) -> None:
        game = make_game()
        with self.assertRaises(GameRuleError) as pending:
            resolve_night_actions(game, rng=random.Random(1), occurred_at=NOW, event_id_prefix="event")
        self.assertEqual(pending.exception.code, "ACTIONS_PENDING")

    def test_seer_result_is_private_and_witch_receives_decision(self) -> None:
        game = submit_required_night_actions(make_game())
        result = resolve_night_actions(
            game,
            rng=random.Random(1),
            occurred_at=NOW,
            event_id_prefix="event",
        )
        self.assertIs(result.game.phase, GamePhase.NIGHT_WITCH)
        self.assertEqual(result.game.pending_decisions[0]["wolf_target_ids"], ["p4"])
        self.assertEqual(
            project_state_for_player(result.game, "p3").pending_decisions[0]["wolf_target_ids"],
            ["p4"],
        )
        self.assertEqual(project_state_for_player(result.game, "p5").pending_decisions, ())
        seer_events = [event for event in result.events if event.event_type is EventType.SEER_RESULT]
        self.assertEqual(seer_events[0].payload["alignment"], "wolf")
        self.assertEqual(len(project_state_for_player(result.game, "p2", events=seer_events).events), 1)
        self.assertEqual(len(project_state_for_player(result.game, "p5", events=seer_events).events), 0)

    def test_witch_can_save_victim_and_setting_remains_locked(self) -> None:
        primary = resolve_night_actions(
            submit_required_night_actions(make_game()),
            rng=random.Random(1),
            occurred_at=NOW,
            event_id_prefix="event",
        )
        result = submit_witch_action(
            primary.game,
            actor_player_id="p3",
            action_id=ActionId.WITCH_ANTIDOTE,
            target_player_ids=("p4",),
            request_id="witch-request",
            expected_revision=primary.game.revision,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        self.assertIs(result.game.phase, GamePhase.DAY)
        self.assertIs(result.game.players[3].status, PlayerStatus.ALIVE)
        self.assertFalse(result.game.role_states["p3"].resources["antidote_available"])
        self.assertTrue(result.game.settings.locked)
        self.assertIsNotNone(result.game.vote_state)

    def test_witch_poison_and_wolf_attack_resolve_simultaneously(self) -> None:
        primary = resolve_night_actions(
            submit_required_night_actions(make_game(), wolf_target="p5"),
            rng=random.Random(1),
            occurred_at=NOW,
            event_id_prefix="event",
        )
        result = submit_witch_action(
            primary.game,
            actor_player_id="p3",
            action_id=ActionId.WITCH_POISON,
            target_player_ids=("p1",),
            request_id="witch-poison",
            expected_revision=primary.game.revision,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        self.assertIs(result.game.phase, GamePhase.ENDED)
        self.assertIs(result.game.winner, WinnerId.GOOD)
        self.assertIs(result.game.players[0].status, PlayerStatus.DEAD)
        self.assertIs(result.game.players[4].status, PlayerStatus.DEAD)
        self.assertFalse(result.game.role_states["p3"].resources["poison_available"])


class DayVoteActionTests(unittest.TestCase):
    def make_day_game(self, *, visibility: VoteVisibility = VoteVisibility.REVEAL_AFTER_RESULT) -> GameState:
        transition = start_day(
            make_game(vote_visibility=visibility),
            occurred_at=NOW,
            event_id_prefix="event",
        )
        return transition.game

    def cast(self, game: GameState, voter: str, target: str | None, request: str) -> GameState:
        return submit_day_vote(
            game,
            voter_player_id=voter,
            target_player_id=target,
            request_id=request,
            expected_revision=game.revision,
            submitted_at=NOW,
            event_id_prefix="event",
        ).game

    def test_vote_tie_starts_next_night(self) -> None:
        game = self.make_day_game()
        targets = {"p1": "p2", "p2": "p1", "p3": "p1", "p4": "p2", "p5": None}
        for voter, target in targets.items():
            game = self.cast(game, voter, target, f"vote-{voter}")
        result = resolve_day_vote(game, occurred_at=NOW, event_id_prefix="event")
        self.assertIs(result.game.phase, GamePhase.NIGHT_ACTIONS)
        self.assertEqual(result.game.round_number, 2)
        self.assertTrue(all(player.status is PlayerStatus.ALIVE for player in result.game.players))

    def test_exiling_last_wolf_ends_game_and_honors_hidden_roles(self) -> None:
        game = self.make_day_game()
        for voter in ("p1", "p2", "p3", "p4", "p5"):
            game = self.cast(game, voter, "p1", f"vote-{voter}")
        result = resolve_day_vote(game, occurred_at=NOW, event_id_prefix="event")
        death_event = next(event for event in result.events if event.event_type is EventType.PLAYER_DIED)
        self.assertIs(result.game.phase, GamePhase.ENDED)
        self.assertIs(result.game.winner, WinnerId.GOOD)
        self.assertNotIn("role_id", death_event.payload)

    def test_anonymous_vote_events_do_not_reveal_voter_or_ballots(self) -> None:
        game = self.make_day_game(visibility=VoteVisibility.ANONYMOUS)
        submitted = submit_day_vote(
            game,
            voter_player_id="p1",
            target_player_id="p2",
            request_id="vote-p1",
            expected_revision=game.revision,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        self.assertNotIn("voter_player_id", submitted.events[0].payload)
        game = submitted.game
        for voter in ("p2", "p3", "p4", "p5"):
            game = self.cast(game, voter, "p2", f"vote-{voter}")
        resolved = resolve_day_vote(game, occurred_at=NOW, event_id_prefix="event")
        vote_event = next(event for event in resolved.events if event.event_type is EventType.VOTE_RESOLVED)
        self.assertNotIn("ballots", vote_event.payload)

    def test_revision_conflict_and_dead_voter_are_rejected(self) -> None:
        game = self.make_day_game()
        with self.assertRaises(GameRuleError) as conflict:
            submit_day_vote(
                game,
                voter_player_id="p1",
                target_player_id="p2",
                request_id="vote",
                expected_revision=999,
                submitted_at=NOW,
                event_id_prefix="event",
            )
        self.assertEqual(conflict.exception.code, "REVISION_CONFLICT")

        game.players[0].status = PlayerStatus.DEAD
        with self.assertRaises(GameRuleError) as dead:
            submit_day_vote(
                game,
                voter_player_id="p1",
                target_player_id="p2",
                request_id="vote-dead",
                expected_revision=game.revision,
                submitted_at=NOW,
                event_id_prefix="event",
            )
        self.assertEqual(dead.exception.code, "VOTER_NOT_ELIGIBLE")


class HunterDecisionTests(unittest.TestCase):
    def make_night_hunter_death(self) -> GameState:
        primary = resolve_night_actions(
            submit_required_night_actions(make_game(), wolf_target="p4"),
            rng=random.Random(1),
            occurred_at=NOW,
            event_id_prefix="event",
        )
        return submit_witch_action(
            primary.game,
            actor_player_id="p3",
            action_id=ActionId.ABSTAIN,
            target_player_ids=(),
            request_id="witch-skip",
            expected_revision=primary.game.revision,
            submitted_at=NOW,
            event_id_prefix="event",
        ).game

    def test_hunter_can_shoot_last_wolf_before_victory(self) -> None:
        game = self.make_night_hunter_death()
        self.assertIs(game.phase, GamePhase.ROLE_SHOOT)
        result = submit_hunter_decision(
            game,
            actor_player_id="p4",
            target_player_id="p1",
            request_id="hunter-shot",
            expected_revision=game.revision,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        self.assertIs(result.game.phase, GamePhase.ENDED)
        self.assertIs(result.game.winner, WinnerId.GOOD)
        self.assertIs(result.game.players[0].status, PlayerStatus.DEAD)

    def test_hunter_can_skip_and_continue_to_day(self) -> None:
        game = self.make_night_hunter_death()
        result = submit_hunter_decision(
            game,
            actor_player_id="p4",
            target_player_id=None,
            request_id="hunter-skip",
            expected_revision=game.revision,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        self.assertIs(result.game.phase, GamePhase.DAY)
        self.assertIsNotNone(result.game.vote_state)

    def test_exiled_hunter_skip_continues_to_next_night(self) -> None:
        game = start_day(make_game(), occurred_at=NOW, event_id_prefix="event").game
        for voter in ("p1", "p2", "p3", "p4", "p5"):
            game = submit_day_vote(
                game,
                voter_player_id=voter,
                target_player_id="p4",
                request_id=f"vote-{voter}",
                expected_revision=game.revision,
                submitted_at=NOW,
                event_id_prefix="event",
            ).game
        exiled = resolve_day_vote(game, occurred_at=NOW, event_id_prefix="event")
        self.assertIs(exiled.game.phase, GamePhase.ROLE_SHOOT)
        self.assertEqual(exiled.game.pending_decisions[0]["after_shoot"], "night")
        skipped = submit_hunter_decision(
            exiled.game,
            actor_player_id="p4",
            target_player_id=None,
            request_id="hunter-skip",
            expected_revision=exiled.game.revision,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        self.assertIs(skipped.game.phase, GamePhase.NIGHT_ACTIONS)
        self.assertEqual(skipped.game.round_number, 2)

    def test_only_current_shooter_can_decide(self) -> None:
        game = self.make_night_hunter_death()
        with self.assertRaises(GameRuleError) as wrong:
            submit_hunter_decision(
                game,
                actor_player_id="p2",
                target_player_id="p1",
                request_id="wrong-shooter",
                expected_revision=game.revision,
                submitted_at=NOW,
                event_id_prefix="event",
            )
        self.assertEqual(wrong.exception.code, "ACTION_NOT_ALLOWED")

    def test_shooting_another_hunter_queues_chain_decision(self) -> None:
        roles = (RoleId.WEREWOLF, RoleId.HUNTER, RoleId.HUNTER, RoleId.VILLAGER)
        players = [
            PlayerState(f"p{index}", str(index), index, f"Player {index}", role_id=role_id)
            for index, role_id in enumerate(roles, start=1)
        ]
        game = GameState(
            "game-chain",
            "room-1",
            BoardId.STANDARD,
            GameSettings(reveal_roles_on_death=False).lock(),
            phase=GamePhase.NIGHT_WITCH,
            round_number=1,
            players=players,
            role_states={player.player_id: create_initial_role_state(player.role_id) for player in players},
        )
        first = resolve_deaths(
            game,
            (DeathRequest("p2", DeathCause.WOLF_ATTACK),),
            occurred_at=NOW,
            event_id_prefix="event",
            continue_phase=GamePhase.DAY,
            after_shoot="day",
        )
        chained = submit_hunter_decision(
            first.game,
            actor_player_id="p2",
            target_player_id="p3",
            request_id="chain-shot",
            expected_revision=first.game.revision,
            submitted_at=NOW,
            event_id_prefix="event",
        )
        self.assertIs(chained.game.phase, GamePhase.ROLE_SHOOT)
        self.assertEqual(chained.game.pending_decisions[0]["player_id"], "p3")


if __name__ == "__main__":
    unittest.main()
