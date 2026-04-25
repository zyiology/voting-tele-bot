from __future__ import annotations

from datetime import datetime
from uuid import UUID

from voting_bot.db import Database, Row
from voting_bot.models import BallotScore, PollSession


async def list_ballot_scores(db: Database, poll_id: UUID) -> list[BallotScore]:
    rows = await db.fetch_all(
        """
        SELECT *
        FROM ballots
        WHERE poll_id = %s
        ORDER BY updated_at ASC
        """,
        (poll_id,),
    )
    return [_ballot_score_from_row(row) for row in rows]


async def get_voter_scores(
    db: Database,
    *,
    poll_id: UUID,
    voter_hash: str,
) -> list[BallotScore]:
    rows = await db.fetch_all(
        """
        SELECT *
        FROM ballots
        WHERE poll_id = %s
          AND voter_hash = %s
        ORDER BY updated_at ASC
        """,
        (poll_id, voter_hash),
    )
    return [_ballot_score_from_row(row) for row in rows]


async def upsert_score(
    db: Database,
    *,
    poll_id: UUID,
    voter_hash: str,
    option_id: UUID,
    score: int,
) -> BallotScore:
    row = await db.fetch_one(
        """
        INSERT INTO ballots (poll_id, voter_hash, option_id, score)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (poll_id, voter_hash, option_id)
        DO UPDATE SET
            score = EXCLUDED.score,
            updated_at = now()
        RETURNING *
        """,
        (poll_id, voter_hash, option_id, score),
    )
    if row is None:
        raise RuntimeError("failed to upsert ballot score")

    return _ballot_score_from_row(row)


async def get_session(
    db: Database,
    *,
    poll_id: UUID,
    voter_hash: str,
) -> PollSession | None:
    row = await db.fetch_one(
        """
        SELECT *
        FROM poll_sessions
        WHERE poll_id = %s
          AND voter_hash = %s
        """,
        (poll_id, voter_hash),
    )
    return _session_from_row(row) if row is not None else None


async def upsert_session(
    db: Database,
    *,
    poll_id: UUID,
    voter_hash: str,
    current_option_id: UUID | None,
) -> PollSession:
    row = await db.fetch_one(
        """
        INSERT INTO poll_sessions (poll_id, voter_hash, current_option_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (poll_id, voter_hash)
        DO UPDATE SET
            current_option_id = EXCLUDED.current_option_id,
            updated_at = now()
        RETURNING *
        """,
        (poll_id, voter_hash, current_option_id),
    )
    if row is None:
        raise RuntimeError("failed to upsert poll session")

    return _session_from_row(row)


async def clear_session(
    db: Database,
    *,
    poll_id: UUID,
    voter_hash: str,
) -> None:
    await db.execute(
        """
        DELETE FROM poll_sessions
        WHERE poll_id = %s
          AND voter_hash = %s
        """,
        (poll_id, voter_hash),
    )


def _ballot_score_from_row(row: Row) -> BallotScore:
    return BallotScore(
        poll_id=_uuid(row["poll_id"]),
        voter_hash=row["voter_hash"],
        option_id=_uuid(row["option_id"]),
        score=row["score"],
        updated_at=_datetime(row["updated_at"]),
    )


def _session_from_row(row: Row) -> PollSession:
    return PollSession(
        poll_id=_uuid(row["poll_id"]),
        voter_hash=row["voter_hash"],
        current_option_id=(
            _uuid(row["current_option_id"])
            if row["current_option_id"] is not None
            else None
        ),
        created_at=_datetime(row["created_at"]),
        updated_at=_datetime(row["updated_at"]),
    )


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    raise TypeError(f"expected datetime value, got {type(value).__name__}")
