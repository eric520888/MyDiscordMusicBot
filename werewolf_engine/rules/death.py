"""Simultaneous death application and victory hand-off."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..events import build_player_died_event
from ..ids import ActionId, DeathCause, EventType, EventVisibility, GamePhase, PlayerStatus, RoleId
from ..models import GameEvent, GameState
from ..roles import get_role_definition
from .victory import determine_winner


@dataclass(frozen=True, slots=True)
class DeathRequest:
    player_id: str
    cause: DeathCause
    force_reveal: bool = False


@dataclass(frozen=True, slots=True)
class DeathResolution:
    game: GameState
    events: tuple[GameEvent, ...]
    pending_shooter_player_ids: tuple[str, ...]


def _clone_game(game: GameState) -> GameState:
    return GameState.from_dict(game.to_dict())


def _can_shoot_after_death(game: GameState, player_id: str, cause: DeathCause) -> bool:
    player = next(player for player in game.players if player.player_id == player_id)
    if player.role_id is None:
        return False
    definition = get_role_definition(player.role_id)
    if not definition.can_shoot:
        return False
    if player.role_id is RoleId.AWAKENED_HUNTER:
        return True
    return cause is not DeathCause.POISON


def _append_game_ended_event(game: GameState, occurred_at: datetime, event_id_prefix: str) -> GameEvent:
    winner = determine_winner(game)
    if winner is None:
        raise ValueError("cannot end a game without a winner")
    game.winner = winner
    game.ended_reason = "victory"
    game.phase = GamePhase.ENDED
    game.event_sequence += 1
    return GameEvent(
        event_id=f"{event_id_prefix}-{game.event_sequence}",
        sequence=game.event_sequence,
        event_type=EventType.GAME_ENDED,
        visibility=EventVisibility.PUBLIC,
        occurred_at=occurred_at,
        payload={"winner": winner.value},
    )


def resolve_deaths(
    game: GameState,
    deaths: tuple[DeathRequest, ...],
    *,
    occurred_at: datetime,
    event_id_prefix: str,
    continue_phase: GamePhase,
    after_shoot: str | None = None,
) -> DeathResolution:
    """Apply simultaneous deaths to a clone, preserving the caller's state."""

    if game.phase in {GamePhase.WAITING, GamePhase.STARTING, GamePhase.ENDED}:
        raise ValueError(f"cannot resolve deaths during {game.phase.value}")
    shoot_destination = after_shoot or ("day" if continue_phase is GamePhase.DAY else "night")
    if shoot_destination not in {"day", "night"}:
        raise ValueError("after_shoot must be 'day' or 'night'")
    death_ids = [death.player_id for death in deaths]
    if len(set(death_ids)) != len(death_ids):
        raise ValueError("a player cannot appear twice in one death batch")

    updated = _clone_game(game)
    players_by_id = {player.player_id: player for player in updated.players}
    normalized: list[DeathRequest] = []
    for request in deaths:
        player = players_by_id.get(request.player_id)
        if player is None:
            raise ValueError(f"unknown player: {request.player_id}")
        if player.status is not PlayerStatus.ALIVE:
            raise ValueError(f"player is already dead: {request.player_id}")
        normalized.append(DeathRequest(request.player_id, DeathCause(request.cause), request.force_reveal))

    # All deaths are marked first so victory and chained decisions see one snapshot.
    for request in normalized:
        players_by_id[request.player_id].status = PlayerStatus.DEAD

    events: list[GameEvent] = []
    pending_shooters: list[str] = []
    for request in normalized:
        event = build_player_died_event(
            updated,
            request.player_id,
            request.cause,
            event_id=f"{event_id_prefix}-{updated.event_sequence + 1}",
            occurred_at=occurred_at,
            force_reveal=request.force_reveal,
        )
        updated.event_sequence = event.sequence
        events.append(event)
        if _can_shoot_after_death(updated, request.player_id, request.cause):
            role_state = updated.role_states[request.player_id]
            shots = int(role_state.resources.get("hunter_shots", 1))
            pending_shooters.extend([request.player_id] * max(1, shots))

    updated.revision += 1
    if pending_shooters:
        updated.phase = GamePhase.ROLE_SHOOT
        updated.pending_decisions.extend(
            {
                "decision_id": f"shoot-{player_id}-{index}",
                "player_id": player_id,
                "action_id": ActionId.HUNTER_SHOOT.value,
                "continue_phase": GamePhase(continue_phase).value,
                "after_shoot": shoot_destination,
            }
            for index, player_id in enumerate(pending_shooters, start=1)
        )
    all_pending_shooters = tuple(
        str(decision["player_id"])
        for decision in updated.pending_decisions
        if decision.get("action_id") == ActionId.HUNTER_SHOOT.value
    )
    if all_pending_shooters:
        updated.phase = GamePhase.ROLE_SHOOT
    else:
        winner = determine_winner(updated)
        if winner is not None:
            events.append(_append_game_ended_event(updated, occurred_at, event_id_prefix))
        else:
            updated.phase = GamePhase(continue_phase)

    return DeathResolution(updated, tuple(events), all_pending_shooters)
