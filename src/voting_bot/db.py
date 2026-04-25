from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast

from psycopg import AsyncConnection, AsyncCursor
from psycopg.abc import QueryNoTemplate
from psycopg.rows import dict_row

from voting_bot.database_url import for_psycopg


Row = dict[str, Any]
Params = Sequence[Any] | Mapping[str, Any] | None


class Database:
    def __init__(self, database_url: str) -> None:
        self._database_url = for_psycopg(database_url)
        self._connection: AsyncConnection[Row] | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._connection is not None:
            return

        connection = cast(
            AsyncConnection[Row],
            await AsyncConnection.connect(
                self._database_url,
                row_factory=cast(Any, dict_row),
            ),
        )
        await connection.set_autocommit(True)
        self._connection = connection

    async def close(self) -> None:
        if self._connection is None:
            return

        await self._connection.close()
        self._connection = None

    @asynccontextmanager
    async def cursor(self) -> AsyncIterator[AsyncCursor[Row]]:
        connection = self._require_connection()
        async with self._lock:
            async with connection.cursor() as cursor:
                yield cursor

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection[Row]]:
        connection = self._require_connection()
        async with self._lock:
            async with connection.transaction():
                yield connection

    async def fetch_one(
        self, query: QueryNoTemplate, params: Params = None
    ) -> Row | None:
        async with self.cursor() as cursor:
            await cursor.execute(query, params)
            return await cursor.fetchone()

    async def fetch_all(
        self, query: QueryNoTemplate, params: Params = None
    ) -> list[Row]:
        async with self.cursor() as cursor:
            await cursor.execute(query, params)
            return list(await cursor.fetchall())

    async def execute(self, query: QueryNoTemplate, params: Params = None) -> None:
        async with self.cursor() as cursor:
            await cursor.execute(query, params)

    def _require_connection(self) -> AsyncConnection[Row]:
        if self._connection is None:
            raise RuntimeError("Database.connect() must be called before use")
        return self._connection
