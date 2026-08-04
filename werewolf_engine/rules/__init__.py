"""Pure rules that operate only on serializable engine state."""

from .assignment import (
    InvalidPlayerCount,
    assign_configured_role_ids,
    assign_role_ids,
    create_initial_role_state,
)
from .death import DeathRequest, DeathResolution, resolve_deaths
from .players import active_wolves, alive_players, players_in_camp
from .targeting import get_action_targets, get_night_action_limit
from .validation import is_player_count_valid
from .victory import determine_winner
from .voting import DayVoteResult, resolve_wolf_votes, tally_day_vote

__all__ = [
    "InvalidPlayerCount",
    "DayVoteResult",
    "DeathRequest",
    "DeathResolution",
    "active_wolves",
    "alive_players",
    "assign_role_ids",
    "assign_configured_role_ids",
    "create_initial_role_state",
    "determine_winner",
    "get_action_targets",
    "get_night_action_limit",
    "is_player_count_valid",
    "players_in_camp",
    "resolve_wolf_votes",
    "resolve_deaths",
    "tally_day_vote",
]
