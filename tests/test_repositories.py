from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from voting_bot.db import Database
from voting_bot.models import (
    PollStatus,
    ResultsVisibility,
    VotingMethodOptions,
    VotingMode,
)
from voting_bot.repositories import ballots, polls


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping repository integration tests")

    try:
        with psycopg.connect(url, connect_timeout=1):
            pass
    except psycopg.OperationalError as exc:
        pytest.skip(f"DATABASE_URL is not reachable: {exc}")

    alembic_config = AlembicConfig("alembic.ini")
    command.upgrade(alembic_config, "head")
    return url


def test_create_and_retrieve_score_poll(database_url: str) -> None:
    async def run() -> None:
        async with _connected_db(database_url) as db:
            poll, options = await polls.create_score_poll(
                db,
                chat_id=_unique_chat_id(),
                created_by_hash="creator",
                title="Lunch",
                option_labels=[" Sushi ", "Pizza"],
                score_min=0,
                score_max=5,
            )
            try:
                assert poll.chat_id < 0
                assert poll.message_id is None
                assert poll.created_by_hash == "creator"
                assert poll.title == "Lunch"
                assert poll.voting_method == VotingMethodOptions.SCORE
                assert poll.voting_mode == VotingMode.DM
                assert poll.results_visibility == ResultsVisibility.HIDDEN_UNTIL_CLOSED
                assert poll.status == PollStatus.OPEN
                assert poll.score_min == 0
                assert poll.score_max == 5
                assert poll.closed_at is None
                assert [option.label for option in options] == ["Sushi", "Pizza"]
                assert [option.display_order for option in options] == [0, 1]

                assert await polls.get_poll(db, poll.id) == poll
                assert await polls.get_open_poll_for_chat(db, poll.chat_id) == poll
                assert await polls.list_poll_options(db, poll.id) == options
                assert await polls.get_poll_with_options(db, poll.id) == (
                    poll,
                    options,
                )
            finally:
                await _delete_poll(db, poll.id)

    asyncio.run(run())


def test_create_score_poll_can_store_quick_voting_mode(database_url: str) -> None:
    async def run() -> None:
        async with _connected_db(database_url) as db:
            poll, _ = await polls.create_score_poll(
                db,
                chat_id=_unique_chat_id(),
                created_by_hash="creator",
                title="Lunch",
                option_labels=["Sushi", "Pizza"],
                score_min=0,
                score_max=5,
                voting_mode=VotingMode.QUICK,
            )
            try:
                assert poll.voting_mode == VotingMode.QUICK
                assert await polls.get_poll(db, poll.id) == poll
            finally:
                await _delete_poll(db, poll.id)

    asyncio.run(run())


def test_create_score_poll_can_store_live_results_visibility(database_url: str) -> None:
    async def run() -> None:
        async with _connected_db(database_url) as db:
            poll, _ = await polls.create_score_poll(
                db,
                chat_id=_unique_chat_id(),
                created_by_hash="creator",
                title="Lunch",
                option_labels=["Sushi", "Pizza"],
                score_min=0,
                score_max=5,
                results_visibility=ResultsVisibility.LIVE,
            )
            try:
                assert poll.results_visibility == ResultsVisibility.LIVE
                assert await polls.get_poll(db, poll.id) == poll
            finally:
                await _delete_poll(db, poll.id)

    asyncio.run(run())


def test_create_score_poll_validates_inputs(database_url: str) -> None:
    async def run() -> None:
        async with _connected_db(database_url) as db:
            with pytest.raises(ValueError, match="option_labels must not be empty"):
                await polls.create_score_poll(
                    db,
                    chat_id=_unique_chat_id(),
                    created_by_hash="creator",
                    title="Lunch",
                    option_labels=[],
                    score_min=0,
                    score_max=5,
                )

            with pytest.raises(
                ValueError,
                match="option_labels must not contain blank labels",
            ):
                await polls.create_score_poll(
                    db,
                    chat_id=_unique_chat_id(),
                    created_by_hash="creator",
                    title="Lunch",
                    option_labels=["Sushi", " "],
                    score_min=0,
                    score_max=5,
                )

            with pytest.raises(
                ValueError,
                match="score_min must be less than or equal to score_max",
            ):
                await polls.create_score_poll(
                    db,
                    chat_id=_unique_chat_id(),
                    created_by_hash="creator",
                    title="Lunch",
                    option_labels=["Sushi"],
                    score_min=5,
                    score_max=0,
                )

    asyncio.run(run())


def test_one_open_poll_per_chat_is_enforced(database_url: str) -> None:
    async def run() -> None:
        async with _connected_db(database_url) as db:
            chat_id = _unique_chat_id()
            poll, _ = await polls.create_score_poll(
                db,
                chat_id=chat_id,
                created_by_hash="creator",
                title="Lunch",
                option_labels=["Sushi"],
                score_min=0,
                score_max=5,
            )
            try:
                with pytest.raises(UniqueViolation):
                    await polls.create_score_poll(
                        db,
                        chat_id=chat_id,
                        created_by_hash="creator",
                        title="Dinner",
                        option_labels=["Pizza"],
                        score_min=0,
                        score_max=5,
                    )
            finally:
                await _delete_poll(db, poll.id)

    asyncio.run(run())


