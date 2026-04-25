from __future__ import annotations


POSTGRESQL_SCHEME = "postgresql://"
POSTGRESQL_PSYCOPG_SCHEME = "postgresql+psycopg://"


def for_sqlalchemy(database_url: str) -> str:
    if database_url.startswith(POSTGRESQL_SCHEME):
        return database_url.replace(POSTGRESQL_SCHEME, POSTGRESQL_PSYCOPG_SCHEME, 1)
    return database_url


def for_psycopg(database_url: str) -> str:
    if database_url.startswith(POSTGRESQL_PSYCOPG_SCHEME):
        return database_url.replace(POSTGRESQL_PSYCOPG_SCHEME, POSTGRESQL_SCHEME, 1)
    return database_url
