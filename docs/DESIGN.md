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

## Date Availability Polls

A group member can create a Telegram-native date poll from an inclusive range:

```
/poll_dates 5 Sep 2026 12 Sep 2026
/poll_dates 5/9/26 18/9/26 --days 'mon,tues,fri'
/poll_dates 5/9/26 18/9/26 --days 'fri,sat,sun'
```

Dates use either the English `D Mon YYYY` format or the numeric `D/M/YY`
format, with both dates in a command using the same format. Month abbreviations
are case-insensitive. Numeric days and months may have one or two digits;
numeric years map to 2000 through 2099 (`00` means 2000 and `99` means 2099).
Without `--days`, every date in the range is included. `--days LIST` selects
weekdays using one comma-separated argument. Names are case-insensitive:
`mon,tue,wed,thu,fri,sat,sun`, full English names, and `tues`, `thur`, `thurs`.
Single or double quotes are required when the list contains spaces; whitespace
around each name is stripped. Unicode whitespace, including nonbreaking spaces,
is supported between command arguments and inside quoted lists. Duplicate names
and aliases collapse into one selection; list order does not change date order.
One selected weekday is allowed when at least two dates remain.

`--days` may appear before, between, or after the dates; examples use trailing
flags. Repeating `--days`, missing or empty lists, empty comma-separated items,
unknown names, malformed quotes, unknown flags, and extra arguments return usage
feedback without creating a poll. `--days=...`, numeric weekdays, day ranges,
and special names such as `weekdays` are unsupported. Public holidays are not
removed.

The resulting regular poll asks `Which dates work? Select all that apply.` and
lists dates chronologically with weekday-prefixed labels such as
`Mon, 7 Sep 2026`. Multiple selections are allowed. Voting is non-anonymous, so
participants can see who selected each option through Telegram's interface.

Telegram-native polls support at most 12 options. A range that produces fewer
than 2 or more than 12 dates after filtering is rejected with guidance to adjust
the range or the selected days. Generation stops at the thirteenth retained date.
Date polls are independent of score polls: they do not consume the
one-active-score-poll slot, and `/closepoll` does not close them.

## Group Poll Message

```
Where should we eat?

Scores determine both results. Higher scores express pairwise preference; equal scores mean no preference.

Options:
1. Sushi
2. Pizza
3. Thai

Votes cast: 0
No complete ballots yet.

[Vote]
```

Every open group message, including initial creation, hidden results, and quick
mode, explains: “Scores determine both results. Higher scores express pairwise
preference; equal scores mean no preference.” This explanation appears above the
option list or results. The message is updated in-place as scores change.
Individual ballots are not posted.

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

Scores determine both results. Higher scores express pairwise preference; equal scores mean no preference.

Options:
1. Sushi
2. Pizza
3. Thai

Votes cast: 0
No complete ballots yet.

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

Scores determine both results. Higher scores express pairwise preference; equal scores mean no preference.

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

Scores determine both results. Higher scores express pairwise preference; equal scores mean no preference.

Votes cast: 7

Current results:
1. Thai — avg 4.1
2. Sushi — avg 3.8
3. Pizza — avg 3.2
Provisional results; scores can still change.

Score winner: Thai
Condorcet winner (from scores): Sushi

[Vote]
```

Only **complete ballots** (every option scored) count toward either result.
The example shows that highest average and head-to-head winner can differ; the
bot announces both without choosing between them. Live summaries are provisional.
Both summaries and averages are hidden for open hidden-results polls.

After closing:

```
Where should we eat? [CLOSED]

Final results (7 votes):
1. Thai — avg 4.1
2. Sushi — avg 3.8
3. Pizza — avg 3.2

Score winner: Thai
Condorcet winner (from scores): Sushi
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
- Score winners are all options tied for the highest average, using dense ranks.
- A Condorcet winner strictly beats every other option in pairwise comparisons.
  Each voter contributes one preference for the higher-scored option regardless
  of score difference; equal scores contribute indifference. For example, 2–1
  with 7 indifferent is a win. A tied pair is not a win.
- Pairwise ties and cycles can produce no Condorcet winner, displayed as
  `Condorcet winner (from scores): None.` followed by
  `No option beats every other option head-to-head.` There is no fallback.
- Tied score summaries use `Score winners (tied): A, B`. Duplicate labels are
  allowed; winner summaries disambiguate them with the original option number,
  such as `2. Pizza`, rather than their result rank.
- Zero complete ballots produce no winner summaries: “No complete ballots yet”
  while open, or “No complete ballots were cast” after closing.
- The final missing score completes a ballot automatically. Done clears the DM
  session. Edits to complete ballots immediately affect both live analyses.
- Results are hidden while the poll is open unless the creator uses `--live-results`.
- Only complete ballots are included in averages.
