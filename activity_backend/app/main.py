"""FastAPI entry point for the standalone Discord Werewolf Activity."""

from __future__ import annotations

import asyncio
import os
import random
import secrets
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .api.schemas import ConnectRequest, OAuthCodeRequest, SocketEnvelope
from .application.models import ActivityContext, RoomAggregate
from .application.service import ApplicationError, WerewolfApplicationService
from .auth import AuthError, DiscordAuth, DiscordIdentity
from .rooms.repository import InMemoryRoomRepository
from .services import build_mvp_board, preview_mvp_boards
from .websocket.hub import RoomSocketHub, SocketPeer


def _now() -> datetime:
    return datetime.now(UTC)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


SESSION_SECRET = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
auth = DiscordAuth(
    client_id=os.getenv("DISCORD_CLIENT_ID", ""),
    client_secret=os.getenv("DISCORD_CLIENT_SECRET", ""),
    session_secret=SESSION_SECRET,
)
repository = InMemoryRoomRepository()
service = WerewolfApplicationService(repository, id_factory=_new_id, now=_now)
hub = RoomSocketHub()

@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_phase_timeout_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Discord Werewolf Activity API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_origin_regex=r"^https://([a-z0-9-]+\.)?(discordsays\.com|discord\.com)$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def _bearer_token(value: str | None) -> str:
    if value is None or not value.startswith("Bearer "):
        raise AuthError("缺少登入工作階段")
    return value.removeprefix("Bearer ").strip()


def require_identity(authorization: str | None = Header(default=None)) -> DiscordIdentity:
    try:
        return auth.verify_session(_bearer_token(authorization))
    except AuthError as exc:
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": str(exc)}) from exc


def _context(identity: DiscordIdentity, body: ConnectRequest) -> ActivityContext:
    return ActivityContext(
        discord_user_id=identity.user_id,
        display_name=identity.display_name,
        instance_id=body.instance_id,
        channel_id=body.channel_id,
        guild_id=body.guild_id,
        locale=body.locale,
    )


def _safe_lobby_player(player: Any) -> dict[str, Any]:
    return {
        "player_id": player.player_id,
        "seat": player.seat,
        "display_name": player.display_name,
        "status": player.status.value,
        "connected": player.connected,
        "ready": player.ready,
        "spectator": player.spectator,
    }


def snapshot_for(aggregate: RoomAggregate, context: ActivityContext) -> dict[str, Any]:
    actor = aggregate.player_for_discord_user(context.discord_user_id)
    if actor is None:
        raise ApplicationError("NOT_A_ROOM_MEMBER", "user is not a room member")
    players = aggregate.game.players if aggregate.game is not None else aggregate.players.values()
    game = None
    if aggregate.game is not None:
        game = service.get_player_projection(aggregate.room.room_id, context).to_dict()
    seated_count = sum(not player.spectator for player in players)
    return {
        "server_time": _now().isoformat().replace("+00:00", "Z"),
        "self_player_id": actor.player_id,
        "is_host": actor.player_id == aggregate.room.host_player_id,
        "room": {
            "room_id": aggregate.room.room_id,
            "revision": aggregate.revision,
            "host_player_id": aggregate.room.host_player_id,
            "selected_board_id": aggregate.selected_board_id.value,
            "board_options": preview_mvp_boards(seated_count),
            "settings": aggregate.room.settings.to_dict(),
            "players": [_safe_lobby_player(player) for player in sorted(players, key=lambda item: item.seat)],
        },
        "game": game,
    }


async def broadcast_room(room_id: str) -> None:
    aggregate = repository.get(room_id)
    if aggregate is None:
        return
    failed: list[WebSocket] = []
    for peer in hub.peers(room_id):
        try:
            await peer.socket.send_json({"type": "state", "payload": snapshot_for(aggregate, peer.context)})
        except (RuntimeError, WebSocketDisconnect):
            failed.append(peer.socket)
    for socket in failed:
        hub.remove(room_id, socket)


async def _phase_timeout_loop() -> None:
    while True:
        await asyncio.sleep(1)
        for aggregate in repository.list_rooms():
            room_id = aggregate.room.room_id
            game = aggregate.game
            if game is None or game.phase_ends_at is None or game.phase_ends_at > _now():
                continue
            async with hub.lock_for(room_id):
                try:
                    result = service.resolve_expired_phase(room_id, rng=random.SystemRandom())
                except ApplicationError:
                    continue
            if result is not None:
                await broadcast_room(room_id)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "discord-werewolf-activity"}


@app.get("/api/config")
async def public_config() -> dict[str, str]:
    return {"discord_client_id": auth.client_id}


