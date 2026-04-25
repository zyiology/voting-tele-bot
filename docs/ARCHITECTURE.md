# Architecture

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12+ |
| Telegram client | `python-telegram-bot` |
| Database | PostgreSQL |
| Containers | Podman + `compose.yaml` |
| Telegram transport | Long polling (no public endpoint required) |
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

**Bot application** — receives Telegram updates, handles commands and callback queries, renders poll messages, validates poll state, records ballots, updates aggregate results.

**PostgreSQL** — stores polls, options, hashed voter IDs, ballots, sessions, and Telegram message references.

**Podman** — runs both containers locally and in production. The database port is not exposed publicly.

## Request Flow

1. User runs `/scorepoll` in a group.
2. Bot creates a poll record and posts a group message with a `[Vote]` button.
3. User taps `[Vote]`; bot opens a private DM and walks them through scoring each option.
4. On each score selection, bot records/updates the ballot and refreshes the group message aggregate.
5. User taps `[Done]`; session is cleared.
6. Poll creator or admin runs `/closepoll`; poll status flips to `closed`, further votes are rejected.

## Deployment

```
Ubuntu VM
├── Podman
│   ├── bot container
│   └── PostgreSQL container (persistent volume, not exposed publicly)
└── .env (secrets, never committed)
```

Local development: `podman compose up --build`
