from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from voting_bot.models import BallotScore, PollOption, ScoreOptionResult, ScorePollResult


class ScoreValidationError(Exception):
    pass


def validate_score(score: int, score_min: int, score_max: int) -> None:
    if score_min > score_max:
        raise ScoreValidationError("score_min must be less than or equal to score_max")

    if score < score_min or score > score_max:
        raise ScoreValidationError(
            f"score must be between {score_min} and {score_max}"
        )


def tally_score_poll(
    poll_id: UUID,
    options: list[PollOption],
    ballot_scores: list[BallotScore],
) -> ScorePollResult:
    option_by_id = {option.id: option for option in options}
    expected_option_ids = set(option_by_id)

    scores_by_voter: dict[str, dict[UUID, int]] = defaultdict(dict)
    for ballot_score in ballot_scores:
        if ballot_score.poll_id != poll_id:
            continue
        if ballot_score.option_id not in expected_option_ids:
            continue

        scores_by_voter[ballot_score.voter_hash][ballot_score.option_id] = (
            ballot_score.score
        )

    complete_ballots = [
        scores
        for scores in scores_by_voter.values()
        if set(scores) == expected_option_ids
    ]

    totals = dict.fromkeys(expected_option_ids, 0)
    for scores in complete_ballots:
        for option_id, score in scores.items():
            totals[option_id] += score

    complete_ballot_count = len(complete_ballots)
    option_results = [
        ScoreOptionResult(
            option=option,
            rank=None,
            total_score=totals[option.id],
            ballot_count=complete_ballot_count,
            average_score=(
                totals[option.id] / complete_ballot_count
                if complete_ballot_count > 0
                else None
            ),
        )
        for option in options
    ]

    return ScorePollResult(
        poll_id=poll_id,
        complete_ballot_count=complete_ballot_count,
        option_results=tuple(option_results),
    )
