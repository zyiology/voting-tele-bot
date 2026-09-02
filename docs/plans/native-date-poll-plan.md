# Native Date Poll Implementation Plan

## Status

Implemented, including recommended tests and documentation.

## Summary and recommendation

Add a separate `/poll_dates` command that turns an inclusive date range into a
Telegram-native, non-anonymous, multiple-answer poll. This is a good fit for
simple date availability: Telegram can render the controls, collect selections,
allow changes, and display aggregate results without using this project's score-poll
database, callback handlers, or custom rendering.

This should complement, not extend or replace, `/scorepoll`. The two features
have different semantics:

- `/poll_dates` asks participants to select every date that works and delegates
  voting and results to Telegram.
- `/scorepoll` records a score for every option and retains the existing custom
  privacy, completion, result-visibility, and closing rules.

The proposed command uses an underscore because Telegram command names may
contain Latin letters, digits, and underscores, but not hyphens. Hyphens remain
valid in command arguments, so `--exclude-weekends` is unchanged.

## Proposed user experience

```text
/poll_dates 5 Sep 2026 18 Sep 2026
/poll_dates 5 Sep 2026 18 Sep 2026 --exclude-weekends
```

The command creates a regular native poll with:

- question: `Which dates work? Select all that apply.`
- options in chronological order, formatted with an unambiguous weekday, for
  example `Mon, 7 Sep 2026`
- multiple answers enabled
- non-anonymous voting enabled so participants and organizers can see who is
  available on each date
- option shuffling disabled/defaulted off so chronological order is preserved
- normal Telegram result visibility and vote editing behavior

The start and end dates are inclusive. `--exclude-weekends` removes Saturdays
and Sundays; it does not attempt to identify public holidays.

## Important constraints and product decisions

### Telegram's option limit

A native poll supports at most 12 options. The unfiltered example from
5 September through 18 September 2026 contains 14 dates and therefore cannot
fit in one poll. With `--exclude-weekends`, it produces 10 weekday options and
does fit.

For the first version, reject any range that produces more than 12 options and
report the generated count with guidance to shorten the range or use
`--exclude-weekends`. Do not automatically split the range: several Telegram
polls would fragment one availability question, make participation and results
harder to assess, and introduce lifecycle decisions that the simple command is
intended to avoid.

Require at least two generated dates even if newer Bot API versions technically
permit one option. A one-date multiple-choice poll is not useful and the
project's locked `python-telegram-bot` version predates that relaxed minimum.

### Independence from score polls

Native date polls should not create database records and should not participate
in the "one active score poll per chat" constraint. A group can have a native
date poll and a custom score poll at the same time.

`/closepoll` continues to mean "close the active custom score poll" and does not
close native date polls. Adding bot-managed closing for native polls would
require retaining their Telegram message references or introducing a
reply-to-poll close command; that is intentionally out of scope for this first
version.

### Abuse and duplicate commands

The first version will not add rate limiting or restrict poll creation to group
admins. The intended MVP audience is a small, trusted group of friends, so that
extra policy and state are not justified yet. Unlike score polls, native date
polls have no database-backed active-poll constraint; rate limiting should be
reconsidered if the bot is made available to a wider audience.

Do prevent accidental duplicates caused by command edits. `CommandHandler`
handles edited command messages by default, so register `/poll_dates` with an
update filter that excludes edited messages. A deliberate new command may still
create another native poll.

### Privacy

Use non-anonymous native polls by default so date availability is attributable;
participants and organizers can inspect who selected each option using
Telegram's native interface. Telegram will also deliver per-user `PollAnswer`
updates for a non-anonymous poll sent by the bot, but this feature does not need
to register a poll-answer handler, process those updates, or persist voter
identities or selections.

This is a separate feature with a deliberately different privacy model from
custom score polls. Existing statements that ballots are private apply only to
`/scorepoll`; they must not be presented as a guarantee for `/poll_dates`. Make
that distinction explicit in `/help`, `README.md`, `docs/DESIGN.md`, and
`docs/SECURITY.md`. Anonymous date polls can be considered later as an explicit
command flag if there is demand.

## Input contract and validation

Accept exactly two dates in the English `D Mon YYYY` format plus an optional
`--exclude-weekends` flag. Month abbreviations are case-insensitive. Allow the
flag before, between, or after the dates for consistency with `/scorepoll`
flags, but document it at the end.

Parse months with an explicit, normalized English abbreviation-to-number map
(`jan` through `dec`) rather than locale-dependent `strptime("%b")`. Construct
each parsed value with `datetime.date` so invalid calendar dates are rejected.
Format option labels explicitly from the date fields and fixed English weekday
and month abbreviations rather than relying on the process locale or
platform-specific `strftime` directives.

Validation should produce specific usage feedback for:

- missing or extra positional values
- an unknown flag or repeated `--exclude-weekends`
- invalid calendar dates or unsupported date syntax
- an end date earlier than the start date
- fewer than two dates after weekend filtering
- more than 12 dates after filtering

Generate the inclusive range with `datetime.date` and `datetime.timedelta`.
Bound generation once a thirteenth retained date is found so an accidentally
huge range cannot consume time or memory merely to produce an error.

Proposed usage text:

```text
Usage: /poll_dates D Mon YYYY D Mon YYYY [--exclude-weekends]
Example: /poll_dates 5 Sep 2026 18 Sep 2026 --exclude-weekends
```

## Implementation steps