def test_update_message_id_and_close_poll(database_url: str) -> None:
    async def run() -> None:
        async with _connected_db(database_url) as db:
            poll, _ = await polls.create_score_poll(
                db,
                chat_id=_unique_chat_id(),
                created_by_hash="creator",
                title="Lunch",
                option_labels=["Sushi"],
                score_min=0,
                score_max=5,
            )
            try:
                updated = await polls.set_poll_message_id(
                    db,
                    poll_id=poll.id,
                    message_id=987,
                )
                assert updated is not None
                assert updated.message_id == 987

                closed = await polls.close_poll(db, poll.id)
                assert closed is not None
                assert closed.status == PollStatus.CLOSED
                assert closed.closed_at is not None
                assert await polls.get_open_poll_for_chat(db, poll.chat_id) is None
                assert await polls.close_poll(db, poll.id) is None
            finally:
                await _delete_poll(db, poll.id)

    asyncio.run(run())


def test_ballot_score_upsert_and_retrieval(database_url: str) -> None:
    async def run() -> None:
        async with _connected_db(database_url) as db:
            poll, options = await polls.create_score_poll(
                db,
                chat_id=_unique_chat_id(),
                created_by_hash="creator",
                title="Lunch",
                option_labels=["Sushi", "Pizza"],
                score_min=0,
                score_max=5,
            )
            try:
                inserted = await ballots.upsert_score(
                    db,
                    poll_id=poll.id,
                    voter_hash="voter-a",
                    option_id=options[0].id,
                    score=2,
                )
                updated = await ballots.upsert_score(
                    db,
                    poll_id=poll.id,
                    voter_hash="voter-a",
                    option_id=options[0].id,
                    score=5,
                )
                other = await ballots.upsert_score(
                    db,
                    poll_id=poll.id,
                    voter_hash="voter-b",
                    option_id=options[1].id,
                    score=3,
                )

                assert inserted.option_id == updated.option_id
                assert updated.score == 5
                assert other.score == 3
                assert await ballots.get_voter_scores(
                    db,
                    poll_id=poll.id,
                    voter_hash="voter-a",
                ) == [updated]
                assert await ballots.list_ballot_scores(db, poll.id) == [
                    updated,
                    other,
                ]
            finally:
                await _delete_poll(db, poll.id)

    asyncio.run(run())


def test_ballot_score_rejects_option_from_another_poll(database_url: str) -> None:
    async def run() -> None:
        async with _connected_db(database_url) as db:
            poll, _ = await polls.create_score_poll(
                db,
                chat_id=_unique_chat_id(),
                created_by_hash="creator",
                title="Lunch",
                option_labels=["Sushi"],
                score_min=0,
                score_max=5,
            )
            try:
                with pytest.raises(ForeignKeyViolation):
                    await ballots.upsert_score(
                        db,
                        poll_id=poll.id,
                        voter_hash="voter-a",
                        option_id=uuid4(),
                        score=5,
                    )
            finally:
                await _delete_poll(db, poll.id)

    asyncio.run(run())


def test_poll_session_upsert_get_and_clear(database_url: str) -> None:
    async def run() -> None:
        async with _connected_db(database_url) as db:
            poll, options = await polls.create_score_poll(
                db,
                chat_id=_unique_chat_id(),
                created_by_hash="creator",
                title="Lunch",
                option_labels=["Sushi", "Pizza"],
                score_min=0,
                score_max=5,
            )
            try:
                inserted = await ballots.upsert_session(
                    db,
                    poll_id=poll.id,
                    voter_hash="voter-a",
                    current_option_id=options[0].id,
                )
                assert inserted.current_option_id == options[0].id

                updated = await ballots.upsert_session(
                    db,
                    poll_id=poll.id,
                    voter_hash="voter-a",
                    current_option_id=None,
                )
                assert updated.current_option_id is None
                assert (
                    await ballots.get_session(
                        db,
                        poll_id=poll.id,
                        voter_hash="voter-a",
                    )
                    == updated
                )

                await ballots.clear_session(
                    db,
                    poll_id=poll.id,
                    voter_hash="voter-a",
                )
                assert (
                    await ballots.get_session(
                        db,
                        poll_id=poll.id,
                        voter_hash="voter-a",
                    )
                    is None
                )
            finally:
                await _delete_poll(db, poll.id)

    asyncio.run(run())


class _connected_db:
    def __init__(self, database_url: str) -> None:
        self._db = Database(database_url)

    async def __aenter__(self) -> Database:
        await self._db.connect()
        return self._db

    async def __aexit__(self, *args: object) -> None:
        await self._db.close()


async def _delete_poll(db: Database, poll_id: UUID) -> None:
    await db.execute("DELETE FROM polls WHERE id = %s", (poll_id,))


def _unique_chat_id() -> int:
    return -int(str(uuid4().int)[:12])
