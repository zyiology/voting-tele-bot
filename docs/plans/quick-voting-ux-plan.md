# Quick Voting (`--quick`) UX Improvements Plan

## Status

Proposed behaviour plan, 22 October 2026. Scheduled after
`docs/plans/condorcet-from-scores-plan.md`; implementation details will be
fleshed out once the Condorcet changes are complete.

## Planned Behaviour Changes

### 1. Private Ballot Review via `[My ballot]` Button

Instead of relying solely on transient callback toasts or Telegram Bot API 10.2
ephemeral messages (which are non-persistent across restarts/devices, clutter
the chat stream, and are unsupported in `python-telegram-bot` 22.7), add a
`[My ballot]` button at the bottom of open `--quick` poll keyboards.

- Tapping `[My ballot]` triggers a private persistent modal alert
  (`answerCallbackQuery` with `show_alert=True`) visible only to the voter.
- If the voter has not scored any options yet, the alert tells them no scores
  are recorded yet and prompts them to score each option.
- Otherwise, the alert lists each option with the voter's recorded score (or
  `not scored`) and indicates whether their ballot is complete or still needs
  remaining options scored to count.

### 2. Concise Voting Instructions in the Group Poll Message

When a `--quick` poll is open, the group message text will include a brief
instruction block explaining:

- Tap one score per option row below.
- Every option must be scored for a ballot to count.
- Votes are private, and tapping another number on any row updates that option's
  score.

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
