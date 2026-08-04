"""Pure event factories that enforce public-information settings."""

from __future__ import annotations

from datetime import datetime

from ..ids import DeathCause, EventType, EventVisibility
from ..models import GameEvent, GameState


def build_player_died_event(
    game: GameState,
    player_id: str,
    cause: DeathCause | str,
    *,
    event_id: str,
    occurred_at: datetime,
    force_reveal: bool = False,
) -> GameEvent:
    """Build a public death event without leaking a hidden role."""

    player = next((candidate for candidate in game.players if candidate.player_id == player_id), None)
    if player is None:
        raise ValueError(f"unknown player: {player_id}")
    payload: dict[str, str] = {
        "player_id": player.player_id,
        "cause": DeathCause(cause).value,
    }
    if (game.settings.reveal_roles_on_death or force_reveal) and player.role_id is not None:
        payload["role_id"] = player.role_id.value
    return GameEvent(
        event_id=event_id,
        sequence=game.event_sequence + 1,
        event_type=EventType.PLAYER_DIED,
        visibility=EventVisibility.PUBLIC,
        occurred_at=occurred_at,
        payload=payload,
    )
