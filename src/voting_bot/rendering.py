from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from voting_bot.models import (
    BallotScore,
    Poll,
    PollOption,
    PollStatus,
    ResultsVisibility,
    ScorePollResult,
    VotingMode,
)
from voting_bot.voting_methods.score import tally_score_poll


def vote_callback_data(poll_id: UUID) -> str:
    return f"v:{poll_id}"


def score_callback_data(poll_id: UUID, option_order: int, score: int) -> str:
    return f"s:{poll_id}:{option_order}:{score}"


def quick_score_callback_data(poll_id: UUID, option_order: int, score: int) -> str:
    return f"q:{poll_id}:{option_order}:{score}"


def edit_callback_data(poll_id: UUID) -> str:
    return f"e:{poll_id}"


def done_callback_data(poll_id: UUID) -> str:
    return f"d:{poll_id}"


def render_group_poll(
    poll: Poll,
    options: Sequence[PollOption],
    ballot_scores: Sequence[BallotScore],
) -> tuple[str, InlineKeyboardMarkup | None]:
    result = tally_score_poll(poll.id, list(options), list(ballot_scores))
    lines = [_poll_title(poll), ""]

    if result.complete_ballot_count == 0:
        lines.extend(_option_lines(options))
        lines.extend(["", "Votes cast: 0"])
    elif _should_hide_results(poll):
        lines.extend(_option_lines(options))
        lines.extend(
            [
                "",
                f"Votes cast: {result.complete_ballot_count}",
                "",
                "Results hidden until the poll closes.",
            ]
        )
    else:
        result_label = (
            f"Final results ({result.complete_ballot_count} votes):"
            if poll.status == PollStatus.CLOSED
            else "Current results:"
        )
        lines.extend([f"Votes cast: {result.complete_ballot_count}", "", result_label])
        lines.extend(_result_lines(result))

    keyboard = None
    if poll.status == PollStatus.OPEN:
        keyboard = _group_keyboard(poll, options)

    return "\n".join(lines), keyboard


def _should_hide_results(poll: Poll) -> bool:
    return (
        poll.status == PollStatus.OPEN
        and poll.results_visibility == ResultsVisibility.HIDDEN_UNTIL_CLOSED
    )


def render_score_prompt(
    poll: Poll,
    option: PollOption,
    existing_scores: Mapping[UUID, int],
) -> tuple[str, InlineKeyboardMarkup]:
    existing = existing_scores.get(option.id)
    lines = [f"Score {option.label} ({poll.score_min}-{poll.score_max}):"]
    if existing is not None:
        lines.append(f"Current score: {existing}")

    buttons = [
        InlineKeyboardButton(
            str(score),
            callback_data=score_callback_data(poll.id, option.display_order, score),
        )
        for score in range(poll.score_min, poll.score_max + 1)
    ]

    return "\n".join(lines), InlineKeyboardMarkup(_chunk_buttons(buttons, size=6))


def render_ballot_summary(
    poll: Poll,
    options: Sequence[PollOption],
    voter_scores: Sequence[BallotScore],
) -> tuple[str, InlineKeyboardMarkup]:
    score_by_option = {score.option_id: score.score for score in voter_scores}
    lines = ["Your ballot has been recorded.", ""]
    lines.extend(
        f"{option.label}: {score_by_option[option.id]}"
        for option in options
        if option.id in score_by_option
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Edit ballot",
                    callback_data=edit_callback_data(poll.id),
                ),
                InlineKeyboardButton("Done", callback_data=done_callback_data(poll.id)),
            ]
        ]
    )
    return "\n".join(lines), keyboard


def _poll_title(poll: Poll) -> str:
    if poll.status == PollStatus.CLOSED:
        return f"{poll.title} [CLOSED]"
    return poll.title


def _option_lines(options: Sequence[PollOption]) -> list[str]:
    return ["Options:"] + [
        f"{option.display_order + 1}. {option.label}" for option in options
    ]


def _result_lines(result: ScorePollResult) -> list[str]:
    lines: list[str] = []
    for option_result in result.option_results:
        if option_result.average_score is None or option_result.rank is None:
            continue
        lines.append(
            f"{option_result.rank}. {option_result.option.label} - "
            f"avg {option_result.average_score:.1f}"
        )
    return lines


def _group_keyboard(
    poll: Poll,
    options: Sequence[PollOption],
) -> InlineKeyboardMarkup:
    if poll.voting_mode == VotingMode.DM:
        return InlineKeyboardMarkup.from_button(
            InlineKeyboardButton("Vote", callback_data=vote_callback_data(poll.id))
        )

    rows: list[list[InlineKeyboardButton]] = []
    for option in options:
        buttons = [
            InlineKeyboardButton(
                (
                    f"{option.display_order + 1}. {option.label}: {score}"
                    if score == poll.score_min
                    else str(score)
                ),
                callback_data=quick_score_callback_data(
                    poll.id,
                    option.display_order,
                    score,
                ),
            )
            for score in range(poll.score_min, poll.score_max + 1)
        ]
        rows.extend(_chunk_buttons(buttons, size=6))

    return InlineKeyboardMarkup(rows)


def _chunk_buttons(
    buttons: Sequence[InlineKeyboardButton],
    *,
    size: int,
) -> list[list[InlineKeyboardButton]]:
    return [list(buttons[index : index + size]) for index in range(0, len(buttons), size)]
