Goal

  Add a group-chat voting mode where users score options by tapping inline buttons directly on the group poll message. It should preserve the current privacy model as much as
  Telegram allows: no individual votes posted publicly, only aggregate results shown.

  Proposed UX

  Command:

  /scorepoll --quick "Where should we eat?" "Sushi" "Pizza" "Thai"

  Group message while open:

  Where should we eat?

  Tap scores below. Your selections are saved privately.

  Sushi
  [0] [1] [2] [3] [4] [5]

  Pizza
  [0] [1] [2] [3] [4] [5]

  Thai
  [0] [1] [2] [3] [4] [5]

  Votes cast: 0

  On button tap:

  Saved Sushi: 4. 1/3 scored.

  That feedback is a Telegram callback notification visible only to the voter. Once they score every option, their complete ballot counts in results.

  After at least one complete ballot:

  Where should we eat?

  Votes cast: 7

  Current results:
  1. Thai - avg 4.1
  2. Sushi - avg 3.8
  3. Pizza - avg 3.2

  [Score buttons remain below]

  For editing, users just tap a different score for any option. The existing ballot score is overwritten.

  Important Limitation

  We should not try to visually mark each user’s selected buttons in the shared group message, because the inline keyboard is shared by the whole chat. If we edit the
  keyboard to show Alice’s selection, everyone sees it.

  So the quick mode should use private callback notifications for “saved” / “complete” feedback, not per-user button state.

  Implementation Plan

  1. Add poll voting mode to the data model

     Add a voting_mode column to polls, probably with values:

     dm
     quick

     Existing polls should default to dm.

     This needs an Alembic migration and a Poll model update.
  2. Parse /scorepoll --quick

     Extend parse_scorepoll_command to accept:

     --quick

     I’d avoid --no-dm for now because it describes implementation instead of user intent. --quick is clearer.

     Validation behavior:

     /scorepoll --quick --max 5 "Question" "A" "B"
     /scorepoll --max 5 --quick "Question" "A" "B"

     Both should work.
  3. Persist voting mode on poll creation

     Update polls.create_score_poll(...) to accept voting_mode.

     Default remains dm, so existing tests and behavior should remain stable unless explicitly using --quick.
  4. Add quick-mode callback payloads

     Current callback payloads are:

     v:<poll_id>
     s:<poll_id>:<option_order>:<score>
     e:<poll_id>
     d:<poll_id>

     We can reuse score callbacks for quick mode if the handler can distinguish the message context, but I’d prefer a separate prefix for clarity:

     q:<poll_id>:<option_order>:<score>

     This keeps the current DM score flow untouched.
  5. Render quick-mode group keyboard

     Update render_group_poll(...) to branch on poll.voting_mode.

     For dm, keep current:

     [Vote]

     For quick, render one row/section per option, with score buttons.

     Need to be careful with Telegram callback size and keyboard size. Current MVP allows up to 10 options and default score range 0-5. That could mean 60 buttons, which is
     probably usable but dense. For --max 10, 110 buttons is too much for group chat UX.

     I’d add a quick-mode validation cap:

     --quick supports score ranges up to 0-5 for MVP.

     Or allow it technically but strongly recommend capping to keep the group message usable. My engineering recommendation is to enforce max 5 for quick mode first.
  6. Handle quick score callbacks

     Add callback handling for q.

     Flow:
      1. Parse poll ID, option order, score.
      2. Hash voter ID using existing hash_voter_id.
      3. Load poll and options.
      4. Reject if poll is missing or closed.
      5. Reject if poll mode is not quick.
      6. Validate option and score.
      7. Upsert the score.
      8. Count how many options this voter has scored.
      9. Answer callback with private feedback:

         Saved Pizza: 4. 2/3 scored.
         or:

         Ballot complete. Saved Pizza: 4.
     10. Refresh group aggregate results.
  7. Preserve complete-ballot semantics

     Keep the current rule: only complete ballots count.

     This is important for quick mode because users may tap only one option and stop. Their partial scores should be saved, but not included in averages until every option is
     scored.
  8. Closing behavior

     /closepoll should continue to work.

     When closed, render_group_poll(...) should remove all voting buttons, same as it currently removes the DM [Vote] button.
  9. Tests

     Add/update tests for:
      - parsing --quick
      - rejecting duplicate or malformed flags if applicable
      - creating polls with voting_mode
      - rendering quick-mode keyboard
      - parsing quick callback payloads
      - recording quick scores
      - partial quick ballots not counted
      - completed quick ballots counted
      - closed polls reject quick voting
  10. Docs

  After implementation, update:

  - README.md: mention quick group voting mode
  - docs/DESIGN.md: document DM vs quick mode UX
  - docs/ARCHITECTURE.md: update request flow
  - docs/DATABASE.md: add voting_mode
  - docs/STRUCTURE.md: required by repo instructions

  Recommendation

  Implement --quick as a separate voting mode, not as a replacement for DM voting. The DM flow is still better for larger score ranges, many options, and clear per-user
  progress. Quick mode is best for small polls where convenience matters more than detailed ballot review.