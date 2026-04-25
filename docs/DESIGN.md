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

The bot posts a poll message in the group.

## Group Poll Message

```
Where should we eat?

Options:
1. Sushi
2. Pizza
3. Thai

Votes cast: 0

[Vote]  [View results]
```

The message is updated in-place as ballots come in. Individual votes are never shown.

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

## Results Display

While the poll is open, the group message shows live aggregate results:

```
Where should we eat?

Votes cast: 7

Current results:
1. Thai — avg 4.1
2. Sushi — avg 3.8
3. Pizza — avg 3.2

[Vote]  [View results]
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
- Results are visible while the poll is open.
- Only complete ballots are included in averages.
