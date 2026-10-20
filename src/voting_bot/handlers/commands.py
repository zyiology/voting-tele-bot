from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass
from datetime import date, timedelta

from psycopg.errors import UniqueViolation
from telegram import Chat, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from voting_bot.config import Config
from voting_bot.db import Database
from voting_bot.handlers.callbacks import refresh_group_poll
from voting_bot.hashing import hash_voter_id
from voting_bot.models import ResultsVisibility, VotingMode
from voting_bot.rendering import render_group_poll
from voting_bot.repositories import polls


MAX_OPTIONS = 10
MAX_QUICK_OPTIONS = 5
MAX_QUICK_SCORE = 5
MAX_TITLE_LENGTH = 140
MAX_OPTION_LENGTH = 80
MIN_OPTIONS = 2
DATE_POLL_MAX_OPTIONS = 12
DATE_POLL_MIN_OPTIONS = 2
DATE_POLL_QUESTION = "Which dates work? Select all that apply."

MONTH_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
MONTH_LABELS = tuple(month.title() for month in MONTH_NUMBERS)
WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
WEEKDAY_NUMBERS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}
ALL_WEEKDAYS = frozenset(range(7))

logger = logging.getLogger(__name__)

SCOREPOLL_USAGE = (
    'Usage: /scorepoll [--max N] [--quick] [--live-results] '
    '"Question?" "Option A" "Option B"'
)
DATE_POLL_USAGE = (
    "Usage: /poll_dates D Mon YYYY D Mon YYYY [--days LIST]\n"
    "   or: /poll_dates D/M/YY D/M/YY [--days LIST]\n"
    "Example: /poll_dates 5/9/26 18/9/26 --days mon,tues,fri\n"
    "Days: mon,tue,wed,thu,fri,sat,sun; full names and tues/thur/thurs also accepted.\n"
    "Supports 2 to 12 dates after filtering."
)


@dataclass(frozen=True)
class ScorePollRequest:
    title: str
    options: tuple[str, ...]
    score_max: int | None
    voting_mode: VotingMode
    results_visibility: ResultsVisibility


class ScorePollParseError(ValueError):
    pass


@dataclass(frozen=True)
class DatePollRequest:
    start_date: date
    end_date: date
    included_weekdays: frozenset[int]


class DatePollParseError(ValueError):
    pass


