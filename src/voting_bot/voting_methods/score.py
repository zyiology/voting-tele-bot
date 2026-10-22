from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from voting_bot.models import BallotScore, PollOption, ScoreOptionResult, ScorePollResult
from voting_bot.voting_methods.ballots import complete_score_ballots


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
    return _tally_complete_score_ballots(
        poll_id, options, complete_score_ballots(poll_id, options, ballot_scores)
    )


def _tally_complete_score_ballots(
    poll_id: UUID,
    options: Sequence[PollOption],
    complete_ballots: Sequence[Mapping[UUID, int]],
) -> ScorePollResult:
    expected_option_ids = {option.id for option in options}

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
