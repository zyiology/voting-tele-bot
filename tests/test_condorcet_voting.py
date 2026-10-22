from dataclasses import replace
from itertools import permutations
from uuid import uuid4

import pytest

from voting_bot.models import BallotScore, CondorcetOutcome, PollOption
from voting_bot.voting_methods import (
    tally_condorcet_poll,
    tally_score_poll,
    tally_score_poll_results,
)


def election(votes: list[tuple[int, ...]], count: int = 3):
    poll_id = uuid4()
    options = [PollOption(uuid4(), poll_id, chr(65 + i), i) for i in range(count)]
    rows = [
        BallotScore(poll_id, str(voter), option.id, score)
        for voter, vote in enumerate(votes)
        for option, score in zip(options, vote, strict=True)
    ]
    return poll_id, options, rows


@pytest.mark.parametrize(
    ('votes', 'winner', 'outcome'),
    [
        ([], None, CondorcetOutcome.NO_BALLOTS),
        ([(3, 2, 1)], 0, CondorcetOutcome.WINNER),
        ([(3, 3, 1)], None, CondorcetOutcome.NO_WINNER),
        ([(2, 2, 2)], None, CondorcetOutcome.NO_WINNER),
        ([(3, 2, 1), (1, 3, 2), (2, 1, 3)], None, CondorcetOutcome.NO_WINNER),
        ([(3, 2, 1), (2, 3, 1)], None, CondorcetOutcome.NO_WINNER),
        ([(-1, -2, -3)], 0, CondorcetOutcome.WINNER),
    ],
)
def test_outcomes(votes, winner, outcome):
    poll_id, options, rows = election(votes)
    results = tally_score_poll_results(poll_id, options, rows)
    result = results.condorcet
    assert result.outcome == outcome
    assert result.winner_option_id == (options[winner].id if winner is not None else None)
    assert results.score == tally_score_poll(poll_id, options, rows)
    assert result == tally_condorcet_poll(poll_id, options, rows)
    assert result.complete_ballot_count == results.score.complete_ballot_count == len(votes)
    assert len(result.comparisons) == 3
    for pair in result.comparisons:
        assert pair.a_over_b + pair.b_over_a + pair.indifferent_count == len(votes)
    if not votes:
        assert results.score.winners == ()


@pytest.mark.parametrize('count', [0, 1, 2])
@pytest.mark.parametrize('with_ballots', [False, True])
def test_rejects_fewer_than_two_distinct_option_ids(count, with_ballots):
    poll_id, options, rows = election([(3, 2, 1)])
    invalid = [replace(options[0], label=str(i)) for i in range(count)]
    for tally in (tally_condorcet_poll, tally_score_poll_results):
        with pytest.raises(ValueError, match='at least two distinct option UUIDs'):
            tally(poll_id, invalid, rows if with_ballots else [])


def test_duplicate_labels_are_valid_and_repeated_ids_do_not_add_pairs():
    poll_id, options, rows = election([(3, 2)], count=2)
    options = [replace(option, label='Same') for option in options]
    result = tally_condorcet_poll(poll_id, options + [options[0]], rows)
    assert result.winner_option_id == options[0].id
    assert len(result.comparisons) == 1


def test_different_winners_and_unweighted_preferences():
    poll_id, options, rows = election([(3, 2), (3, 2), (0, 3)], count=2)
    result = tally_score_poll_results(poll_id, options, rows)
    assert result.score.winners[0].option.id == options[1].id
    assert result.condorcet.winner_option_id == options[0].id
    pair = result.condorcet.comparisons[0]
    assert (pair.a_over_b, pair.b_over_a, pair.indifferent_count) == (2, 1, 0)


def test_majority_among_expressed_preferences_with_indifference():
    poll_id, options, rows = election([(1, 0)] * 2 + [(0, 5)] + [(3, 3)] * 7, count=2)
    result = tally_condorcet_poll(poll_id, options, rows)
    assert result.complete_ballot_count == 10
    assert result.winner_option_id == options[0].id
    pair = result.comparisons[0]
    assert (pair.a_over_b, pair.b_over_a, pair.indifferent_count) == (2, 1, 7)


def test_cycle_among_losers_does_not_prevent_winner():
    poll_id, options, rows = election([(5, 3, 2, 1), (5, 1, 3, 2), (5, 2, 1, 3)], count=4)
    assert tally_condorcet_poll(poll_id, options, rows).winner_option_id == options[0].id


def test_normalization_completion_and_edit_use_one_electorate():
    poll_id, options, rows = election([(3, 2)], count=2)
    noise = [
        BallotScore(uuid4(), 'foreign', option.id, 99) for option in options
    ] + [
        BallotScore(poll_id, 'unknown', uuid4(), 99),
        BallotScore(poll_id, 'partial', options[0].id, -5),
    ]
    baseline = tally_score_poll_results(poll_id, options, rows)
    assert tally_score_poll_results(poll_id, options, rows + noise) == baseline
    completed = rows + noise + [BallotScore(poll_id, 'partial', options[1].id, 5)]
    result = tally_score_poll_results(poll_id, options, completed)
    assert result.score.complete_ballot_count == result.condorcet.complete_ballot_count == 2
    assert result.condorcet.outcome == CondorcetOutcome.NO_WINNER
    edited = completed + [BallotScore(poll_id, '0', options[0].id, 0)]
    result = tally_score_poll_results(poll_id, options, edited)
    assert result.condorcet.winner_option_id == options[1].id
    assert result.score.option_results[1].total_score == -5
    assert result.score.winners[0].option.id == options[1].id
    assert result.score == tally_score_poll(poll_id, options, edited)


def test_option_voter_order_and_labels_do_not_change_analysis():
    poll_id, options, rows = election([(3, 2, 0), (3, 1, 2), (0, 3, 2)])
    baseline = tally_score_poll_results(poll_id, options, rows)
    for reordered in permutations(options):
        renamed = [replace(option, label='New') for option in reordered]
        result = tally_score_poll_results(poll_id, renamed, list(reversed(rows)))
        assert result.condorcet == baseline.condorcet
        assert [winner.option.id for winner in result.score.winners] == [
            winner.option.id for winner in baseline.score.winners
        ]


def test_all_score_ties_retained():
    poll_id, options, rows = election([(4, 4, 4)])
    result = tally_score_poll_results(poll_id, options, rows)
    assert [winner.option.id for winner in result.score.winners] == [o.id for o in options]
    assert result.condorcet.outcome == CondorcetOutcome.NO_WINNER
