from __future__ import annotations

import asyncio
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from telegram import CallbackQuery, Chat, Message, Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

from voting_bot.handlers import callbacks
from voting_bot.handlers.callbacks import (
    CallbackDataError,
    _record_quick_score,
    parse_callback_data,
)
from voting_bot.handlers.commands import (
    DATE_POLL_QUESTION,
    DatePollParseError,
    DatePollRequest,
    ScorePollParseError,
    generate_date_poll_options,
    help_command,
    parse_poll_dates_command,
    parse_scorepoll_command,
    poll_dates,
)
from voting_bot.main import register_handlers
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


def test_parse_poll_dates_accepts_documented_and_botname_commands() -> None:
    documented = parse_poll_dates_command(
        "/poll_dates 5 Sep 2026 18 Sep 2026 --days mon,tue,wed,thu,fri"
    )
    addressed = parse_poll_dates_command(
        "/poll_dates@calendar_bot 5 Sep 2026 18 Sep 2026"
    )

    assert documented == DatePollRequest(
        date(2026, 9, 5), date(2026, 9, 18), frozenset(range(5))
    )
    assert addressed == DatePollRequest(
        date(2026, 9, 5), date(2026, 9, 18), frozenset(range(7))
    )


def test_parse_poll_dates_accepts_mixed_case_months() -> None:
    request = parse_poll_dates_command("/poll_dates 30 dEc 2026 2 jAN 2027")

    assert request.start_date == date(2026, 12, 30)
    assert request.end_date == date(2027, 1, 2)


def test_parse_poll_dates_accepts_numeric_dates() -> None:
    request = parse_poll_dates_command(
        "/poll_dates 5/9/26 18/9/26 --days mon,tue,wed,thu,fri"
    )

    assert request == DatePollRequest(
        date(2026, 9, 5), date(2026, 9, 18), frozenset(range(5))
    )


@pytest.mark.parametrize(
    ("text", "expected_start", "expected_end"),
    [
        ("/poll_dates 1/1/00 2/1/00", date(2000, 1, 1), date(2000, 1, 2)),
        ("/poll_dates 30/12/99 31/12/99", date(2099, 12, 30), date(2099, 12, 31)),
        ("/poll_dates 01/09/26 02/09/26", date(2026, 9, 1), date(2026, 9, 2)),
    ],
)
def test_parse_poll_dates_maps_numeric_years_to_2000s(
    text: str,
    expected_start: date,
    expected_end: date,
) -> None:
    request = parse_poll_dates_command(text)

    assert request.start_date == expected_start
    assert request.end_date == expected_end


@pytest.mark.parametrize(
    "text",
    [
        "/poll_dates",
        "/poll_dates 5 Sep 2026",
        "/poll_dates 5 Sep 2026 8 Sep 2026 extra",
        "/poll_dates 5 September 2026 8 Sep 2026",
        "/poll_dates +5 Sep 2026 8 Sep 2026",
        "/poll_dates 5 Sep 26 8 Sep 2026",
        "/poll_dates 31 Apr 2026 2 May 2026",
        "/poll_dates 5 Sep 2026 4 Sep 2026",
        "/poll_dates 5/9/26 18 Sep 2026",
        "/poll_dates 5/9/2026 18/9/2026",
        "/poll_dates 31/4/26 2/5/26",
        "/poll_dates 5-9-26 18-9-26",
        "/poll_dates 5 Sep 2026 8 Sep 2026 --unknown",
        "/poll_dates 5 Sep 2026 8 Sep 2026 --exclude-weekends",
    ],
)
def test_parse_poll_dates_rejects_invalid_input(text: str) -> None:
    with pytest.raises(DatePollParseError):
        parse_poll_dates_command(text)


def test_parse_poll_dates_validates_leap_days() -> None:
    request = parse_poll_dates_command("/poll_dates 28 Feb 2028 29 Feb 2028")

    assert request.end_date == date(2028, 2, 29)
    with pytest.raises(DatePollParseError, match="Invalid date"):
        parse_poll_dates_command("/poll_dates 28 Feb 2027 29 Feb 2027")


def test_generate_date_poll_options_crosses_month_and_year_in_order() -> None:
    options = generate_date_poll_options(
        DatePollRequest(date(2026, 12, 30), date(2027, 1, 2), frozenset(range(7)))
    )

    assert options == (
        "Wed, 30 Dec 2026",
        "Thu, 31 Dec 2026",
        "Fri, 1 Jan 2027",
        "Sat, 2 Jan 2027",
    )


