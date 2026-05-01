# VM Deployment

This guide deploys the bot on a Linux VM with Podman Compose. The bot and
Postgres run as containers. TLS termination and public HTTPS routing are
handled by a reverse proxy on the host, such as Caddy.

The production request path is:

```text
Telegram
  -> https://static.227.25.225.46.clients.your-server.de/tg/long-random-secret
  -> host reverse proxy
  -> http://127.0.0.1:8080
  -> bot container
  -> PostgreSQL container
```

## Prerequisites

- A Linux VM with ports `80` and `443` reachable from the public internet.
- Podman or Docker with the Compose plugin.
- A host-level reverse proxy. The examples below use Caddy, but do not
  cover Caddy installation.
- A Telegram bot token from @BotFather.

## Clone and Configure

Clone the repository on the VM and create `.env`:

```sh
cp .env.example .env
```

Set the base variables:

```env
TELEGRAM_BOT_TOKEN=replace-me

POSTGRES_USER=voting_bot
POSTGRES_PASSWORD=replace-with-a-long-random-password
POSTGRES_DB=voting_bot
DATABASE_URL=postgresql+psycopg://voting_bot:replace-with-a-long-random-password@db:5432/voting_bot

VOTER_HASH_SECRET=replace-with-openssl-rand-hex-32
SCORE_MIN=0
SCORE_MAX=5
LOG_LEVEL=INFO
```

Generate secrets on the VM:

```sh
openssl rand -hex 32
```

Use the same Postgres password in `POSTGRES_PASSWORD` and `DATABASE_URL`.
`VOTER_HASH_SECRET` must stay stable after deployment; changing it makes
existing voter hashes impossible to match.

## Webhook URL

Production uses webhook mode when `WEBHOOK_URL` is set. Prefer a random
webhook path that is not the bot token, for example:

```env
WEBHOOK_URL=https://static.227.25.225.46.clients.your-server.de/tg/long-random-secret
WEBHOOK_URL_PATH=/tg/long-random-secret
WEBHOOK_SECRET_TOKEN=replace-with-openssl-rand-hex-32
```

`WEBHOOK_URL_PATH` must exactly match the path part of `WEBHOOK_URL`.
`WEBHOOK_SECRET_TOKEN` may contain only letters, numbers, `_`, and `-`.
The bot registers the webhook with Telegram during startup; do not call
Telegram's `setWebhook` manually.

## Reverse Proxy

If using Caddy on the host, a minimal Caddyfile can route only the
webhook path to the bot and return `404` for everything else:

```caddyfile
static.227.25.225.46.clients.your-server.de {
    handle /tg/long-random-secret {
        reverse_proxy 127.0.0.1:8080
    }

    respond "not found" 404
}
```

Keep the Caddy path, `WEBHOOK_URL`, and `WEBHOOK_URL_PATH` in sync. With
the example above, the matching env values are:

```env
WEBHOOK_URL=https://static.227.25.225.46.clients.your-server.de/tg/long-random-secret
WEBHOOK_URL_PATH=/tg/long-random-secret
```

`compose.prod.yaml` publishes the bot only on `127.0.0.1:8080`, so the
container is reachable by host Caddy but is not directly exposed on the
public network.

## First Deploy

Build the bot image:

```sh
podman compose -f compose.yaml -f compose.prod.yaml build bot
```

Start Postgres:

```sh
podman compose -f compose.yaml -f compose.prod.yaml up -d db
```

Run migrations:

```sh
podman compose -f compose.yaml -f compose.prod.yaml run --rm bot uv run --no-sync alembic upgrade head
```

Start the bot:

```sh
podman compose -f compose.yaml -f compose.prod.yaml up -d bot
```

Check logs:

```sh
podman compose -f compose.yaml -f compose.prod.yaml logs -f bot
```

## Update Deploy

After pulling new code:

```sh
podman compose -f compose.yaml -f compose.prod.yaml build bot
podman compose -f compose.yaml -f compose.prod.yaml run --rm bot uv run --no-sync alembic upgrade head
podman compose -f compose.yaml -f compose.prod.yaml up -d bot
```

Migrations are intentionally not run automatically on service startup.
Run them as an explicit deployment step before restarting the bot.

## Operational Notes

- Keep `.env` private and do not commit it.
- Back up the `db_data` volume before risky upgrades.
- Keep Caddy's certificate storage persistent according to your host
  setup.
- Leave `WEBHOOK_URL` unset only for long-polling deployments. The
  production Compose override expects webhook mode.
