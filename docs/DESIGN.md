# UI/UX Design

## Poll Creation

A group member creates a poll:

```
/scorepoll "Where should we eat?" "Sushi" "Pizza" "Thai"
```

Optional score range flag (defaults to 0–5):

```
/scorepoll --max 10 "Best framework?" "Django" "FastAPI" "Flask"
```

Quick group voting mode:

```
/scorepoll --quick "Where should we eat?" "Sushi" "Pizza" "Thai"
```

Quick mode supports up to 5 options and scores up to 5. Use the default DM flow for larger polls or wider score ranges.

Live results opt-in:

```
/scorepoll --live-results "Where should we eat?" "Sushi" "Pizza" "Thai"
```

Without `--live-results`, the group message shows the number of completed ballots while the poll is open, but hides option-level aggregates until the poll closes.

The bot posts a poll message in the group.

## Group Poll Message

```
Where should we eat?

Options:
1. Sushi
2. Pizza
3. Thai

Votes cast: 0

[Vote]
```

The message is updated in-place as complete ballots come in. Individual votes are never shown.

## Voting Flow (private DM)

When a user taps `[Vote]`, the bot sends them a private message and walks through each option:

```
Score Sushi (0–5):
[0] [1] [2] [3] [4] [5]
```

After each selection, the next option appears automatically. On completion:

```
Your ballot has been recorded.

Sushi: 4 | Pizza: 2 | Thai: 5

[Edit ballot]  [Done]
```

Tapping `[Edit ballot]` restarts the scoring flow with current scores pre-displayed (as text, not pre-selected buttons). Tapping `[Done]` ends the session.

If the user has already voted, `[Vote]` opens the same flow with prior scores shown.

## Voting Flow (quick group mode)

When a poll is created with `--quick`, the group message shows score buttons for every option:

```
Where should we eat?

Options:
1. Sushi
2. Pizza
3. Thai

Votes cast: 0

[1. Sushi: 0] [1] [2] [3] [4] [5]
[2. Pizza: 0] [1] [2] [3] [4] [5]
[3. Thai: 0]  [1] [2] [3] [4] [5]
```

Each tap records or updates that user's score for the option. Telegram callback notifications give private progress feedback, for example `Saved Pizza: 4. 2/3 scored.` Once every option has a score, the ballot is complete and included in the vote count and, after results are visible, aggregate results.

Quick mode does not mark selected buttons in the shared group message, because any keyboard edit would be visible to the entire group. Use DM mode when users need a private per-option review flow.

## Results Display

While the poll is open, the default group message hides option-level aggregate results:

```
Where should we eat?

Options:
1. Sushi
2. Pizza
3. Thai

Votes cast: 7

Results hidden until the poll closes.

[Vote]
```

If the creator uses `--live-results`, the open poll message shows live aggregate results:

```
Where should we eat?

Votes cast: 7

Current results:
1. Thai — avg 4.1
2. Sushi — avg 3.8
3. Pizza — avg 3.2

[Vote]
```

Only **complete ballots** (every option scored) count toward results.

After closing:

```
Where should we eat? [CLOSED]

Final results (7 votes):
1. Thai — avg 4.1
2. Sushi — avg 3.8
3. Pizza — avg 3.2
```

## Closing a Poll

```
/closepoll
```

Only the poll creator or a group admin may close the poll. After closing, the `[Vote]` button is removed and new ballot attempts are rejected with a notice.

## Score Voting Rules

- Integer scale: configurable min–max, default 0–5.
- Every option must be scored for a ballot to count.
- Abstaining on individual options is not supported.
- The winner is the option with the highest average score.
- Results are hidden while the poll is open unless the creator uses `--live-results`.
- Only complete ballots are included in averages.
