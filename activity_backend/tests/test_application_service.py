from __future__ import annotations

import itertools
import random
import unittest
import ast
from datetime import datetime, timezone
from pathlib import Path

from activity_backend.app.application import (
    ActivityContext,
    ApplicationError,
    WerewolfApplicationService,
)
from activity_backend.app.rooms import InMemoryRoomRepository
from werewolf_engine.ids import BoardId, EventType, GamePhase, RoleId
from werewolf_engine.models import BoardConfiguration


NOW = datetime(2026, 8, 4, 18, 0, tzinfo=timezone.utc)


def make_context(user_id: str, *, instance: str = "instance-1") -> ActivityContext:
    return ActivityContext(
        discord_user_id=user_id,
        display_name=f"User {user_id}",
        instance_id=instance,
        channel_id="channel-1",
        guild_id="guild-1",
        locale="zh-TW",
    )


def make_configuration() -> BoardConfiguration:
    roles = (
        RoleId.WEREWOLF,
        RoleId.WEREWOLF,
        RoleId.SEER,
        RoleId.WITCH,
        RoleId.HUNTER,
        RoleId.VILLAGER,
    )
    return BoardConfiguration(
        BoardId.STANDARD,
        roles,
        6,
        6,
        True,
        engine_enabled=True,
    )


class ApplicationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        counter = itertools.count(1)
        self.repository = InMemoryRoomRepository()
        self.service = WerewolfApplicationService(
            self.repository,
            id_factory=lambda prefix: f"{prefix}-{next(counter)}",
            now=lambda: NOW,
        )
        self.host = make_context("100")
        self.room = self.service.create_room(self.host, reveal_roles_on_death=False)

    def join_players(self, count: int = 5) -> list[ActivityContext]:
        contexts = [make_context(str(200 + index)) for index in range(count)]
        for context in contexts:
            self.service.join_room(self.room.room.room_id, context)
        return contexts

    def ready_all(self, contexts: list[ActivityContext]) -> None:
        self.service.set_ready(self.room.room.room_id, self.host, ready=True)
        for context in contexts:
            self.service.set_ready(self.room.room.room_id, context, ready=True)

    def test_room_requires_unique_trusted_activity_binding(self) -> None:
        with self.assertRaises(ApplicationError) as duplicate:
            self.service.create_room(self.host, reveal_roles_on_death=True)
        self.assertEqual(duplicate.exception.code, "ROOM_ALREADY_EXISTS")

        wrong_binding = make_context("200", instance="different-instance")
        with self.assertRaises(ApplicationError) as mismatch:
            self.service.join_room(self.room.room.room_id, wrong_binding)
        self.assertEqual(mismatch.exception.code, "ROOM_BINDING_MISMATCH")

    def test_reconnect_reuses_same_player_identity(self) -> None:
        context = make_context("200")
        joined = self.service.join_room(self.room.room.room_id, context)
        original = joined.player_for_discord_user("200")
        reconnected = self.service.join_room(self.room.room.room_id, context)
        self.assertEqual(reconnected.player_for_discord_user("200").player_id, original.player_id)
        self.assertEqual(len(reconnected.players), 2)

    def test_host_controls_death_reveal_until_game_start(self) -> None:
        guest = self.join_players(1)[0]
        with self.assertRaises(ApplicationError) as forbidden:
            self.service.set_death_reveal(
                self.room.room.room_id,
                guest,
                reveal_roles_on_death=True,
            )
        self.assertEqual(forbidden.exception.code, "HOST_ONLY")

        updated = self.service.set_death_reveal(
            self.room.room.room_id,
            self.host,
            reveal_roles_on_death=True,
        )
        self.assertTrue(updated.room.settings.reveal_roles_on_death)

    def test_host_transfer_uses_earliest_remaining_seat(self) -> None:
        guests = self.join_players(2)
        updated = self.service.leave_room(self.room.room.room_id, self.host)
        self.assertEqual(updated.room.host_player_id, updated.player_for_discord_user(guests[0].discord_user_id).player_id)

    def test_non_host_and_unready_players_cannot_start(self) -> None:
        guests = self.join_players()
        with self.assertRaises(ApplicationError) as non_host:
            self.service.start_game(
                self.room.room.room_id,
                guests[0],
                configuration=make_configuration(),
                rng=random.Random(1),
            )
        self.assertEqual(non_host.exception.code, "HOST_ONLY")
        with self.assertRaises(ApplicationError) as unready:
            self.service.start_game(
                self.room.room.room_id,
                self.host,
                configuration=make_configuration(),
                rng=random.Random(1),
            )
        self.assertEqual(unready.exception.code, "PLAYERS_NOT_READY")

    def test_start_game_assigns_explicit_roles_and_locks_settings(self) -> None:
        guests = self.join_players()
        self.ready_all(guests)
        result = self.service.start_game(
            self.room.room.room_id,
            self.host,
            configuration=make_configuration(),
            rng=random.Random(8),
        )
        self.assertIs(result.aggregate.game.phase, GamePhase.STARTING)
        self.assertTrue(result.aggregate.room.settings.locked)
        self.assertFalse(result.aggregate.game.settings.reveal_roles_on_death)
        self.assertCountEqual(
            [player.role_id for player in result.aggregate.game.players],
            make_configuration().role_ids,
        )
        self.assertEqual(result.events[0].event_type, EventType.GAME_STARTED)
        self.assertEqual(
            sum(event.event_type is EventType.ROLE_ASSIGNED for event in result.events),
            6,
        )
        with self.assertRaises(ApplicationError) as locked:
            self.service.set_death_reveal(
                self.room.room.room_id,
                self.host,
                reveal_roles_on_death=True,
            )
        self.assertEqual(locked.exception.code, "SETTINGS_LOCKED")

    def test_first_night_and_projection_keep_other_roles_private(self) -> None:
        guests = self.join_players()
        self.ready_all(guests)
        self.service.start_game(
            self.room.room.room_id,
            self.host,
            configuration=make_configuration(),
            rng=random.Random(8),
        )
        advanced = self.service.start_first_night(self.room.room.room_id, self.host)
        projection = self.service.get_player_projection(self.room.room.room_id, guests[0])
        self.assertIs(advanced.aggregate.game.phase, GamePhase.NIGHT_ACTIONS)
        self.assertIsNotNone(projection.self_role_state)
        visible_other_roles = [
            player.revealed_role_id
            for player in projection.players
            if player.player_id != projection.viewer_player_id
        ]
        self.assertTrue(all(role_id is None for role_id in visible_other_roles))

    def test_repository_returns_isolated_copies(self) -> None:
        fetched = self.repository.get(self.room.room.room_id)
        fetched.players[fetched.room.host_player_id].display_name = "mutated"
        stored = self.repository.get(self.room.room.room_id)
        self.assertNotEqual(stored.players[stored.room.host_player_id].display_name, "mutated")

    def test_application_and_repository_layers_have_no_transport_imports(self) -> None:
        app_root = Path(__file__).resolve().parents[1] / "app"
        forbidden = {"discord", "fastapi", "starlette", "redis", "websockets"}
        violations: list[str] = []
        for folder in (app_root / "application", app_root / "rooms"):
            for path in folder.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        names = {alias.name.split(".")[0] for alias in node.names}
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        names = {node.module.split(".")[0]}
                    else:
                        continue
                    if names & forbidden:
                        violations.append(f"{path.name}:{node.lineno}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
