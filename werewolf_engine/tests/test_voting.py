from __future__ import annotations

import random
import unittest

from werewolf_engine.models import VoteState
from werewolf_engine.rules import resolve_wolf_votes, tally_day_vote


class DayVoteTests(unittest.TestCase):
    def test_unique_top_candidate_is_exiled(self) -> None:
        state = VoteState(
            eligible_voter_ids={"p1", "p2", "p3"},
            ballots={"p1": "p3", "p2": "p3", "p3": "p1"},
        )
        result = tally_day_vote(state, {"p1", "p2", "p3"})
        self.assertEqual(result.counts, (("p3", 2), ("p1", 1)))
        self.assertEqual(result.exiled_player_id, "p3")
        self.assertFalse(result.is_tie)

    def test_tie_and_no_votes_exile_nobody(self) -> None:
        tied = VoteState(
            eligible_voter_ids={"p1", "p2"},
            ballots={"p1": "p2", "p2": "p1"},
        )
        tie_result = tally_day_vote(tied, {"p1", "p2"})
        self.assertTrue(tie_result.is_tie)
        self.assertIsNone(tie_result.exiled_player_id)

        empty_result = tally_day_vote(VoteState({"p1"}, {"p1": None}), {"p1"})
        self.assertFalse(empty_result.has_votes)
        self.assertIsNone(empty_result.exiled_player_id)

    def test_invalid_target_is_rejected_at_resolution_boundary(self) -> None:
        state = VoteState({"p1"}, {"p1": "dead-player"})
        with self.assertRaisesRegex(ValueError, "invalid vote targets"):
            tally_day_vote(state, {"p1"})


class WolfVoteTests(unittest.TestCase):
    def test_majority_target_wins(self) -> None:
        result = resolve_wolf_votes(
            {"w1": ("p1",), "w2": ("p1",), "w3": ("p2",)},
            {"w1", "w2", "w3"},
            {"p1", "p2"},
            slot_count=1,
            rng=random.Random(1),
        )
        self.assertEqual(result, ("p1",))

    def test_tie_uses_injected_rng_and_is_reproducible(self) -> None:
        kwargs = {
            "votes": {"w1": ("p1",), "w2": ("p2",)},
            "eligible_wolf_ids": {"w1", "w2"},
            "valid_target_ids": {"p1", "p2"},
            "slot_count": 1,
        }
        first = resolve_wolf_votes(**kwargs, rng=random.Random(2026))
        second = resolve_wolf_votes(**kwargs, rng=random.Random(2026))
        self.assertEqual(first, second)
        self.assertIn(first[0], {"p1", "p2"})

    def test_empty_and_double_kill_slots_match_legacy_shape(self) -> None:
        self.assertEqual(
            resolve_wolf_votes({}, {"w1"}, {"p1"}, slot_count=1, rng=random.Random(1)),
            (),
        )
        result = resolve_wolf_votes(
            {"w1": ("p1", "p2"), "w2": ("p1", "p3")},
            {"w1", "w2"},
            {"p1", "p2", "p3"},
            slot_count=2,
            rng=random.Random(9),
        )
        self.assertEqual(result[0], "p1")
        self.assertIn(result[1], {"p2", "p3"})

    def test_ineligible_votes_are_ignored_and_invalid_targets_rejected(self) -> None:
        result = resolve_wolf_votes(
            {"w1": ("p1",), "outsider": ("p2",)},
            {"w1"},
            {"p1", "p2"},
            slot_count=1,
            rng=random.Random(1),
        )
        self.assertEqual(result, ("p1",))
        with self.assertRaisesRegex(ValueError, "invalid wolf targets"):
            resolve_wolf_votes(
                {"w1": ("unknown",)},
                {"w1"},
                {"p1"},
                slot_count=1,
                rng=random.Random(1),
            )


if __name__ == "__main__":
    unittest.main()
