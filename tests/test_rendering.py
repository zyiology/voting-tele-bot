from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from voting_bot.handlers.commands import MAX_OPTION_LENGTH, MAX_OPTIONS, MAX_TITLE_LENGTH
from voting_bot.models import (
    BallotScore,
    Poll,
    PollOption,
    PollStatus,
    ResultsVisibility,
    VotingMethodOptions,
    VotingMode,
)
from voting_bot.rendering import (
    SCORE_RESULTS_EXPLANATION,
    done_callback_data,
    edit_callback_data,
    quick_score_callback_data,
    render_ballot_summary,
    render_group_poll,
    render_score_prompt,
    score_callback_data,
    vote_callback_data,
)


def make_poll(
    *,
    poll_id: UUID | None = None,
    status: PollStatus = PollStatus.OPEN,
    voting_mode: VotingMode = VotingMode.DM,
    results_visibility: ResultsVisibility = ResultsVisibility.HIDDEN_UNTIL_CLOSED,
) -> Poll:
    return Poll(
        id=poll_id or uuid4(),
        chat_id=-100,
        message_id=123,
        created_by_hash="creator",
        title="Where should we eat?",
        voting_method=VotingMethodOptions.SCORE,
        voting_mode=voting_mode,
        results_visibility=results_visibility,
        status=status,
        score_min=0,
        score_max=5,
        created_at=datetime.now(UTC),
        closed_at=datetime.now(UTC) if status == PollStatus.CLOSED else None,
    )


def make_options(poll_id: UUID) -> list[PollOption]:
    return [
        PollOption(uuid4(), poll_id, "Sushi", 0),
        PollOption(uuid4(), poll_id, "Pizza", 1),
    ]


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


def test_render_group_poll_open_zero_votes_shows_options_and_vote_button() -> None:
    poll = make_poll()
    options = make_options(poll.id)

    text, keyboard = render_group_poll(poll, options, [])

    assert "Where should we eat?" in text
    assert "Options:" in text
    assert "1. Sushi" in text
    assert "Votes cast: 0" in text
    assert keyboard is not None
    button = keyboard.inline_keyboard[0][0]
    assert button.text == "Vote"
    assert button.callback_data == vote_callback_data(poll.id)


def test_render_group_poll_quick_mode_shows_score_buttons() -> None:
    poll = make_poll(voting_mode=VotingMode.QUICK)
    options = make_options(poll.id)

    text, keyboard = render_group_poll(poll, options, [])

    assert "Where should we eat?" in text
    assert "Votes cast: 0" in text
    assert keyboard is not None
    assert keyboard.inline_keyboard[0][0].text == "1. Sushi: 0"
    assert keyboard.inline_keyboard[0][0].callback_data == quick_score_callback_data(
        poll.id,
        0,
        0,
    )
    assert keyboard.inline_keyboard[1][0].text == "2. Pizza: 0"
    assert keyboard.inline_keyboard[1][5].callback_data == quick_score_callback_data(
        poll.id,
        1,
        5,
    )


def test_render_group_poll_hides_open_results_by_default() -> None:
    poll = make_poll()
    options = make_options(poll.id)
    scores = [
        make_score(poll.id, "a", options[0].id, 2),
        make_score(poll.id, "a", options[1].id, 5),
    ]

    text, keyboard = render_group_poll(poll, options, scores)

    assert "Votes cast: 1" in text
    assert "Results hidden until the poll closes." in text
    assert "Current results:" not in text
    assert "1. Pizza - avg 5.0" not in text
    assert "2. Sushi - avg 2.0" not in text
    assert keyboard is not None


def test_render_group_poll_shows_live_ranked_results_when_enabled() -> None:
    poll = make_poll(results_visibility=ResultsVisibility.LIVE)
    options = make_options(poll.id)
    scores = [
        make_score(poll.id, "a", options[0].id, 2),
        make_score(poll.id, "a", options[1].id, 5),
    ]

    text, keyboard = render_group_poll(poll, options, scores)

    assert "Votes cast: 1" in text
    assert "Current results:" in text
    assert "1. Pizza - avg 5.0" in text
    assert "2. Sushi - avg 2.0" in text
    assert keyboard is not None


def test_render_group_poll_closed_omits_vote_button() -> None:
    poll = make_poll(status=PollStatus.CLOSED)
    options = make_options(poll.id)
    scores = [
        make_score(poll.id, "a", options[0].id, 4),
        make_score(poll.id, "a", options[1].id, 3),
    ]

    text, keyboard = render_group_poll(poll, options, scores)

    assert "Where should we eat? [CLOSED]" in text
    assert "Final results (1 votes):" in text
    assert keyboard is None


def test_render_score_prompt_uses_poll_range_and_existing_score() -> None:
    poll = make_poll()
    option = make_options(poll.id)[0]

    text, keyboard = render_score_prompt(poll, option, {option.id: 4})

    assert text == "Score Sushi (0-5):\nCurrent score: 4"
    assert [button.text for button in keyboard.inline_keyboard[0]] == [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
    ]
    assert keyboard.inline_keyboard[0][4].callback_data == score_callback_data(
        poll.id,
        option.display_order,
        4,
    )


def test_render_ballot_summary_lists_scores_and_actions() -> None:
    poll = make_poll()
    options = make_options(poll.id)
    scores = [
        make_score(poll.id, "a", options[0].id, 4),
        make_score(poll.id, "a", options[1].id, 2),
    ]

    text, keyboard = render_ballot_summary(poll, options, scores)

    assert "Your ballot has been recorded." in text
    assert "Sushi: 4" in text
    assert "Pizza: 2" in text
    assert keyboard.inline_keyboard[0][0].callback_data == edit_callback_data(poll.id)
    assert keyboard.inline_keyboard[0][1].callback_data == done_callback_data(poll.id)


