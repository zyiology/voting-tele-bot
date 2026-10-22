from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from telegram.ext import ContextTypes

from voting_bot.db import Database, Row
from voting_bot.handlers.callbacks import refresh_group_poll
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


@pytest.mark.parametrize("existing_score", [False, True])
def test_closed_poll_rejects_score_insert_and_edit(database_url: str, existing_score: bool):
    async def run():
        async with _connected_db(database_url) as db:
            poll, options = await polls.create_score_poll(
                db, chat_id=_unique_chat_id(), created_by_hash="creator", title="Lunch",
                option_labels=["Sushi", "Pizza"], score_min=0, score_max=5,
            )
            try:
                if existing_score:
                    await ballots.upsert_score(
                        db, poll_id=poll.id, voter_hash="voter", option_id=options[0].id, score=2,
                    )
                await polls.close_poll(db, poll.id)
                before = await ballots.list_ballot_scores(db, poll.id)
                with pytest.raises(ballots.PollNotOpenError):
                    await ballots.upsert_score(
                        db, poll_id=poll.id, voter_hash="voter", option_id=options[0].id, score=5,
                    )
                assert await ballots.list_ballot_scores(db, poll.id) == before
            finally:
                await _delete_poll(db, poll.id)
    asyncio.run(run())


@pytest.mark.parametrize("close_first", [False, True])
def test_close_and_score_serialize_across_connections(database_url: str, close_first: bool):
    async def run():
        async with (
            _connected_db(database_url) as db,
            _connected_db(database_url) as writer,
            _connected_db(database_url) as closer,
        ):
            poll, options = await polls.create_score_poll(
                db, chat_id=_unique_chat_id(), created_by_hash="creator", title="Lunch",
                option_labels=["Sushi", "Pizza"], score_min=0, score_max=5,
            )
            writer_pid = await writer.fetch_one("SELECT pg_backend_pid() AS pid")
            closer_pid = await closer.fetch_one("SELECT pg_backend_pid() AS pid")
            assert writer_pid is not None and closer_pid is not None
            try:
                # Queue both real repository operations behind an explicit row
                # lock. Observe database waits rather than relying on sleeps to
                # guess which operation acquired the lock first.
                async with asyncio.TaskGroup() as tasks:
                    async with db.transaction() as connection:
                        await connection.execute(
                            "SELECT id FROM polls WHERE id = %s FOR UPDATE", (poll.id,),
                        )
                        if close_first:
                            close_task = tasks.create_task(polls.close_poll(closer, poll.id))
                            await _wait_for_row_lock(connection, closer_pid["pid"])
                        score_task = tasks.create_task(_attempt_score(writer, poll.id, options[0].id))
                        await _wait_for_row_lock(connection, writer_pid["pid"])
                        if not close_first:
                            close_task = tasks.create_task(polls.close_poll(closer, poll.id))
                            await _wait_for_row_lock(connection, closer_pid["pid"])
                assert close_task.result() is not None
                assert score_task.result() is (not close_first)
                scores = await ballots.list_ballot_scores(db, poll.id)
                assert [score.score for score in scores] == ([] if close_first else [5])
                closed = await polls.get_poll(db, poll.id)
                assert closed is not None and closed.status == PollStatus.CLOSED
            finally:
                await _delete_poll(db, poll.id)
    asyncio.run(run())


async def _attempt_score(db: Database, poll_id: UUID, option_id: UUID) -> bool:
    try:
        await ballots.upsert_score(
            db, poll_id=poll_id, voter_hash="voter", option_id=option_id, score=5,
        )
    except ballots.PollNotOpenError:
        return False
    return True


async def _wait_for_row_lock(connection: psycopg.AsyncConnection[Row], pid: int) -> None:
    async with asyncio.timeout(5):
        while True:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT cardinality(pg_blocking_pids(%s)) > 0 AS waiting", (pid,),
                )
                row = await cursor.fetchone()
                if row and row["waiting"]:
                    return
            await asyncio.sleep(0.01)


def test_delayed_refresh_cannot_overwrite_closed_message(database_url: str):
    async def run():
        async with (
            _connected_db(database_url) as db,
            _connected_db(database_url) as other,
        ):
            poll, options = await polls.create_score_poll(
                db, chat_id=_unique_chat_id(), created_by_hash="creator", title="Lunch",
                option_labels=["Sushi", "Pizza"], score_min=0, score_max=5,
            )
            poll = await polls.set_poll_message_id(db, poll_id=poll.id, message_id=123)
            assert poll is not None
            edit_started = asyncio.Event()
            release_edit = asyncio.Event()
            messages = []

            async def edit(**kwargs):
                if not edit_started.is_set():
                    edit_started.set()
                    await release_edit.wait()
                messages.append(kwargs)

            bot = SimpleNamespace(edit_message_text=edit)
            context = cast(ContextTypes.DEFAULT_TYPE, SimpleNamespace(bot=bot, bot_data={"db": db}))
            other_context = cast(
                ContextTypes.DEFAULT_TYPE, SimpleNamespace(bot=bot, bot_data={"db": other}),
            )
            try:
                async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
                    tasks.create_task(refresh_group_poll(context, poll, options))
                    await edit_started.wait()
                    closed = await polls.close_poll(other, poll.id)
                    assert closed is not None
                    tasks.create_task(refresh_group_poll(other_context, closed, options))
                    try:
                        # The closed refresh must wait for the in-flight open
                        # edit, even though it uses a different Database object.
                        async with asyncio.timeout(5):
                            while True:
                                waiting = await other.fetch_one(
                                    """
                                    SELECT EXISTS (
                                        SELECT FROM pg_locks
                                        WHERE locktype = 'advisory' AND NOT granted
                                          AND database = (
                                              SELECT oid FROM pg_database
                                              WHERE datname = current_database()
                                          )
                                    ) AS waiting
                                    """,
                                )
                                if waiting and waiting["waiting"]:
                                    break
                                await asyncio.sleep(0.01)
                        assert not messages
                    finally:
                        release_edit.set()
                assert messages[0]["reply_markup"] is not None
                assert messages[1]["reply_markup"] is None
                assert "CLOSED" in messages[1]["text"]
                # A much later refresh with an old Poll object must also render
                # the database's closed state rather than restore voting buttons.
                await refresh_group_poll(context, poll, options)
                assert messages[-1]["reply_markup"] is None
                assert "CLOSED" in messages[-1]["text"]
            finally:
                release_edit.set()
                await _delete_poll(db, poll.id)
    asyncio.run(run())


@pytest.mark.parametrize("cancel", [False, True])
def test_refresh_lock_is_released_on_failure(database_url: str, cancel: bool):
    async def run():
        async with _connected_db(database_url) as db, _connected_db(database_url) as other:
            poll_id = uuid4()
            entered = asyncio.Event()

            async def fail():
                async with polls.message_refresh_lock(db, poll_id):
                    entered.set()
                    if cancel:
                        await asyncio.Event().wait()
                    raise RuntimeError("Telegram failed")

            task = asyncio.create_task(fail())
            await asyncio.wait_for(entered.wait(), timeout=5)
            if cancel:
                task.cancel()
            with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
                await task
            async with asyncio.timeout(5), polls.message_refresh_lock(other, poll_id):
                assert await other.fetch_one("SELECT 1 AS ok") == {"ok": 1}
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
