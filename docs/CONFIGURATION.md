# Configuration

All configuration is loaded from environment variables. Use `.env` locally (never committed). In production, inject via the container environment.

## Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | — | Bot token from @BotFather |
| `POSTGRES_USER` | yes | — | Postgres role; used by the `db` container |
| `POSTGRES_PASSWORD` | yes | — | Postgres password; used by the `db` container |
| `POSTGRES_DB` | yes | — | Postgres database name; used by the `db` container |
| `DATABASE_URL` | yes | — | PostgreSQL DSN, e.g. `postgresql+psycopg://user:pass@db:5432/voting_bot`. Must stay consistent with the three `POSTGRES_*` values |
| `VOTER_HASH_SECRET` | yes | — | HMAC secret for hashing voter IDs; must be long and random |
| `SCORE_MIN` | no | `0` | Default minimum score for new polls |
| `SCORE_MAX` | no | `5` | Default maximum score for new polls |
| `LOG_LEVEL` | no | `INFO` | Python logging level |
| `WEBHOOK_URL` | no | — | Full public HTTPS URL Telegram should POST to. When set, the bot runs in webhook mode instead of long polling |
| `WEBHOOK_URL_PATH` | no | `/telegram/<TELEGRAM_BOT_TOKEN>` | Internal webhook path the bot listens on. `WEBHOOK_URL` must use the same path |
| `WEBHOOK_SECRET_TOKEN` | webhook mode | — | Secret token Telegram sends in `X-Telegram-Bot-Api-Secret-Token`; generate with `openssl rand -hex 32` |
| `WEBHOOK_LISTEN_HOST` | no | `0.0.0.0` | Interface used by the bot's webhook HTTP server |
| `WEBHOOK_LISTEN_PORT` | no | `8080` | Port used by the bot's webhook HTTP server |

## `.env.example`

Provided at repo root.

## Notes

- `VOTER_HASH_SECRET` must be generated with a CSPRNG (e.g. `openssl rand -hex 32`). Changing it invalidates all existing voter hashes.
- The poll creator can override the score range per poll via `/scorepoll --max N`; `SCORE_MIN` and `SCORE_MAX` are the defaults shown to the creator.
- `DATABASE_URL` uses the internal Podman network hostname `db` when running via `compose.yaml`.
- `postgresql+psycopg://` is recommended so Alembic/SQLAlchemy uses the installed psycopg v3 driver. Plain `postgresql://` is also normalized for compatibility.
- Managed PostgreSQL providers such as Neon and Supabase usually provide a `postgresql://` URL and may require TLS via `sslmode=require`.
- Migrations are not run automatically when the bot starts. Run `uv run alembic upgrade head` locally or the equivalent `podman compose run --rm bot uv run --no-sync alembic upgrade head` command for Compose.
- Leave `WEBHOOK_URL` unset for local development and long-polling deployments.
- In production webhook mode, `WEBHOOK_URL` must start with `https://` and its path must match `WEBHOOK_URL_PATH`. For the Hetzner VM, prefer a random path such as `https://static.227.25.225.46.clients.your-server.de/tg/long-random-secret` with `WEBHOOK_URL_PATH=/tg/long-random-secret`.
- `WEBHOOK_SECRET_TOKEN` may contain only letters, numbers, `_`, and `-`, up to 256 characters.
