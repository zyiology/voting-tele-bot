# Repository Structure

```
voting-tele-bot/
├── README.md
├── .env.example
├── .todo
├── pyproject.toml
├── Containerfile               # Bot image
├── compose.yaml                # Bot + DB services
├── compose.dev.yaml            # Dev overrides (exposes Postgres on localhost:5432)
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   ├── DESIGN.md
│   ├── DATABASE.md
│   ├── STRUCTURE.md            # This file
│   ├── CONFIGURATION.md
│   └── TESTING.md
├── src/
│   └── voting_bot/
│       ├── __init__.py
│       ├── main.py             # Entry point; builds Application, registers handlers
│       ├── config.py           # Loads and validates env vars
│       ├── db.py               # Connection pool; migration runner
│       ├── hashing.py          # HMAC voter ID helper
│       ├── models.py           # Dataclasses / typed dicts for Poll, Option, Ballot
│       ├── repositories/
│       │   ├── polls.py        # Poll and option CRUD
│       │   └── ballots.py      # Ballot upsert; session management
│       ├── voting_methods/
│       │   ├── __init__.py
│       │   ├── base.py         # VotingMethod abstract base class
│       │   └── score.py        # Score voting: validation, averages, ranking
│       ├── handlers/
│       │   ├── commands.py     # /scorepoll, /closepoll, /start, /help
│       │   └── callbacks.py    # Inline button callback dispatch
│       └── rendering.py        # Builds poll message text and InlineKeyboardMarkup
└── tests/
    ├── test_score_voting.py
    ├── test_hashing.py
    └── test_rendering.py
```

## Implementation Status

This document is the source of truth for repository structure and coarse
implementation status.

| Path | Status |
|---|---|
| `compose.yaml`, `compose.dev.yaml`, `Containerfile` | Implemented |
| `alembic/versions/0001_initial_schema.py` | Implemented |
| `src/voting_bot/main.py` | Minimal bot startup implemented |
| `src/voting_bot/config.py` | Minimal Telegram/log config implemented |
| `src/voting_bot/models.py` | Implemented |
| `src/voting_bot/voting_methods/` | Score voting core implemented |
| `src/voting_bot/handlers/commands.py` | Placeholder command handlers only |
| `src/voting_bot/db.py` | Planned |
| `src/voting_bot/hashing.py` | Planned |
| `src/voting_bot/repositories/` | Planned |
| `src/voting_bot/handlers/callbacks.py` | Planned |
| `src/voting_bot/rendering.py` | Planned |
| `tests/test_score_voting.py` | Implemented |
| `tests/test_hashing.py` | Planned |
| `tests/test_rendering.py` | Planned |

## Key Boundaries

- `voting_methods/` has no Telegram dependencies — pure Python, fully unit-testable.
- `handlers/` contains all Telegram-specific logic; it calls repositories and voting methods.
- `rendering.py` is the only place that constructs message text and keyboard layouts.
- `repositories/` owns all SQL; no raw queries elsewhere.
