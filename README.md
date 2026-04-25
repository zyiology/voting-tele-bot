# Telegram Score Voting Bot

A Telegram bot for running score voting polls in group chats. Telegram's native polls do not support score voting or other advanced social-choice methods. This bot fills that gap: poll creation happens via a slash command, voting happens through inline buttons in a private DM flow, and only aggregate results are shown in the group.

## MVP Features

- Create a score voting poll in a group chat with `/scorepoll`
- Configurable integer score range (e.g. 0–5, 0–10)
- Guided per-option ballot via inline buttons in a private message
- Ballots are private — no individual votes posted to the group
- Voter identities stored as HMAC-hashed IDs, never raw
- Live aggregate results visible in the group message as votes come in
- Ballot editing while the poll is open
- Close a poll with `/closepoll` (creator or group admin only)
- One active poll per group chat at a time

## Out of Scope for MVP

See [`.todo`](.todo) for future work.
