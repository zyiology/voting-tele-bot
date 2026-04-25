from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from telegram import CallbackQuery
from telegram.ext import ContextTypes

from voting_bot.handlers import callbacks
from voting_bot.handlers.callbacks import (
    CallbackDataError,
    _record_quick_score,
    parse_callback_data,
)
from voting_bot.handlers.commands import (
    ScorePollParseError,
    parse_scorepoll_command,
)
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
    done_callback_data,
    edit_callback_data,
    quick_score_callback_data,
    score_callback_data,
    vote_callback_data,
)


def test_parse_scorepoll_command_accepts_max_before_values() -> None:
    request = parse_scorepoll_command(
        '/scorepoll --max 10 "Best food?" "Sushi" "Pizza"'
    )

    assert request.title == "Best food?"
    assert request.options == ("Sushi", "Pizza")
    assert request.score_max == 10
    assert request.voting_mode == VotingMode.DM
    assert request.results_visibility == ResultsVisibility.HIDDEN_UNTIL_CLOSED


def test_parse_scorepoll_command_accepts_max_after_values() -> None:
    request = parse_scorepoll_command(
        '/scorepoll "Best food?" "Sushi" "Pizza" --max=7'
    )

    assert request.title == "Best food?"
    assert request.options == ("Sushi", "Pizza")
    assert request.score_max == 7
    assert request.voting_mode == VotingMode.DM
    assert request.results_visibility == ResultsVisibility.HIDDEN_UNTIL_CLOSED


def test_parse_scorepoll_command_accepts_quick_mode() -> None:
    request = parse_scorepoll_command(
        '/scorepoll --quick --max 5 "Best food?" "Sushi" "Pizza"'
    )

    assert request.title == "Best food?"
    assert request.options == ("Sushi", "Pizza")
    assert request.score_max == 5
    assert request.voting_mode == VotingMode.QUICK
    assert request.results_visibility == ResultsVisibility.HIDDEN_UNTIL_CLOSED


def test_parse_scorepoll_command_accepts_live_results() -> None:
    request = parse_scorepoll_command(
        '/scorepoll --live-results "Best food?" "Sushi" "Pizza"'
    )

    assert request.title == "Best food?"
    assert request.options == ("Sushi", "Pizza")
    assert request.score_max is None
    assert request.voting_mode == VotingMode.DM
    assert request.results_visibility == ResultsVisibility.LIVE


@pytest.mark.parametrize(
    "text",
    [
        "/scorepoll",
        '/scorepoll "Question?" "Only one option"',
        '/scorepoll --max "Question?" "Sushi" "Pizza"',
        '/scorepoll --quick --quick "Question?" "Sushi" "Pizza"',
        '/scorepoll --live-results --live-results "Question?" "Sushi" "Pizza"',
        '/scorepoll --quick "Question?" "A" "B" "C" "D" "E" "F"',
        '/scorepoll --unknown "Question?" "Sushi" "Pizza"',
        '/scorepoll "Question?" "Sushi',
    ],
)
def test_parse_scorepoll_command_rejects_malformed_input(text: str) -> None:
    with pytest.raises(ScorePollParseError):
        parse_scorepoll_command(text)


def test_parse_callback_data_round_trips_vote_edit_done_actions() -> None:
    poll_id = uuid4()

    assert parse_callback_data(vote_callback_data(poll_id)).kind == "v"
    assert parse_callback_data(edit_callback_data(poll_id)).kind == "e"
    assert parse_callback_data(done_callback_data(poll_id)).kind == "d"


def test_parse_callback_data_round_trips_score_action() -> None:
    poll_id = uuid4()

    action = parse_callback_data(score_callback_data(poll_id, 3, 5))

    assert action.kind == "s"
    assert action.poll_id == poll_id
    assert action.option_order == 3
    assert action.score == 5


def test_parse_callback_data_round_trips_quick_score_action() -> None:
    poll_id = uuid4()

    action = parse_callback_data(quick_score_callback_data(poll_id, 1, 4))

    assert action.kind == "q"
    assert action.poll_id == poll_id
    assert action.option_order == 1
    assert action.score == 4


@pytest.mark.parametrize("data", ["", "x:not-a-uuid", "v:not-a-uuid", "s:not-enough"])
def test_parse_callback_data_rejects_invalid_payloads(data: str) -> None:
    with pytest.raises(CallbackDataError):
        parse_callback_data(data)


