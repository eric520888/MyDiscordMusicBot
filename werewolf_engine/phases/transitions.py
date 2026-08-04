"""Server-timed phase transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..ids import EventType, EventVisibility, GamePhase
from ..models import GameEvent, GameState, VoteState
from ..rules.players import alive_players


@dataclass(frozen=True, slots=True)
class PhaseTransition:
    game: GameState
    event: GameEvent


def _clone_game(game: GameState) -> GameState:
    return GameState.from_dict(game.to_dict())


def _make_phase_event(game: GameState, occurred_at: datetime, event_id_prefix: str) -> GameEvent:
    game.event_sequence += 1
    return GameEvent(
        event_id=f"{event_id_prefix}-{game.event_sequence}",
        sequence=game.event_sequence,
        event_type=EventType.PHASE_CHANGED,
        visibility=EventVisibility.PUBLIC,
        occurred_at=occurred_at,
        payload={"phase": game.phase.value, "round_number": game.round_number},
    )


def start_night(game: GameState, *, occurred_at: datetime, event_id_prefix: str) -> PhaseTransition:
    if game.phase not in {GamePhase.STARTING, GamePhase.DAY}:
        raise ValueError(f"cannot start night from {game.phase.value}")
    if game.pending_decisions:
        raise ValueError("cannot start night with pending decisions")
    updated = _clone_game(game)
    updated.phase = GamePhase.NIGHT_ACTIONS
    updated.round_number += 1
    updated.revision += 1
    updated.phase_started_at = occurred_at
    updated.phase_ends_at = occurred_at + timedelta(seconds=updated.settings.night_seconds)
    updated.night_actions.clear()
    updated.vote_state = None
    updated.pending_decisions.clear()
    event = _make_phase_event(updated, occurred_at, event_id_prefix)
    return PhaseTransition(updated, event)


def start_day(game: GameState, *, occurred_at: datetime, event_id_prefix: str) -> PhaseTransition:
    if game.phase not in {GamePhase.NIGHT_ACTIONS, GamePhase.NIGHT_WITCH, GamePhase.DAY}:
        raise ValueError(f"cannot start day from {game.phase.value}")
    if game.pending_decisions:
        raise ValueError("cannot start day with pending decisions")
    updated = _clone_game(game)
    updated.phase = GamePhase.DAY
    updated.revision += 1
    updated.phase_started_at = occurred_at
    duration = updated.settings.day_discussion_seconds + updated.settings.vote_seconds
    updated.phase_ends_at = occurred_at + timedelta(seconds=duration)
    eligible = {
        player.player_id
        for player in alive_players(updated)
        if player.vote_enabled
    }
    updated.vote_state = VoteState(
        eligible_voter_ids=eligible,
        visibility=updated.settings.vote_visibility,
    )
    updated.night_actions.clear()
    event = _make_phase_event(updated, occurred_at, event_id_prefix)
    return PhaseTransition(updated, event)
