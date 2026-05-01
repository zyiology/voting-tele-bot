# Plan: VM webhook deployment for v1

## Goal

Add Telegram webhook support to the bot while keeping local development on
long polling. The first production target is a Hetzner VM where Caddy runs
on the host, outside this repository.

Production shape:

```text
Telegram
  -> https://static.227.25.225.46.clients.your-server.de
  -> host Caddy on VM
  -> http://127.0.0.1:8080
  -> bot container
  -> PostgreSQL container
```

Cloud Run can be reconsidered later. This iteration avoids Cloud Run
deployment files, Cloud Build changes, and a repo-managed Caddy container.

## Runtime behavior

The bot chooses its Telegram transport by configuration:

- `WEBHOOK_URL` unset: use long polling.
- `WEBHOOK_URL` set: run an internal webhook HTTP server and register the
  public webhook URL with Telegram on startup.

Webhook mode uses PTB's `Application.run_webhook()` and the
`python-telegram-bot[webhooks]` dependency extra.

## Configuration

Add these optional environment variables:

- `WEBHOOK_URL`: full public HTTPS URL Telegram should POST to.
- `WEBHOOK_URL_PATH`: path the bot listens on; defaults to
  `/telegram/<TELEGRAM_BOT_TOKEN>`.
- `WEBHOOK_SECRET_TOKEN`: required in webhook mode; sent by Telegram in
  `X-Telegram-Bot-Api-Secret-Token`.
- `WEBHOOK_LISTEN_HOST`: defaults to `0.0.0.0`.
- `WEBHOOK_LISTEN_PORT`: defaults to `8080`.

For the Hetzner VM, prefer a random path such as:

```env
WEBHOOK_URL=https://static.227.25.225.46.clients.your-server.de/tg/long-random-secret
WEBHOOK_URL_PATH=/tg/long-random-secret
WEBHOOK_SECRET_TOKEN=<openssl rand -hex 32>
```

Validation rules:

- `WEBHOOK_URL` must start with `https://`.
- `WEBHOOK_SECRET_TOKEN` is required when `WEBHOOK_URL` is set.
- `WEBHOOK_SECRET_TOKEN` may contain only `A-Z`, `a-z`, `0-9`, `_`, and
  `-`, length 1-256.
- `WEBHOOK_URL` path must match `WEBHOOK_URL_PATH`.
- `WEBHOOK_LISTEN_PORT` must be an integer.

## Compose production override

Add `compose.prod.yaml` to enable webhook mode and publish the bot only on
VM localhost:

```yaml
services:
  bot:
    environment:
      WEBHOOK_URL: ${WEBHOOK_URL}
      WEBHOOK_SECRET_TOKEN: ${WEBHOOK_SECRET_TOKEN}
      WEBHOOK_LISTEN_HOST: 0.0.0.0
      WEBHOOK_LISTEN_PORT: 8080
    ports:
      - "127.0.0.1:8080:8080"
```

Run production with:

```sh
podman compose -f compose.yaml -f compose.prod.yaml up -d --build
```

Run migrations explicitly:

```sh
podman compose -f compose.yaml -f compose.prod.yaml run --rm bot uv run --no-sync alembic upgrade head
```

## Host Caddy responsibility

Caddy is configured on the VM, not in the repo. It should:

- serve `static.227.25.225.46.clients.your-server.de`;
- terminate TLS with a publicly trusted certificate;
- reverse proxy to `127.0.0.1:8080`;
- keep ports `80` and `443` reachable from the public internet for
  certificate issuance and Telegram delivery.

## Completed implementation scope

1. Add webhook config fields and validation.
2. Add PTB webhook dependency extra and refresh `uv.lock`.
3. Branch `main.py` between polling and webhook mode.
4. Add `compose.prod.yaml`.
5. Add focused config tests.
6. Update `.env.example`, README, architecture, configuration, and
   structure docs.

## Deferred

- Cloud Run deployment.
- Cloud Build changes.
- Repo-managed Caddy container or committed `Caddyfile`.
- Health-check endpoint.
- Telegram IP allow-listing.
- Rate limiting at the reverse proxy.
