from __future__ import annotations

from uuid import uuid4

import pytest

from voting_bot.handlers.callbacks import (
    CallbackDataError,
    parse_callback_data,
)
from voting_bot.handlers.commands import (
    ScorePollParseError,
    parse_scorepoll_command,
)
from voting_bot.rendering import (
    done_callback_data,
    edit_callback_data,
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


def test_parse_scorepoll_command_accepts_max_after_values() -> None:
    request = parse_scorepoll_command(
        '/scorepoll "Best food?" "Sushi" "Pizza" --max=7'
    )

    assert request.title == "Best food?"
    assert request.options == ("Sushi", "Pizza")
    assert request.score_max == 7


@pytest.mark.parametrize(
    "text",
    [
        "/scorepoll",
        '/scorepoll "Question?" "Only one option"',
        '/scorepoll --max "Question?" "Sushi" "Pizza"',
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


@pytest.mark.parametrize("data", ["", "x:not-a-uuid", "v:not-a-uuid", "s:not-enough"])
def test_parse_callback_data_rejects_invalid_payloads(data: str) -> None:
    with pytest.raises(CallbackDataError):
        parse_callback_data(data)
