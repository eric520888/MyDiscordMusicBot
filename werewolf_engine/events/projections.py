"""Create one player's view without exposing the authoritative game state."""

from __future__ import annotations

from collections.abc import Iterable

from ..ids import CampId, EventVisibility, GamePhase, PlayerStatus
from ..models import (
    GameEvent,
    GameState,
    PlayerProjection,
    ProjectedEvent,
    ProjectedPlayer,
)
from ..roles import get_role_definition


def is_event_visible_to(game: GameState, event: GameEvent, viewer_player_id: str) -> bool:
    if event.visibility is EventVisibility.PUBLIC:
        return True
    if event.visibility is EventVisibility.AFTER_GAME:
        return game.phase is GamePhase.ENDED
    return viewer_player_id in event.recipient_player_ids


def project_event(game: GameState, event: GameEvent, viewer_player_id: str) -> ProjectedEvent | None:
    if not is_event_visible_to(game, event, viewer_player_id):
        return None
    return ProjectedEvent(
        sequence=event.sequence,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        payload=event.payload,
    )


def _can_see_role(game: GameState, viewer_player_id: str, subject_player_id: str) -> bool:
    if viewer_player_id == subject_player_id:
        return True
    subject = next(player for player in game.players if player.player_id == subject_player_id)
    if game.phase is GamePhase.ENDED and game.settings.reveal_all_roles_at_game_end:
        return True
    return subject.status is PlayerStatus.DEAD and game.settings.reveal_roles_on_death


def _known_wolf_team(game: GameState, viewer_player_id: str) -> tuple[str, ...]:
    viewer = next(player for player in game.players if player.player_id == viewer_player_id)
    if viewer.role_id is None:
        return ()
    viewer_role = get_role_definition(viewer.role_id)
    if viewer_role.camp is not CampId.WOLF or viewer_role.isolated_wolf:
        return ()
    return tuple(
        player.player_id
        for player in game.players
        if player.role_id is not None
        and get_role_definition(player.role_id).camp is CampId.WOLF
        and get_role_definition(player.role_id).joins_wolf_vote
        and not get_role_definition(player.role_id).isolated_wolf
    )


def project_state_for_player(
    game: GameState,
    viewer_player_id: str,
    *,
    events: Iterable[GameEvent] = (),
) -> PlayerProjection:
    viewer = next((player for player in game.players if player.player_id == viewer_player_id), None)
    if viewer is None:
        raise ValueError(f"viewer is not in this game: {viewer_player_id}")

    projected_players = tuple(
        ProjectedPlayer(
            player_id=player.player_id,
            seat=player.seat,
            display_name=player.display_name,
            status=player.status,
            connected=player.connected,
            ready=player.ready,
            spectator=player.spectator,
            vote_enabled=player.vote_enabled,
            revealed_role_id=player.role_id if _can_see_role(game, viewer_player_id, player.player_id) else None,
        )
        for player in game.players
    )
    projected_events = tuple(
        projected
        for event in events
        if (projected := project_event(game, event, viewer_player_id)) is not None
    )
    self_role_state = game.role_states.get(viewer_player_id)
    if self_role_state is not None:
        self_role_state = type(self_role_state).from_dict(self_role_state.to_dict())
    return PlayerProjection(
        game_id=game.game_id,
        viewer_player_id=viewer_player_id,
        board_id=game.board_id,
        phase=game.phase,
        round_number=game.round_number,
        revision=game.revision,
        settings=game.settings,
        players=projected_players,
        phase_started_at=game.phase_started_at,
        phase_ends_at=game.phase_ends_at,
        self_role_state=self_role_state,
        wolf_team_player_ids=_known_wolf_team(game, viewer_player_id),
        pending_decisions=tuple(
            decision
            for decision in game.pending_decisions
            if decision.get("player_id") == viewer_player_id
        ),
        events=projected_events,
        winner=game.winner,
        ended_reason=game.ended_reason,
    )
