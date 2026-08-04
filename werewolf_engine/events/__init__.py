"""Domain event factories and per-player projections."""

from .factories import build_player_died_event
from .projections import is_event_visible_to, project_event, project_state_for_player

__all__ = [
    "build_player_died_event",
    "is_event_visible_to",
    "project_event",
    "project_state_for_player",
]
