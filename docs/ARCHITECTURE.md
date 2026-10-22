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

### Custom score polls

1. User runs `/scorepoll` in a group.
2. Bot creates a poll record and posts a group message.
3. In default DM mode, the group message has a `[Vote]` button. User taps it; bot opens a private DM and walks them through scoring each option.
4. In quick mode (`/scorepoll --quick`), the group message has score buttons for each option. Each tap records that user's score and answers the callback with private progress feedback.
5. On each score selection, bot records/updates the ballot and refreshes the group message aggregate.
   The shared renderer normalizes this saved snapshot once: foreign/unknown
   rows are ignored, the last row for each voter/option wins, and incomplete
   ballots are excluded. `analysis.py` passes the same complete score maps to
   `score.py` and `condorcet.py`. Frozen result types retain both outcomes and
   each pair's directional and indifferent counts. Condorcet tally requires at
   least two distinct option UUIDs; equal labels are allowed.
6. User taps `[Done]` in DM mode; session is cleared. The last missing score
   already made the ballot count; edits to a complete ballot affect both tallies
   immediately, including intermediate scores during a multi-option edit.
7. Poll creator or admin runs `/closepoll`; poll status flips to `closed`, further votes are rejected.

Pairwise tally takes `O(V * N²)` time and `O(N²)` pairwise storage for V complete
ballots and N options. At the ten-option limit there are 45 pairs per voter.
Results are recomputed on refresh without another query, cache, new dependency,
or migration. The stored method remains `score`.

Score writes lock the poll row and recheck its status in the same transaction
as the ballot upsert. Closing a poll updates that same row, so a score that
acquires the lock first commits before closure; if closure wins, the write is
rejected in both DM and quick modes. Closed ballots cannot be inserted or edited
through the ballot repository.

Group-message refreshes use a per-poll PostgreSQL transaction advisory lock,
held through the Telegram edit, to serialize updates across bot instances.
Each refresh reloads the poll after acquiring the lock, so an old handler cannot
restore open-poll text or buttons after the final closed refresh. The lock uses
a short-lived separate connection, leaving the main database connection available
during Telegram requests. This adds a connection and a poll-state query per
refresh, without schema changes. Telegram failures still propagate (apart from
the existing harmless "message is not modified" response); delivery retries and
recovery after a process crash are outside this guarantee.

### Native date polls

1. User runs `/poll_dates` with an inclusive date range and optional
   `--exclude-weekends` flag in a group.
2. The command handler parses and validates the range and produces 2–12
   chronological date labels.
3. The bot sends a non-anonymous Telegram-native poll with multiple answers
   enabled.
4. Telegram owns voting, vote editing, and result display. The bot does not
   process poll-answer updates or write native date-poll state to PostgreSQL.

This direct command-to-Telegram flow is independent of custom score-poll state,
including the one-active-poll constraint and `/closepoll` lifecycle.

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