@pytest.mark.parametrize('mode', list(VotingMode))
@pytest.mark.parametrize('visibility', list(ResultsVisibility))
@pytest.mark.parametrize('count', [0, 1])
def test_open_messages_always_explain_both_results(mode, visibility, count):
    poll = make_poll(voting_mode=mode, results_visibility=visibility)
    options = make_options(poll.id)
    rows = [make_score(poll.id, 'a', option.id, 3) for option in options] if count else []
    text, keyboard = render_group_poll(poll, options, rows)
    assert SCORE_RESULTS_EXPLANATION in text
    assert keyboard is not None
    if visibility == ResultsVisibility.HIDDEN_UNTIL_CLOSED:
        assert 'Score winner' not in text
        assert 'Condorcet winner' not in text
        assert 'avg' not in text
        assert 'head-to-head' not in text
    elif count:
        assert 'Provisional results' in text
        assert 'Score winners (tied): Sushi, Pizza' in text
        assert 'Condorcet winner (from scores): None.' in text


@pytest.mark.parametrize('status', list(PollStatus))
def test_zero_ballots_have_no_winner_summaries(status):
    poll = make_poll(status=status)
    text, keyboard = render_group_poll(poll, make_options(poll.id), [])
    assert 'Votes cast: 0' in text
    assert 'No complete ballots' in text
    assert ('yet.' if status == PollStatus.OPEN else 'were cast.') in text
    assert 'winner' not in text
    assert 'avg' not in text
    assert (keyboard is None) == (status == PollStatus.CLOSED)


@pytest.mark.parametrize('status', list(PollStatus))
def test_differing_winners_render_separately(status):
    poll = make_poll(status=status, results_visibility=ResultsVisibility.LIVE)
    options = make_options(poll.id)
    rows = [
        make_score(poll.id, str(voter), option.id, value)
        for voter, values in enumerate([(3, 2), (3, 2), (0, 3)])
        for option, value in zip(options, values, strict=True)
    ]
    text, keyboard = render_group_poll(poll, options, rows)
    assert '1. Pizza - avg 2.3' in text
    assert '2. Sushi - avg 2.0' in text
    assert 'Score winner: Pizza' in text
    assert 'Condorcet winner (from scores): Sushi' in text
    assert (keyboard is None) == (status == PollStatus.CLOSED)


def test_duplicate_winners_use_original_option_numbers_after_ranking():
    poll = make_poll(status=PollStatus.CLOSED)
    options = [
        PollOption(uuid4(), poll.id, 'Other', 0),
        PollOption(uuid4(), poll.id, 'Pizza', 1),
        PollOption(uuid4(), poll.id, 'Pizza', 2),
    ]
    rows = [make_score(poll.id, 'a', option.id, score)
            for option, score in zip(options, [0, 5, 3], strict=True)]
    text, _ = render_group_poll(poll, options, rows)
    assert 'Score winner: 2. Pizza' in text
    assert 'Condorcet winner (from scores): 2. Pizza' in text
    rows.append(make_score(poll.id, 'a', options[2].id, 5))
    text, _ = render_group_poll(poll, options, rows)
    assert 'Score winners (tied): 2. Pizza, 3. Pizza' in text
    assert 'Condorcet winner (from scores): None.' in text


def test_rounded_averages_do_not_create_score_ties():
    poll = make_poll(status=PollStatus.CLOSED)
    options = make_options(poll.id)
    rows = [
        make_score(poll.id, str(voter), option.id, 3 if voter < index + 1 else 2)
        for voter in range(100)
        for index, option in enumerate(options)
    ]
    text, _ = render_group_poll(poll, options, rows)
    assert '1. Pizza - avg 2.0' in text
    assert '2. Sushi - avg 2.0' in text
    assert 'Score winner: Pizza' in text
    assert 'Score winners (tied)' not in text


def test_cycle_renders_no_winner_without_fallback():
    poll = make_poll(status=PollStatus.CLOSED)
    options = make_options(poll.id) + [PollOption(uuid4(), poll.id, 'Thai', 2)]
    rows = [
        make_score(poll.id, str(voter), option.id, score)
        for voter, values in enumerate([(3, 2, 1), (1, 3, 2), (2, 1, 3)])
        for option, score in zip(options, values, strict=True)
    ]
    text, _ = render_group_poll(poll, options, rows)
    assert 'Score winners (tied): Sushi, Pizza, Thai' in text
    assert 'Condorcet winner (from scores): None.' in text
    assert 'No option beats every other option head-to-head.' in text


@pytest.mark.parametrize('status', list(PollStatus))
@pytest.mark.parametrize('tied', [False, True])
def test_maximum_unicode_messages_fit_telegram_budget(status, tied):
    poll = replace(make_poll(status=status, results_visibility=ResultsVisibility.LIVE),
                   title='🍣' * MAX_TITLE_LENGTH)
    options = [PollOption(uuid4(), poll.id, '🍕' * MAX_OPTION_LENGTH, i)
               for i in range(MAX_OPTIONS)]
    rows = [make_score(poll.id, 'a', option.id, 5 if tied else option.display_order % 6)
            for option in options]
    text, _ = render_group_poll(poll, options, rows)
    assert len(text.encode('utf-16-le')) // 2 <= 4096
    if tied:
        summary = text.split('Score winners (tied): ')[1].splitlines()[0]
        for i in range(MAX_OPTIONS):
            assert f'{i + 1}. ' in summary
