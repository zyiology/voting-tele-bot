# Report score and Condorcet winners from score ballots

## Status and confirmed direction

Proposed implementation plan, 21 October 2026. Implementation awaits user review;
this planning task makes no application, database, or test changes.

The user chose to reuse existing scores to calculate both results and announce
each type of winner. Users decide how to use that information. There is no
combined winner, preferred method, automatic runoff, or fallback when a Condorcet
winner does not exist.

This replaces the [tentatively abandoned ranked-ballot plan](add-condorcet-voting-plan.md).
Its separate command, ranked storage, draft/submission system, migration, and
method-dispatch expansion are not prerequisites for this approach.

## Feasibility and scope

This is a small extension of the existing score tally and rendering path.
`BallotScore` already records each voter's score for each option. Scores induce
pairwise preferences, including indifference when scores are equal. No new
dependency, environment variable, migration, or Telegram voting interface is
needed.

Apply both analyses to every `/scorepoll`, including DM and `--quick` modes.
Keep the stored method `score`: this remains a score ballot with two result
summaries, rather than a new ballot system. Existing stored score ballots can
be analyzed without conversion. Existing closed Telegram posts are not rewritten
automatically; any future re-render can compute both results from their ballots.

`/poll_dates` remains independent, with Telegram-managed date availability and no
score or Condorcet analysis. The one-open-custom-poll rule and `/closepoll`
permissions stay as they are.

The limitation is that a coarse score scale may hide preferences behind equal
scores. Do not invent an ordering within ties. This approach intentionally uses
the preferences participants expressed through their scores.

## Exact counting rules

### One electorate for both results

Use only voters with a saved score for every poll option, matching
`tally_score_poll` today. Incomplete ballots contribute to neither result, even
if they contain scores for a particular pair. Do not treat missing scores as zero.

Preserve current filtering of rows from other polls or for unknown options.
Group by HMAC voter hash and option UUID. The database primary key guarantees
one saved score per voter/option; retain existing last-row-wins normalization for
duplicate input rows rather than changing score semantics during this feature.

Both analyses must use the same normalized complete ballots from the same input
snapshot, and report the same completed-ballot count.

### Score result

Preserve existing averages, dense ranking, and all tied highest-average winners
from `ScorePollResult.winners`. Explicitly announce the score winner or winners;
the current renderer lists ranked averages but does not name winners separately.
With no complete ballots, there is no score winner.

### Condorcet result derived from scores

For each unordered pair A and B and each complete ballot:

- `score(A) > score(B)`: add one to A-over-B.
- `score(A) < score(B)`: add one to B-over-A.
- Equal scores: add one to the indifferent count; neither side receives a vote.

A defeats B precisely when A-over-B is greater than B-over-A. This is a majority
among voters expressing a preference for that pair, not necessarily a majority
of all voters. For example, 2 prefer A, 1 prefers B, and 7 are indifferent: A
defeats B, 2–1, with 7 indifferent. Score differences do not weight pairwise votes:
a difference of 1 and a difference of 5 each contribute one preference.

A Condorcet winner must strictly defeat every other option. A tied comparison,
including 0–0 when everyone is indifferent, is not a win. At most one option can
satisfy this rule for a valid poll of at least two options.

Represent three outcomes explicitly:

- `no_ballots`: no complete ballots; do not choose either type of winner.
- `winner`: exactly one option defeats every opponent.
- `no_winner`: complete ballots exist, but no option defeats every opponent.

Do not call all no-winner outcomes cycles: pairwise ties also cause them. Do not
substitute the score winner, average rank, pairwise win count, or option order.

### Edits and completion

Retain current score semantics: the last missing score makes a ballot count
automatically; DM Done clears the session and is not a submission step. Editing
one score on an already complete ballot immediately affects both results.
There is no new draft or atomic whole-ballot replacement workflow.

Users should understand that while they edit several scores, interim complete
ballots can affect live results. Both analyses nevertheless use the same saved
snapshot. Transactional changes to the existing close-versus-score-write race
are separate work; this feature must not claim to resolve that existing issue.

## User-facing results

Continue showing ranked score averages and add separately labeled outcomes:

