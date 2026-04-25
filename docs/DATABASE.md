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
    voting_method   TEXT NOT NULL,        -- 'score'
    status          TEXT NOT NULL,        -- 'open' | 'closed'
    score_min       INTEGER NOT NULL DEFAULT 0,
    score_max       INTEGER NOT NULL DEFAULT 5,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at       TIMESTAMPTZ
);

CREATE TABLE poll_options (
    id            UUID PRIMARY KEY,
    poll_id       UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    label         TEXT NOT NULL,
    display_order INTEGER NOT NULL
);

CREATE TABLE ballots (
    poll_id    UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    voter_hash TEXT NOT NULL,
    option_id  UUID NOT NULL REFERENCES poll_options(id) ON DELETE CASCADE,
    score      INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (poll_id, voter_hash, option_id)
    -- Composite PK enforces one score per voter per option; updates replace, not duplicate.
);

CREATE TABLE poll_sessions (
    poll_id           UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    voter_hash        TEXT NOT NULL,
    current_option_id UUID REFERENCES poll_options(id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (poll_id, voter_hash)
);
```

## Notes

- `ballots` primary key `(poll_id, voter_hash, option_id)` makes ballot updates an upsert — no duplicate detection logic needed in the application.
- `poll_sessions` tracks which option a voter is currently scoring during the inline flow; cleared when voting completes.
- `message_id` on `polls` is set after the bot posts the group message; used to edit the message when results update.
- All ballot history is retained after a poll closes.
- One active poll per `chat_id` is enforced at the application layer (query for `status = 'open'` before creating).

## Callback Data Format

Telegram inline button callback data is size-limited. Use compact payloads:

```
vote:<poll_id>
results:<poll_id>
score:<poll_id>:<option_id>:<score>
close:<poll_id>
done:<poll_id>
edit:<poll_id>
```

If UUID length causes issues, fall back to short numeric IDs or a token lookup table.
