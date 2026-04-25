# Configuration

All configuration is loaded from environment variables. Use `.env` locally (never committed). In production, inject via the container environment.

## Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | — | Bot token from @BotFather |
| `POSTGRES_USER` | yes | — | Postgres role; used by the `db` container |
| `POSTGRES_PASSWORD` | yes | — | Postgres password; used by the `db` container |
| `POSTGRES_DB` | yes | — | Postgres database name; used by the `db` container |
| `DATABASE_URL` | yes | — | PostgreSQL DSN, e.g. `postgresql://user:pass@db:5432/voting_bot`. Must stay consistent with the three `POSTGRES_*` values |
| `VOTER_HASH_SECRET` | yes | — | HMAC secret for hashing voter IDs; must be long and random |
| `SCORE_MIN` | no | `0` | Default minimum score for new polls |
| `SCORE_MAX` | no | `5` | Default maximum score for new polls |
| `LOG_LEVEL` | no | `INFO` | Python logging level |

## `.env.example`

Provided at repo root.

## Notes

- `VOTER_HASH_SECRET` must be generated with a CSPRNG (e.g. `openssl rand -hex 32`). Changing it invalidates all existing voter hashes.
- The poll creator can override the score range per poll via `/scorepoll --max N`; `SCORE_MIN` and `SCORE_MAX` are the defaults shown to the creator.
- `DATABASE_URL` uses the internal Podman network hostname `db` when running via `compose.yaml`.
