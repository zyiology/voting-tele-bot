# Security & Privacy

## Score-Poll Privacy Model

Individual ballots are hidden from other group members. Voting happens through private inline button interactions. The bot never posts "Alice voted 4 for Sushi." By default, the group message shows only a completed ballot count while the poll is open, then shows aggregate results after closing.

Poll creators can opt into live aggregate results with `/scorepoll --live-results`. This is less private for small groups or early voting because the first completed ballot is visible as an aggregate, even though the voter identity is not shown.

Both score and score-derived Condorcet summaries follow the same visibility
setting. Small aggregates and live changes can reveal preferences, particularly
with one voter or knowledge of other ballots. The Condorcet label does not add
anonymity. Individual ballot rows and pairwise tables are not posted.

This is **not** cryptographic anonymity. The bot server receives Telegram user data on each interaction, and Telegram itself sees the interaction. The bot does not directly publish individual ballots, but aggregate results can still allow inferences about them.

## Native Date-Poll Privacy Model

`/poll_dates` deliberately creates a non-anonymous Telegram-native poll.
Participants and organizers can inspect who selected each date through
Telegram's interface. Telegram sends the bot per-user poll-answer updates for
these polls, but the bot does not handle or persist those updates.

The private-ballot guarantee above applies only to custom `/scorepoll` ballots;
it does not apply to date-poll selections.

## Voter Identity Hashing

Raw Telegram user IDs are never stored. Every voter is identified by an HMAC:

```
stored_voter_id = HMAC_SHA256(VOTER_HASH_SECRET, str(telegram_user_id))
```

Plain SHA-256 is insufficient — Telegram user IDs are small integers and can be brute-forced. HMAC with a server-side secret makes reversal computationally infeasible.

- `VOTER_HASH_SECRET` is loaded from an environment variable.
- It must never be committed to the repository.
- Changing the secret invalidates all existing voter hashes (users could vote again as if new).

## Bot Token

The Telegram bot token grants full control of the bot. Store it only in environment variables or a secret manager. Never commit it.

## Database Access

The PostgreSQL container must not expose its port publicly. It should be reachable only from the bot container (via the internal Podman network) and local admin tooling.

## Admin Permissions (MVP)

- Poll creator can close their own poll.
- Group admins can close any poll in their chat.
- No other privileged operations are defined for the MVP.

## Abuse Mitigations (MVP)

- Maximum number of options per poll (e.g. 10).
- Maximum length for poll title and option labels.
- One active score poll per group chat — prevents score-poll spam.
- Callback query handling is idempotent to tolerate repeated button presses.
- Message edits are batched/debounced if Telegram rate limits become a problem.
- Date polls are limited to 12 generated options and edited `/poll_dates`
  commands are ignored to prevent accidental duplicates.

Native date polls have no database-backed active-poll constraint, rate limit,
or admin-only creation policy. This is acceptable for the trusted-group MVP and
must be reconsidered before broader bot availability.
