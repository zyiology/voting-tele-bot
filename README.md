# Telegram Score Voting Bot

A Telegram bot for running score voting polls in group chats. Telegram's native polls do not support score voting or other advanced social-choice methods. This bot fills that gap: poll creation happens via a slash command, voting happens through inline buttons in a private DM flow, and only aggregate results are shown in the group.

## MVP Features

- Create a score voting poll in a group chat with `/scorepoll`
- Configurable integer score range (e.g. 0–5, 0–10)
- Guided per-option ballot via inline buttons in a private message
- Optional quick voting mode via score buttons directly in the group message
- Ballots are private — no individual votes posted to the group
- Voter identities stored as HMAC-hashed IDs, never raw
- Live aggregate results visible in the group message as votes come in
- Ballot editing while the poll is open
- Close a poll with `/closepoll` (creator or group admin only)
- One active poll per group chat at a time

## Out of Scope for MVP

See [`.todo`](.todo) for future work.

## Deployment

The bot and Postgres run as containers via `compose.yaml`. Migrations are applied automatically on bot startup (`alembic upgrade head`).

### Prerequisites

- `podman` (or `docker`) with the compose plugin
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### Configuration

Copy `.env.example` to `.env` and fill in:

- `TELEGRAM_BOT_TOKEN` — from BotFather
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — Postgres credentials. Keep `DATABASE_URL` consistent with these.
- `VOTER_HASH_SECRET` — generate with `openssl rand -hex 32`. Changing this invalidates all existing voter hashes.

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for the full variable reference.

### Production / non-dev

```
podman compose up -d --build
```

Postgres is reachable only on the internal compose network. Logs:

```
podman compose logs -f bot
```

To apply new migrations after pulling code, rebuild and restart the bot — `alembic upgrade head` runs on every container start:

```
podman compose up -d --build bot
```

### Development

The dev override exposes Postgres on `localhost:5432` so you can connect with `psql` or a GUI:

```
podman compose -f compose.yaml -f compose.dev.yaml up --build
```

Run a one-off psql session against the running db:

```
podman compose exec db psql -U voting_bot -d voting_bot
```

Run the bot directly on the host (against the containerized db) for faster iteration:

```
podman compose -f compose.yaml -f compose.dev.yaml up -d db
uv run alembic upgrade head
uv run voting-bot
```

### Migrations

Schema changes are managed with Alembic. To create a new migration:

```
uv run alembic revision -m "describe change"
```

Edit the generated file in `alembic/versions/` (raw SQL via `op.execute(...)` — we don't use SQLAlchemy ORM models). Apply with:

```
uv run alembic upgrade head
```

Roll back one revision:

```
uv run alembic downgrade -1
```