def test_generate_date_poll_options_excludes_saturday_and_sunday() -> None:
    options = generate_date_poll_options(
        DatePollRequest(date(2026, 9, 5), date(2026, 9, 8), frozenset(range(5)))
    )

    assert options == ("Mon, 7 Sep 2026", "Tue, 8 Sep 2026")


@pytest.mark.parametrize("option_count", [2, 12])
def test_generate_date_poll_options_accepts_option_boundaries(
    option_count: int,
) -> None:
    options = generate_date_poll_options(
        DatePollRequest(
            date(2026, 9, 7),
            date(2026, 9, 7 + option_count - 1),
            frozenset(range(7)),
        )
    )

    assert len(options) == option_count


def test_generate_date_poll_options_rejects_too_few_after_filtering() -> None:
    with pytest.raises(DatePollParseError, match="at least two"):
        generate_date_poll_options(
            DatePollRequest(date(2026, 9, 5), date(2026, 9, 6), frozenset(range(5)))
        )


def test_generate_date_poll_options_stops_at_thirteenth_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    formatted_dates: list[date] = []

    def track_format(value: date) -> str:
        formatted_dates.append(value)
        return value.isoformat()

    monkeypatch.setattr(
        "voting_bot.handlers.commands._format_english_date",
        track_format,
    )

    with pytest.raises(DatePollParseError, match="at least 13"):
        generate_date_poll_options(
            DatePollRequest(date(1, 1, 1), date(9999, 12, 31), frozenset(range(7)))
        )

    assert len(formatted_dates) == 13


@pytest.mark.parametrize(
    "dates", [("5/9/26", "18/9/26"), ("5 Sep 2026", "18 Sep 2026")]
)
@pytest.mark.parametrize("position", [0, 1, 2])
@pytest.mark.parametrize(
    "days", ["mon,tues,fri", "'Mon, tUeS, FRI'", '"mon, tues, fri"']
)
def test_parse_poll_dates_accepts_days_in_any_position(
    dates: tuple[str, str], position: int, days: str
) -> None:
    args = list(dates)
    args.insert(position, f"--days {days}")
    request = parse_poll_dates_command("/poll_dates@calendar_bot " + " ".join(args))

    assert request == DatePollRequest(
        date(2026, 9, 5), date(2026, 9, 18), frozenset({0, 1, 4})
    )


@pytest.mark.parametrize(
    ("aliases", "weekday"),
    [
        ("mon,monday,MON", 0),
        ("tue,tues,tuesday", 1),
        ("wed,wednesday", 2),
        ("thu,thur,thurs,thursday", 3),
        ("fri,friday", 4),
        ("sat,saturday", 5),
        ("sun,sunday", 6),
    ],
)
def test_parse_poll_dates_normalizes_aliases(aliases: str, weekday: int) -> None:
    request = parse_poll_dates_command(f"/poll_dates 5/9/26 18/9/26 --days {aliases}")
    assert request.included_weekdays == frozenset({weekday})


@pytest.mark.parametrize("separator", ["\u00a0", "\u202f"])
@pytest.mark.parametrize("dates", ["5/9/26 18/9/26", "5 Sep 2026 18 Sep 2026"])
@pytest.mark.parametrize(
    ("flag", "weekdays"),
    [
        ("", frozenset(range(7))),
        ('--days "mon, tues, fri"', frozenset({0, 1, 4})),
    ],
)
def test_parse_poll_dates_preserves_unicode_whitespace(
    separator: str, dates: str, flag: str, weekdays: frozenset[int]
) -> None:
    text = f"/poll_dates {dates} {flag}".replace(" ", separator)
    request = parse_poll_dates_command(text)
    assert request == DatePollRequest(date(2026, 9, 5), date(2026, 9, 18), weekdays)


@pytest.mark.parametrize(
    ("flag", "error"),
    [
        ("--days", "requires a comma-separated list"),
        ("--days --unknown", "requires a comma-separated list"),
        ("--days ''", "requires a comma-separated list"),
        ('--days "  "', "requires a comma-separated list"),
        ("--days mon,,fri", "contains an empty day"),
        ("--days ,mon", "contains an empty day"),
        ("--days mon,", "contains an empty day"),
        ("--days funday", "Unknown day"),
        ("--days 0", "Unknown day"),
        ("--days mon-fri", "Unknown day"),
        ("--days weekdays", "Unknown day"),
        ("--days 'mon,fri", "Malformed command"),
        ('--days "mon,fri', "Malformed command"),
        ("--days mon --days fri", "only be provided once"),
        ("--days=mon,fri", "Unknown option"),
        ("--days mon, fri", "contains an empty day"),
        ("--days mon,fri extra", "exactly two dates"),
        ("--days mon,\u00a0fri", "contains an empty day"),
        ("--days mon,\u202ffri", "contains an empty day"),
        ("--days mon,fri # comment", "exactly two dates"),
    ],
)
def test_parse_poll_dates_rejects_invalid_days(flag: str, error: str) -> None:
    with pytest.raises(DatePollParseError, match=error):
        parse_poll_dates_command(f"/poll_dates 5/9/26 18/9/26 {flag}")


