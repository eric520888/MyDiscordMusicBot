"""Authorized lobby and game-start operations for the standalone Activity."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timedelta

from werewolf_engine.ids import EventType, EventVisibility, GamePhase, PlayerStatus
from werewolf_engine.models import (
    BoardConfiguration,
    GameEvent,
    GameSettings,
    GameState,
    PlayerProjection,
    PlayerState,
    RoomState,
)
from werewolf_engine.events import project_state_for_player
from werewolf_engine.phases import start_night
from werewolf_engine.rules import assign_configured_role_ids, create_initial_role_state

from ..rooms.repository import RepositoryConflict, RoomRepository
from .models import ActivityContext, IdFactory, RoomAggregate, RoomCommandResult


class ApplicationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class WerewolfApplicationService:
    def __init__(
        self,
        repository: RoomRepository,
        *,
        id_factory: IdFactory,
        now: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._now = now

    def _get_room(self, room_id: str) -> RoomAggregate:
        aggregate = self._repository.get(room_id)
        if aggregate is None:
            raise ApplicationError("ROOM_NOT_FOUND", "room does not exist")
        return aggregate

    @staticmethod
    def _assert_binding(aggregate: RoomAggregate, context: ActivityContext) -> None:
        expected = (
            aggregate.room.discord_instance_id,
            aggregate.room.discord_channel_id,
            aggregate.room.discord_guild_id,
        )
        if context.binding_key != expected:
            raise ApplicationError("ROOM_BINDING_MISMATCH", "Discord Activity context does not match this room")

    @staticmethod
    def _actor(aggregate: RoomAggregate, context: ActivityContext) -> PlayerState:
        player = aggregate.player_for_discord_user(context.discord_user_id)
        if player is None:
            raise ApplicationError("NOT_A_ROOM_MEMBER", "user is not a room member")
        return player

    def _save(self, aggregate: RoomAggregate, expected_revision: int) -> None:
        aggregate.revision = expected_revision + 1
        aggregate.room.updated_at = self._now()
        try:
            self._repository.save(aggregate, expected_revision=expected_revision)
        except RepositoryConflict as exc:
            raise ApplicationError("ROOM_REVISION_CONFLICT", str(exc)) from exc

    def create_room(
        self,
        context: ActivityContext,
        *,
        reveal_roles_on_death: bool,
    ) -> RoomAggregate:
        if self._repository.find_by_binding(context.binding_key) is not None:
            raise ApplicationError("ROOM_ALREADY_EXISTS", "this Activity instance already has a room")
        now = self._now()
        room_id = self._id_factory("room")
        player_id = self._id_factory("player")
        settings = GameSettings(
            reveal_roles_on_death=reveal_roles_on_death,
            default_locale=context.locale,
        )
        host = PlayerState(
            player_id=player_id,
            discord_user_id=context.discord_user_id,
            seat=1,
            display_name=context.display_name,
        )
        room = RoomState(
            room_id=room_id,
            discord_instance_id=context.instance_id,
            discord_channel_id=context.channel_id,
            discord_guild_id=context.guild_id,
            host_player_id=player_id,
            member_player_ids=[player_id],
            settings=settings,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=6),
        )
        aggregate = RoomAggregate(room=room, players={player_id: host})
        try:
            self._repository.add(aggregate)
        except RepositoryConflict as exc:
            raise ApplicationError("ROOM_ALREADY_EXISTS", str(exc)) from exc
        return self._get_room(room_id)

    def join_room(
        self,
        room_id: str,
        context: ActivityContext,
        *,
        spectator: bool = False,
    ) -> RoomAggregate:
        aggregate = self._get_room(room_id)
        self._assert_binding(aggregate, context)
        existing = aggregate.player_for_discord_user(context.discord_user_id)
        if existing is not None:
            expected_revision = aggregate.revision
            existing.connected = True
            existing.display_name = context.display_name
            self._save(aggregate, expected_revision)
            return self._get_room(room_id)
        if aggregate.game is not None:
            raise ApplicationError("GAME_ALREADY_STARTED", "new players cannot join an active game")
        if spectator and not aggregate.room.settings.allow_spectators:
            raise ApplicationError("SPECTATORS_DISABLED", "spectators are disabled for this room")
        expected_revision = aggregate.revision
        seat = max((player.seat for player in aggregate.players.values()), default=0) + 1
        player_id = self._id_factory("player")
        player = PlayerState(
            player_id=player_id,
            discord_user_id=context.discord_user_id,
            seat=seat,
            display_name=context.display_name,
            spectator=spectator,
            vote_enabled=not spectator,
        )
        aggregate.players[player_id] = player
        aggregate.room.member_player_ids.append(player_id)
        self._save(aggregate, expected_revision)
        return self._get_room(room_id)

    def leave_room(self, room_id: str, context: ActivityContext) -> RoomAggregate | None:
        aggregate = self._get_room(room_id)
        self._assert_binding(aggregate, context)
        actor = self._actor(aggregate, context)
        if aggregate.game is not None:
            raise ApplicationError("GAME_ALREADY_STARTED", "players cannot leave an active game")
        expected_revision = aggregate.revision
        del aggregate.players[actor.player_id]
        aggregate.room.member_player_ids.remove(actor.player_id)
        if not aggregate.players:
            self._repository.delete(room_id, expected_revision=expected_revision)
            return None
        if aggregate.room.host_player_id == actor.player_id:
            new_host = min(aggregate.players.values(), key=lambda player: player.seat)
            aggregate.room.host_player_id = new_host.player_id
        self._save(aggregate, expected_revision)
        return self._get_room(room_id)

    def set_ready(self, room_id: str, context: ActivityContext, *, ready: bool) -> RoomAggregate:
        aggregate = self._get_room(room_id)
        self._assert_binding(aggregate, context)
        actor = self._actor(aggregate, context)
        if aggregate.game is not None:
            raise ApplicationError("GAME_ALREADY_STARTED", "ready state is locked after game start")
        if actor.spectator:
            raise ApplicationError("SPECTATOR_CANNOT_READY", "spectators cannot ready for a seat")
        if not isinstance(ready, bool):
            raise ApplicationError("INVALID_READY_STATE", "ready must be a boolean")
        expected_revision = aggregate.revision
        actor.ready = ready
        self._save(aggregate, expected_revision)
        return self._get_room(room_id)

    def set_death_reveal(
        self,
        room_id: str,
        context: ActivityContext,
        *,
        reveal_roles_on_death: bool,
    ) -> RoomAggregate:
        aggregate = self._get_room(room_id)
        self._assert_binding(aggregate, context)
        actor = self._actor(aggregate, context)
        if actor.player_id != aggregate.room.host_player_id:
            raise ApplicationError("HOST_ONLY", "only the host can change room settings")
        if aggregate.game is not None or aggregate.room.settings.locked:
            raise ApplicationError("SETTINGS_LOCKED", "room settings are locked after game start")
        expected_revision = aggregate.revision
        aggregate.room.settings = aggregate.room.settings.with_updates(
            reveal_roles_on_death=reveal_roles_on_death
        )
        self._save(aggregate, expected_revision)
        return self._get_room(room_id)

    def start_game(
        self,
        room_id: str,
        context: ActivityContext,
        *,
        configuration: BoardConfiguration,
        rng: random.Random,
    ) -> RoomCommandResult:
        aggregate = self._get_room(room_id)
        self._assert_binding(aggregate, context)
        actor = self._actor(aggregate, context)
        if actor.player_id != aggregate.room.host_player_id:
            raise ApplicationError("HOST_ONLY", "only the host can start the game")
        if aggregate.game is not None:
            raise ApplicationError("GAME_ALREADY_STARTED", "room already has a game")
        seated = sorted(
            (player for player in aggregate.players.values() if not player.spectator),
            key=lambda player: player.seat,
        )
        if not seated or any(not player.ready for player in seated):
            raise ApplicationError("PLAYERS_NOT_READY", "all seated players must be ready")
        try:
            assignments = assign_configured_role_ids(
                configuration,
                [player.player_id for player in seated],
                rng=rng,
            )
        except ValueError as exc:
            raise ApplicationError("INVALID_BOARD_CONFIGURATION", str(exc)) from exc

        expected_revision = aggregate.revision
        settings = aggregate.room.settings.lock()
        for player in seated:
            player.role_id = assignments[player.player_id]
            player.status = PlayerStatus.ALIVE
        game_id = self._id_factory("game")
        game = GameState(
            game_id=game_id,
            room_id=room_id,
            board_id=configuration.board_id,
            settings=settings,
            phase=GamePhase.STARTING,
            revision=1,
            players=list(aggregate.players.values()),
            role_states={
                player.player_id: create_initial_role_state(player.role_id)
                for player in seated
            },
        )
        now = self._now()
        events: list[GameEvent] = []
        game.event_sequence += 1
        events.append(
            GameEvent(
                event_id=f"game-event-{game.event_sequence}",
                sequence=game.event_sequence,
                event_type=EventType.GAME_STARTED,
                visibility=EventVisibility.PUBLIC,
                occurred_at=now,
                payload={"board_id": configuration.board_id.value},
            )
        )
        for player in seated:
            game.event_sequence += 1
            events.append(
                GameEvent(
                    event_id=f"game-event-{game.event_sequence}",
                    sequence=game.event_sequence,
                    event_type=EventType.ROLE_ASSIGNED,
                    visibility=EventVisibility.PLAYER_ONLY,
                    occurred_at=now,
                    payload={"role_id": player.role_id.value},
                    recipient_player_ids=frozenset({player.player_id}),
                )
            )
        aggregate.game = game
        aggregate.room.game_id = game_id
        aggregate.room.settings = settings
        self._save(aggregate, expected_revision)
        return RoomCommandResult(self._get_room(room_id), tuple(events))

    def start_first_night(self, room_id: str, context: ActivityContext) -> RoomCommandResult:
        aggregate = self._get_room(room_id)
        self._assert_binding(aggregate, context)
        actor = self._actor(aggregate, context)
        if actor.player_id != aggregate.room.host_player_id:
            raise ApplicationError("HOST_ONLY", "only the host can advance the initial reveal")
        if aggregate.game is None:
            raise ApplicationError("GAME_NOT_STARTED", "room has no active game")
        expected_revision = aggregate.revision
        transition = start_night(
            aggregate.game,
            occurred_at=self._now(),
            event_id_prefix="game-event",
        )
        aggregate.game = transition.game
        self._save(aggregate, expected_revision)
        return RoomCommandResult(self._get_room(room_id), (transition.event,))

    def get_player_projection(self, room_id: str, context: ActivityContext) -> PlayerProjection:
        aggregate = self._get_room(room_id)
        self._assert_binding(aggregate, context)
        actor = self._actor(aggregate, context)
        if aggregate.game is None:
            raise ApplicationError("GAME_NOT_STARTED", "room has no active game")
        return project_state_for_player(aggregate.game, actor.player_id)
