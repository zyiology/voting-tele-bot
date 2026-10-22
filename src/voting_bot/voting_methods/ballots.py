"""Shared inclusion rules for analyses of saved score ballots."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from uuid import UUID

from voting_bot.models import BallotScore, PollOption


def complete_score_ballots(
    poll_id: UUID,
    options: Sequence[PollOption],
    ballot_scores: Sequence[BallotScore],
) -> list[Mapping[UUID, int]]:
    """Filter foreign/unknown rows, keep last rows, then require every option."""
    expected_option_ids = {option.id for option in options}
    scores_by_voter: dict[str, dict[UUID, int]] = defaultdict(dict)
    for row in ballot_scores:
        if row.poll_id == poll_id and row.option_id in expected_option_ids:
            scores_by_voter[row.voter_hash][row.option_id] = row.score

    return [
        scores
        for scores in scores_by_voter.values()
        if set(scores) == expected_option_ids
    ]