async def reply(update: Update, text: str) -> None:
    message = update.effective_message
    if message is None:
        return

    await message.reply_text(text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(
        update,
        "Hi! I run score voting polls. Use /scorepoll in a group to start one.",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(
        update,
        "\n".join(
            [
                SCOREPOLL_USAGE,
                DATE_POLL_USAGE,
                "Score-poll ballots are private. Date-poll voters and their "
                "selections are visible.",
                "Close the active score poll with /closepoll.",
            ]
        ),
    )


async def poll_dates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or message is None:
        return

    if not _is_group_chat(chat):
        await reply(update, "Create date polls from a group chat.")
        return

    try:
        request = parse_poll_dates_command(message.text or "")
        options = generate_date_poll_options(request)
    except DatePollParseError as exc:
        await reply(update, f"{exc}\n{DATE_POLL_USAGE}")
        return

    try:
        await message.reply_poll(
            DATE_POLL_QUESTION,
            options,
            allows_multiple_answers=True,
            is_anonymous=False,
            do_quote=False,
        )
    except TelegramError:
        logger.exception("Telegram could not create a native date poll")
        try:
            await reply(
                update,
                "I couldn't create the date poll. Try again or check that I have "
                "permission to send polls.",
            )
        except TelegramError:
            logger.exception("Telegram also rejected the date-poll failure reply")


async def scorepoll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    if chat is None or user is None or message is None:
        return

    if not _is_group_chat(chat):
        await reply(update, "Create polls from a group chat.")
        return

    try:
        request = parse_scorepoll_command(message.text or "")
    except ScorePollParseError as exc:
        await reply(update, f"{exc}\n{SCOREPOLL_USAGE}")
        return

    db = _db(context)
    config = _config(context)
    score_max = request.score_max if request.score_max is not None else config.score_max
    if score_max < config.score_min:
        await reply(update, f"--max must be at least {config.score_min}.")
        return
    if request.voting_mode == VotingMode.QUICK and score_max > MAX_QUICK_SCORE:
        await reply(update, f"--quick supports --max {MAX_QUICK_SCORE} or lower.")
        return
    if (
        request.voting_mode == VotingMode.QUICK
        and len(request.options) > MAX_QUICK_OPTIONS
    ):
        await reply(
            update,
            f"--quick supports no more than {MAX_QUICK_OPTIONS} options. "
            "Use the default DM mode for larger polls.",
        )
        return

    creator_hash = hash_voter_id(user.id, config.voter_hash_secret)
    try:
        poll, options = await polls.create_score_poll(
            db,
            chat_id=chat.id,
            created_by_hash=creator_hash,
            title=request.title,
            option_labels=request.options,
            score_min=config.score_min,
            score_max=score_max,
            voting_mode=request.voting_mode,
            results_visibility=request.results_visibility,
        )
    except UniqueViolation:
        await reply(update, "This chat already has an open poll. Close it first.")
        return

    text, keyboard = render_group_poll(poll, options, [])
    sent_message = await chat.send_message(text, reply_markup=keyboard)
    await polls.set_poll_message_id(db, poll_id=poll.id, message_id=sent_message.message_id)


async def closepoll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return

    if not _is_group_chat(chat):
        await reply(update, "Close polls from the group chat where they were created.")
        return

    db = _db(context)
    poll = await polls.get_open_poll_for_chat(db, chat.id)
    if poll is None:
        await reply(update, "There is no open poll in this chat.")
        return

    config = _config(context)
    voter_hash = hash_voter_id(user.id, config.voter_hash_secret)
    if voter_hash != poll.created_by_hash and not await _is_chat_admin(
        update,
        context,
        user.id,
    ):
        await reply(update, "Only the poll creator or a group admin can close this poll.")
        return

    closed_poll = await polls.close_poll(db, poll.id)
    if closed_poll is None:
        await reply(update, "This poll is already closed.")
        return

    options = await polls.list_poll_options(db, closed_poll.id)
    await refresh_group_poll(context, closed_poll, options)
    await reply(update, "Poll closed.")


def parse_scorepoll_command(text: str) -> ScorePollRequest:
    raw_args = _strip_command(text)
    if not raw_args:
        raise ScorePollParseError("Missing poll title and options.")

    try:
        parts = shlex.split(raw_args)
    except ValueError as exc:
        raise ScorePollParseError("Malformed command.") from exc

    score_max: int | None = None
    voting_mode = VotingMode.DM
    results_visibility = ResultsVisibility.HIDDEN_UNTIL_CLOSED
    values: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "--quick":
            if voting_mode == VotingMode.QUICK:
                raise ScorePollParseError("--quick can only be provided once.")
            voting_mode = VotingMode.QUICK
        elif part == "--live-results":
            if results_visibility == ResultsVisibility.LIVE:
                raise ScorePollParseError("--live-results can only be provided once.")
            results_visibility = ResultsVisibility.LIVE
        elif part == "--max":
            if score_max is not None:
                raise ScorePollParseError("--max can only be provided once.")
            index += 1
            if index >= len(parts):
                raise ScorePollParseError("--max requires an integer value.")
            try:
                score_max = int(parts[index])
            except ValueError as exc:
                raise ScorePollParseError("--max requires an integer value.") from exc
        elif part.startswith("--max="):
            if score_max is not None:
                raise ScorePollParseError("--max can only be provided once.")
            raw_value = part.removeprefix("--max=")
            try:
                score_max = int(raw_value)
            except ValueError as exc:
                raise ScorePollParseError("--max requires an integer value.") from exc
        elif part.startswith("--"):
            raise ScorePollParseError(f"Unknown option: {part}")
        else:
            values.append(part.strip())
        index += 1

    if len(values) < MIN_OPTIONS + 1:
        raise ScorePollParseError("Provide a title and at least two options.")

    title = values[0]
    option_labels = tuple(values[1:])
    if not title:
        raise ScorePollParseError("Poll title cannot be blank.")
    if len(title) > MAX_TITLE_LENGTH:
        raise ScorePollParseError(f"Poll title must be {MAX_TITLE_LENGTH} characters or less.")
    if len(option_labels) > MAX_OPTIONS:
        raise ScorePollParseError(f"Provide no more than {MAX_OPTIONS} options.")
    if voting_mode == VotingMode.QUICK and len(option_labels) > MAX_QUICK_OPTIONS:
        raise ScorePollParseError(
            f"--quick supports no more than {MAX_QUICK_OPTIONS} options. "
            "Use the default DM mode for larger polls."
        )
    if any(not option for option in option_labels):
        raise ScorePollParseError("Poll options cannot be blank.")
    if any(len(option) > MAX_OPTION_LENGTH for option in option_labels):
        raise ScorePollParseError(
            f"Poll options must be {MAX_OPTION_LENGTH} characters or less."
        )
    if score_max is not None and score_max < 0:
        raise ScorePollParseError("--max must be zero or greater.")

    return ScorePollRequest(
        title=title,
        options=option_labels,
        score_max=score_max,
        voting_mode=voting_mode,
        results_visibility=results_visibility,
    )


def _parse_weekdays(value: str) -> frozenset[int]:
    if not value.strip():
        raise DatePollParseError(
            "--days requires a comma-separated list, e.g. --days mon,tue,fri."
        )
    weekdays: set[int] = set()
    for item in value.split(","):
        name = item.strip().lower()
        if not name:
            raise DatePollParseError(
                "--days contains an empty day. Provide a day between each comma."
            )
        if name not in WEEKDAY_NUMBERS:
            raise DatePollParseError(
                f'Unknown day: "{name}". Use mon,tue,wed,thu,fri,sat,sun '
                "(tues is also accepted)."
            )
        weekdays.add(WEEKDAY_NUMBERS[name])
    return frozenset(weekdays)


def parse_poll_dates_command(text: str) -> DatePollRequest:
    raw_args = _strip_command(text)
    if not raw_args:
        raise DatePollParseError("Provide a start date and an end date.")

    lexer = shlex.shlex(raw_args, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.whitespace += "".join(sorted({c for c in raw_args if c.isspace()}))
    try:
        parts = list(lexer)
    except ValueError as exc:
        raise DatePollParseError("Malformed command. Check quotes around --days.") from exc

    included_weekdays = ALL_WEEKDAYS
    days_provided = False
    values: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "--days":
            if days_provided:
                raise DatePollParseError("--days can only be provided once.")
            days_provided = True
            index += 1
            if index >= len(parts) or parts[index].startswith("--"):
                raise DatePollParseError(
                    "--days requires a comma-separated list, e.g. --days mon,tue,fri."
                )
            included_weekdays = _parse_weekdays(parts[index])
        elif part.startswith("--"):
            raise DatePollParseError(f"Unknown option: {part}")
        else:
            values.append(part)
        index += 1

    if len(values) == 6:
        start_date = _parse_english_date(values[:3])
        end_date = _parse_english_date(values[3:])
    elif len(values) == 2:
        start_date = _parse_numeric_date(values[0])
        end_date = _parse_numeric_date(values[1])
    else:
        raise DatePollParseError(
            "Provide exactly two dates in the format D Mon YYYY or D/M/YY."
        )

    if end_date < start_date:
        raise DatePollParseError("The end date cannot be earlier than the start date.")

    return DatePollRequest(
        start_date=start_date,
        end_date=end_date,
        included_weekdays=included_weekdays,
    )


def generate_date_poll_options(request: DatePollRequest) -> tuple[str, ...]:
    if not request.included_weekdays or not request.included_weekdays <= ALL_WEEKDAYS:
        raise DatePollParseError("Select at least one weekday, using values from 0 to 6.")
    options: list[str] = []
    current_date = request.start_date
    while current_date <= request.end_date:
        if current_date.weekday() in request.included_weekdays:
            options.append(_format_english_date(current_date))
            if len(options) > DATE_POLL_MAX_OPTIONS:
                raise DatePollParseError(
                    "The range produces at least 13 dates after day filtering. "
                    "Shorten the range or select fewer days; native polls support "
                    "no more than 12."
                )
        if current_date == request.end_date:
            break
        current_date += timedelta(days=1)

    if len(options) < DATE_POLL_MIN_OPTIONS:
        raise DatePollParseError(
            "The range must produce at least two dates after day filtering. "
            "Extend the range or select more days."
        )

    return tuple(options)


def _parse_english_date(parts: list[str]) -> date:
    day_text, month_text, year_text = parts
    if not (
        day_text.isascii()
        and day_text.isdecimal()
        and 1 <= len(day_text) <= 2
        and year_text.isascii()
        and year_text.isdecimal()
        and len(year_text) == 4
    ):
        raise DatePollParseError(
            f"Invalid date: {' '.join(parts)}. Use the format D Mon YYYY."
        )

    month = MONTH_NUMBERS.get(month_text.casefold())
    if month is None:
        raise DatePollParseError(
            f"Invalid date: {' '.join(parts)}. Use an English month abbreviation."
        )

    try:
        day = int(day_text)
        year = int(year_text)
        return date(year, month, day)
    except ValueError as exc:
        raise DatePollParseError(f"Invalid date: {' '.join(parts)}.") from exc


def _parse_numeric_date(value: str) -> date:
    parts = value.split("/")
    if len(parts) != 3:
        raise DatePollParseError(f"Invalid date: {value}. Use the format D/M/YY.")

    day_text, month_text, year_text = parts
    if not (
        day_text.isascii()
        and day_text.isdecimal()
        and 1 <= len(day_text) <= 2
        and month_text.isascii()
        and month_text.isdecimal()
        and 1 <= len(month_text) <= 2
        and year_text.isascii()
        and year_text.isdecimal()
        and len(year_text) == 2
    ):
        raise DatePollParseError(f"Invalid date: {value}. Use the format D/M/YY.")

    try:
        return date(2000 + int(year_text), int(month_text), int(day_text))
    except ValueError as exc:
        raise DatePollParseError(f"Invalid date: {value}.") from exc


def _format_english_date(value: date) -> str:
    return (
        f"{WEEKDAY_LABELS[value.weekday()]}, {value.day} "
        f"{MONTH_LABELS[value.month - 1]} {value.year}"
    )


def _strip_command(text: str) -> str:
    return text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) == 2 else ""


def _is_group_chat(chat: Chat) -> bool:
    return chat.type in {"group", "supergroup"}


async def _is_chat_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
) -> bool:
    chat = update.effective_chat
    if chat is None:
        return False

    member = await context.bot.get_chat_member(chat.id, user_id)
    return member.status in {"administrator", "creator"}


def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    db = context.bot_data["db"]
    if not isinstance(db, Database):
        raise RuntimeError("bot_data['db'] must be a Database")
    return db


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    config = context.bot_data["config"]
    if not isinstance(config, Config):
        raise RuntimeError("bot_data['config'] must be a Config")
    return config
