from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from telegram import CallbackQuery, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from voting_bot.config import Config
from voting_bot.db import Database
from voting_bot.hashing import hash_voter_id
from voting_bot.models import BallotScore, Poll, PollOption, PollStatus, VotingMode
from voting_bot.rendering import (
    render_ballot_summary,
    render_group_poll,
    render_score_prompt,
)
from voting_bot.repositories import ballots, polls
from voting_bot.voting_methods.score import ScoreValidationError, validate_score


@dataclass(frozen=True)
class CallbackAction:
    kind: str
    poll_id: UUID
    option_order: int | None = None
    score: int | None = None


class CallbackDataError(ValueError):
    pass


class PrivateMessageUnavailable(RuntimeError):
    pass


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return

    try:
        action = parse_callback_data(query.data)
    except CallbackDataError:
        await query.answer("This button is no longer valid.", show_alert=True)
        return

    db = _db(context)
    config = _config(context)
    voter_hash = hash_voter_id(user.id, config.voter_hash_secret)

    if action.kind == "v":
        try:
            await _start_or_resume_vote(context, action.poll_id, voter_hash, user.id)
        except PrivateMessageUnavailable:
            await query.answer(
                "Please open a private chat with this bot and press Start first.",
                show_alert=True,
            )
            return
        await query.answer("Check your private chat.")
        return

    if action.kind == "s":
        await query.answer()
        if action.option_order is None or action.score is None:
            return
        await _record_score(
            context,
            action.poll_id,
            voter_hash,
            user.id,
            action.option_order,
            action.score,
        )
        return

    if action.kind == "q":
        if action.option_order is None or action.score is None:
            await query.answer("This button is no longer valid.", show_alert=True)
            return
        await _record_quick_score(
            context,
            action.poll_id,
            voter_hash,
            action.option_order,
            action.score,
            query,
        )
        return

    if action.kind == "e":
        try:
            await _restart_vote(context, action.poll_id, voter_hash, user.id)
        except PrivateMessageUnavailable:
            await query.answer(
                "Please open a private chat with this bot and press Start first.",
                show_alert=True,
            )
            return
        await query.answer()
        return

    if action.kind == "d":
        await ballots.clear_session(db, poll_id=action.poll_id, voter_hash=voter_hash)
        await query.answer("Done.")
        if query.message is not None:
            await query.edit_message_reply_markup(reply_markup=None)


def parse_callback_data(data: str) -> CallbackAction:
    parts = data.split(":")
    if len(parts) < 2:
        raise CallbackDataError("missing callback fields")

    kind = parts[0]
    if kind not in {"v", "s", "q", "e", "d"}:
        raise CallbackDataError("unknown callback kind")

    try:
        poll_id = UUID(parts[1])
    except ValueError as exc:
        raise CallbackDataError("invalid poll id") from exc

    if kind in {"s", "q"}:
        if len(parts) != 4:
            raise CallbackDataError("score callback requires four fields")
        try:
            option_order = int(parts[2])
            score = int(parts[3])
        except ValueError as exc:
            raise CallbackDataError("invalid score callback fields") from exc
        return CallbackAction(kind, poll_id, option_order, score)

    if len(parts) != 2:
        raise CallbackDataError("unexpected callback fields")
    return CallbackAction(kind, poll_id)


async def refresh_group_poll(
    context: ContextTypes.DEFAULT_TYPE,
    poll: Poll,
    options: list[PollOption] | None = None,
) -> None:
    if poll.message_id is None:
        return

    db = _db(context)
    poll_options = options if options is not None else await polls.list_poll_options(db, poll.id)
    all_scores = await ballots.list_ballot_scores(db, poll.id)
    text, keyboard = render_group_poll(poll, poll_options, all_scores)
    try:
        await context.bot.edit_message_text(
            chat_id=poll.chat_id,
            message_id=poll.message_id,
            text=text,
            reply_markup=keyboard,
        )
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def _start_or_resume_vote(
    context: ContextTypes.DEFAULT_TYPE,
    poll_id: UUID,
    voter_hash: str,
    user_id: int,
) -> None:
    poll_with_options = await _load_open_poll_with_options(context, poll_id, user_id)
    if poll_with_options is None:
        return

    poll, options = poll_with_options
    voter_scores = await ballots.get_voter_scores(
        _db(context),
        poll_id=poll.id,
        voter_hash=voter_hash,
    )
    next_option = _next_unscored_option(options, voter_scores) or options[0]
    await _send_score_prompt(context, poll, next_option, voter_scores, voter_hash, user_id)


async def _restart_vote(
    context: ContextTypes.DEFAULT_TYPE,
    poll_id: UUID,
    voter_hash: str,
    user_id: int,
) -> None:
    poll_with_options = await _load_open_poll_with_options(context, poll_id, user_id)
    if poll_with_options is None:
        return

    poll, options = poll_with_options
    voter_scores = await ballots.get_voter_scores(
        _db(context),
        poll_id=poll.id,
        voter_hash=voter_hash,
    )
    await _send_score_prompt(context, poll, options[0], voter_scores, voter_hash, user_id)