1. Add the pure request parser and date-option generator in
   `src/voting_bot/handlers/commands.py`, following the existing
   `ScorePollRequest`/parse-error pattern. Keep Telegram I/O out of these helper
   functions so their validation can be unit tested directly.

2. Add an async `poll_dates` command handler. Restrict it to group and
   supergroup chats, matching `/scorepoll`; parse the command message, generate
   the options, and return actionable usage errors without calling Telegram on
   invalid input.

3. On valid input, send one native regular poll with
   `message.reply_poll(..., allows_multiple_answers=True, is_anonymous=False,
   do_quote=False)`. In the project's locked `python-telegram-bot` version, this
   shortcut automatically preserves the originating forum topic; `do_quote=False`
   avoids visually quoting the command message. Keep options in chronological
   order. Do not add database, repository, callback, or migration work.

4. Register the handler in `src/voting_bot/main.py` with a filter excluding
   edited messages, for example `CommandHandler("poll_dates", poll_dates,
   filters=~filters.UpdateType.EDITED_MESSAGE)`, and add the new usage and
   visible-voter warning to `/help`. Keep `/start`, `/scorepoll`, and
   `/closepoll` semantics unchanged.

5. Catch only `telegram.error.TelegramError` around the poll send, log the
   exception, and make a best-effort reply that the bot could not create the
   poll and that the user can try again or check the bot's permission to send
   polls. If that fallback reply also raises `TelegramError`, log it without
   masking the original failure. Do not catch Python programming errors or claim
   that every Telegram error is a permission problem.

6. Run the existing checks through the project toolchain:

   ```text
   uv run ruff check
   uv run ty check
   uv run pytest
   ```

7. After the code change, follow the repository's approval checkpoint: report
   the recommended tests and documentation updates below and ask for approval
   before modifying those files. Treat the feature as implemented but not
   complete or ready to deploy until the approved tests and documentation are
   applied and all checks pass.

## Recommended tests (approval required after implementation)

Extend `tests/test_handlers.py` with focused cases for:

- parsing the documented command and an `@botname` command form
- parsing mixed-case English month abbreviations without locale dependence
- accepting the flag in supported positions and rejecting duplicates
- inclusive date generation across a month or year boundary
- leap-day validation
- chronological, weekday-prefixed option formatting
- Saturday/Sunday exclusion
- reversed ranges, malformed dates, unknown flags, and extra tokens
- exactly 2 and exactly 12 generated options succeeding
- fewer than 2 and more than 12 generated options failing
- stopping generation after the upper limit for very large ranges
- the handler sending a non-anonymous multiple-answer native poll with the
  expected question/options, preserving the message thread, and not quoting the
  command
- group-only behavior, ignoring edited commands, handler registration, and a
  mocked Telegram poll-permission failure
- `/help` identifying native date-poll selections as visible while retaining
  the private score-poll distinction

No database-backed tests or migrations are needed because Telegram owns native
poll state.

## Recommended documentation updates (approval required after implementation)

- `README.md`: add native date polls to the feature list, show both command
  examples, and scope existing ballot-privacy claims to score polls.
- `docs/DESIGN.md`: document the date format, inclusive range, weekend behavior,
  visible-voter behavior, and 12-option limit.
- `docs/SECURITY.md`: distinguish the private custom score-poll model from the
  intentionally attributable native date-poll model.
- `docs/ARCHITECTURE.md`: add the direct command-to-native-poll request flow and
  clarify that it bypasses PostgreSQL.
- `docs/TESTING.md`: list the date parsing/generation and handler test coverage.
- `docs/STRUCTURE.md`: reflect any final file responsibility changes and mark the
  feature's implementation status.

The BotFather command menu is operational configuration rather than repository
code. After deployment, add `poll_dates` with a short description through
BotFather (or a future startup-time `set_my_commands` configuration) so users
can discover it.

## Acceptance criteria

- The documented `/poll_dates` command creates one Telegram-native poll in a
  group or supergroup.
- Every retained date in the inclusive range appears exactly once and in order.
- Participants can select multiple dates and see who selected each option using
  Telegram's native non-anonymous poll interface.
- The bot does not process or persist the resulting per-user poll-answer updates.
- `--exclude-weekends` removes only Saturdays and Sundays.
- Invalid input receives a clear correction and does not create a poll.
- The handler never attempts to create a native poll with fewer than 2 or more
  than 12 options.
- Native date polls require no new schema, do not affect custom active-poll
  limits, and do not change `/closepoll` behavior.
- Editing a `/poll_dates` command does not create an additional poll.
- Native date polls are not rate-limited in the trusted-group MVP; this decision
  is documented for reconsideration before broader availability.
- Existing lint, type checks, and tests continue to pass.

## Possible follow-ups, deliberately out of scope

- a custom poll question flag
- an explicit anonymous-poll flag
- reply-based closing of a bot-created native poll
- automatic close dates or durations
- public-holiday calendars and locale-specific date input/output
- splitting ranges into multiple polls

These additions should be driven by observed use rather than included in the
first implementation.

## References

- [Telegram Bot Features: command naming](https://core.telegram.org/bots/features#commands)
- [Telegram Bot API: `sendPoll`](https://core.telegram.org/bots/api#sendpoll)
- [`python-telegram-bot` 22.7: `Bot.send_poll`](https://docs.python-telegram-bot.org/en/v22.7/telegram.bot.html#telegram.Bot.send_poll)