def test_date_poll_filters_preserve_existing_results() -> None:
    command = "/poll_dates 5/9/26 14/9/26"
    original = parse_poll_dates_command(command)
    selected = parse_poll_dates_command(
        f"{command} --days mon,tue,wed,thu,fri,sat,sun"
    )
    assert original == selected
    assert generate_date_poll_options(original) == generate_date_poll_options(selected)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (
            "mon,tues,fri",
            (
                "Mon, 7 Sep 2026",
                "Tue, 8 Sep 2026",
                "Fri, 11 Sep 2026",
                "Mon, 14 Sep 2026",
                "Tue, 15 Sep 2026",
                "Fri, 18 Sep 2026",
            ),
        ),
        (
            "fri,sat,sun",
            (
                "Sat, 5 Sep 2026",
                "Sun, 6 Sep 2026",
                "Fri, 11 Sep 2026",
                "Sat, 12 Sep 2026",
                "Sun, 13 Sep 2026",
                "Fri, 18 Sep 2026",
            ),
        ),
        (
            "fri,mon,monday,mon",
            (
                "Mon, 7 Sep 2026",
                "Fri, 11 Sep 2026",
                "Mon, 14 Sep 2026",
                "Fri, 18 Sep 2026",
            ),
        ),
    ],
)
def test_date_poll_days_examples(days: str, expected: tuple[str, ...]) -> None:
    request = parse_poll_dates_command(f"/poll_dates 5/9/26 18/9/26 --days '{days}'")
    assert generate_date_poll_options(request) == expected


@pytest.mark.parametrize(
    ("dates", "days", "expected"),
    [
        ("30/12/26 2/1/27", "wed,sat", ("Wed, 30 Dec 2026", "Sat, 2 Jan 2027")),
        ("28/2/28 1/3/28", "tue,wed", ("Tue, 29 Feb 2028", "Wed, 1 Mar 2028")),
    ],
)
def test_date_poll_days_cross_calendar_boundaries(
    dates: str, days: str, expected: tuple[str, ...]
) -> None:
    request = parse_poll_dates_command(f"/poll_dates {dates} --days {days}")
    assert generate_date_poll_options(request) == expected


@pytest.mark.parametrize("count", [0, 1, 2, 12, 13])
def test_date_poll_limits_apply_after_single_weekday_filter(count: int) -> None:
    start = date(2026, 9, 7)
    request = DatePollRequest(
        start,
        start + timedelta(days=max(0, count - 1) * 7),
        frozenset({1 if count == 0 else 0}),
    )
    if count < 2:
        with pytest.raises(
            DatePollParseError, match="Extend the range or select more days"
        ):
            generate_date_poll_options(request)
    elif count > 12:
        with pytest.raises(DatePollParseError, match="at least 13"):
            generate_date_poll_options(request)
    else:
        options = generate_date_poll_options(request)
        assert len(options) == count
        assert options[0] == "Mon, 7 Sep 2026"
        assert all(option.startswith("Mon,") for option in options)


def test_date_poll_single_weekday_stops_after_thirteenth_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    formatted: list[date] = []

    def track_format(value: date) -> str:
        formatted.append(value)
        return value.isoformat()

    monkeypatch.setattr(
        "voting_bot.handlers.commands._format_english_date", track_format
    )
    with pytest.raises(DatePollParseError, match="at least 13"):
        generate_date_poll_options(DatePollRequest(date.min, date.max, frozenset({0})))
    assert formatted == [date.min + timedelta(weeks=i) for i in range(13)]


