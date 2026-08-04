"""Action target filters extracted from the legacy game helpers."""

from __future__ import annotations

from ..ids import ActionId, CampId, PlayerStatus, RoleId
from ..models import GameState, PlayerState
from ..roles import get_role_definition
from .players import alive_players


_NO_SELF_ACTIONS = frozenset(
    {
        ActionId.MERCHANT_GIVE,
        ActionId.CHARM,
        ActionId.AWAKENED_CHARM,
        ActionId.EXACT_CHECK,
        ActionId.WOLF_WITCH_CHECK,
        ActionId.PURE_WHITE_CHECK,
        ActionId.HUNT,
        ActionId.FEAR,
        ActionId.CONFUSE,
        ActionId.DEVOUR,
        ActionId.LIGHT_GUARD,
        ActionId.NIGHT_SERVANT,
        ActionId.MIRROR_CHECK,
        ActionId.MIMIC,
        ActionId.DOUBLE_CHECK,
        ActionId.FATE_BIND,
        ActionId.KNIGHT_DUEL,
        ActionId.CLAW_PASS,
        ActionId.SEER_CHECK,
        ActionId.DREAM,
        ActionId.CHOOSE_IDOL,
        ActionId.DREAM_SPEECH,
        ActionId.CONVERT,
    }
)

_NO_CONSECUTIVE_TARGET_ACTIONS = frozenset(
    {
        ActionId.GUARD,
        ActionId.FEAR,
        ActionId.CONFUSE,
        ActionId.DEVOUR,
        ActionId.LIGHT_GUARD,
        ActionId.AWAKENED_GUARD,
        ActionId.DREAM_SPEECH,
    }
)

_AWAKENED_SELF_KILL_ROLES = frozenset(
    {
        RoleId.AWAKENED_GARGOYLE,
        RoleId.AWAKENED_WOLF_KING,
        RoleId.AWAKENED_WHITE_WOLF_KING,
    }
)


def _camp(player: PlayerState) -> CampId:
    if player.role_id is None:
        raise ValueError(f"player {player.player_id} has no role")
    return get_role_definition(player.role_id).camp


def get_action_targets(
    game: GameState,
    actor_player_id: str,
    action_id: ActionId | str,
) -> list[PlayerState]:
    parsed_action = ActionId(action_id)
    actor = next((player for player in game.players if player.player_id == actor_player_id), None)
    if actor is None:
        raise ValueError(f"unknown actor: {actor_player_id}")
    if actor.status is not PlayerStatus.ALIVE or actor.spectator:
        return []
    if actor.role_id is None or actor.player_id not in game.role_states:
        raise ValueError("actor does not have role state")

    targets = alive_players(game)
    if parsed_action in _NO_SELF_ACTIONS:
        targets = [target for target in targets if target.player_id != actor.player_id]
    if parsed_action is ActionId.WOLF_KILL:
        targets = [
            target
            for target in targets
            if _camp(target) is not CampId.WOLF or target.role_id in _AWAKENED_SELF_KILL_ROLES
        ]
    if parsed_action in {ActionId.CHARM, ActionId.AWAKENED_CHARM, ActionId.WOLF_WITCH_CHECK, ActionId.DEVOUR}:
        targets = [target for target in targets if _camp(target) is not CampId.WOLF]
    if parsed_action is ActionId.CLAW_PASS:
        targets = [target for target in targets if _camp(target) is CampId.WOLF]
    if parsed_action is ActionId.CONVERT:
        seated_players = [player for player in game.players if not player.spectator]
        actor_index = seated_players.index(actor)
        adjacent_ids = {
            seated_players[(actor_index - 1) % len(seated_players)].player_id,
            seated_players[(actor_index + 1) % len(seated_players)].player_id,
        }
        targets = [target for target in targets if target.player_id in adjacent_ids]

    role_state = game.role_states[actor.player_id]
    if parsed_action in {ActionId.EXACT_CHECK, ActionId.MIRROR_CHECK}:
        checked = set(role_state.checked_target_ids)
        targets = [target for target in targets if target.player_id not in checked]
    if parsed_action in _NO_CONSECUTIVE_TARGET_ACTIONS:
        previous = set(role_state.last_target_ids)
        targets = [target for target in targets if target.player_id not in previous]
    return targets


def get_night_action_limit(
    action_id: ActionId | str,
    *,
    has_action_bonus: bool = False,
    has_extra_wolf_kill: bool = False,
) -> int:
    parsed_action = ActionId(action_id)
    if parsed_action in {ActionId.DOUBLE_CHECK, ActionId.FATE_BIND}:
        return 2
    if parsed_action is ActionId.WOLF_KILL and has_extra_wolf_kill:
        return 2
    return 1 + int(has_action_bonus)
