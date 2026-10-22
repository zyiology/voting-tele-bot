"""Analyze both outcomes from one normalized snapshot of saved scores."""

from collections.abc import Sequence
from uuid import UUID

from voting_bot.models import BallotScore, PollOption, ScorePollResults
from voting_bot.voting_methods.ballots import complete_score_ballots
from voting_bot.voting_methods.condorcet import _tally_complete_condorcet_ballots
from voting_bot.voting_methods.score import _tally_complete_score_ballots


def tally_score_poll_results(
    poll_id: UUID,
    options: Sequence[PollOption],
    ballot_scores: Sequence[BallotScore],
) -> ScorePollResults:
    ballots = complete_score_ballots(poll_id, options, ballot_scores)
    return ScorePollResults(
        score=_tally_complete_score_ballots(poll_id, options, ballots),
        condorcet=_tally_complete_condorcet_ballots(poll_id, options, ballots),
    )
