from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from voting_bot.models import BallotScore, PollOption, ScoreOptionResult, ScorePollResult
from voting_bot.voting_methods.score import (
    ScoreValidationError,
    tally_score_poll,
    validate_score,
)


def make_option(poll_id: UUID, label: str, display_order: int) -> PollOption:
    return PollOption(
        id=uuid4(),
        poll_id=poll_id,
        label=label,
        display_order=display_order,
    )


def make_score(
    poll_id: UUID,
    voter_hash: str,
    option_id: UUID,
    score: int,
) -> BallotScore:
    return BallotScore(
        poll_id=poll_id,
        voter_hash=voter_hash,
        option_id=option_id,
        score=score,
    )


def test_tally_score_poll_ranks_options_by_average_score() -> None:
    poll_id = uuid4()
    sushi = make_option(poll_id, "Sushi", 0)
    pizza = make_option(poll_id, "Pizza", 1)

    result = tally_score_poll(
        poll_id=poll_id,
        options=[sushi, pizza],
        ballot_scores=[
            make_score(poll_id, "voter-a", sushi.id, 5),
            make_score(poll_id, "voter-a", pizza.id, 2),
            make_score(poll_id, "voter-b", sushi.id, 3),
            make_score(poll_id, "voter-b", pizza.id, 4),
        ],
    )

    assert result.complete_ballot_count == 2
    assert [option_result.option.label for option_result in result.option_results] == [
        "Sushi",
        "Pizza",
    ]
    assert [option_result.rank for option_result in result.option_results] == [1, 2]
    assert result.option_results[0].average_score == 4.0
    assert result.option_results[1].average_score == 3.0
    assert [winner.option.label for winner in result.winners] == ["Sushi"]


def test_tally_score_poll_excludes_incomplete_ballots() -> None:
    poll_id = uuid4()
    sushi = make_option(poll_id, "Sushi", 0)
    pizza = make_option(poll_id, "Pizza", 1)

    result = tally_score_poll(
        poll_id=poll_id,
        options=[sushi, pizza],
        ballot_scores=[
            make_score(poll_id, "voter-a", sushi.id, 5),
            make_score(poll_id, "voter-a", pizza.id, 2),
            make_score(poll_id, "voter-b", sushi.id, 1),
        ],
    )

    assert result.complete_ballot_count == 1
    assert result.option_results[0].total_score == 5
    assert result.option_results[1].total_score == 2


def test_tally_score_poll_uses_last_score_for_duplicate_voter_option() -> None:
    poll_id = uuid4()
    sushi = make_option(poll_id, "Sushi", 0)
    pizza = make_option(poll_id, "Pizza", 1)

    result = tally_score_poll(
        poll_id=poll_id,
        options=[sushi, pizza],
        ballot_scores=[
            make_score(poll_id, "voter-a", sushi.id, 1),
            make_score(poll_id, "voter-a", sushi.id, 5),
            make_score(poll_id, "voter-a", pizza.id, 2),
        ],
    )

    assert result.complete_ballot_count == 1
    assert result.option_results[0].option == sushi
    assert result.option_results[0].total_score == 5


def test_tally_score_poll_preserves_option_order_for_ties() -> None:
    poll_id = uuid4()
    sushi = make_option(poll_id, "Sushi", 0)
    pizza = make_option(poll_id, "Pizza", 1)

    result = tally_score_poll(
        poll_id=poll_id,
        options=[sushi, pizza],
        ballot_scores=[
            make_score(poll_id, "voter-a", sushi.id, 3),
            make_score(poll_id, "voter-a", pizza.id, 3),
        ],
    )

    assert [option_result.option.label for option_result in result.option_results] == [
        "Sushi",
        "Pizza",
    ]
    assert [option_result.rank for option_result in result.option_results] == [1, 1]
    assert [winner.option.label for winner in result.winners] == ["Sushi", "Pizza"]


def test_tally_score_poll_uses_dense_ranking() -> None:
    poll_id = uuid4()
    sushi = make_option(poll_id, "Sushi", 0)
    pizza = make_option(poll_id, "Pizza", 1)
    ramen = make_option(poll_id, "Ramen", 2)
    tacos = make_option(poll_id, "Tacos", 3)

    result = tally_score_poll(
        poll_id=poll_id,
        options=[sushi, pizza, ramen, tacos],
        ballot_scores=[
            make_score(poll_id, "voter-a", sushi.id, 5),
            make_score(poll_id, "voter-a", pizza.id, 4),
            make_score(poll_id, "voter-a", ramen.id, 4),
            make_score(poll_id, "voter-a", tacos.id, 3),
        ],
    )

    assert [option_result.option.label for option_result in result.option_results] == [
        "Sushi",
        "Pizza",
        "Ramen",
        "Tacos",
    ]
    assert [option_result.rank for option_result in result.option_results] == [
        1,
        2,
        2,
        3,
    ]


def test_score_poll_result_normalizes_sorting_and_dense_ranks() -> None:
    poll_id = uuid4()
    sushi = make_option(poll_id, "Sushi", 0)
    pizza = make_option(poll_id, "Pizza", 1)
    ramen = make_option(poll_id, "Ramen", 2)

    result = ScorePollResult(
        poll_id=poll_id,
        complete_ballot_count=1,
        option_results=(
            ScoreOptionResult(
                option=ramen,
                rank=99,
                total_score=4,
                ballot_count=1,
                average_score=4.0,
            ),
            ScoreOptionResult(
                option=pizza,
                rank=99,
                total_score=4,
                ballot_count=1,
                average_score=4.0,
            ),
            ScoreOptionResult(
                option=sushi,
                rank=99,
                total_score=5,
                ballot_count=1,
                average_score=5.0,
            ),
        ),
    )

    assert [option_result.option.label for option_result in result.option_results] == [
        "Sushi",
        "Pizza",
        "Ramen",
    ]
    assert [option_result.rank for option_result in result.option_results] == [1, 2, 2]


def test_tally_score_poll_handles_zero_complete_ballots() -> None:
    poll_id = uuid4()
    sushi = make_option(poll_id, "Sushi", 0)
    pizza = make_option(poll_id, "Pizza", 1)

    result = tally_score_poll(
        poll_id=poll_id,
        options=[sushi, pizza],
        ballot_scores=[],
    )

    assert result.complete_ballot_count == 0
    assert [option_result.average_score for option_result in result.option_results] == [
        None,
        None,
    ]
    assert [option_result.rank for option_result in result.option_results] == [
        None,
        None,
    ]
    assert result.winners == ()


def test_validate_score_accepts_bounds() -> None:
    validate_score(0, 0, 5)
    validate_score(5, 0, 5)


@pytest.mark.parametrize("score", [-1, 6])
def test_validate_score_rejects_scores_outside_bounds(score: int) -> None:
    with pytest.raises(ScoreValidationError):
        validate_score(score, 0, 5)


def test_validate_score_rejects_invalid_bounds() -> None:
    with pytest.raises(ScoreValidationError):
        validate_score(3, 5, 0)
