# Add Condorcet voting through ranked ballots

## Status and review decisions

**Tentatively abandoned, 21 October 2026.** The user chose to derive pairwise
preferences from existing score ballots and announce both score and Condorcet
winners. See [the replacement plan](condorcet-from-scores-plan.md).

No application code or schema changes were made for this plan. The design below
is retained for reference if a separate ranked-ballot mode becomes useful;
it is not the current implementation direction.

Confirmed by the user: if no option beats every other option head-to-head,
report **no Condorcet winner**. Do not select a fallback winner.

The remaining choices below are recommendations for review: complete strict
rankings, private-message voting, explicit submission, and one open custom
poll per chat shared between score and Condorcet polls.

## Feasibility and scope

This is feasible with the existing Python, PostgreSQL, and Telegram stack.
No new service, web interface, or voting library is needed. Tallying is small;
most work is in ballot state, safe edits, migration, and dispatch between voting
methods. Treat this as a moderate feature spanning several layers, rather than
just adding another tally function.

Score and Condorcet are two custom voting systems. `/poll_dates` remains a
separate Telegram-native availability feature: it has no custom ballot rows,
does not occupy the custom-poll slot, and is not closed by `/closepoll`.

### Findings from the current implementation

| Area | Current behavior | Required change |
| --- | --- | --- |
| `models.py` | `VotingMethodOptions` only includes score; result types describe averages | Add ranked ballot and Condorcet result types |
| `voting_methods/score.py` | Pure tally function; only complete score ballots count | Add a separate pure pairwise tally |
| `voting_methods/base.py` | Generic abstract class exists, but score uses standalone functions | Keep function-based methods; avoid an unnecessary framework rewrite |
| `repositories/polls.py` | Creation hardcodes score; lookup and closing are already general | Add method-aware creation, retaining the score entry point |
| `repositories/ballots.py` | Stores per-option scores and a current-option cursor | Add dedicated ranked storage and draft operations |
| `handlers/callbacks.py` | Vote/edit paths assume scores; refresh always loads scores | Dispatch by the stored voting method and reject mismatched actions |
| `rendering.py` | Group rendering calls score tally directly | Separate tally orchestration from method-specific presentation |
| `handlers/commands.py`, `main.py` | `/scorepoll`, generic `/closepoll`, introductory text specific to scores | Register `/condorcetpoll` and generalize relevant help |
| `0001_initial_schema.py` | Score-only method check; one open poll per chat | Add a new migration; preserve the shared uniqueness rule |

The repository records an existing deployed bot, so do not edit migration
`0001` in place. Existing score rows and open score polls must survive upgrade.

## Voting rules

A participant ranks every option exactly once, most preferred first. Equal
preferences and partial submissions are excluded from the first version.
This gives every submitted voter one preference for every pair and avoids
implicit rules for unranked candidates. An unfinished draft contributes nothing.

