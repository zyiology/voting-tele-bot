from __future__ import annotations

import shlex
from dataclasses import dataclass

from psycopg.errors import UniqueViolation
from telegram import Chat, Update
from telegram.ext import ContextTypes

from voting_bot.config import Config
from voting_bot.db import Database
from voting_bot.handlers.callbacks import refresh_group_poll
from voting_bot.hashing import hash_voter_id
from voting_bot.rendering import render_group_poll
from voting_bot.repositories import polls


MAX_OPTIONS = 10
MAX_TITLE_LENGTH = 140
MAX_OPTION_LENGTH = 80
MIN_OPTIONS = 2

SCOREPOLL_USAGE = (
    'Usage: /scorepoll [--max N] "Question?" "Option A" "Option B"'
)


@dataclass(frozen=True)
class ScorePollRequest:
    title: str
    options: tuple[str, ...]
    score_max: int | None


class ScorePollParseError(ValueError):
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
                "Close the active poll with /closepoll.",
            ]
        ),
    )


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
    values: list[str] = []
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "--max":
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
    if any(not option for option in option_labels):
        raise ScorePollParseError("Poll options cannot be blank.")
    if any(len(option) > MAX_OPTION_LENGTH for option in option_labels):
        raise ScorePollParseError(
            f"Poll options must be {MAX_OPTION_LENGTH} characters or less."
        )
    if score_max is not None and score_max < 0:
        raise ScorePollParseError("--max must be zero or greater.")

    return ScorePollRequest(title=title, options=option_labels, score_max=score_max)


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
