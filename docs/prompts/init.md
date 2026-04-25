# Telegram Score Voting Bot

A Telegram bot for running richer voting methods in group chats, starting with **score voting**.

Telegram already has a built-in poll feature, but it does not support score voting or more advanced social-choice methods. This project aims to provide a bot-driven alternative where users can vote from within the group chat while individual ballots remain hidden from other chat members.

The initial implementation will use:

- Python
- `python-telegram-bot`
- PostgreSQL
- Podman
- Long polling for Telegram updates
- A Hetzner VM or similar Linux VPS for hosting

The first milestone is a working score voting bot. Other voting systems can be added later once the core poll, ballot, and result infrastructure is stable.

---

## Goals

### Initial goal

Build a Telegram bot that can run a score voting poll in a group chat.

A user should be able to create a poll such as:

```text
/scorepoll "Where should we eat?" "Sushi" "Pizza" "Thai"

The bot should post a message in the group with the poll title, options, and voting controls. Other users should be able to interact with the bot using inline buttons. Their individual votes should not be posted publicly in the group.
The public poll message should show only aggregate information, such as:
Where should we eat?

Votes cast: 12

Current results:
1. Thai — average 4.1
2. Sushi — average 3.8
3. Pizza — average 3.2

Longer-term goal
Show individual votes if poll creator enables it
Support multiple voting systems using a shared poll and ballot infrastructure.
Possible future systems:
Score voting
Approval voting
Ranked-choice voting
STAR voting
Condorcet methods
Majority judgment
Quadratic voting
Simple plurality polls
The codebase should avoid hard-coding assumptions that make future voting methods difficult to add.

Non-goals for the first version
The first version should stay intentionally small.
Not included in the MVP:
Web dashboard
Public HTTP API
Webhooks
Let’s Encrypt / TLS setup
User accounts outside Telegram
Cryptographic ballot anonymity
Multi-language support
Complex poll scheduling
Advanced admin permissions
Full audit or export system
These may be added later, but they are not required for the first working bot.

Privacy model
The bot should hide individual votes from other Telegram group members.
This means:
Voting should happen through inline button interactions.
The bot should not post messages like “Alice voted 4 for Sushi.”
The public group message should show only aggregate results.
The number of voters may be shown publicly.
However, this is not cryptographic anonymity.
The bot server necessarily receives Telegram user information when a user interacts with the bot. Telegram itself also knows that the interaction occurred. The intended privacy level is:
Other group members should not be able to see how an individual person voted.
To reduce unnecessary data retention, the bot should store hashed Telegram user IDs rather than raw Telegram user IDs where practical.
Suggested approach:
stored_voter_id = HMAC_SHA256(secret_key, telegram_user_id)

Using HMAC rather than a plain hash is important because Telegram user IDs are relatively small and guessable. A plain SHA-256 hash of a user ID could be brute-forced. An HMAC with a server-side secret makes this much harder.
The HMAC secret should be configured through an environment variable and should not be committed to the repository.
Example environment variable:
VOTER_HASH_SECRET=replace-this-with-a-long-random-secret


User experience
Poll creation
A group member creates a score poll:
/scorepoll "Where should we eat?" "Sushi" "Pizza" "Thai"

The bot posts a poll message in the group.
Voting
The preferred voting interaction is a compact inline menu rather than a very large grid of buttons.
A simple version could look like this:
Where should we eat?

Options:
1. Sushi
2. Pizza
3. Thai

Votes cast: 0

[Vote]
[View results]

When a user taps Vote, the bot walks them through the ballot using inline buttons.
Example flow:
Score Sushi:
[0] [1] [2] [3] [4] [5]

After the user picks a score:
Score Pizza:
[0] [1] [2] [3] [4] [5]

Then:
Score Thai:
[0] [1] [2] [3] [4] [5]

Finally:
Your ballot has been recorded.

Sushi: 4
Pizza: 2
Thai: 5

[Edit ballot]
[Done]

The group message should be updated with aggregate results, not individual ballots.
Editing a ballot
Users should be able to change their ballot while the poll is open.
The database should treat a new score from the same voter for the same option as an update, not a duplicate vote.
Closing a poll
The poll creator, or possibly a group admin, should be able to close the poll:
/closepoll

Once closed:
New votes should be rejected.
Existing ballots should no longer be editable.
Final results should be shown in the group message.

Score voting rules
For the MVP, score voting should use a fixed integer scale.
Default scale:
0 to 5

Each voter may give each option a score from 0 to 5.
The winner is the option with the highest average score.
Example:
Option A:
scores = [5, 4, 3]
average = 4.0

Option B:
scores = [5, 5, 1]
average = 3.67

Option A wins.
Open design questions:
Should voters be required to score every option?
Should unrated options count as 0, or should they be excluded from the average?
Should the poll creator be able to choose the score range?
Should results be visible while the poll is open, or only after closing?
For the first implementation, a reasonable default is:
Voters are encouraged to score every option.
A ballot is only complete once every option has a score.
Only complete ballots count.
Results are visible while the poll is open.
Score range is fixed at 0–5.
These defaults can be revisited later.

Technical architecture
The initial deployment should be simple:
Telegram
   |
   | long polling
   v
Python bot container
   |
   v
PostgreSQL container

There is no need for a public web server or HTTPS certificate for the initial long-polling version.
Components
Bot application
Responsible for:
Receiving Telegram updates
Handling commands
Rendering poll messages
Handling inline button callbacks
Validating poll state
Recording ballots
Updating aggregate results
PostgreSQL database
Responsible for storing:
Polls
Poll options
Hashed voter identifiers
Ballots
Poll state
Telegram message references
Podman
Used to run the application and database containers.
The local development setup should eventually support:
podman compose up

or an equivalent Podman workflow.

Proposed database model
This is an initial sketch and may change.
polls
Stores top-level poll data.
CREATE TABLE polls (
    id UUID PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT,
    created_by_hash TEXT NOT NULL,
    title TEXT NOT NULL,
    voting_method TEXT NOT NULL,
    status TEXT NOT NULL,
    score_min INTEGER,
    score_max INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);

Possible values:
voting_method = 'score'
status = 'open' | 'closed'

poll_options
Stores options for each poll.
CREATE TABLE poll_options (
    id UUID PRIMARY KEY,
    poll_id UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    display_order INTEGER NOT NULL
);

ballots
Stores scores.
CREATE TABLE ballots (
    poll_id UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    voter_hash TEXT NOT NULL,
    option_id UUID NOT NULL REFERENCES poll_options(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (poll_id, voter_hash, option_id)
);

This primary key allows a user to update their score for an option without creating duplicate votes.
poll_sessions
Optional table for managing compact voting flows.
CREATE TABLE poll_sessions (
    poll_id UUID NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    voter_hash TEXT NOT NULL,
    current_option_id UUID REFERENCES poll_options(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (poll_id, voter_hash)
);

This may be useful if the bot walks a voter through one option at a time.

Callback data design
Telegram inline buttons can include callback data. The bot receives this data when a user presses a button.
Example callback payloads:
poll:<poll_id>:vote
poll:<poll_id>:results
score:<poll_id>:<option_id>:<score>
poll:<poll_id>:close

Because callback data has size limits, use compact identifiers where needed.
Possible alternatives:
Use short database IDs instead of UUIDs in callback data.
Store temporary callback tokens in the database.
Encode callback data using a compact format.
The MVP should keep this simple unless callback data length becomes a real issue.

Suggested Python structure
One possible layout:
telegram-score-voting-bot/
├── README.md
├── pyproject.toml
├── Containerfile
├── compose.yaml
├── .env.example
├── src/
│   └── voting_bot/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── db.py
│       ├── hashing.py
│       ├── telegram_handlers.py
│       ├── rendering.py
│       ├── models.py
│       ├── repositories/
│       │   ├── polls.py
│       │   └── ballots.py
│       └── voting_methods/
│           ├── __init__.py
│           ├── base.py
│           └── score.py
└── tests/
    ├── test_score_voting.py
    ├── test_hashing.py
    └── test_rendering.py

voting_methods/base.py
Defines a common interface for voting systems.
class VotingMethod:
    name: str

    def calculate_results(self, poll, options, ballots):
        raise NotImplementedError

voting_methods/score.py
Implements score voting.
Responsibilities:
Validate score ranges
Calculate average score per option
Count complete ballots
Sort options by result
Determine winner or tie

Configuration
Configuration should come from environment variables.
Example .env.example:
TELEGRAM_BOT_TOKEN=replace-me
DATABASE_URL=postgresql://voting_bot:voting_bot@db:5432/voting_bot
VOTER_HASH_SECRET=replace-with-a-long-random-secret
SCORE_MIN=0
SCORE_MAX=5
LOG_LEVEL=INFO

Secrets should never be committed to the repository.

Local development
Target development flow:
podman compose up --build

or, if using separate commands:
podman build -t telegram-score-voting-bot .
podman run --env-file .env telegram-score-voting-bot

The PostgreSQL database should run in a separate container with a persistent volume.
Example services:
bot
db

The bot service depends on the database service.

Deployment
The initial production deployment can use a small Hetzner VM running Ubuntu.
Suggested setup:
Ubuntu VM
├── Podman
├── bot container
├── PostgreSQL container
└── persistent PostgreSQL volume

For the first version, use Telegram long polling.
Benefits:
No public HTTPS endpoint required
No Let’s Encrypt setup required
No reverse proxy required
Fewer moving parts
Later, if the project needs webhooks or a web dashboard, add:
Caddy or nginx
Let's Encrypt
Webhook endpoint
Admin dashboard or API


Security considerations
Bot token
The Telegram bot token is equivalent to control over the bot. It must be stored only in environment variables or a secret manager.
Do not commit it.
Voter identity
Store HMAC-hashed Telegram user IDs instead of raw user IDs.
Do not use plain unsalted hashes.
Database access
The PostgreSQL container should not expose its port publicly.
The database should be reachable only from the bot container or local host administration tools.
Admin permissions
The MVP can start with a simple model:
Poll creator can close the poll.
Group admins may close any poll.
Admin checks can be added after basic polling works.
Abuse prevention
Potential issues:
Very large polls
Very long option names
Spam poll creation
Repeated callback presses
Message edit rate limits
MVP mitigations:
Limit number of options.
Limit title and option length.
Allow only one active poll per chat initially, or make poll selection explicit.
Debounce or batch message edits if needed.

Testing strategy
The score voting logic should be testable without Telegram.
Important tests:
Average score calculation
Tie handling
Ballot updates
Complete vs incomplete ballot behavior
Score range validation
Result ordering
HMAC voter hashing stability
HMAC voter hashing changes when secret changes
Example test case:
Poll:
- Sushi
- Pizza

Ballots:
- Voter A: Sushi 5, Pizza 2
- Voter B: Sushi 3, Pizza 4

Results:
- Sushi average = 4.0
- Pizza average = 3.0
- Sushi wins

Telegram handler tests can be added later, but the voting method itself should be plain Python and easy to test.

Initial milestones
Milestone 1: Project skeleton
Create Python project
Add python-telegram-bot
Add PostgreSQL dependency
Add basic config loading
Add Containerfile
Add local Podman setup
Milestone 2: Basic bot
Bot starts successfully
/start works
/help works
Bot can post a test inline keyboard
Bot can receive callback query events
Milestone 3: Create score poll
/scorepoll creates a poll
Poll is stored in PostgreSQL
Poll options are stored
Bot posts a group poll message
Milestone 4: Cast and update votes
User can open compact voting menu
User can score each option
Ballot is stored using hashed voter ID
User can edit their ballot
Milestone 5: Results
Bot calculates aggregate score results
Group message updates with number of voters
Group message shows ranking by average score
Milestone 6: Close poll
Poll creator can close poll
Closed polls reject new votes
Final results are displayed

Questions
-Should incomplete ballots count?
no, only once user submits them.

-Should users be able to abstain on specific options?
for score voting, they shouldn't be able to.

-Should results be hidden until the poll closes?
no, we can show results as they come in

-Should the score range be configurable per poll?
yes, users can define 0-a positive integer

-Should only group admins be allowed to create polls?
no

-Should the bot support multiple simultaneous polls in one chat?
no

-How much ballot history should be retained after a poll closes?
we can just retain all for now

-Should raw Telegram user IDs ever be stored temporarily?
if we can avoid it, no

-Should poll creators be able to export results?
not for now, just displaying results in telegram is fine

-What should happen if the original poll message is deleted?
not sure, maybe we delete the poll?

Design principles
Keep the MVP small.
Keep voting methods separate from Telegram-specific code.
Store as little user-identifying data as possible.
Prefer long polling until webhooks are actually needed.
Make the score voting implementation easy to test.
Avoid building a web app too early.
Design the data model so other voting systems can be added later.
