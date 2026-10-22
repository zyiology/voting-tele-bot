# Repository Structure

```
voting-tele-bot/
├── README.md
├── .env.example
├── .todo
├── pyproject.toml
├── Containerfile               # Bot image
├── cloudbuild.yaml             # Cloud Build config for Cloud Run image builds
├── compose.yaml                # Bot + DB services
├── compose.dev.yaml            # Dev overrides (exposes Postgres on localhost:5432)
├── compose.prod.yaml           # Production overrides (webhook mode on localhost:8080)
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
│   ├── deployment-cloud-run.md # Cloud Run service and migration job deployment guide
│   ├── deployment-vm.md        # VM deployment guide with host reverse proxy
│   ├── STRUCTURE.md            # This file
│   ├── CONFIGURATION.md
│   ├── TESTING.md
│   └── plans/
│       ├── condorcet-from-scores-plan.md # Implemented dual results from existing scores
│       ├── date-poll-days-filter-plan.md # Implemented selectable days for date polls
│       ├── init-plan.md
│       ├── native-date-poll-plan.md # Telegram-native date availability poll plan
│       ├── no-dm-plan.md
│       ├── quick-voting-ux-plan.md  # Proposed UX improvements for --quick polls
│       └── webhooks-caddy-plan.md
├── src/
│   └── voting_bot/
│       ├── __init__.py
│       ├── main.py             # Entry point; builds Application, registers handlers
│       ├── config.py           # Loads and validates env vars
│       ├── database_url.py     # Normalizes Postgres URLs for SQLAlchemy and psycopg
│       ├── db.py               # Serialized async connection, transactions, isolated connections
│       ├── hashing.py          # HMAC voter ID helper
│       ├── models.py           # Dataclasses / typed dicts for Poll, Option, Ballot, visibility settings
│       ├── repositories/
│       │   ├── polls.py        # Poll and option CRUD; cross-instance message refresh lock
│       │   └── ballots.py      # Open-poll guarded ballot upsert; session management
│       ├── voting_methods/
│       │   ├── __init__.py
│       │   ├── base.py         # VotingMethod abstract base class
│       │   ├── ballots.py      # Shared complete score-ballot normalization
│       │   ├── analysis.py     # Both analyses from one normalized snapshot
│       │   ├── condorcet.py    # Strict pairwise majorities derived from scores
│       │   └── score.py        # Score voting: validation, averages, ranking
│       ├── handlers/
│       │   ├── commands.py     # /scorepoll, /poll_dates, /closepoll, /start, /help
│       │   └── callbacks.py    # Inline button callback dispatch
│       └── rendering.py        # Builds poll message text and InlineKeyboardMarkup
└── tests/
    ├── test_config.py
    ├── test_database_url.py
    ├── test_hashing.py
    ├── test_repositories.py
    ├── test_condorcet_voting.py
    ├── test_score_voting.py
    ├── test_handlers.py
    └── test_rendering.py
```

## Key Boundaries

- `voting_methods/` has no Telegram dependencies — pure Python, fully unit-testable.
- `handlers/` contains all Telegram-specific logic; it calls repositories and voting methods.
- `rendering.py` is the only place that constructs message text and keyboard layouts.
- `repositories/` owns all SQL; no raw queries elsewhere.

## Implementation Progress

- Close-versus-score-write race fixed on 2026-10-22: ballot writes lock and
  recheck the poll row in one transaction, so closure rejects subsequent inserts
  and edits in both DM and quick modes. Group refreshes acquire a per-poll
  PostgreSQL advisory lock through the Telegram edit and reload current poll
  state; stale handlers cannot overwrite the final closed message. Refreshes
  use a short-lived separate connection, with no schema or dependency changes.
  Verification: lint and type checks passed; all 235 tests passed against a
  temporary PostgreSQL instance, including both close/write orderings, delayed
  refreshes across connections, and lock release on failure or cancellation.
- Quick voting UX plan recorded on 2026-10-22 in
  [plans/quick-voting-ux-plan.md](plans/quick-voting-ux-plan.md): adds a
  `[My ballot]` modal alert button (`show_alert=True`), concise group-message
  voting instructions, `#N: 0` score button prefixes with a persistent option
  legend, and skips redundant group message edits on partial taps. Scheduled
  after [plans/condorcet-from-scores-plan.md](plans/condorcet-from-scores-plan.md).
- Condorcet plan proposed on 2026-10-21: the
  [implementation plan](plans/condorcet-from-scores-plan.md) derives pairwise preferences from
  existing score ballots and announces score and Condorcet winners separately,
  with no Condorcet fallback. Reviewed on 2026-10-22 with approved plan
  refinements for group-message explanations, duplicate-label winner summaries,
  and distinct-option validation tests. Implemented on 2026-10-22: one shared
  complete-ballot snapshot drives both analyses, separate winner summaries follow
  existing visibility rules, duplicate labels use original option numbers, and
  open group messages and help explain equal-score indifference. Date availability
  remains independent; no schema or dependency changes. Verification: lint and
  type checks passed; 217 tests passed and 9 database tests skipped without a
  configured test database. Live Telegram smoke tests remain a pre-rollout step.
  DESIGN examples now include the open-poll explanation and quick-mode
  zero-ballot notice to match rendered messages.
- VM deployment inspected on 2026-10-20; operational details and maintenance
  commands are recorded in `/root/README.md` on the VM. The bot uses Docker
  Compose with `unless-stopped` restart policies and host Caddy for HTTPS.
- `/poll_dates --days` is implemented with English aliases, quoted lists,
  Unicode whitespace support, and duplicate-day normalization. The legacy
  `--exclude-weekends` flag has been removed, and `DATE_POLL_USAGE` now documents
  `--days` and the 2–12 filtered date limit. Weekday selections are validated
  before generation, option limits apply after filtering, and generation safely
  handles `date.max` and oversized ranges.
  See [plans/date-poll-days-filter-plan.md](plans/date-poll-days-filter-plan.md).
- `/poll_dates` creates Telegram-native, non-anonymous, multiple-answer date
  polls without database state. Its parser accepts `D Mon YYYY` and `D/M/YY`
  ranges, and its bounded date-option generator lives in
  `handlers/commands.py`. Both formats have focused parser coverage in
  `tests/test_handlers.py`.
