"""Pure white-day and wolf-team vote resolution."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass

from ..models import VoteState


@dataclass(frozen=True, slots=True)
class DayVoteResult:
    counts: tuple[tuple[str, int], ...]
    top_candidate_ids: tuple[str, ...]
    exiled_player_id: str | None

    @property
    def is_tie(self) -> bool:
        return len(self.top_candidate_ids) > 1

    @property
    def has_votes(self) -> bool:
        return bool(self.counts)


def tally_day_vote(vote_state: VoteState, valid_target_ids: Set[str]) -> DayVoteResult:
    targets = [target_id for target_id in vote_state.ballots.values() if target_id is not None]
    invalid = set(targets) - set(valid_target_ids)
    if invalid:
        raise ValueError(f"invalid vote targets: {', '.join(sorted(invalid))}")
    counts = Counter(targets)
    if not counts:
        return DayVoteResult((), (), None)
    ordered_counts = tuple(counts.most_common())
    max_votes = ordered_counts[0][1]
    top_candidates = tuple(candidate_id for candidate_id, count in ordered_counts if count == max_votes)
    exiled = top_candidates[0] if len(top_candidates) == 1 else None
    return DayVoteResult(ordered_counts, top_candidates, exiled)


def resolve_wolf_votes(
    votes: Mapping[str, Sequence[str]],
    eligible_wolf_ids: Set[str],
    valid_target_ids: Set[str],
    *,
    slot_count: int,
    rng: random.Random,
) -> tuple[str, ...]:
    """Resolve each wolf-kill slot; tied top targets use injected randomness."""

    if slot_count < 1:
        raise ValueError("slot_count must be positive")
    normalized_votes: list[tuple[str, ...]] = []
    for voter_id, target_ids in votes.items():
        if voter_id not in eligible_wolf_ids:
            continue
        normalized = tuple(target_ids)
        if len(normalized) > slot_count:
            raise ValueError("wolf vote contains too many target slots")
        invalid = set(normalized) - set(valid_target_ids)
        if invalid:
            raise ValueError(f"invalid wolf targets: {', '.join(sorted(invalid))}")
        normalized_votes.append(normalized)

    resolved: list[str] = []
    for slot in range(slot_count):
        slot_votes = [targets[slot] for targets in normalized_votes if len(targets) > slot]
        if not slot_votes:
            continue
        counts = Counter(slot_votes).most_common()
        max_votes = counts[0][1]
        candidates = [target_id for target_id, count in counts if count == max_votes]
        resolved.append(rng.choice(candidates))
    return tuple(resolved)
