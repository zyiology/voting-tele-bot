# Security & Privacy

## Privacy Model

Individual ballots are hidden from other group members. Voting happens through private inline button interactions. The bot never posts "Alice voted 4 for Sushi." By default, the group message shows only a completed ballot count while the poll is open, then shows aggregate results after closing.

Poll creators can opt into live aggregate results with `/scorepoll --live-results`. This is less private for small groups or early voting because the first completed ballot is visible as an aggregate, even though the voter identity is not shown.

This is **not** cryptographic anonymity. The bot server receives Telegram user data on each interaction, and Telegram itself sees the interaction. The guarantee is: *other group members cannot see how an individual voted.*

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
- One active poll per group chat — prevents poll spam.
- Callback query handling is idempotent to tolerate repeated button presses.
- Message edits are batched/debounced if Telegram rate limits become a problem.
