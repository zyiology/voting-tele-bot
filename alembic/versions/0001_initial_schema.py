"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-25

"""
from __future__ import annotations

from alembic import op


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE polls (
            id              UUID PRIMARY KEY,
            chat_id         BIGINT NOT NULL,
            message_id      BIGINT,
            created_by_hash TEXT NOT NULL,
            title           TEXT NOT NULL,
            voting_method   TEXT NOT NULL,
            status          TEXT NOT NULL,
            score_min       INTEGER NOT NULL DEFAULT 0,
            score_max       INTEGER NOT NULL DEFAULT 5,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at       TIMESTAMPTZ
        )
        """
    )

    op.execute(
        """
        CREATE TABLE poll_options (
            id            UUID PRIMARY KEY,
            poll_id       UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            label         TEXT NOT NULL,
            display_order INTEGER NOT NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE ballots (
            poll_id    UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            voter_hash TEXT NOT NULL,
            option_id  UUID NOT NULL REFERENCES poll_options(id) ON DELETE CASCADE,
            score      INTEGER NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (poll_id, voter_hash, option_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE poll_sessions (
            poll_id           UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            voter_hash        TEXT NOT NULL,
            current_option_id UUID REFERENCES poll_options(id),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (poll_id, voter_hash)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS poll_sessions")
    op.execute("DROP TABLE IF EXISTS ballots")
    op.execute("DROP TABLE IF EXISTS poll_options")
    op.execute("DROP TABLE IF EXISTS polls")
