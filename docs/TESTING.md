# Testing

## Strategy

Voting logic lives in `voting_methods/` with no Telegram dependencies, so the core rules are tested with plain pytest — no mocking of the Telegram API required.

Telegram handler tests are deferred until after the core logic is stable.

## Test Files

| File | Covers |
|---|---|
| `tests/test_score_voting.py` | Score calculation, ranking, tie handling, ballot updates, incomplete ballots |
| `tests/test_hashing.py` | HMAC stability, secret rotation behavior |
| `tests/test_rendering.py` | Poll message text and keyboard structure |

## Key Cases

### Score voting (`test_score_voting.py`)

- Average score per option calculated correctly
- Options ranked highest-to-lowest average
- Tie: stable ordering (e.g. alphabetical or insertion order)
- Incomplete ballot (not all options scored) excluded from results
- Ballot update: second score for same voter+option replaces, not duplicates
- Score outside `[score_min, score_max]` rejected
- Zero voters: results show empty / no winner

**Canonical example:**

```
Poll: ["Sushi", "Pizza"]
Voter A: Sushi=5, Pizza=2
Voter B: Sushi=3, Pizza=4

Results:
  Sushi avg = 4.0
  Pizza avg = 3.0
  Winner: Sushi
```

### Hashing (`test_hashing.py`)

- Same user ID + same secret → same hash (deterministic)
- Same user ID + different secret → different hash
- Different user IDs → different hashes
- Output is a valid hex string of expected length

### Rendering (`test_rendering.py`)

- Open poll message includes title, option list, vote count, `[Vote]` button
- Closed poll message omits `[Vote]`, shows "CLOSED" label
- Results ranked correctly in rendered text
- Zero-vote state renders without errors

## Running Tests

```
uv run pytest
```

## Database-Backed Tests

Repository tests need a real Postgres (per project policy: no DB mocks). 
Spin up a one-off Postgres container per test session (e.g. via `testcontainers` or a `pytest` fixture that runs `podman run --rm postgres:18-alpine`), run `alembic upgrade head` against it, and tear it down at the end. Slower startup, fully isolated.

- Migrations are applied via `alembic upgrade head` against the test DSN before any repository tests run — never hand-create schema in fixtures, otherwise the test schema drifts from prod.
- Per-test isolation is best done by wrapping each test in a transaction that rolls back, rather than truncating tables.
- Set `DATABASE_URL` in the test env so `alembic/env.py` picks it up unchanged.