async def _record_score(
    context: ContextTypes.DEFAULT_TYPE,
    poll_id: UUID,
    voter_hash: str,
    user_id: int,
    option_order: int,
    score: int,
) -> None:
    poll_with_options = await _load_open_poll_with_options(context, poll_id, user_id)
    if poll_with_options is None:
        return

    poll, options = poll_with_options
    option = _option_by_order(options, option_order)
    if option is None:
        await _send_private_message(context, user_id, "This button is no longer valid.")
        return

    try:
        validate_score(score, poll.score_min, poll.score_max)
    except ScoreValidationError:
        await _send_private_message(
            context,
            user_id,
            "That score is outside this poll's range.",
        )
        return

    await ballots.upsert_score(
        _db(context),
        poll_id=poll.id,
        voter_hash=voter_hash,
        option_id=option.id,
        score=score,
    )

    voter_scores = await ballots.get_voter_scores(
        _db(context),
        poll_id=poll.id,
        voter_hash=voter_hash,
    )
    next_option = _next_unscored_option(options, voter_scores)
    if next_option is None:
        await ballots.upsert_session(
            _db(context),
            poll_id=poll.id,
            voter_hash=voter_hash,
            current_option_id=None,
        )
        text, keyboard = render_ballot_summary(poll, options, voter_scores)
        await _send_private_message(context, user_id, text, reply_markup=keyboard)
    else:
        await _send_score_prompt(
            context,
            poll,
            next_option,
            voter_scores,
            voter_hash,
            user_id,
        )

    await refresh_group_poll(context, poll, options)


async def _record_quick_score(
    context: ContextTypes.DEFAULT_TYPE,
    poll_id: UUID,
    voter_hash: str,
    option_order: int,
    score: int,
    query: CallbackQuery,
) -> None:
    poll_with_options = await polls.get_poll_with_options(_db(context), poll_id)
    if poll_with_options is None:
        await query.answer("This poll no longer exists.", show_alert=True)
        return

    poll, options = poll_with_options
    if poll.status != PollStatus.OPEN:
        await query.answer("This poll is closed.", show_alert=True)
        return
    if poll.voting_mode != VotingMode.QUICK:
        await query.answer("This button is no longer valid.", show_alert=True)
        return

    option = _option_by_order(options, option_order)
    if option is None:
        await query.answer("This button is no longer valid.", show_alert=True)
        return

    try:
        validate_score(score, poll.score_min, poll.score_max)
    except ScoreValidationError:
        await query.answer("That score is outside this poll's range.", show_alert=True)
        return

    await ballots.upsert_score(
        _db(context),
        poll_id=poll.id,
        voter_hash=voter_hash,
        option_id=option.id,
        score=score,
    )
    voter_scores = await ballots.get_voter_scores(
        _db(context),
        poll_id=poll.id,
        voter_hash=voter_hash,
    )
    scored_count = len({voter_score.option_id for voter_score in voter_scores})
    if scored_count == len(options):
        message = f"Ballot complete. Saved {option.label}: {score}."
    else:
        message = f"Saved {option.label}: {score}. {scored_count}/{len(options)} scored."

    await query.answer(message)
    await refresh_group_poll(context, poll, options)


async def _send_score_prompt(
    context: ContextTypes.DEFAULT_TYPE,
    poll: Poll,
    option: PollOption,
    voter_scores: list[BallotScore],
    voter_hash: str,
    user_id: int,
) -> None:
    await ballots.upsert_session(
        _db(context),
        poll_id=poll.id,
        voter_hash=voter_hash,
        current_option_id=option.id,
    )
    existing_scores = {score.option_id: score.score for score in voter_scores}
    text, keyboard = render_score_prompt(poll, option, existing_scores)
    await _send_private_message(context, user_id, text, reply_markup=keyboard)


async def _load_open_poll_with_options(
    context: ContextTypes.DEFAULT_TYPE,
    poll_id: UUID,
    user_id: int,
) -> tuple[Poll, list[PollOption]] | None:
    poll_with_options = await polls.get_poll_with_options(_db(context), poll_id)
    if poll_with_options is None:
        await _send_private_message(context, user_id, "This poll no longer exists.")
        return None

    poll, options = poll_with_options
    if poll.status != PollStatus.OPEN:
        await _send_private_message(context, user_id, "This poll is closed.")
        return None

    if not options:
        await _send_private_message(context, user_id, "This poll has no options.")
        return None

    return poll, options


def _next_unscored_option(
    options: list[PollOption],
    voter_scores: list[BallotScore],
) -> PollOption | None:
    scored_option_ids = {score.option_id for score in voter_scores}
    return next(
        (option for option in options if option.id not in scored_option_ids),
        None,
    )


def _option_by_order(
    options: list[PollOption],
    option_order: int,
) -> PollOption | None:
    return next(
        (option for option in options if option.display_order == option_order),
        None,
    )


async def _send_private_message(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
        )
    except (BadRequest, Forbidden) as exc:
        raise PrivateMessageUnavailable from exc


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
