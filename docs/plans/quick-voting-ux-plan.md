# Quick Voting (`--quick`) UX Improvements Plan

## Status

Reviewed against the current implementation on 23 October 2026. The prerequisite
Condorcet changes are implemented. The user accepted a numbered private ballot
summary on 23 October 2026. All five points now have implementation details below,
pending user review before code changes. No application code or tests have been
changed as part of this review.

## Planned Behaviour Changes

### 1. Private Ballot Review via `[My ballot]` Button

Add a `[My ballot]` button in its own bottom row on open `--quick` poll keyboards.
Tapping it shows a private callback alert with each original option number and
its saved score or `not scored`, followed by completion status. Full option labels
remain in the group message's persistent `Options:` legend. Duplicate labels are
unambiguous because the summary uses original option numbers, never result ranks.

**Review finding:** Telegram's
[`answerCallbackQuery`](https://core.telegram.org/bots/api#answercallbackquery)
limits notification/alert text to 200 characters. Quick polls allow five options
with labels up to 80 characters each, so the proposed full summary cannot always
fit. `show_alert=True` selects an alert instead of a toast; it does not create a
saved chat message. Persistence belongs to the database-backed ballot, which can
be fetched again on another tap. Client presentation should be verified manually.

**Accepted presentation:** use a numbered summary without title or option labels:

```text
Your ballot (# matches Options):
#1: 4
#2: not scored
#3: 0

2/3 scored. Score every option to count.
```

Use the same structure for all states. With no scores, list every option as
`not scored` and end with `0/N scored. Score every option to count.` With a
complete ballot, end with `Ballot complete. Your vote counts.` A saved zero must
display as `0`. The fixed wording and at most five numbered rows fit the
200-character limit without truncating any ballot information.

Review is read-only and available while the quick poll is open. Closed polls
remove the button; a stale review callback receives `This poll is closed.`
instead of a summary. Every tap fetches saved scores anew, so review works without
a DM session or a previously opened private chat with the bot.

### 2. Concise Voting Instructions in the Group Poll Message

When a `--quick` poll is open, the group message text will include a brief
instruction block explaining:

- Tap one score per option row below.
- Every option must be scored for a ballot to count.
- Individual scores are not posted to the group, and tapping another number on
  any row updates that option's score. This wording avoids promising anonymity:
  small live aggregates can still reveal preferences, as described in SECURITY.

### 3. Compact `#N: 0` Prefix on Score Buttons & Persistent Option Legend

To prevent mobile button truncation and avoid `[1. Sushi: 0]` looking like a
persistent status readout:

- Keep one row of score buttons per option, but change the first button label
  from `[1. Sushi: 0]` to `[#1: 0]` (e.g. `[#1: 0] [1] [2] [3] [4] [5]`).
- Keep the numbered `Options:` list (`1. Sushi`, `2. Pizza`, ...) visible in the
  message text for all open `--quick` polls — including when `--live-results` is
  enabled — so button row numbers `#1..#N` always match the option list rather
  than conflicting with rank-ordered `Current results:`.

### 4. Retain Lightweight Score-Tap Toasts

Ordinary score button taps (`[0]`–`[5]`) keep their existing lightweight toast
feedback (`Saved <Option>: <score>. X/Y scored.` / `Ballot complete. Saved ...`),
leaving full ballot inspection to the `[My ballot]` button.

### 5. Skip Redundant Group Message Edits on Partial Taps

Recording a score in `--quick` mode will only refresh the shared group poll
message when the voter's ballot is complete (`scored_count == len(options)`),
avoiding unnecessary database reads and Telegram `editMessageText` calls on
partial ballots that cannot change aggregate results.

This means every tap on an already complete ballot still reaches the refresh
path, including edits. It does not mean "refresh only on the first completion."
The voter-score read is still required for private progress feedback; the saved
work is the refresh lock, poll reload, all-voter score read, tally, and Telegram
edit attempt. Identical-score taps and complete-ballot edits in hidden-results
mode remain eligible for refresh; further deduplication is outside this change.

## Implementation details

### Rendering changes (`src/voting_bot/rendering.py`)

1. Add a single quick-voting instruction constant alongside
   `SCORE_RESULTS_EXPLANATION`. Suggested copy:

   ```text
   Tap one score per option row (# matches Options). Score every option for your ballot to count.
   Tap another number in a row to update its score. Individual scores are not posted to the group.
   Tap My ballot to review your saved scores privately.
   ```

   Include it only when the poll is open and `voting_mode == QUICK`, after the
   existing explanation of the two voting results and before `Options:`. Preserve the explanation
   about higher and equal scores in both voting modes.

2. Restructure the option-list condition in `render_group_poll` so the legend is
   emitted once, before the count/results, when any of these conditions holds:
   the poll is open and quick; there are zero complete ballots; or open results
   are hidden. Remove the duplicated `_option_lines(options)` calls in the
   existing zero-ballot and hidden-results branches. These branches continue to
   supply their current vote-count and status text.

   This preserves current DM and closed-poll layouts while adding the missing
   legend for open quick polls with live results and completed ballots. Keep
   original `display_order` numbering, independent of ranked result order. The
   `Options:` and `Current results:` headings distinguish option IDs from ranks;
   existing rank calculation and result text remain unchanged.

3. In `_group_keyboard`, change only the text of the first score button in each
   quick option row to `f"#{option.display_order + 1}: {score}"`. Use
   `score == poll.score_min`, as today, rather than hard-coding zero. Remaining
   button labels stay numeric. The first button remains a real score button;
   it records the minimum score and is not a heading or a selection indicator.

4. Keep `quick_score_callback_data`, zero-based callback option orders, score
   ranges, and row chunking unchanged. Retain the five-option/maximum-score-five
   creation limits. No private scores or selected-state markers enter the shared
   message or keyboard.

5. Add `my_ballot_callback_data(poll_id)` returning `b:<poll_id>`. Append a
   single `My ballot` button row after all quick score rows. The existing open
   status check ensures closed polls have no keyboard; DM polls retain `[Vote]`.

6. Add a pure `render_quick_ballot_review(options, voter_scores) -> str` helper
   for the numbered alert. Order rows by `display_order`, look up saved scores
   by option UUID, and count only scores belonging to those options. Use explicit
   membership checks so zero scores are retained. Return the fixed presentation
   in point 1 without reusing the DM summary's recorded-ballot heading or keyboard.

Example of the relevant layout for an open live quick poll after completion:

```text
Options:
1. Sushi
2. Pizza

Votes cast: 1

Current results:
1. Pizza - avg 5.0
2. Sushi - avg 2.0
Provisional results; scores can still change.

Score winner: Pizza
Condorcet winner (from scores): Pizza

[#1: 0] [1] [2] [3] [4] [5]
[#2: 0] [1] [2] [3] [4] [5]
[My ballot]
```

The title, existing score-results explanation, and new instructions precede this
excerpt. `#1` continues to mean Sushi even when Pizza ranks first.

### Callback changes (`src/voting_bot/handlers/callbacks.py`)

1. Keep `_record_quick_score` validation, guarded `ballots.upsert_score`, and
   subsequent `ballots.get_voter_scores` in their current order. A closure between
   the initial open check and the write must still yield the closed-poll alert
   through `PollNotOpenError`, without a success toast or refresh.
2. Derive the scored count from distinct saved option IDs belonging to this
   poll's loaded options. Define `is_complete` once as that count equalling the
   option count. A saved zero is a score; do not use truthiness of score values.
3. Keep the existing partial/completed toast wording. Answer the callback after
   saving and reading progress, before any shared-message refresh, so the user
   receives feedback without waiting for the message edit lock.
4. Call `refresh_group_poll(context, poll, options)` only if `is_complete` is
   true. Leave the DM `_record_score` path unchanged.
5. Preserve `refresh_group_poll` and its cross-instance advisory lock, current
   poll reload, and handling of Telegram's "message is not modified" response.
   Closure still refreshes unconditionally through `/closepoll`. A complete tap
   whose refresh runs after closure must render the closed state and remove the
   keyboard; skipping a partial refresh must not affect the close command.

The score-tap changes require no repository API, schema, migration, dependency,
or handler registration changes. Scores remain stored immediately on every tap;
only the shared refresh is conditional. Concurrent taps can observe newer saved
progress and cause extra eligible refreshes; existing serialization preserves
the final state. Do not add in-memory completion tracking or new background jobs.

### Private review callback (`src/voting_bot/handlers/callbacks.py`)

1. Extend `parse_callback_data` to accept kind `b` with exactly two fields and a
   valid poll UUID, like the existing non-score actions. Retain strict rejection
   of extra fields and malformed payloads. `b:<UUID>` fits the 64-byte callback
   limit. The existing unrestricted `CallbackQueryHandler` needs no change.
2. Dispatch `b` to a read-only `_show_quick_ballot` handler using the voter hash
   already derived from the callback's actual Telegram user. Never accept voter
   identity from the payload or read another voter's scores.
3. Load the poll and options with `polls.get_poll_with_options`. Answer missing
   polls with `This poll no longer exists.`, closed polls with `This poll is
   closed.`, non-quick polls with `This button is no longer valid.`, and empty
   option lists with `This poll has no options.` All use `show_alert=True` and
   return without further work.
4. Read only that voter's scores with `ballots.get_voter_scores`, render the
   numbered summary, and answer once with `show_alert=True, cache_time=0`.
   Reuse existing repository functions; no aggregate reads, session writes,
   score writes, DM sends, or shared-message edits are needed.
5. The alert reflects scores read during that request; a concurrent score tap
   appears on the next review. If closure occurs after the open check, the
   read-only request may finish with its summary. It cannot reopen voting or
   overwrite the closed message. No new lock is required for this snapshot.

## Proposed verification after implementation

These are recommended test changes for review, not changes made during planning.
Follow AGENTS.md's approval rule before editing tests during implementation.

- In `tests/test_rendering.py`, cover open quick polls across hidden/live results
  and zero, partial, and complete ballots. Check instructions and exactly one
  original-order option legend; use a case where result order differs from option
  order. Confirm privacy/visibility rules and both winner summaries still hold.
- Check compact button labels, unchanged callback payloads, minimum-score button
  behavior, supported smaller score ranges, and five-option/six-score layouts.
  Include duplicate and long Unicode labels; the legend retains full labels.
- Extend message-budget coverage to the maximum quick title/labels, the new
  instructions, repeated labels, and tied winner summaries. Check against
  Telegram's 4096-character message limit, including UTF-16 accounting for
  supplementary characters as in the existing budget tests.
- Verify the review button is the sole button in the bottom row for open quick
  polls, absent in DM and closed polls, and uses the expected `b:<UUID>` payload.
- Test review rendering for empty, partial, complete, zero-valued, duplicate-label,
  and reordered-option inputs. Check every original option number is included,
  unknown option scores do not affect completion, and no full labels enter the
  alert. Verify the maximum five-option summary in every completion state fits
  200 characters (also check UTF-16 length).
- Cover parsing and dispatch of valid/malformed review callbacks. Verify the
  actual clicking user's hash scopes the read, exactly one uncached alert is
  answered, and no write, aggregate fetch, DM send, or shared refresh occurs.
  Cover missing/closed/wrong-mode/empty-option polls and fresh reads on repeated
  review taps after scores change.
- In `tests/test_handlers.py`, cover first and repeated partial taps: the write
  and private progress answer occur, but shared refresh does not. Cover final
  missing score, zero-valued completion, complete-ballot edits, and identical
  complete taps: refresh remains eligible and the completed toast is preserved.
- Preserve invalid option/range, wrong mode, missing/closed poll, and concurrent
  close rejection behavior. Assert callback answer precedes eligible refresh.
  Keep existing real-PostgreSQL close/write and refresh-lock regressions passing;
  no new SQL or repository tests are required for this change alone.
- Run `uv run ruff check`, `uv run ty check`, and `uv run pytest` after code and
  approved test updates. Report database test skips if no test database is set.
- Manually check Telegram mobile rendering with six buttons per row and long
  labels, minimum-score selection, partial progress, completion, complete-ballot
  editing, hidden/live results, and closure. Automated tests cannot prove mobile
  truncation is eliminated on every client.
- Manually review an empty, partial, and complete ballot from two voters. Check
  each sees only their own scores, including zero, the alert can be reopened,
  the legend is easy to match, and no private chat setup is required. Check a
  stale review button after closure shows the closed-poll alert.

## Delivery and documentation

Review this plan before application changes. Implement the rendering changes,
read-only private review callback, and partial-refresh guard together. Acceptance
requires a private numbered review within the alert limit, stable option-to-row
mapping, clear quick instructions, unchanged private toast feedback, no refresh
for an incomplete ballot, and refresh eligibility for every completed-ballot tap.

After implementation, propose updates to DESIGN's quick-flow and live-results
examples and its review-flow guidance, plus TESTING's coverage summary, and obtain
approval before editing them. Update STRUCTURE's implementation progress as
required. Include the numbered review and its unsaved-alert behavior in DESIGN;
add the `b:<poll_id>` format to DATABASE's callback reference after approval.
Avoid unrelated documentation changes.

New polls receive the layout immediately. Existing open polls receive it on their
next eligible refresh; a partial tap will no longer trigger that refresh. No
automatic backfill of existing messages is proposed. Closing always refreshes.
Rolling back restores the previous presentation and refresh behavior without
converting or losing saved ballots.
