"""Repository port and isolated in-memory development adapter."""

from __future__ import annotations

from typing import Protocol

from ..application.models import RoomAggregate


class RepositoryConflict(RuntimeError):
    pass


class RoomRepository(Protocol):
    def add(self, aggregate: RoomAggregate) -> None: ...

    def get(self, room_id: str) -> RoomAggregate | None: ...

    def find_by_binding(self, binding: tuple[str, str, str | None]) -> RoomAggregate | None: ...

    def save(self, aggregate: RoomAggregate, *, expected_revision: int) -> None: ...

    def delete(self, room_id: str, *, expected_revision: int) -> None: ...

    def list_rooms(self) -> tuple[RoomAggregate, ...]: ...


def _clone(aggregate: RoomAggregate) -> RoomAggregate:
    return RoomAggregate.from_dict(aggregate.to_dict())


class InMemoryRoomRepository:
    def __init__(self) -> None:
        self._rooms: dict[str, RoomAggregate] = {}
        self._binding_index: dict[tuple[str, str, str | None], str] = {}

    def add(self, aggregate: RoomAggregate) -> None:
        room_id = aggregate.room.room_id
        binding = (
            aggregate.room.discord_instance_id,
            aggregate.room.discord_channel_id,
            aggregate.room.discord_guild_id,
        )
        if room_id in self._rooms or binding in self._binding_index:
            raise RepositoryConflict("room ID or Discord binding already exists")
        self._rooms[room_id] = _clone(aggregate)
        self._binding_index[binding] = room_id

    def get(self, room_id: str) -> RoomAggregate | None:
        aggregate = self._rooms.get(room_id)
        return _clone(aggregate) if aggregate is not None else None

    def find_by_binding(self, binding: tuple[str, str, str | None]) -> RoomAggregate | None:
        room_id = self._binding_index.get(binding)
        return self.get(room_id) if room_id is not None else None

    def save(self, aggregate: RoomAggregate, *, expected_revision: int) -> None:
        current = self._rooms.get(aggregate.room.room_id)
        if current is None:
            raise RepositoryConflict("room does not exist")
        if current.revision != expected_revision:
            raise RepositoryConflict("room revision conflict")
        if aggregate.revision != expected_revision + 1:
            raise RepositoryConflict("saved aggregate must advance one revision")
        self._rooms[aggregate.room.room_id] = _clone(aggregate)

    def delete(self, room_id: str, *, expected_revision: int) -> None:
        current = self._rooms.get(room_id)
        if current is None:
            return
        if current.revision != expected_revision:
            raise RepositoryConflict("room revision conflict")
        binding = (
            current.room.discord_instance_id,
            current.room.discord_channel_id,
            current.room.discord_guild_id,
        )
        del self._rooms[room_id]
        self._binding_index.pop(binding, None)

    def list_rooms(self) -> tuple[RoomAggregate, ...]:
        return tuple(_clone(aggregate) for aggregate in self._rooms.values())
