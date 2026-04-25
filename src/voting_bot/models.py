from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class PollStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class VotingMethodOptions(StrEnum):
    SCORE = "score"


@dataclass(frozen=True)
class Poll:
    id: UUID
    chat_id: int
    message_id: int | None
    created_by_hash: str
    title: str
    voting_method: VotingMethodOptions
    status: PollStatus
    score_min: int
    score_max: int
    created_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True)
class PollOption:
    id: UUID
    poll_id: UUID
    label: str
    display_order: int


@dataclass(frozen=True)
class BallotScore:
    poll_id: UUID
    voter_hash: str
    option_id: UUID
    score: int
    updated_at: datetime | None = None


@dataclass(frozen=True)
class PollSession:
    poll_id: UUID
    voter_hash: str
    current_option_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ScoreOptionResult:
    option: PollOption
    rank: int | None
    total_score: int
    ballot_count: int
    average_score: float | None


@dataclass(frozen=True)
class ScorePollResult:
    poll_id: UUID
    complete_ballot_count: int
    option_results: tuple[ScoreOptionResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "option_results",
            _rank_score_option_results(self.option_results),
        )

    @property
    def winners(self) -> tuple[ScoreOptionResult, ...]:
        """Return all options with the highest average score.

        Tied options are all returned. Display order only controls their
        presentation order within the tied group.
        Returns empty tuple if no ballots were recorded.
        """
        if not self.option_results:
            return ()

        best_average = self.option_results[0].average_score
        if best_average is None:
            return ()

        return tuple(
            result
            for result in self.option_results
            if result.average_score == best_average
        )


def _rank_score_option_results(
    option_results: tuple[ScoreOptionResult, ...],
) -> tuple[ScoreOptionResult, ...]:
    sorted_results = sorted(
        option_results,
        key=lambda result: (
            result.average_score is not None,
            result.average_score or 0,
            -result.option.display_order,
        ),
        reverse=True,
    )

    ranked_results = []
    current_rank: int | None = None
    previous_average: float | None = None

    for result in sorted_results:
        if result.average_score is None:
            rank = None
        elif previous_average is None or result.average_score != previous_average:
            current_rank = 1 if current_rank is None else current_rank + 1
            previous_average = result.average_score
            rank = current_rank
        else:
            rank = current_rank

        ranked_results.append(replace(result, rank=rank))

    return tuple(ranked_results)