```text
Votes cast: 3

Final results (3 votes):
1. B - avg 2.3
2. A - avg 2.0

Score winner: B
Condorcet winner (from scores): A
```

This example comes from two ballots `A=3, B=2` and one `A=0, B=3`:
B wins on average, while A defeats B 2–1. Display both without resolving their
disagreement. When they coincide, still show both labels so the agreement is
explicit.

For a score tie, use `Score winners (tied): A, B` and include every tied option.
For no Condorcet winner, use:

```text
Condorcet winner (from scores): None.
No option beats every other option head-to-head.
```

For zero complete ballots, show the options, `Votes cast: 0`, and “No complete
ballots yet” while open or “No complete ballots were cast” when closed. Do not
present this as a cycle or tie between winners.

Apply the existing visibility rule to both results: an open hidden-results poll
reveals neither winner, averages, nor pairwise information. Live results are
clearly provisional, and closing reveals both final summaries. Continue removing
voting controls on close.

Briefly explain the rule in poll instructions/help: “Scores determine both
results. Higher scores express pairwise preference; equal scores mean no
preference.” Participants should know this before voting, including in quick
mode. Full pairwise tables and detail buttons are unnecessary for the first
version; retain pairwise counts in the result model for verification and future
explanations.

Reuse option identity and display order for stable presentation, never as a
tie-breaker. Bound text at the existing ten-option and label/title limits;
test the all-score-winners case, Unicode, and long labels. Avoid adding a matrix
that unnecessarily expands the group message.

## Implementation design

### Shared ballot normalization

Extract the existing grouping/filtering/completeness logic from `score.py` into
a pure internal helper, proposed `voting_methods/ballots.py`. Have it return
complete score maps keyed by option UUID. No Telegram or SQL dependencies.

Keep the public `tally_score_poll` signature and behavior compatible. Factor its
arithmetic into an internal function accepting normalized ballots. Add an
orchestrator, proposed `tally_score_poll_results`, that normalizes once and
passes the same ballots to score and Condorcet calculations. Return a typed
combined result containing the existing `ScorePollResult` and a separate
`CondorcetPollResult`.

This avoids two subtly different completion rules and avoids querying the
database twice. No generalized plugin registry or conversion to the unused
`VotingMethod` abstract base class is needed.

### Domain types and pure pairwise tally

In `models.py`, add immutable result types for:

- Pairwise comparison: both option UUIDs, each directional preference count,
  and indifferent count.
- Condorcet result: poll ID, complete-ballot count, explicit outcome, optional
  winner option UUID, and deterministic pairwise comparisons.
- Combined score-poll analysis: score result plus Condorcet result, with no
  synthetic overall-winner field.

Implement the pairwise algorithm in `voting_methods/condorcet.py`. Initialize all
pairs, accumulate directional/indifferent counts, and identify an option winning
every comparison. Handle zero ballots explicitly. Invalid internal option lists
with fewer than two options must not produce a vacuous winner; reject them with
a clear validation error at the Condorcet tally boundary.

For V complete ballots and N options, computation is `O(V * N²)` and pairwise
storage is `O(N²)`, excluding input storage. At ten options there are 45 pairs per
voter. Recompute from saved ballots on refresh; no persistent matrix or cache is
needed.

### Integration points

| File | Planned change |
| --- | --- |
| `models.py` | Pairwise, Condorcet, and combined result types |
| `voting_methods/ballots.py` (new) | Shared complete-score-ballot normalization |
| `voting_methods/score.py` | Reuse normalization; preserve score results/API |
| `voting_methods/condorcet.py` (new) | Pure score-derived pairwise tally |
| `voting_methods/__init__.py` and a small orchestration module if needed | Expose combined analysis without circular imports |
| `rendering.py` | Compute combined analysis from its existing ballot input and display both outcomes under the same visibility guard |
| `handlers/commands.py` | Explain both outcomes in help/start text; preserve command syntax |

Keep `render_group_poll(poll, options, ballot_scores)` compatible. Its callers
already cover initial creation, live score changes, and close; replacing its
internal tally call reaches all three paths. `refresh_group_poll` continues to
fetch score rows once. Repositories, schema, callback payloads, score prompts,
and date-poll behavior do not need structural changes.