@pytest.mark.parametrize(
    "weekdays", [frozenset(), frozenset({-1}), frozenset({7}), frozenset({0, 7})]
)
def test_date_poll_rejects_invalid_direct_weekdays_before_scanning(
    weekdays: frozenset[int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_on_iteration(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid weekday selection must fail before date iteration")

    monkeypatch.setattr(
        "voting_bot.handlers.commands._format_english_date", fail_on_iteration
    )
    monkeypatch.setattr("voting_bot.handlers.commands.timedelta", fail_on_iteration)
    with pytest.raises(DatePollParseError, match="Select at least one weekday"):
        generate_date_poll_options(DatePollRequest(date.min, date.max, weekdays))


@pytest.mark.parametrize(
    "weekdays", [frozenset(range(7)), frozenset({3, 4}), frozenset({2, 3})]
)
def test_date_poll_handles_date_max(weekdays: frozenset[int]) -> None:
    options = generate_date_poll_options(
        DatePollRequest(date(9999, 12, 29), date.max, weekdays)
    )
    expected = {2: "Wed, 29 Dec 9999", 3: "Thu, 30 Dec 9999", 4: "Fri, 31 Dec 9999"}
    assert options == tuple(label for day, label in expected.items() if day in weekdays)


@pytest.mark.parametrize(
    "text",
    [
        "/poll_dates 7 Sep 2026 8 Sep 2026",
        "/poll_dates 5/9/26 10/9/26 --days mon,tues",
    ],
)
def test_poll_dates_sends_native_visible_multiple_answer_poll(text: str) -> None:
    message = SimpleNamespace(
        text=text,
        reply_poll=AsyncMock(),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="supergroup"),
        effective_message=message,
    )

    asyncio.run(
        poll_dates(
            cast(Update, update),
            cast(ContextTypes.DEFAULT_TYPE, SimpleNamespace()),
        )
    )

    message.reply_poll.assert_awaited_once_with(
        DATE_POLL_QUESTION,
        ("Mon, 7 Sep 2026", "Tue, 8 Sep 2026"),
        allows_multiple_answers=True,
        is_anonymous=False,
        do_quote=False,
    )


def test_poll_dates_rejects_private_chats() -> None:
    message = SimpleNamespace(
        text="/poll_dates 7 Sep 2026 8 Sep 2026",
        reply_poll=AsyncMock(),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="private"),
        effective_message=message,
    )

    asyncio.run(
        poll_dates(
            cast(Update, update),
            cast(ContextTypes.DEFAULT_TYPE, SimpleNamespace()),
        )
    )

    message.reply_poll.assert_not_awaited()
    message.reply_text.assert_awaited_once_with("Create date polls from a group chat.")


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("/poll_dates 31 Feb 2026 1 Mar 2026", "Invalid date"),
        ("/poll_dates 5/9/26 18/9/26 --days funday", "Unknown day"),
    ],
)
def test_poll_dates_replies_with_usage_without_sending_invalid_poll(
    text: str,
    error: str,
) -> None:
    message = SimpleNamespace(
        text=text,
        reply_poll=AsyncMock(),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="group"),
        effective_message=message,
    )

    asyncio.run(
        poll_dates(
            cast(Update, update),
            cast(ContextTypes.DEFAULT_TYPE, SimpleNamespace()),
        )
    )

    message.reply_poll.assert_not_awaited()
    error_text = message.reply_text.await_args.args[0]
    assert error in error_text
    assert "Usage: /poll_dates" in error_text


def test_poll_dates_reports_telegram_failure() -> None:
    message = SimpleNamespace(
        text="/poll_dates 7 Sep 2026 8 Sep 2026",
        reply_poll=AsyncMock(side_effect=TelegramError("polls forbidden")),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_chat=SimpleNamespace(type="group"),
        effective_message=message,
    )

    asyncio.run(
        poll_dates(
            cast(Update, update),
            cast(ContextTypes.DEFAULT_TYPE, SimpleNamespace()),
        )
    )

    message.reply_text.assert_awaited_once()
    assert "permission to send polls" in message.reply_text.await_args.args[0]


def test_help_distinguishes_score_and_date_poll_privacy() -> None:
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_message=message)

    asyncio.run(
        help_command(
            cast(Update, update),
            cast(ContextTypes.DEFAULT_TYPE, SimpleNamespace()),
        )
    )

    help_text = message.reply_text.await_args.args[0]
    assert "/poll_dates" in help_text
    assert "[--days LIST]" in help_text
    assert "--exclude-weekends" not in help_text
    assert "Supports 2 to 12 dates after filtering." in help_text
    assert "Score-poll ballots are private" in help_text
    assert "Date-poll voters and their selections are visible" in help_text
    assert "Score winners have the highest average" in help_text
    assert "A Condorcet winner must beat every other option head-to-head" in help_text
    assert "equal scores mean no preference" in help_text
    assert "Only complete ballots count for both results" in help_text


