"""Strict pairwise majorities derived from complete score ballots."""

from collections.abc import Mapping, Sequence
from itertools import combinations
from uuid import UUID

from voting_bot.models import (
    BallotScore,
    CondorcetOutcome,
    CondorcetPollResult,
    PairwiseComparison,
    PollOption,
)
from voting_bot.voting_methods.ballots import complete_score_ballots


def tally_condorcet_poll(
    poll_id: UUID,
    options: Sequence[PollOption],
    ballot_scores: Sequence[BallotScore],
) -> CondorcetPollResult:
    return _tally_complete_condorcet_ballots(
        poll_id, options, complete_score_ballots(poll_id, options, ballot_scores)
    )


def _tally_complete_condorcet_ballots(
    poll_id: UUID,
    options: Sequence[PollOption],
    complete_ballots: Sequence[Mapping[UUID, int]],
) -> CondorcetPollResult:
    option_by_id = {option.id: option for option in options}
    if len(option_by_id) < 2:
        raise ValueError("Condorcet tally requires at least two distinct option UUIDs")

    option_ids = sorted(
        option_by_id,
        key=lambda option_id: (option_by_id[option_id].display_order, option_id.int),
    )
    candidates = set(option_ids)
    comparisons = []
    for a, b in combinations(option_ids, 2):
        a_over_b = b_over_a = indifferent = 0
        for scores in complete_ballots:
            if scores[a] > scores[b]:
                a_over_b += 1
            elif scores[a] < scores[b]:
                b_over_a += 1
            else:
                indifferent += 1
        comparisons.append(PairwiseComparison(a, b, a_over_b, b_over_a, indifferent))
        if a_over_b <= b_over_a:
            candidates.discard(a)
        if b_over_a <= a_over_b:
            candidates.discard(b)

    winner = next(iter(candidates), None)
    if not complete_ballots:
        outcome = CondorcetOutcome.NO_BALLOTS
    elif winner is not None:
        outcome = CondorcetOutcome.WINNER
    else:
        outcome = CondorcetOutcome.NO_WINNER
    return CondorcetPollResult(
        poll_id, len(complete_ballots), outcome, winner, tuple(comparisons)
    )
