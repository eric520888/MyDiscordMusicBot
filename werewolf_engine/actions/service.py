"""Pure command handlers for the first Activity-compatible rules slice."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..ids import (
    ActionId,
    CampId,
    DeathCause,
    EventType,
    EventVisibility,
    GamePhase,
    PlayerStatus,
    RoleId,
    VoteVisibility,
)
from ..models import GameEvent, GameState, NightAction
from ..models.common import require_identifier, require_int
from ..phases import start_day, start_night
from ..roles import get_role_definition
from ..rules import (
    DeathRequest,
    active_wolves,
    alive_players,
    get_action_targets,
    resolve_deaths,
    resolve_wolf_votes,
    tally_day_vote,
)


class GameRuleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CommandResult:
    game: GameState
    events: tuple[GameEvent, ...] = ()
    duplicate: bool = False


def _clone_game(game: GameState) -> GameState:
    return GameState.from_dict(game.to_dict())


def _check_request(game: GameState, request_id: str, expected_revision: int) -> CommandResult | None:
    try:
        require_identifier(request_id, "request_id")
        require_int(expected_revision, "expected_revision")
    except (TypeError, ValueError) as exc:
        raise GameRuleError("INVALID_COMMAND", str(exc)) from exc
    if request_id in game.processed_request_ids:
        return CommandResult(_clone_game(game), duplicate=True)
    if expected_revision != game.revision:
        raise GameRuleError("REVISION_CONFLICT", "game state revision does not match")
    return None


def _player(game: GameState, player_id: str):
    player = next((candidate for candidate in game.players if candidate.player_id == player_id), None)
    if player is None:
        raise GameRuleError("PLAYER_NOT_FOUND", "player is not in this game")
    return player


def _append_event(
    game: GameState,
    *,
    event_type: EventType,
    visibility: EventVisibility,
    occurred_at: datetime,
    event_id_prefix: str,
    payload: dict,
    recipients: frozenset[str] = frozenset(),
) -> GameEvent:
    game.event_sequence += 1
    return GameEvent(
        event_id=f"{event_id_prefix}-{game.event_sequence}",
        sequence=game.event_sequence,
        event_type=event_type,
        visibility=visibility,
        occurred_at=occurred_at,
        payload=payload,
        recipient_player_ids=recipients,
    )


def submit_night_action(
    game: GameState,
    *,
    actor_player_id: str,
    action_id: ActionId | str,
    target_player_ids: tuple[str, ...],
    request_id: str,
    expected_revision: int,
    submitted_at: datetime,
    event_id_prefix: str,
) -> CommandResult:
    duplicate = _check_request(game, request_id, expected_revision)
    if duplicate is not None:
        return duplicate
    if game.phase is not GamePhase.NIGHT_ACTIONS:
        raise GameRuleError("WRONG_PHASE", "night action is not available in this phase")
    actor = _player(game, actor_player_id)
    if actor.status is not PlayerStatus.ALIVE:
        raise GameRuleError("PLAYER_DEAD", "dead players cannot act")
    parsed_action = ActionId(action_id)
    if parsed_action is ActionId.WOLF_KILL:
        if actor.player_id not in {wolf.player_id for wolf in active_wolves(game)}:
            raise GameRuleError("ACTION_NOT_ALLOWED", "player cannot submit a wolf vote")
    elif parsed_action is ActionId.SEER_CHECK:
        if actor.role_id is not RoleId.SEER or game.role_states[actor.player_id].disabled:
            raise GameRuleError("ACTION_NOT_ALLOWED", "player cannot use seer check")
    else:
        raise GameRuleError("UNSUPPORTED_ACTION", "action is not part of this MVP phase")
    if len(target_player_ids) != 1:
        raise GameRuleError("INVALID_TARGET_COUNT", "this action requires exactly one target")
    legal_targets = {target.player_id for target in get_action_targets(game, actor.player_id, parsed_action)}
    if target_player_ids[0] not in legal_targets:
        raise GameRuleError("INVALID_TARGET", "target is not legal for this action")
    if any(
        action.actor_player_id == actor.player_id
        and action.action_id is parsed_action
        and action.round_number == game.round_number
        for action in game.night_actions
    ):
        raise GameRuleError("ACTION_ALREADY_SUBMITTED", "this action was already submitted")

    updated = _clone_game(game)
    updated.night_actions.append(
        NightAction(
            actor.player_id,
            parsed_action,
            target_player_ids,
            submitted_at,
            request_id,
            updated.round_number,
        )
    )
    updated.processed_request_ids.add(request_id)
    updated.revision += 1
    event = _append_event(
        updated,
        event_type=EventType.ACTION_ACCEPTED,
        visibility=EventVisibility.PLAYER_ONLY,
        occurred_at=submitted_at,
        event_id_prefix=event_id_prefix,
        payload={"action_id": parsed_action.value, "target_player_ids": list(target_player_ids)},
        recipients=frozenset({actor.player_id}),
    )
    return CommandResult(updated, (event,))


def _required_primary_night_tasks(game: GameState) -> set[tuple[str, ActionId]]:
    tasks = {(wolf.player_id, ActionId.WOLF_KILL) for wolf in active_wolves(game)}
    for player in alive_players(game):
        if player.role_id is RoleId.SEER and not game.role_states[player.player_id].disabled:
            tasks.add((player.player_id, ActionId.SEER_CHECK))
    return tasks


def _start_day_after_resolution(
    game: GameState,
    events: list[GameEvent],
    *,
    occurred_at: datetime,
    event_id_prefix: str,
) -> CommandResult:
    if game.phase is GamePhase.DAY:
        transition = start_day(game, occurred_at=occurred_at, event_id_prefix=event_id_prefix)
        events.append(transition.event)
        game = transition.game
    return CommandResult(game, tuple(events))


def _continue_after_shooting(
    game: GameState,
    events: list[GameEvent],
    *,
    destination: str,
    occurred_at: datetime,
    event_id_prefix: str,
) -> CommandResult:
    if game.phase in {GamePhase.ENDED, GamePhase.ROLE_SHOOT}:
        return CommandResult(game, tuple(events))
    if destination == "day":
        transition = start_day(game, occurred_at=occurred_at, event_id_prefix=event_id_prefix)
    elif destination == "night":
        transition = start_night(game, occurred_at=occurred_at, event_id_prefix=event_id_prefix)
    else:
        raise ValueError("unknown shooting continuation")
    events.append(transition.event)
    return CommandResult(transition.game, tuple(events))


def resolve_night_actions(
    game: GameState,
    *,
    rng: random.Random,
    occurred_at: datetime,
    event_id_prefix: str,
    allow_incomplete: bool = False,
) -> CommandResult:
    if game.phase is not GamePhase.NIGHT_ACTIONS:
        raise GameRuleError("WRONG_PHASE", "primary night actions cannot be resolved now")
    submitted = {
        (action.actor_player_id, action.action_id)
        for action in game.night_actions
        if action.round_number == game.round_number
    }
    missing = _required_primary_night_tasks(game) - submitted
    if missing and not allow_incomplete:
        raise GameRuleError("ACTIONS_PENDING", "required night actions are still pending")

    updated = _clone_game(game)
    events: list[GameEvent] = []
    wolves = active_wolves(updated)
    wolf_ids = {wolf.player_id for wolf in wolves}
    wolf_votes = {
        action.actor_player_id: action.target_player_ids
        for action in updated.night_actions
        if action.action_id is ActionId.WOLF_KILL and action.actor_player_id in wolf_ids
    }
    valid_wolf_targets = {
        target.player_id
        for wolf in wolves
        for target in get_action_targets(updated, wolf.player_id, ActionId.WOLF_KILL)
    }
    wolf_targets = resolve_wolf_votes(
        wolf_votes,
        wolf_ids,
        valid_wolf_targets,
        slot_count=1,
        rng=rng,
    )

    for action in updated.night_actions:
        if action.action_id is not ActionId.SEER_CHECK or action.round_number != updated.round_number:
            continue
        target = _player(updated, action.target_player_ids[0])
        alignment = "wolf" if get_role_definition(target.role_id).camp is CampId.WOLF else "good"
        role_state = updated.role_states[action.actor_player_id]
        if target.player_id not in role_state.checked_target_ids:
            role_state.checked_target_ids.append(target.player_id)
        events.append(
            _append_event(
                updated,
                event_type=EventType.SEER_RESULT,
                visibility=EventVisibility.PLAYER_ONLY,
                occurred_at=occurred_at,
                event_id_prefix=event_id_prefix,
                payload={"target_player_id": target.player_id, "alignment": alignment},
                recipients=frozenset({action.actor_player_id}),
            )
        )

    living_witches = [
        player
        for player in alive_players(updated)
        if player.role_id is RoleId.WITCH
        and not updated.role_states[player.player_id].disabled
        and (
            updated.role_states[player.player_id].resources.get("antidote_available", False)
            or updated.role_states[player.player_id].resources.get("poison_available", False)
        )
    ]
    if living_witches:
        updated.phase = GamePhase.NIGHT_WITCH
        updated.revision += 1
        updated.phase_started_at = occurred_at
        updated.phase_ends_at = occurred_at + timedelta(seconds=updated.settings.night_seconds)
        updated.pending_decisions = [
            {
                "decision_id": f"witch-{updated.round_number}",
                "player_id": living_witches[0].player_id,
                "action_id": "witch_action",
                "wolf_target_ids": list(wolf_targets),
            }
        ]
        events.append(
            _append_event(
                updated,
                event_type=EventType.PHASE_CHANGED,
                visibility=EventVisibility.PUBLIC,
                occurred_at=occurred_at,
                event_id_prefix=event_id_prefix,
                payload={"phase": GamePhase.NIGHT_WITCH.value, "round_number": updated.round_number},
            )
        )
        return CommandResult(updated, tuple(events))

    death_result = resolve_deaths(
        updated,
        tuple(DeathRequest(player_id, DeathCause.WOLF_ATTACK) for player_id in wolf_targets),
        occurred_at=occurred_at,
        event_id_prefix=event_id_prefix,
        continue_phase=GamePhase.DAY,
        after_shoot="day",
    )
    events.extend(death_result.events)
    return _start_day_after_resolution(
        death_result.game,
        events,
        occurred_at=occurred_at,
        event_id_prefix=event_id_prefix,
    )


def submit_witch_action(
    game: GameState,
    *,
    actor_player_id: str,
    action_id: ActionId | str,
    target_player_ids: tuple[str, ...],
    request_id: str,
    expected_revision: int,
    submitted_at: datetime,
    event_id_prefix: str,
) -> CommandResult:
    duplicate = _check_request(game, request_id, expected_revision)
    if duplicate is not None:
        return duplicate
    if game.phase is not GamePhase.NIGHT_WITCH:
        raise GameRuleError("WRONG_PHASE", "witch action is not available in this phase")
    decision = next(
        (
            item
            for item in game.pending_decisions
            if item.get("action_id") == "witch_action" and item.get("player_id") == actor_player_id
        ),
        None,
    )
    if decision is None:
        raise GameRuleError("ACTION_NOT_ALLOWED", "player has no witch decision")
    actor = _player(game, actor_player_id)
    if actor.status is not PlayerStatus.ALIVE or actor.role_id is not RoleId.WITCH:
        raise GameRuleError("ACTION_NOT_ALLOWED", "player cannot use a witch action")
    parsed_action = ActionId(action_id)
    role_state = game.role_states[actor.player_id]
    wolf_targets = tuple(decision.get("wolf_target_ids", []))

    if parsed_action is ActionId.WITCH_ANTIDOTE:
        if len(target_player_ids) != 1 or target_player_ids[0] not in wolf_targets:
            raise GameRuleError("INVALID_TARGET", "antidote must target a wolf-attack victim")
        if target_player_ids[0] == actor.player_id:
            raise GameRuleError("WITCH_CANNOT_SELF_SAVE", "witch cannot save herself")
        if not role_state.resources.get("antidote_available", False):
            raise GameRuleError("RESOURCE_EXHAUSTED", "antidote is no longer available")
    elif parsed_action is ActionId.WITCH_POISON:
        if len(target_player_ids) != 1:
            raise GameRuleError("INVALID_TARGET_COUNT", "poison requires exactly one target")
        target = _player(game, target_player_ids[0])
        if target.status is not PlayerStatus.ALIVE:
            raise GameRuleError("INVALID_TARGET", "poison target is not alive")
        if not role_state.resources.get("poison_available", False):
            raise GameRuleError("RESOURCE_EXHAUSTED", "poison is no longer available")
    elif parsed_action is ActionId.ABSTAIN:
        if target_player_ids:
            raise GameRuleError("INVALID_TARGET_COUNT", "abstain does not take a target")
    else:
        raise GameRuleError("UNSUPPORTED_ACTION", "unsupported witch action")

    updated = _clone_game(game)
    updated_role = updated.role_states[actor.player_id]
    if parsed_action is ActionId.WITCH_ANTIDOTE:
        updated_role.resources["antidote_available"] = False
    elif parsed_action is ActionId.WITCH_POISON:
        updated_role.resources["poison_available"] = False
    updated.night_actions.append(
        NightAction(
            actor.player_id,
            parsed_action,
            target_player_ids,
            submitted_at,
            request_id,
            updated.round_number,
        )
    )
    updated.processed_request_ids.add(request_id)
    updated.pending_decisions = [item for item in updated.pending_decisions if item.get("decision_id") != decision["decision_id"]]
    updated.revision += 1
    events = [
        _append_event(
            updated,
            event_type=EventType.ACTION_ACCEPTED,
            visibility=EventVisibility.PLAYER_ONLY,
            occurred_at=submitted_at,
            event_id_prefix=event_id_prefix,
            payload={"action_id": parsed_action.value, "target_player_ids": list(target_player_ids)},
            recipients=frozenset({actor.player_id}),
        )
    ]

    remaining_wolf_targets = list(wolf_targets)
    if parsed_action is ActionId.WITCH_ANTIDOTE:
        remaining_wolf_targets.remove(target_player_ids[0])
    poison_target = target_player_ids[0] if parsed_action is ActionId.WITCH_POISON else None
    death_requests: list[DeathRequest] = []
    for player_id in remaining_wolf_targets:
        cause = DeathCause.POISON if player_id == poison_target else DeathCause.WOLF_ATTACK
        death_requests.append(DeathRequest(player_id, cause))
    if poison_target is not None and poison_target not in remaining_wolf_targets:
        death_requests.append(DeathRequest(poison_target, DeathCause.POISON))

    death_result = resolve_deaths(
        updated,
        tuple(death_requests),
        occurred_at=submitted_at,
        event_id_prefix=event_id_prefix,
        continue_phase=GamePhase.DAY,
        after_shoot="day",
    )
    events.extend(death_result.events)
    return _start_day_after_resolution(
        death_result.game,
        events,
        occurred_at=submitted_at,
        event_id_prefix=event_id_prefix,
    )


def submit_day_vote(
    game: GameState,
    *,
    voter_player_id: str,
    target_player_id: str | None,
    request_id: str,
    expected_revision: int,
    submitted_at: datetime,
    event_id_prefix: str,
) -> CommandResult:
    duplicate = _check_request(game, request_id, expected_revision)
    if duplicate is not None:
        return duplicate
    if game.phase is not GamePhase.DAY or game.vote_state is None:
        raise GameRuleError("WRONG_PHASE", "day voting is not active")
    voter = _player(game, voter_player_id)
    if voter.status is not PlayerStatus.ALIVE or not voter.vote_enabled:
        raise GameRuleError("VOTER_NOT_ELIGIBLE", "player cannot vote")
    if voter.player_id in game.vote_state.ballots:
        raise GameRuleError("ACTION_ALREADY_SUBMITTED", "player already voted")
    if target_player_id is not None:
        target = _player(game, target_player_id)
        if target.status is not PlayerStatus.ALIVE or target.spectator:
            raise GameRuleError("INVALID_TARGET", "vote target is not alive")

    updated = _clone_game(game)
    updated.vote_state.ballots[voter.player_id] = target_player_id
    updated.processed_request_ids.add(request_id)
    updated.revision += 1
    payload: dict[str, object] = {"submitted_count": len(updated.vote_state.ballots)}
    if updated.vote_state.visibility is not VoteVisibility.ANONYMOUS:
        payload["voter_player_id"] = voter.player_id
    if updated.vote_state.visibility is VoteVisibility.LIVE:
        payload["target_player_id"] = target_player_id
    event = _append_event(
        updated,
        event_type=EventType.VOTE_CAST,
        visibility=EventVisibility.PUBLIC,
        occurred_at=submitted_at,
        event_id_prefix=event_id_prefix,
        payload=payload,
    )
    return CommandResult(updated, (event,))


def resolve_day_vote(
    game: GameState,
    *,
    occurred_at: datetime,
    event_id_prefix: str,
    allow_incomplete: bool = False,
) -> CommandResult:
    if game.phase is not GamePhase.DAY or game.vote_state is None:
        raise GameRuleError("WRONG_PHASE", "day voting is not active")
    missing = game.vote_state.eligible_voter_ids - set(game.vote_state.ballots)
    if missing and not allow_incomplete:
        raise GameRuleError("VOTES_PENDING", "eligible players have not all voted")

    updated = _clone_game(game)
    valid_targets = {player.player_id for player in alive_players(updated)}
    tally = tally_day_vote(updated.vote_state, valid_targets)
    updated.vote_state.closed = True
    updated.revision += 1
    payload: dict[str, object] = {
        "counts": {player_id: count for player_id, count in tally.counts},
        "top_candidate_ids": list(tally.top_candidate_ids),
        "exiled_player_id": tally.exiled_player_id,
    }
    if updated.vote_state.visibility is not VoteVisibility.ANONYMOUS:
        payload["ballots"] = dict(updated.vote_state.ballots)
    events = [
        _append_event(
            updated,
            event_type=EventType.VOTE_RESOLVED,
            visibility=EventVisibility.PUBLIC,
            occurred_at=occurred_at,
            event_id_prefix=event_id_prefix,
            payload=payload,
        )
    ]

    if tally.exiled_player_id is not None:
        death_result = resolve_deaths(
            updated,
            (DeathRequest(tally.exiled_player_id, DeathCause.EXILE),),
            occurred_at=occurred_at,
            event_id_prefix=event_id_prefix,
            continue_phase=GamePhase.DAY,
            after_shoot="night",
        )
        events.extend(death_result.events)
        if death_result.game.phase in {GamePhase.ENDED, GamePhase.ROLE_SHOOT}:
            return CommandResult(death_result.game, tuple(events))
        updated = death_result.game

    transition = start_night(updated, occurred_at=occurred_at, event_id_prefix=event_id_prefix)
    events.append(transition.event)
    return CommandResult(transition.game, tuple(events))


def submit_hunter_decision(
    game: GameState,
    *,
    actor_player_id: str,
    target_player_id: str | None,
    request_id: str,
    expected_revision: int,
    submitted_at: datetime,
    event_id_prefix: str,
) -> CommandResult:
    duplicate = _check_request(game, request_id, expected_revision)
    if duplicate is not None:
        return duplicate
    if game.phase is not GamePhase.ROLE_SHOOT:
        raise GameRuleError("WRONG_PHASE", "hunter decision is not active")
    decision = next(
        (item for item in game.pending_decisions if item.get("action_id") == ActionId.HUNTER_SHOOT.value),
        None,
    )
    if decision is None or decision.get("player_id") != actor_player_id:
        raise GameRuleError("ACTION_NOT_ALLOWED", "player is not the current shooter")
    actor = _player(game, actor_player_id)
    if actor.status is not PlayerStatus.DEAD or actor.role_id is None:
        raise GameRuleError("ACTION_NOT_ALLOWED", "shooter state is invalid")
    if not get_role_definition(actor.role_id).can_shoot:
        raise GameRuleError("ACTION_NOT_ALLOWED", "role cannot shoot")
    if target_player_id is not None:
        target = _player(game, target_player_id)
        if target.status is not PlayerStatus.ALIVE:
            raise GameRuleError("INVALID_TARGET", "shot target is not alive")

    updated = _clone_game(game)
    updated.pending_decisions.remove(
        next(item for item in updated.pending_decisions if item.get("decision_id") == decision["decision_id"])
    )
    updated.processed_request_ids.add(request_id)
    updated.revision += 1
    role_state = updated.role_states[actor.player_id]
    shots = int(role_state.resources.get("hunter_shots", 1))
    role_state.resources["hunter_shots"] = max(0, shots - 1)
    action_id = ActionId.HUNTER_SHOOT if target_player_id is not None else ActionId.ABSTAIN
    events = [
        _append_event(
            updated,
            event_type=EventType.ACTION_ACCEPTED,
            visibility=EventVisibility.PLAYER_ONLY,
            occurred_at=submitted_at,
            event_id_prefix=event_id_prefix,
            payload={
                "action_id": action_id.value,
                "target_player_ids": [target_player_id] if target_player_id is not None else [],
            },
            recipients=frozenset({actor.player_id}),
        )
    ]
    destination = str(decision.get("after_shoot", "day"))
    death_result = resolve_deaths(
        updated,
        (DeathRequest(target_player_id, DeathCause.SHOT),) if target_player_id is not None else (),
        occurred_at=submitted_at,
        event_id_prefix=event_id_prefix,
        continue_phase=GamePhase.DAY,
        after_shoot=destination,
    )
    events.extend(death_result.events)
    return _continue_after_shooting(
        death_result.game,
        events,
        destination=destination,
        occurred_at=submitted_at,
        event_id_prefix=event_id_prefix,
    )
