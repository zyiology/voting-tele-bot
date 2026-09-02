# Telegram Voting Bot

A Telegram bot for running score voting and simple date-availability polls in
group chats. Custom score polls use private inline-button ballots and show only
aggregate results. Date availability uses Telegram's native poll interface so
participants can select multiple dates and see who selected each option.

## MVP Features

- Create a score voting poll in a group chat with `/scorepoll`
- Create a native date-availability poll with `/poll_dates`
- Configurable integer score range (e.g. 0–5, 0–10)
- Guided per-option ballot via inline buttons in a private message
- Optional quick voting mode via score buttons directly in the group message
- Score-poll ballots are private — no individual scores are posted to the group
- Voter identities stored as HMAC-hashed IDs, never raw
- Live aggregate results are hidden by default while voting is open, with opt-in live display via `--live-results`
- Ballot editing while the poll is open
- Close a poll with `/closepoll` (creator or group admin only)
- One active score poll per group chat at a time
- Native date polls are independent of the active score-poll limit and database

## Commands

Create a score poll:

```
/scorepoll "Where should we eat?" "Sushi" "Pizza" "Thai"
```

Create an inclusive date-availability poll:

```
/poll_dates 5 Sep 2026 18 Sep 2026
/poll_dates 5 Sep 2026 18 Sep 2026 --exclude-weekends
/poll_dates 5/9/26 18/9/26 --exclude-weekends
```

Date polls accept either English `D Mon YYYY` dates or numeric `D/M/YY` dates
and at most 12 generated options. Both dates must use the same format. Numeric
years always mean 2000 through 2099, so `26` means 2026. Date polls are
non-anonymous: voters and their selections are visible through Telegram.
`--exclude-weekends` removes Saturdays and Sundays only.

## Out of Scope for MVP

See [`.todo`](.todo) for future work.

## Deployment

The bot and Postgres run as containers via `compose.yaml`. Migrations are
run explicitly with Alembic before starting or updating the bot service.

### Prerequisites

- `podman` (or `docker`) with the compose plugin
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### Configuration

Copy `.env.example` to `.env` and fill in:

- `TELEGRAM_BOT_TOKEN` — from BotFather
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — Postgres credentials. Keep `DATABASE_URL` consistent with these.
- `VOTER_HASH_SECRET` — generate with `openssl rand -hex 32`. Changing this invalidates all existing voter hashes.

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for the full variable reference.

### Production on a VM

```
podman compose -f compose.yaml -f compose.prod.yaml build bot
podman compose -f compose.yaml -f compose.prod.yaml up -d db
podman compose -f compose.yaml -f compose.prod.yaml run --rm bot uv run --no-sync alembic upgrade head
podman compose -f compose.yaml -f compose.prod.yaml up -d bot
```

`compose.prod.yaml` enables Telegram webhooks and publishes the bot HTTP
server on `127.0.0.1:8080` for a host-level reverse proxy such as Caddy.
Configure Caddy on the VM to terminate TLS for
`static.227.25.225.46.clients.your-server.de` and proxy to
`127.0.0.1:8080`.

See [`docs/deployment-vm.md`](docs/deployment-vm.md) for the full VM
deployment guide, including an example Caddy reverse proxy config.

Set these production variables in `.env`:

- `WEBHOOK_URL=https://static.227.25.225.46.clients.your-server.de/tg/long-random-secret`
- `WEBHOOK_URL_PATH=/tg/long-random-secret`
- `WEBHOOK_SECRET_TOKEN` — generate with `openssl rand -hex 32`

Postgres is reachable only on the internal compose network. Logs:

```
podman compose logs -f bot
```

To apply new migrations after pulling code, rebuild the image, run
migrations explicitly, and restart the bot:

```
podman compose -f compose.yaml -f compose.prod.yaml build bot
podman compose -f compose.yaml -f compose.prod.yaml run --rm bot uv run --no-sync alembic upgrade head
podman compose -f compose.yaml -f compose.prod.yaml up -d bot
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
