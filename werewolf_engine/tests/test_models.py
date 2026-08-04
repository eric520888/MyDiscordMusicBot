from __future__ import annotations

import ast
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from werewolf_engine.ids import (
    ActionId,
    BoardId,
    CampId,
    EventType,
    EventVisibility,
    GamePhase,
    PlayerStatus,
    RoleId,
    VoteVisibility,
)
from werewolf_engine.models import (
    BoardConfiguration,
    EffectState,
    GameEvent,
    GameSettings,
    GameState,
    NightAction,
    PlayerState,
    ReplayEntry,
    RoleState,
    RoomState,
    VoteState,
)


NOW = datetime(2026, 8, 4, 8, 30, tzinfo=timezone.utc)


class GameSettingsTests(unittest.TestCase):
    def test_death_reveal_is_an_explicit_room_setting(self) -> None:
        with self.assertRaises(ValueError):
            GameSettings.from_dict({})

        hidden = GameSettings(reveal_roles_on_death=False)
        revealed = hidden.with_updates(reveal_roles_on_death=True)
        self.assertFalse(hidden.reveal_roles_on_death)
        self.assertTrue(revealed.reveal_roles_on_death)

    def test_settings_cannot_change_after_lock(self) -> None:
        settings = GameSettings(reveal_roles_on_death=True).lock()
        self.assertTrue(settings.locked)
        with self.assertRaises(ValueError):
            settings.with_updates(reveal_roles_on_death=False)


class ModelRoundTripTests(unittest.TestCase):
    def make_game(self) -> GameState:
        settings = GameSettings(
            reveal_roles_on_death=False,
            default_locale="zh-TW",
            vote_visibility=VoteVisibility.REVEAL_AFTER_RESULT,
        ).lock()
        players = [
            PlayerState("p1", "1001", 1, "Player 1", PlayerStatus.ALIVE, RoleId.SEER, ready=True),
            PlayerState("p2", "1002", 2, "Player 2", PlayerStatus.ALIVE, RoleId.WEREWOLF, ready=True),
        ]
        role_states = {
            "p1": RoleState(
                RoleId.SEER,
                CampId.GOD,
                used_abilities={"seer_check"},
                checked_target_ids=["p2"],
                effects=[EffectState("protected", "p1", "p1", 2, {"strength": 1})],
            ),
            "p2": RoleState(RoleId.WEREWOLF, CampId.WOLF),
        }
        action = NightAction(
            "p1",
            ActionId.SEER_CHECK,
            ("p2",),
            NOW,
            "request-1",
            1,
        )
        vote_state = VoteState(
            eligible_voter_ids={"p1", "p2"},
            ballots={"p1": "p2", "p2": None},
        )
        return GameState(
            game_id="game-1",
            room_id="room-1",
            board_id=BoardId.STANDARD,
            settings=settings,
            phase=GamePhase.NIGHT_ACTIONS,
            round_number=1,
            revision=4,
            phase_started_at=NOW,
            phase_ends_at=NOW + timedelta(minutes=2),
            players=players,
            role_states=role_states,
            night_actions=[action],
            vote_state=vote_state,
            pending_effects=[EffectState("pending-poison", "p1", "p2", 1)],
            pending_decisions=[{"decision_id": "witch", "player_id": "p1"}],
            processed_request_ids={"request-0"},
            event_sequence=9,
        )

    def test_game_state_round_trips_through_json(self) -> None:
        game = self.make_game()
        encoded = game.to_json()
        decoded = GameState.from_json(encoded)
        self.assertEqual(decoded, game)
        self.assertEqual(json.loads(encoded)["settings"]["reveal_roles_on_death"], False)

    def test_all_top_level_models_round_trip(self) -> None:
        settings = GameSettings(reveal_roles_on_death=True)
        models = [
            settings,
            PlayerState("p1", "1001", 1, "Player"),
            RoleState(RoleId.WITCH, CampId.GOD, resources={"antidote_available": True, "poison_available": True}),
            NightAction("p1", ActionId.WOLF_KILL, ("p2",), NOW, "r1", 1),
            VoteState({"p1"}, {"p1": None}),
            GameEvent("e1", 1, EventType.GAME_CREATED, EventVisibility.PUBLIC, NOW),
            ReplayEntry("e1", 1, 0, GamePhase.WAITING, EventType.GAME_CREATED, EventVisibility.PUBLIC, NOW),
            BoardConfiguration.from_definition(BoardId.STANDARD),
            RoomState(
                "room-1",
                "instance-1",
                "channel-1",
                "guild-1",
                "p1",
                ["p1"],
                settings,
                NOW,
                NOW,
                NOW + timedelta(hours=1),
            ),
        ]
        for model in models:
            with self.subTest(model=type(model).__name__):
                restored = type(model).from_json(model.to_json())
                self.assertEqual(restored, model)


class ModelValidationTests(unittest.TestCase):
    def test_unknown_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            PlayerState.from_dict(
                {
                    "player_id": "p1",
                    "discord_user_id": "1",
                    "seat": 1,
                    "display_name": "Player",
                    "discord_member": "must-not-enter-state",
                }
            )

    def test_non_json_event_payload_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            GameEvent(
                "e1",
                1,
                EventType.GAME_CREATED,
                EventVisibility.PUBLIC,
                NOW,
                payload={"discord_object": object()},
            )

    def test_unregistered_role_resources_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unregistered role resources"):
            RoleState(RoleId.WITCH, CampId.GOD, resources={"arbitrary": True})

    def test_role_camp_cannot_be_forged(self) -> None:
        with self.assertRaisesRegex(ValueError, "must use camp wolf"):
            RoleState(RoleId.WEREWOLF, CampId.GOD)

    def test_naive_timestamps_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            GameEvent(
                "e1",
                1,
                EventType.GAME_CREATED,
                EventVisibility.PUBLIC,
                datetime(2026, 8, 4, 8, 30),
            )

    def test_running_game_requires_locked_settings(self) -> None:
        with self.assertRaisesRegex(ValueError, "settings must be locked"):
            GameState(
                "game-1",
                "room-1",
                BoardId.STANDARD,
                GameSettings(reveal_roles_on_death=True),
                phase=GamePhase.NIGHT_ACTIONS,
            )


class ImportBoundaryTests(unittest.TestCase):
    def test_engine_source_has_no_transport_imports(self) -> None:
        root = Path(__file__).resolve().parents[1]
        forbidden = {"discord", "fastapi", "starlette", "redis", "websockets"}
        violations: list[str] = []
        for path in root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = {node.module.split(".")[0]}
                else:
                    continue
                if names & forbidden:
                    violations.append(f"{path.relative_to(root)}:{node.lineno}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
