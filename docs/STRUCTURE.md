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
├── scripts/
│   └── inspect_poll_voters.py   # Inspect poll voter hashes and optionally match known Telegram IDs
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
│       ├── database_url.py     # Normalizes Postgres URLs for SQLAlchemy and psycopg
│       ├── db.py               # Connection pool; migration runner
│       ├── hashing.py          # HMAC voter ID helper
│       ├── models.py           # Dataclasses / typed dicts for Poll, Option, Ballot, visibility settings
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
    ├── test_config.py
    ├── test_database_url.py
    ├── test_hashing.py
    ├── test_repositories.py
    ├── test_score_voting.py
    ├── test_handlers.py
    └── test_rendering.py
```

## Key Boundaries

- `voting_methods/` has no Telegram dependencies — pure Python, fully unit-testable.
- `handlers/` contains all Telegram-specific logic; it calls repositories and voting methods.
- `rendering.py` is the only place that constructs message text and keyboard layouts.
- `repositories/` owns all SQL; no raw queries elsewhere.
