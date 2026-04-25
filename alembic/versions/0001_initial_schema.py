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
            voting_method   TEXT NOT NULL CHECK (voting_method IN ('score')),
            voting_mode     TEXT NOT NULL CHECK (voting_mode IN ('dm', 'quick')),
            status          TEXT NOT NULL CHECK (status IN ('open', 'closed')),
            score_min       INTEGER NOT NULL DEFAULT 0,
            score_max       INTEGER NOT NULL DEFAULT 5,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at       TIMESTAMPTZ,
            CHECK (score_min <= score_max)
        )
        """
    )

    # Enforces "one open poll per chat" at the DB layer; avoids a race when
    # two /scorepoll commands land concurrently.
    op.execute(
        """
        CREATE UNIQUE INDEX polls_one_open_per_chat
            ON polls (chat_id) WHERE status = 'open'
        """
    )

    # UNIQUE (poll_id, id) lets ballots and poll_sessions reference
    # (poll_id, option_id) as a composite FK, preventing cross-poll mismatches.
    op.execute(
        """
        CREATE TABLE poll_options (
            id            UUID PRIMARY KEY,
            poll_id       UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            label         TEXT NOT NULL,
            display_order INTEGER NOT NULL,
            UNIQUE (poll_id, id),
            UNIQUE (poll_id, display_order)
        )
        """
    )

    # Composite FK guarantees the option belongs to the same poll as the
    # ballot. Cascade chains through poll_options when a poll is deleted.
    op.execute(
        """
        CREATE TABLE ballots (
            poll_id    UUID NOT NULL,
            voter_hash TEXT NOT NULL,
            option_id  UUID NOT NULL,
            score      INTEGER NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (poll_id, voter_hash, option_id),
            FOREIGN KEY (poll_id, option_id)
                REFERENCES poll_options (poll_id, id) ON DELETE CASCADE
        )
        """
    )

    # poll_id FK to polls handles row cleanup on poll deletion. The composite
    # FK to poll_options enforces (poll_id, current_option_id) consistency
    # when current_option_id is set; MATCH SIMPLE skips the check when null.
    op.execute(
        """
        CREATE TABLE poll_sessions (
            poll_id           UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
            voter_hash        TEXT NOT NULL,
            current_option_id UUID,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (poll_id, voter_hash),
            FOREIGN KEY (poll_id, current_option_id)
                REFERENCES poll_options (poll_id, id)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS poll_sessions")
    op.execute("DROP TABLE IF EXISTS ballots")
    op.execute("DROP TABLE IF EXISTS poll_options")
    op.execute("DROP TABLE IF EXISTS polls")
