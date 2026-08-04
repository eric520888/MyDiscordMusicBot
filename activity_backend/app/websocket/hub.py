"""Room-scoped WebSocket peer registry."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import WebSocket

from ..application.models import ActivityContext


@dataclass(frozen=True, slots=True)
class SocketPeer:
    socket: WebSocket
    context: ActivityContext


class RoomSocketHub:
    def __init__(self) -> None:
        self._peers: dict[str, list[SocketPeer]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, room_id: str) -> asyncio.Lock:
        return self._locks.setdefault(room_id, asyncio.Lock())

    def add(self, room_id: str, peer: SocketPeer) -> None:
        self._peers.setdefault(room_id, []).append(peer)

    def remove(self, room_id: str, socket: WebSocket) -> None:
        peers = self._peers.get(room_id, [])
        self._peers[room_id] = [peer for peer in peers if peer.socket is not socket]
        if not self._peers[room_id]:
            self._peers.pop(room_id, None)
            self._locks.pop(room_id, None)

    def peers(self, room_id: str) -> tuple[SocketPeer, ...]:
        return tuple(self._peers.get(room_id, ()))