For options A and B, count submitted ballots placing A before B as `P[A,B]`.
A defeats B only when `P[A,B] > P[B,A]`. A Condorcet winner defeats every other
option. A tied comparison is not a victory. With at least two options there
can be at most one strict Condorcet winner. This follows the pairwise-majority
definition in [Krishnamoorthy and Raghavachari](https://arxiv.org/abs/math/0511140).

Return one of three outcomes:

- `no_ballots`: zero submitted ballots; display “No ballots submitted.”
- `winner`: a strict Condorcet winner; display its label and comparisons.
- `no_winner`: submitted ballots exist, but none beats all opponents; display
  “No Condorcet winner: no option beats every other option head-to-head.”

Do not describe every no-winner result as a cycle: pairwise ties can also
prevent a winner. Do not infer an overall ranking from average rank, first-place
votes, or pairwise win counts. Option order is presentation order only.

Examples to use as executable specifications:

- `A > B > C`, `A > C > B`, `B > A > C`: A beats B 2–1 and C 3–0; A wins.
- `A > B > C`, `B > C > A`, `C > A > B`: A beats B, B beats C, C beats A,
  each 2–1; no winner.
- `A > B` and `B > A`: 1–1 tie; no winner.

## Commands and ballot experience

```text
/condorcetpoll "Where should we eat?" "Sushi" "Pizza" "Thai"
/condorcetpoll --live-results "Where should we eat?" "Sushi" "Pizza" "Thai"
```

Use the current title and option limits: 140 characters for the title, 80 per
label, and 2–10 options. Reject blank and duplicate trimmed labels for the new
command so choices are distinguishable. Follow existing quoted-argument and
bot-addressed-command conventions. Reject unknown/repeated flags, `--max`, and
`--quick`; Condorcet MVP is DM-only. Ignore edited creation commands.

The group message identifies the method and explains that each voter ranks all
options and that a winner may not exist. It displays the submitted-ballot count.
Results are hidden until close unless `--live-results` was explicitly selected.

Recommended private flow:

1. A group Vote link opens `https://t.me/<bot_username>?start=rank_<poll_uuid_hex>`.
   Add validated private `/start` payload handling; ordinary `/start` still
   displays help. This lets first-time users start the bot and resume the target
   poll. Telegram documents this mechanism under
   [deep linking](https://core.telegram.org/bots/features#deep-linking).
2. Display “Choose your first preference” and buttons for available options.
   After selection, show the ordered prefix and ask for the next preference.
3. Offer Undo, Restart, and Cancel. Undo removes the last choice; Restart clears
   the draft; Cancel discards it. Automatically append the only remaining option
   and show the complete ranking for review.
4. Submit explicitly commits the complete ranking. Until then, even a complete
   draft is not counted. Confirm that the vote was recorded only after commit.
5. Reopening a submitted ballot displays it with an Edit button. Editing creates
   a draft; the previous submission continues to count until its replacement is
   submitted. Cancel leaves the previous submission intact. Editing can rebuild
   the ranking using Restart and Undo; drag-and-drop is unnecessary.
6. Persist drafts so users can resume after bot restarts. Prefer editing the
   current private prompt; if it is unavailable, send a fresh prompt backed by
   the same current draft. Failure to send a message must not alter a submission.

Keep score DM and quick flows compatible. A shared group keyboard cannot display
a different mutable ranking to every voter, which makes private prompts a
straightforward first implementation.

Use HMAC voter hashes as today. Resolve identity from the Telegram update, never
from callback data. Private ranking actions must originate from that user's
private chat. Deep links identify a poll, not an authorization secret. Retain the
current trusted-group participation model; this does not add a membership gate
or promise protection against forwarded poll links. Tightening eligibility is a
separate product decision.

## Data model and migration

Add `VotingMethodOptions.CONDORCET = "condorcet"`. Introduce typed models for a
submitted ranked ballot, a draft, pairwise counts, and a `CondorcetPollResult`
containing poll ID, submitted count, outcome, optional winner ID, and comparisons.
Use option UUIDs for identity, never labels. Keep score result types separate.

Create `0002_add_condorcet_voting.py` with:

- An expanded method check on `polls` and a constraint requiring DM mode for
  Condorcet. Preserve `polls_one_open_per_chat`, covering both custom methods.
- Nullable `score_min`/`score_max`; retain score defaults for compatibility, but
  explicitly insert NULL for Condorcet. Add a method-aware check: score requires
  non-NULL ordered bounds; Condorcet requires both NULL. Update `Poll` typing and
  validate/narrow bounds before score operations. Do not use dummy score limits
  to represent rank positions.
- `ranked_ballots(poll_id, voter_hash, submitted_at)` with composite primary key
  and a cascading poll FK: one current submitted ballot per voter per poll.
- `ranked_ballot_choices(poll_id, voter_hash, option_id, rank)` with primary key
  `(poll_id, voter_hash, option_id)`, unique `(poll_id, voter_hash, rank)`, positive
  rank check, cascading ballot-header FK, and composite `(poll_id, option_id)` FK
  to `poll_options`. Rank 1 means most preferred.
- `ranked_ballot_drafts(poll_id, voter_hash, revision, active, updated_at)` with
  composite primary key, cascading poll FK, and nonnegative BIGINT revision.
- `ranked_draft_choices` using the same option/rank constraints as submitted
  choices, but referencing the draft header. Draft ranks must be a contiguous
  prefix; repository validation enforces this.

Keep the score `ballots` and `poll_sessions` tables intact. Separate draft and
submitted storage prevents a half-edited vote from changing the tally. Normalized
choices preserve database-level option membership and rank uniqueness; the
repository validates complete permutations and method ownership transactionally.
SQL checks alone cannot enforce that every poll option appears in a ballot.

Retain inactive draft headers with increasing revisions after submit/cancel so
old buttons cannot become valid when a new draft starts. Clear draft choices on
submit/cancel; clear remaining draft choices and deactivate drafts on close.
Submitted ballots are retained. Poll deletion cascades through all new tables.

Upgrade should not rewrite existing score ballots. A downgrade must refuse if
Condorcet polls exist; do not silently drop voting data to restore a score-only
constraint. Test upgrade from populated `0001` and document deployment order.

## Repository operations and concurrency

Add `repositories/ranked_ballots.py` for draft start/resume, append, undo,
restart, cancel, submit, get submitted ballot, and list submitted ballots.
All SQL stays in repositories. Retain `create_score_poll` as a wrapper and share
poll/option insertion internally with a new `create_condorcet_poll` entry point.

For each ranked mutation, in one database transaction:

1. Lock the poll row first (`SELECT ... FOR UPDATE`); verify method and open
   status. Then lock/create the voter's draft header in consistent lock order.
2. Verify active draft and expected revision where applicable. Check the chosen
   option belongs to this poll and has not already been selected.
3. Apply the action and increment the revision. For Submit, require a full
   permutation with contiguous ranks `1..N`, replace all submitted choices
   atomically, update the submission timestamp, then deactivate/clear the draft.

The existing close UPDATE locks the same poll row; extend close to a transaction
that also deactivates ranked drafts. Thus a submit either commits before close
and counts, or waits and is rejected after close. Handler-only status checks
are insufficient. Poll-level serialization is acceptable for these small polls.
Do not hold database locks while calling Telegram.

Callbacks should encode action, poll UUID in hex, revision, and optional numeric
option order, e.g. `ra:<uuid_hex>:<revision>:<order>`. Use short distinct actions
for append/undo/restart/cancel/submit/edit. With at most 19 decimal revision digits
and two option-order digits, this example fits the 64-byte callback limit in the
[Telegram Bot API](https://core.telegram.org/bots/api#inlinekeyboardbutton).
Validate exact field counts, integer bounds, UUIDs, and encoded byte length.

Duplicate or stale callbacks must never append another preference or resubmit
an old ranking. Reject their revision and show/resume current state. Method
checks must also be added to legacy score callbacks so forged `s`/`q`/`e`/`d`
actions cannot operate on Condorcet polls. Preserve existing score payloads.

Refresh aggregate messages only after submit or close, not each draft selection.
Reload current poll status before rendering. Serialize refresh and close-message
updates per poll within the single bot process so a delayed live refresh cannot
overwrite the final closed message. Treat Telegram edit errors as display
failures; never undo an already committed vote. A future multi-process deployment
would need coordination beyond an in-memory refresh lock.

## Tally and rendering boundaries

Implement `validate_ranking` and `tally_condorcet_poll` in
`voting_methods/condorcet.py`, with no Telegram or database dependencies.
Reject invalid complete-ballot inputs rather than quietly treating omissions as
last place. Validate poll identity, option membership, duplicates, completeness,
and unique voter identity in the tally input. Persisted invalid ballots should
surface as integrity failures, never silently alter results.

Build a position map per ballot and increment one side of every unordered pair.
For V voters and N options this costs `O(V * N²)` time and `O(N²)` tally space,
excluding loaded input. At the current 10-option limit there are only 45 pairs
per ballot. No cached matrix is necessary; computing from current submissions
avoids invalidation problems on edits.

Dispatch loading/tallying by `poll.voting_method` in the application orchestration
used by creation, refresh, and close. Rendering receives the appropriate typed
result rather than loading ballots or assuming score fields. Use a small explicit
dispatch for two methods; retain or wrap the current score renderer as necessary
to preserve callers and existing tests.

For Condorcet rendering:

- Hidden open polls reveal only labels, rules, and submitted count; no winner,
  pairwise information, draft progress, or individual preferences.
- Live results are labeled provisional; closed results are final and remove Vote.
- Show winner/no-winner/no-ballots distinctly. Pairwise comparisons explain the
  result without claiming an overall candidate ordering.
- Use numbered option labels once and compact pair lines (`1 vs 2: 7–4`) to
  bound message size at 10 options. Verify worst-case title, labels, Unicode,
  and vote-count lengths against Telegram's message limit; paginate details
  if needed. Any details callback must enforce results visibility server-side.
- Preserve aggregate privacy language: server and Telegram see interactions;
  HMAC identities do not provide cryptographic anonymity. Live or tiny-sample
  aggregate pairwise results can reveal preferences, just as score aggregates can.

## Implementation sequence and review checkpoints

1. Review this plan, including the proposed DM-only complete-ranking contract.
   The no-fallback decision is already confirmed. Make no code changes before
   plan review, per `AGENTS.md`.
2. Add domain models, pure validation/tally, and method dispatch types. Keep
   score behavior intact; no adoption of the unused ABC is required.
3. Add the forward migration and ranked repositories, including revision checks,
   atomic replacement, and submission-versus-close locking.
4. Add `/condorcetpoll`, registration, private deep-link entry, and ranked callback
   flow. Generalize shared lifecycle code and add method guards to score paths.
5. Add result rendering, private review/confirmation, message refresh sequencing,
   and failure feedback. Check that date handlers remain independent.
6. At the post-implementation checkpoint required by `AGENTS.md`, summarize and
   request approval for the test/documentation updates below before editing those
   files, unless that scope was already explicitly authorized. Existing checks
   may be run without editing tests. The feature is not complete until the
   approved coverage and documentation are finished.
7. Run required checks and a Telegram smoke test, then update implementation
   status in this plan and `docs/STRUCTURE.md`. Report skipped checks explicitly.

## Recommended verification after implementation

Pure tally tests in `tests/test_condorcet_voting.py`:

- The three explicit examples above; zero ballots, one ballot, two options,
  unanimous rankings, ties, and a winner that is not the first displayed option.
- A candidate tied with one opponent is not a strict winner; a cycle among
  losing candidates does not invalidate a candidate that defeats all of them.
- Reject missing, duplicate, foreign, malformed, and cross-poll preferences;
  reject duplicate voters in tally input.
- Pairwise invariant `P[A,B] + P[B,A] == submitted_count`; candidate-label,
  option-display-order, and ballot-input-order permutations do not change winners.

Real PostgreSQL tests in `tests/test_repositories.py` (no database mocks):

- Apply migrations to an isolated test database, including upgrade from populated
  `0001`; preserve score polls, scores, sessions, and constraints.
- Method/mode/bounds constraints; option membership and rank uniqueness; cascade
  deletion; shared open-poll limit in both method creation orders.
- Resume after reconnect; complete draft excluded until Submit; atomic ballot
  replacement; cancel/edit preserving the prior vote; transaction rollback.
- Concurrent duplicate actions and simultaneous edits; stale revisions after
  undo/restart/cancel/reopen; concurrent submit/close in both lock orders.
- Downgrade succeeds with score-only data and refuses with Condorcet data.

Handler and rendering coverage:

- Command limits, quotes, invalid flags, duplicate labels, private-chat rejection,
  edited commands, registration, and help distinguishing all three poll features.
- First-time deep-link start, malformed payload, missing/closed poll, blocked DM,
  draft resume, all actions, explicit submission, and repeated/stale buttons.
- Wrong-method callbacks and private-user context rejection; unchanged legacy
  score callbacks; creator/admin close authorization for both custom methods.
- Hidden/live/final outputs, zero votes, no winner, winner, Unicode labels,
  callback byte limits, and worst-case message lengths.
- Telegram failure after successful commit, refresh racing with close, and stale
  messages that must not reopen voting or display a provisional final result.
- Existing score DM/quick and native date-poll regression suite remains green.

Run `uv run ruff check`, `uv run ty check`, and `uv run pytest`. Repository tests
currently skip without a reachable `DATABASE_URL`; arrange an isolated PostgreSQL
database with migrations applied and confirm these tests actually execute before
calling the feature verified. Do not point migration tests at production.

Manual Telegram smoke test: create a score poll and close it, create a Condorcet
poll, use several accounts to submit/edit/cancel, demonstrate a cycle and a winner,
restart during a draft, then close with a draft pending. Also create a date poll
while a custom poll is open and verify its independent behavior.

## Documentation and rollout

After the applicable approval checkpoint, update README, ARCHITECTURE, DESIGN,
DATABASE, SECURITY, TESTING, and STRUCTURE for the new command, ranked rules,
schema, submission semantics, privacy, shared custom-poll limit, and verification.
Keep date availability described separately. Correct touched stale score-only
wording; avoid unrelated documentation rewrites.

For deployment, back up the database, stop the old bot, apply the new migration,
then start the new code and smoke-test it. Old code cannot deserialize the new
method or safely handle nullable score bounds, so do not run it alongside new
Condorcet polls. Prefer a forward fix after data exists; do not downgrade by
deleting polls. No new environment variable or dependency is expected.

Acceptance requires correct pairwise outcomes, no fallback winner, complete
explicitly submitted ballots only, safe editing and closing, privacy visibility
enforcement, preserved score behavior/data, independent date polling, and the
approved tests/documentation completed. Partial rankings, equal ranks, alternative
Condorcet completion methods, simultaneous custom polls, and a ranking web UI
remain future work.