def test_record_quick_score_saves_score_and_reports_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    poll = _make_poll(voting_mode=VotingMode.QUICK)
    options = _make_options(poll.id)
    db = object()
    query = SimpleNamespace(answer=AsyncMock())
    refresh = AsyncMock()
    upsert_score = AsyncMock()
    get_poll_with_options = AsyncMock(return_value=(poll, options))
    get_voter_scores = AsyncMock(
        return_value=[
            BallotScore(poll.id, "voter", options[0].id, 4),
        ]
    )

    monkeypatch.setattr(callbacks, "_db", lambda context: db)
    monkeypatch.setattr(callbacks.polls, "get_poll_with_options", get_poll_with_options)
    monkeypatch.setattr(callbacks.ballots, "upsert_score", upsert_score)
    monkeypatch.setattr(callbacks.ballots, "get_voter_scores", get_voter_scores)
    monkeypatch.setattr(callbacks, "refresh_group_poll", refresh)

    context = SimpleNamespace()
    asyncio.run(
        _record_quick_score(
            cast(ContextTypes.DEFAULT_TYPE, context),
            poll.id,
            "voter",
            options[0].display_order,
            4,
            cast(CallbackQuery, query),
        )
    )

    upsert_score.assert_awaited_once_with(
        db,
        poll_id=poll.id,
        voter_hash="voter",
        option_id=options[0].id,
        score=4,
    )
    query.answer.assert_awaited_once_with("Saved Sushi: 4. 1/2 scored.")
    refresh.assert_awaited_once_with(context, poll, options)


def test_record_quick_score_reports_complete_ballot(monkeypatch: pytest.MonkeyPatch) -> None:
    poll = _make_poll(voting_mode=VotingMode.QUICK)
    options = _make_options(poll.id)
    db = object()
    query = SimpleNamespace(answer=AsyncMock())

    monkeypatch.setattr(callbacks, "_db", lambda context: db)
    monkeypatch.setattr(
        callbacks.polls,
        "get_poll_with_options",
        AsyncMock(return_value=(poll, options)),
    )
    monkeypatch.setattr(callbacks.ballots, "upsert_score", AsyncMock())
    monkeypatch.setattr(
        callbacks.ballots,
        "get_voter_scores",
        AsyncMock(
            return_value=[
                BallotScore(poll.id, "voter", options[0].id, 4),
                BallotScore(poll.id, "voter", options[1].id, 5),
            ]
        ),
    )
    monkeypatch.setattr(callbacks, "refresh_group_poll", AsyncMock())

    asyncio.run(
        _record_quick_score(
            cast(ContextTypes.DEFAULT_TYPE, SimpleNamespace()),
            poll.id,
            "voter",
            options[1].display_order,
            5,
            cast(CallbackQuery, query),
        )
    )

    query.answer.assert_awaited_once_with("Ballot complete. Saved Pizza: 5.")


def test_record_quick_score_rejects_dm_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    poll = _make_poll(voting_mode=VotingMode.DM)
    options = _make_options(poll.id)
    query = SimpleNamespace(answer=AsyncMock())
    upsert_score = AsyncMock()

    monkeypatch.setattr(callbacks, "_db", lambda context: object())
    monkeypatch.setattr(
        callbacks.polls,
        "get_poll_with_options",
        AsyncMock(return_value=(poll, options)),
    )
    monkeypatch.setattr(callbacks.ballots, "upsert_score", upsert_score)

    asyncio.run(
        _record_quick_score(
            cast(ContextTypes.DEFAULT_TYPE, SimpleNamespace()),
            poll.id,
            "voter",
            options[0].display_order,
            4,
            cast(CallbackQuery, query),
        )
    )

    query.answer.assert_awaited_once_with(
        "This button is no longer valid.",
        show_alert=True,
    )
    upsert_score.assert_not_awaited()


def _make_poll(*, voting_mode: VotingMode) -> Poll:
    return Poll(
        id=uuid4(),
        chat_id=-100,
        message_id=123,
        created_by_hash="creator",
        title="Where should we eat?",
        voting_method=VotingMethodOptions.SCORE,
        voting_mode=voting_mode,
        results_visibility=ResultsVisibility.HIDDEN_UNTIL_CLOSED,
        status=PollStatus.OPEN,
        score_min=0,
        score_max=5,
        created_at=datetime.now(UTC),
        closed_at=None,
    )


def _make_options(poll_id: UUID) -> list[PollOption]:
    return [
        PollOption(uuid4(), poll_id, "Sushi", 0),
        PollOption(uuid4(), poll_id, "Pizza", 1),
    ]
