from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from voting_bot.db import Database, Row
from voting_bot.models import Poll, PollOption, PollStatus, VotingMethodOptions, VotingMode


async def create_score_poll(
    db: Database,
    *,
    chat_id: int,
    created_by_hash: str,
    title: str,
    option_labels: Sequence[str],
    score_min: int,
    score_max: int,
    voting_mode: VotingMode = VotingMode.DM,
) -> tuple[Poll, list[PollOption]]:
    if score_min > score_max:
        raise ValueError("score_min must be less than or equal to score_max")

    labels = tuple(label.strip() for label in option_labels)
    if not labels:
        raise ValueError("option_labels must not be empty")
    if any(not label for label in labels):
        raise ValueError("option_labels must not contain blank labels")

    poll_id = uuid4()
    option_ids = [uuid4() for _ in labels]

    async with db.transaction() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO polls (
                    id, chat_id, created_by_hash, title, voting_method, voting_mode,
                    status, score_min, score_max
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    poll_id,
                    chat_id,
                    created_by_hash,
                    title,
                    VotingMethodOptions.SCORE.value,
                    voting_mode.value,
                    PollStatus.OPEN.value,
                    score_min,
                    score_max,
                ),
            )
            poll_row = await cursor.fetchone()
            if poll_row is None:
                raise RuntimeError("failed to create poll")

            option_rows: list[Row] = []
            for display_order, (option_id, label) in enumerate(
                zip(option_ids, labels, strict=True)
            ):
                await cursor.execute(
                    """
                    INSERT INTO poll_options (id, poll_id, label, display_order)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                    """,
                    (option_id, poll_id, label, display_order),
                )
                option_row = await cursor.fetchone()
                if option_row is None:
                    raise RuntimeError("failed to create poll option")
                option_rows.append(option_row)

    return _poll_from_row(poll_row), [_option_from_row(row) for row in option_rows]


async def get_poll(db: Database, poll_id: UUID) -> Poll | None:
    row = await db.fetch_one(
        """
        SELECT *
        FROM polls
        WHERE id = %s
        """,
        (poll_id,),
    )
    return _poll_from_row(row) if row is not None else None


async def get_open_poll_for_chat(db: Database, chat_id: int) -> Poll | None:
    row = await db.fetch_one(
        """
        SELECT *
        FROM polls
        WHERE chat_id = %s
          AND status = %s
        """,
        (chat_id, PollStatus.OPEN.value),
    )
    return _poll_from_row(row) if row is not None else None


async def list_poll_options(db: Database, poll_id: UUID) -> list[PollOption]:
    rows = await db.fetch_all(
        """
        SELECT *
        FROM poll_options
        WHERE poll_id = %s
        ORDER BY display_order ASC
        """,
        (poll_id,),
    )
    return [_option_from_row(row) for row in rows]


async def get_poll_with_options(
    db: Database,
    poll_id: UUID,
) -> tuple[Poll, list[PollOption]] | None:
    poll = await get_poll(db, poll_id)
    if poll is None:
        return None

    return poll, await list_poll_options(db, poll.id)


async def set_poll_message_id(
    db: Database,
    *,
    poll_id: UUID,
    message_id: int,
) -> Poll | None:
    row = await db.fetch_one(
        """
        UPDATE polls
        SET message_id = %s
        WHERE id = %s
        RETURNING *
        """,
        (message_id, poll_id),
    )
    return _poll_from_row(row) if row is not None else None


async def close_poll(db: Database, poll_id: UUID) -> Poll | None:
    row = await db.fetch_one(
        """
        UPDATE polls
        SET status = %s,
            closed_at = now()
        WHERE id = %s
          AND status = %s
        RETURNING *
        """,
        (PollStatus.CLOSED.value, poll_id, PollStatus.OPEN.value),
    )
    return _poll_from_row(row) if row is not None else None


def _poll_from_row(row: Row) -> Poll:
    return Poll(
        id=_uuid(row["id"]),
        chat_id=row["chat_id"],
        message_id=row["message_id"],
        created_by_hash=row["created_by_hash"],
        title=row["title"],
        voting_method=VotingMethodOptions(row["voting_method"]),
        voting_mode=VotingMode(row["voting_mode"]),
        status=PollStatus(row["status"]),
        score_min=row["score_min"],
        score_max=row["score_max"],
        created_at=_datetime(row["created_at"]),
        closed_at=_datetime(row["closed_at"]) if row["closed_at"] is not None else None,
    )


def _option_from_row(row: Row) -> PollOption:
    return PollOption(
        id=_uuid(row["id"]),
        poll_id=_uuid(row["poll_id"]),
        label=row["label"],
        display_order=row["display_order"],
    )


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    raise TypeError(f"expected datetime value, got {type(value).__name__}")