def test_register_handlers_excludes_edited_poll_dates_commands() -> None:
    app = SimpleNamespace(add_handler=Mock())

    register_handlers(cast(Application, app))

    handlers = [call.args[0] for call in app.add_handler.call_args_list]
    date_handler = next(
        handler
        for handler in handlers
        if isinstance(handler, CommandHandler) and handler.callback is poll_dates
    )
    normal_update = Update(
        1,
        message=Message(
            message_id=1,
            date=datetime.now(UTC),
            chat=Chat(-100, "group"),
        ),
    )
    edited_update = Update(
        2,
        edited_message=Message(
            message_id=2,
            date=datetime.now(UTC),
            chat=Chat(-100, "group"),
        ),
    )

    assert date_handler.filters.check_update(normal_update)
    assert not date_handler.filters.check_update(edited_update)


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


@pytest.mark.parametrize("mode", list(VotingMode))
def test_score_reports_closure_during_save(monkeypatch: pytest.MonkeyPatch, mode: VotingMode):
    poll = _make_poll(voting_mode=mode)
    options = _make_options(poll.id)
    query = SimpleNamespace(answer=AsyncMock())
    private_message = AsyncMock()
    refresh = AsyncMock()
    get_scores = AsyncMock()
    monkeypatch.setattr(callbacks, "_db", lambda context: object())
    monkeypatch.setattr(
        callbacks.polls, "get_poll_with_options", AsyncMock(return_value=(poll, options))
    )
    monkeypatch.setattr(
        callbacks.ballots, "upsert_score",
        AsyncMock(side_effect=callbacks.ballots.PollNotOpenError),
    )
    monkeypatch.setattr(callbacks.ballots, "get_voter_scores", get_scores)
    monkeypatch.setattr(callbacks, "_send_private_message", private_message)
    monkeypatch.setattr(callbacks, "refresh_group_poll", refresh)
    context = cast(ContextTypes.DEFAULT_TYPE, SimpleNamespace())

    if mode == VotingMode.QUICK:
        asyncio.run(callbacks._record_quick_score(
            context, poll.id, "voter", 0, 4, cast(CallbackQuery, query)
        ))
        query.answer.assert_awaited_once_with("This poll is closed.", show_alert=True)
        private_message.assert_not_awaited()
    else:
        asyncio.run(callbacks._record_score(context, poll.id, "voter", 42, 0, 4))
        private_message.assert_awaited_once_with(context, 42, "This poll is closed.")
    get_scores.assert_not_awaited()
    refresh.assert_not_awaited()


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


@pytest.mark.parametrize('mode', list(VotingMode))
@pytest.mark.parametrize('visibility', list(ResultsVisibility))
@pytest.mark.parametrize('status', list(PollStatus))
def test_refresh_uses_one_saved_snapshot_for_both_results(monkeypatch, mode, visibility, status):
    from dataclasses import replace

    poll = replace(_make_poll(voting_mode=mode), results_visibility=visibility, status=status)
    options = _make_options(poll.id)
    rows = [
        BallotScore(poll.id, str(voter), option.id, score)
        for voter, values in enumerate([(3, 2), (3, 2), (0, 3)])
        for option, score in zip(options, values, strict=True)
    ]
    db = object()
    list_scores = AsyncMock(return_value=rows)
    edit_message = AsyncMock()
    monkeypatch.setattr(callbacks, '_db', lambda context: db)
    monkeypatch.setattr(callbacks.polls, 'message_refresh_lock', lambda db, poll_id: nullcontext())
    monkeypatch.setattr(callbacks.polls, 'get_poll', AsyncMock(return_value=poll))
    monkeypatch.setattr(callbacks.ballots, 'list_ballot_scores', list_scores)
    context = SimpleNamespace(bot=SimpleNamespace(edit_message_text=edit_message))
    asyncio.run(callbacks.refresh_group_poll(cast(ContextTypes.DEFAULT_TYPE, context), poll, options))
    list_scores.assert_awaited_once_with(db, poll.id)
    edit_message.assert_awaited_once()
    assert edit_message.await_args is not None
    args = edit_message.await_args.kwargs
    text = args['text']
    if status == PollStatus.OPEN and visibility == ResultsVisibility.HIDDEN_UNTIL_CLOSED:
        assert 'winner' not in text
        assert 'avg' not in text
    else:
        assert 'Score winner: Pizza' in text
        assert 'Condorcet winner (from scores): Sushi' in text
    assert (args['reply_markup'] is None) == (status == PollStatus.CLOSED)
