from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from voting_bot.models import BallotScore, Poll, PollOption, PollStatus, VotingMethodOptions
from voting_bot.rendering import (
    done_callback_data,
    edit_callback_data,
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
) -> Poll:
    return Poll(
        id=poll_id or uuid4(),
        chat_id=-100,
        message_id=123,
        created_by_hash="creator",
        title="Where should we eat?",
        voting_method=VotingMethodOptions.SCORE,
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


def test_render_group_poll_shows_ranked_results() -> None:
    poll = make_poll()
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