## Implementation sequence

1. Review this plan. The user has approved the overall direction; implementation
   details remain subject to review under `AGENTS.md`'s planning rule.
2. Extract normalization while preserving the score tally's public behavior.
   Run existing score tests to check the refactor.
3. Add result types, pure pairwise tally, and combined analysis orchestration.
4. Render both winner summaries with the existing score ranking and visibility
   rules; update in-product instructions/help to describe equal scores.
5. At the repository's post-implementation checkpoint, summarize the test and
   documentation changes below and request approval before editing those files,
   unless that scope has already been explicitly authorized. Run existing checks
   as needed. Do not mark the feature complete before approved verification.
6. Complete approved tests/documentation, run checks, and update this plan and
   `docs/STRUCTURE.md` with actual implementation and verification status.

## Proposed tests

Add `tests/test_condorcet_voting.py` and extend existing score/rendering/handler
coverage after the applicable approval checkpoint.

Algorithm examples and invariants:

- Zero complete ballots; one complete ballot with a unique top score; two options.
- All equal scores: all options tie for score winner, no Condorcet winner.
- A single voter tying two top options: neither can be a Condorcet winner.
- Majority preference with indifferent voters: 2–1–7 behaves as defined above.
- Same winner under both methods; different winners using the explicit 3-voter
  example; all tied score winners are retained.
- Cycle using ballots `(A=3,B=2,C=1)`, `(A=1,B=3,C=2)`, and
  `(A=2,B=1,C=3)`: each pair has a 2–1 majority, but no Condorcet winner.
- Tied head-to-head prevents a winner even if that option wins all other pairs.
  A cycle among losers does not invalidate a candidate beating every opponent.
- Score difference magnitude does not weight a pairwise vote. Valid negative
  scores work by ordinary comparison; configured ranges are not assumed to be 0–5.
- Every pair satisfies `A_over_B + B_over_A + indifferent == complete_count`.
- Both result counts match; reordering voters/options or relabeling options does
  not change winner identities. Display order only affects presentation.
- Incomplete ballots, foreign poll rows, unknown options, duplicate input rows,
  and final-score completion follow exactly the shared normalization contract.
- Editing a saved complete ballot changes both analyses from the same snapshot;
  score arithmetic/ranking remains identical to the pre-refactor implementation.

Rendering and integration:

- Open hidden polls expose neither winner; live polls expose both as provisional;
  closed polls expose both as final and remove voting controls.
- Zero ballots, tied score winners, differing winners, and no Condorcet winner
  have distinct clear output. Rounded average text does not determine ties.
- Long labels, maximum options, all tied winners, Unicode, and title lengths
  fit the supported message budget.
- Existing DM, quick, completion/edit, close authorization, and callback behavior
  still work through the shared renderer; help describes both analyses.
- Existing native date-poll tests remain unchanged in meaning.

No new database tests are needed solely for a derived tally with no SQL changes;
run the existing repository suite when a test database is available. Use
`uv run ruff check`, `uv run ty check`, and `uv run pytest`, and report database
skips accurately. Manually smoke-test a hidden poll and a live quick poll with
the different-winners example and the cycle example before rollout.

## Documentation, rollout, and acceptance

After approval, update README, DESIGN, ARCHITECTURE, SECURITY, TESTING, and
STRUCTURE to explain the two results, pairwise ties, complete-ballot inclusion,
and unchanged date availability. DATABASE can receive a short clarification
that both analyses derive from existing score rows; its schema does not change.
Explain that live results and small aggregates can reveal preference information;
adding a Condorcet label does not improve anonymity.

Deploy through the existing bot update process; no database migration is required
for this feature. Open score polls will show both summaries on their next eligible
refresh; hidden polls keep hiding them until close. Existing closed posts remain
as posted unless explicitly refreshed. Rollback to the previous code retains
all ballot data and simply restores the previous score-only presentation.

Acceptance requires both correctly labeled outcomes from the same complete
ballots, all tied score winners preserved, no Condorcet fallback, equal-score
indifference, consistent visibility, unchanged voting/editing semantics, and
independent native date polling. Users determine how to act on the two results.