@app.post("/api/auth/token")
async def exchange_token(body: OAuthCodeRequest) -> dict[str, Any]:
    try:
        access_token, expires_in, identity = await auth.exchange_code(body.code)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail={"code": "OAUTH_FAILED", "message": str(exc)}) from exc
    return {
        "access_token": access_token,
        "expires_in": expires_in,
        "session_token": auth.issue_session(identity, ttl_seconds=expires_in),
        "user": {"id": identity.user_id, "display_name": identity.display_name},
    }


@app.post("/api/rooms/connect")
async def connect_room(
    body: ConnectRequest,
    identity: DiscordIdentity = Depends(require_identity),
) -> dict[str, Any]:
    context = _context(identity, body)
    try:
        aggregate = repository.find_by_binding(context.binding_key)
        if aggregate is None:
            aggregate = service.create_room(context, reveal_roles_on_death=False)
        else:
            aggregate = service.join_room(aggregate.room.room_id, context)
        result = snapshot_for(aggregate, context)
    except ApplicationError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    await broadcast_room(aggregate.room.room_id)
    return result


async def _handle_socket_command(room_id: str, context: ActivityContext, envelope: SocketEnvelope) -> None:
    aggregate = repository.get(room_id)
    if aggregate is None:
        raise ApplicationError("ROOM_NOT_FOUND", "room does not exist")
    payload = envelope.payload
    if envelope.type == "set_ready":
        ready = payload.get("ready")
        if not isinstance(ready, bool):
            raise ApplicationError("INVALID_READY_STATE", "ready must be a boolean")
        service.set_ready(room_id, context, ready=ready)
    elif envelope.type == "set_death_reveal":
        reveal = payload.get("reveal_roles_on_death")
        if not isinstance(reveal, bool):
            raise ApplicationError("INVALID_SETTING", "reveal_roles_on_death must be a boolean")
        service.set_death_reveal(
            room_id,
            context,
            reveal_roles_on_death=reveal,
        )
    elif envelope.type == "set_board":
        board_id = payload.get("board_id")
        if not isinstance(board_id, str):
            raise ApplicationError("INVALID_BOARD", "board_id must be a string")
        service.set_board(room_id, context, board_id=board_id)
    elif envelope.type == "start_game":
        seated_count = sum(not player.spectator for player in aggregate.players.values())
        service.start_game(
            room_id,
            context,
            configuration=build_mvp_board(seated_count, aggregate.selected_board_id),
            rng=random.SystemRandom(),
        )
    elif envelope.type == "advance_first_night":
        service.start_first_night(room_id, context)
    elif envelope.type == "submit_action":
        targets = payload.get("target_player_ids", [])
        if not isinstance(targets, list) or not all(isinstance(item, str) for item in targets):
            raise ApplicationError("INVALID_TARGET", "target_player_ids must be a string list")
        service.submit_game_action(
            room_id,
            context,
            action_id=str(payload.get("action_id", "")),
            target_player_ids=tuple(targets),
            request_id=envelope.request_id,
            expected_revision=int(payload.get("expected_revision", -1)),
            rng=random.SystemRandom(),
        )
    elif envelope.type == "ping":
        return
    else:
        raise ApplicationError("UNKNOWN_COMMAND", "unknown WebSocket command")


@app.websocket("/ws/rooms/{room_id}")
async def room_socket(
    socket: WebSocket,
    room_id: str,
    token: str,
    instance_id: str,
    channel_id: str,
    guild_id: str | None = None,
    locale: str = "zh-TW",
) -> None:
    try:
        identity = auth.verify_session(token)
        context = ActivityContext(
            discord_user_id=identity.user_id,
            display_name=identity.display_name,
            instance_id=instance_id,
            channel_id=channel_id,
            guild_id=guild_id,
            locale=locale,
        )
        aggregate = repository.get(room_id)
        if aggregate is None:
            raise ApplicationError("ROOM_NOT_FOUND", "room does not exist")
        service.get_room_for_context(room_id, context)
    except (AuthError, ApplicationError, ValueError):
        await socket.close(code=4401)
        return

    await socket.accept()
    hub.add(room_id, SocketPeer(socket, context))
    await broadcast_room(room_id)
    try:
        while True:
            raw = await socket.receive_json()
            try:
                envelope = SocketEnvelope.model_validate(raw)
                async with hub.lock_for(room_id):
                    await _handle_socket_command(room_id, context, envelope)
                await socket.send_json(
                    {"type": "action_result", "request_id": envelope.request_id, "success": True, "payload": {}}
                )
                await broadcast_room(room_id)
            except (ApplicationError, ValidationError, ValueError, TypeError) as exc:
                code = exc.code if isinstance(exc, ApplicationError) else "INVALID_COMMAND"
                request_id = raw.get("request_id") if isinstance(raw, dict) else None
                await socket.send_json(
                    {
                        "type": "error",
                        "request_id": request_id,
                        "code": code,
                        "message": str(exc),
                    }
                )
                if code == "REVISION_CONFLICT":
                    await broadcast_room(room_id)
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(room_id, socket)
