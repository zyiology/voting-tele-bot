# Database

PostgreSQL. All tables use `ON DELETE CASCADE` so removing a poll cleans up its options, ballots, and sessions.

Schema is managed by Alembic (`alembic/versions/`). The DDL below documents the current state — the migration files in `alembic/versions/` are the source of truth. The bot container runs `alembic upgrade head` on startup before launching.

## Schema

```sql
CREATE TABLE polls (
    id              UUID PRIMARY KEY,
    chat_id         BIGINT NOT NULL,
    message_id      BIGINT,               -- Telegram message ID of the group poll post
    created_by_hash TEXT NOT NULL,        -- HMAC of creator's Telegram user ID
    title           TEXT NOT NULL,
    voting_method   TEXT NOT NULL CHECK (voting_method IN ('score')),
    voting_mode     TEXT NOT NULL CHECK (voting_mode IN ('dm', 'quick')),
    status          TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    score_min       INTEGER NOT NULL DEFAULT 0,
    score_max       INTEGER NOT NULL DEFAULT 5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at       TIMESTAMPTZ,
    CHECK (score_min <= score_max)
);

-- Enforces one open poll per chat at the DB layer (race-safe).
CREATE UNIQUE INDEX polls_one_open_per_chat
    ON polls (chat_id) WHERE status = 'open';

CREATE TABLE poll_options (
    id            UUID PRIMARY KEY,
    poll_id       UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    label         TEXT NOT NULL,
    display_order INTEGER NOT NULL,
    UNIQUE (poll_id, id),                 -- target for composite FKs below
    UNIQUE (poll_id, display_order)
);

CREATE TABLE ballots (
    poll_id    UUID NOT NULL,
    voter_hash TEXT NOT NULL,
    option_id  UUID NOT NULL,
    score      INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (poll_id, voter_hash, option_id),
    -- Composite FK prevents pairing an option with a different poll.
    FOREIGN KEY (poll_id, option_id)
        REFERENCES poll_options (poll_id, id) ON DELETE CASCADE
);

CREATE TABLE poll_sessions (
    poll_id           UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    voter_hash        TEXT NOT NULL,
    current_option_id UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (poll_id, voter_hash),
    FOREIGN KEY (poll_id, current_option_id)
        REFERENCES poll_options (poll_id, id)
);
```

## Notes

- `ballots` primary key `(poll_id, voter_hash, option_id)` makes ballot updates an upsert — no duplicate detection logic needed in the application.
- `poll_sessions` tracks which option a voter is currently scoring during the inline flow; cleared when voting completes.
- `message_id` on `polls` is set after the bot posts the group message; used to edit the message when results update.
- `voting_mode` controls whether the poll uses the private DM flow (`dm`) or group inline score buttons (`quick`).
- All ballot history is retained after a poll closes.
- One active poll per `chat_id` is enforced by the partial unique index `polls_one_open_per_chat`.
- Score bounds (`score_min <= score_max`) are enforced at the poll level; per-ballot range validation lives in the application layer (`voting_methods/score.py`).
- `poll_sessions.current_option_id` is nullable; the composite FK uses MATCH SIMPLE so the constraint is only checked when the column is set.

## Migration Policy

Pre-production: edit migrations in place when fixing schema design. Once the bot is running against a real environment, switch to forward-only migrations (`alembic revision -m ...`) and never edit applied files.

## Callback Data Format

Telegram inline button callback data is size-limited. Use compact payloads:

```
v:<poll_id>
s:<poll_id>:<option_order>:<score>
q:<poll_id>:<option_order>:<score>
d:<poll_id>
e:<poll_id>
```

If UUID length causes issues, fall back to short numeric IDs or a token lookup table.
