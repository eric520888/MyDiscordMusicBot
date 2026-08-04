"""Serializable day-vote state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Self

from ..ids import VoteVisibility
from .common import JsonModel, assert_allowed_keys, require_bool, require_identifier, require_identifier_list


@dataclass(slots=True)
class VoteState(JsonModel):
    eligible_voter_ids: set[str] = field(default_factory=set)
    ballots: dict[str, str | None] = field(default_factory=dict)
    visibility: VoteVisibility = VoteVisibility.REVEAL_AFTER_RESULT
    tied_candidate_ids: set[str] = field(default_factory=set)
    closed: bool = False

    def __post_init__(self) -> None:
        self.eligible_voter_ids = set(require_identifier_list(self.eligible_voter_ids, "eligible_voter_ids"))
        normalized_ballots: dict[str, str | None] = {}
        for voter_id, target_id in self.ballots.items():
            voter = require_identifier(voter_id, "ballot voter")
            if voter not in self.eligible_voter_ids:
                raise ValueError("ballot voter is not eligible")
            normalized_ballots[voter] = require_identifier(target_id, "ballot target") if target_id is not None else None
        self.ballots = normalized_ballots
        self.visibility = VoteVisibility(self.visibility)
        self.tied_candidate_ids = set(require_identifier_list(self.tied_candidate_ids, "tied_candidate_ids"))
        self.closed = require_bool(self.closed, "closed")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {"eligible_voter_ids", "ballots", "visibility", "tied_candidate_ids", "closed"}
        assert_allowed_keys(data, allowed)
        ballots = data.get("ballots", {})
        if not isinstance(ballots, Mapping):
            raise TypeError("ballots must be an object")
        return cls(
            eligible_voter_ids=set(data.get("eligible_voter_ids", [])),
            ballots=dict(ballots),
            visibility=VoteVisibility(data.get("visibility", VoteVisibility.REVEAL_AFTER_RESULT)),
            tied_candidate_ids=set(data.get("tied_candidate_ids", [])),
            closed=data.get("closed", False),
        )
