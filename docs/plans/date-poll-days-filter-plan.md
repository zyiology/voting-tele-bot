# Date Poll Day Filter Implementation Plan

## Status

Implemented and verified on 12 September 2026. The user approved implementation
and the subsequent test/documentation checkpoint. The command parser, normalized
weekday request model, bounded filtering, help text, regression tests, and
README/DESIGN/TESTING/STRUCTURE documentation are updated.

Validation: `uv run ruff check` and `uv run ty check` pass;
`uv run pytest -ra` reports 181 passed and 9 repository integration tests skipped
because `DATABASE_URL` is unset. No new dependencies or migrations were needed.
The design and implementation checklist below records the approved plan.

## Objective and feasibility

Extend `/poll_dates` with `--days` so an organizer can select which days of the
week appear within the inclusive date range:

```text
/poll_dates 5/9/26 18/9/26 --days 'mon,tues,fri'
/poll_dates 5/9/26 18/9/26 --days 'fri,sat,sun'
/poll_dates 5 Sep 2026 18 Sep 2026 --days mon,wed,fri
```

This fits the existing implementation in `src/voting_bot/handlers/commands.py`.
`parse_poll_dates_command` currently records an `exclude_weekends` boolean in
`DatePollRequest`, and `generate_date_poll_options` filters dates using that
boolean. Generalize this into a normalized set of weekday numbers. The Telegram
handler can continue sending the generated options as it does today; no new
dependencies, database state, or migrations are needed.

## Proposed input contract

### Accepted names and syntax

- Accept `--days LIST`, where LIST is one comma-separated argument.
- Accept an unquoted list without spaces, or a single- or double-quoted list.
  Strip whitespace around each comma-separated item, so `"mon, tues, fri"`
  works. A list containing spaces must be quoted.
- Preserve Unicode whitespace as a separator outside quotes, matching the
  existing command parser, including nonbreaking spaces copied into dates.
  Preserve quoted content until individual day names are stripped.
- Match names case-insensitively using an explicit English lookup table:

  | Day | Accepted names |
  | --- | --- |
  | Monday | `mon`, `monday` |
  | Tuesday | `tue`, `tues`, `tuesday` |
  | Wednesday | `wed`, `wednesday` |
  | Thursday | `thu`, `thur`, `thurs`, `thursday` |
  | Friday | `fri`, `friday` |
  | Saturday | `sat`, `saturday` |
  | Sunday | `sun`, `sunday` |

- Normalize repeated days and aliases into one selection: `mon,monday,mon`
  means Monday only. List order does not affect chronological option order.
- Allow a single selected day; a sufficiently long range can contain multiple
  occurrences of that day. Require at least two retained dates, not two distinct
  days of the week.
- Permit the flag and its value before, between, or after the two dates, matching
  the existing flag-position convention. Document trailing flags.
- Keep the existing date formats and validation, including same-format endpoints
  and numeric years mapping to 2000–2099.
- Do not add `--days=...`, numeric weekday identifiers, day ranges such as
  `mon-fri`, or special names such as `weekdays` in this change.

### Defaults and compatibility

- Without a filter, include every date as before.
- Retain `--exclude-weekends` as a supported shortcut for `--days mon,tue,wed,thu,fri`.
  No deprecation is proposed.
- Reject combining `--days` and `--exclude-weekends`, even when equivalent.
  Tell the user to choose one filter. This avoids implicit precedence or an
  intersection that silently discards explicitly selected days.
- Reject repeated `--days` flags, as the parser already does for repeated
  `--exclude-weekends`.

### Validation and feedback

Reject missing values, an empty quoted value, empty comma-separated items
(`mon,,fri`, `,mon`, `mon,`), unknown names, malformed quotes, unknown flags,
and extra positional arguments. Do not silently discard invalid entries.

Use actionable errors, for example:

```text
--days requires a comma-separated list, e.g. --days mon,tue,fri.
Unknown day: "funday". Use mon,tue,wed,thu,fri,sat,sun (tues is also accepted).
--days contains an empty day. Provide a day between each comma.
Use either --days or --exclude-weekends, not both.
```

Preserve the project's current minimum of 2 and maximum of 12 generated options,
applying both limits after filtering. Update errors to refer to day filtering
rather than weekend filtering. For too few dates, suggest extending the range
or selecting more days; for too many, suggest shortening the range or selecting
fewer days. Continue reporting "at least 13" when generation stops early.

Proposed usage text:

```text
Usage: /poll_dates D Mon YYYY D Mon YYYY [--days LIST | --exclude-weekends]
   or: /poll_dates D/M/YY D/M/YY [--days LIST | --exclude-weekends]
Example: /poll_dates 5/9/26 18/9/26 --days mon,tues,fri
Days: mon,tue,wed,thu,fri,sat,sun; full names and tues/thur/thurs also accepted.
```

## Implementation steps

1. Add explicit weekday-name normalization near the existing month and weekday
   constants in `handlers/commands.py`. Keep day-list parsing in a small pure
   helper that raises `DatePollParseError`. Avoid locale-dependent parsing.

2. Replace `DatePollRequest.exclude_weekends` with
   `included_weekdays: frozenset[int]`, using Python's Monday=0 through Sunday=6
   convention. Normalize all three command forms into this one representation:
   all seven days by default, Monday–Friday for the legacy flag, or the explicit
   nonempty selection for `--days`. Update production callers together; do not
   retain redundant boolean and set fields that could disagree.

