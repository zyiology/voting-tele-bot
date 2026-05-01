# Architecture

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12+ |
| Telegram client | `python-telegram-bot` |
| Database | PostgreSQL |
| Containers | Podman + `compose.yaml` |
| Telegram transport | Long polling for development; HTTPS webhooks for production |
| Hosting | Hetzner (or similar) Linux VPS |

## Component Overview

```
Telegram
   |
   | long polling
   v
Bot container (Python)
   |
   v
PostgreSQL container
```

Production webhook mode:

```
Telegram
   |
   | HTTPS webhook
   v
Host Caddy reverse proxy
   |
   | http://127.0.0.1:8080
   v
Bot container (Python)
   |
   v
PostgreSQL container
```

**Bot application** — receives Telegram updates, handles commands and callback queries, renders poll messages, validates poll state, records ballots, updates aggregate results.

**PostgreSQL** — stores polls, options, hashed voter IDs, ballots, sessions, and Telegram message references.

**Host Caddy** — terminates TLS on the VM and proxies Telegram webhook requests to the bot's localhost-only published port in production.

**Podman** — runs the bot and database containers locally and in production. The database port is not exposed publicly.

## Request Flow

1. User runs `/scorepoll` in a group.
2. Bot creates a poll record and posts a group message.
3. In default DM mode, the group message has a `[Vote]` button. User taps it; bot opens a private DM and walks them through scoring each option.
4. In quick mode (`/scorepoll --quick`), the group message has score buttons for each option. Each tap records that user's score and answers the callback with private progress feedback.
5. On each score selection, bot records/updates the ballot and refreshes the group message aggregate.
6. User taps `[Done]` in DM mode; session is cleared.
7. Poll creator or admin runs `/closepoll`; poll status flips to `closed`, further votes are rejected.

## Deployment

```
Ubuntu VM
├── Caddy on the host (TLS, reverse proxy)
├── Podman
│   ├── bot container
│   └── PostgreSQL container (persistent volume, not exposed publicly)
└── .env (secrets, never committed)
```

Local development uses long polling: `podman compose up --build`