3. Replace `str.split()` with a configured `shlex.shlex` tokenizer to support
   quoted strings while preserving Unicode whitespace compatibility. Use
   POSIX mode, enable `whitespace_split`, and disable comments, matching
   `shlex.split()` behavior. Extend the tokenizer's `whitespace` with characters
   in the raw arguments for which `str.isspace()` is true; the tokenizer then
   treats these as separators outside quotes while preserving quoted content.
   Plain `shlex.split()` alone would regress inputs containing nonbreaking
   spaces. The module already imports `shlex` for score polls. Translate
   tokenizer `ValueError` into a date usage error.
   Iterate through tokens while consuming the token after `--days`; recognize
   a following flag as a missing value. Track duplicate flags and conflicts
   separately from the normalized set, then reuse the existing date parsers.

4. Filter with `current_date.weekday() in request.included_weekdays`. Preserve
   inclusive endpoints, English option labels, and chronological order. Stop
   immediately on the thirteenth retained date. Because a parsed selection is
   nonempty and repeats weekly, even a one-day selection reaches that bound
   within 91 scanned calendar dates on a long range. Before scanning, require
   `included_weekdays` to be a nonempty subset of `{0, 1, 2, 3, 4, 5, 6}`,
   raising `DatePollParseError` otherwise. This also protects requests
   constructed directly by Python callers: a nonempty set such as `{7}` would
   never match and would otherwise scan the entire range. Reject mixed valid
   and invalid selections rather than silently discarding invalid values. Guard the
   increment at the inclusive endpoint so ranges ending on `date.max` cannot
   overflow.

5. Update `DATE_POLL_USAGE` and filter-related errors. `/help` already includes
   this constant, so it will expose the new syntax without another command or
   registration change. Preserve the existing native-poll visibility and
   multiple-answer behavior.

6. Run linting and type checking through `uv`. At the repository's required
   post-implementation checkpoint, summarize the tests and documentation below
   and obtain approval before editing those files, unless that approval has
   already been explicitly granted. The request-model change means existing
   tests that construct or inspect `DatePollRequest` must be migrated before
   the feature can pass the full suite; do not treat code-only work as complete.

7. After the approved test and documentation updates, run:

   ```text
   uv run ruff check
   uv run ty check
   uv run pytest
   ```

   Report any database-dependent skips or environment blockers. Update
   `docs/STRUCTURE.md` and this plan's status to reflect the completed work.

## Recommended tests (approval checkpoint)

Extend `tests/test_handlers.py` and migrate existing request constructors and
assertions to the normalized weekday set. Keep existing date-format, error,
group-only, and Telegram behavior coverage.

- Parse both date formats with quoted/unquoted lists, mixed case, whitespace
  inside quoted lists, all supported aliases, bot-addressed commands, and flags
  before/between/after dates.
- Verify Unicode whitespace separators in both date formats, with no filter,
  the legacy filter, and `--days`; include nonbreaking spaces (`U+00A0`) and
  narrow nonbreaking spaces (`U+202F`). Verify whitespace inside quoted lists
  remains within one token and is stripped around individual day names, while
  unquoted lists with Unicode whitespace between items are rejected.
- Reject missing or empty values, empty list items, unknown names, unmatched
  quotes, duplicate flags, conflicting filters in either order, unsupported
  `--days=...`, and extra tokens from unquoted lists containing spaces.
- Verify no-filter and legacy-filter results remain equivalent to all seven
  days and Monday–Friday respectively.
- Verify aliases and duplicates produce a unique normalized selection, and
  input order does not reorder generated dates.
- Check the first example generates exactly 7, 8, 11, 14, 15, and 18 September
  2026; the second generates exactly 5, 6, 11, 12, 13, and 18 September 2026.
- Cover one selected weekday over multiple weeks, inclusive endpoints,
  month/year boundaries, and a leap-day range with filtering.
- Exercise zero, one, two, twelve, and thirteen retained dates. Include a range
  exceeding twelve calendar days that becomes valid after filtering.
- Verify a huge range with a one-day filter stops at the thirteenth match;
  cover a range ending at `date.max`.
- Verify directly constructed empty selections and selections containing
  out-of-range values (`{-1}`, `{7}`, and `{0, 7}`) raise `DatePollParseError`
  before scanning, including for a huge range.
- Verify the handler passes the exact filtered options to `reply_poll`, while
  invalid day input produces usage feedback without sending a poll.
- Verify `/help` advertises `--days` and retains the visible-voter explanation.

## Recommended documentation (approval checkpoint)

- `README.md`: add both requested examples, list supported names and quoting
  rules, explain the legacy shortcut and mutual exclusion, and state that option
  limits apply after filtering.
- `docs/DESIGN.md`: record the approved command contract, chronological ordering,
  compatibility behavior, and validation rules.
- `docs/TESTING.md`: add selected-day parsing and generation coverage.
- `docs/STRUCTURE.md`: mark the feature implemented after verification and
  retain the new plan entry.

## Acceptance criteria

- Both requested day lists create the expected dates for a valid range.
- Every matching date appears once, in chronological order, including matching
  endpoints; no other dates appear.
- Existing unfiltered and `--exclude-weekends` commands retain their behavior.
- Unicode whitespace remains supported between command arguments, with quoted
  day lists preserved as single arguments.
- Invalid filters return actionable feedback and create no poll.
- Option limits apply after filtering, and generation remains bounded.
- Directly constructed weekday selections must be nonempty and contain only
  values from 0 through 6; invalid selections fail before date iteration.
- Approved tests and documentation are updated and required checks pass.

## Review decisions

The alias table, retention of `--exclude-weekends`, rejection of combined
filters, and duplicate-day normalization were approved and implemented as
described above. Test and documentation updates were approved at the required
post-implementation checkpoint.
