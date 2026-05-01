#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import psycopg

from voting_bot.database_url import for_psycopg
from voting_bot.hashing import hash_voter_id

"""
example usage:
uv run python scripts/inspect_poll_voters.py 2dbe86a7-1a77-444f-9ab3-bfa792f679c9 \
    --database-url 'postgresql+psycopg://voting_bot:voting_bot@localhost:5432/voting_bot' \
    --voter-hash-secret 'this-is-a-long-random-secret-for-hashing-voter-ids' \
    --candidate-file tmp/user_ids.txt
"""


@dataclass(frozen=True)
class VoteRow:
    voter_hash: str
    display_order: int
    label: str
    score: int
    updated_at: object


@dataclass(frozen=True)
class Candidate:
    user_id: int
    name: str


def main() -> int:
    args = _parse_args()
    _load_dotenv(args.env_file)

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required. Set it in the environment or pass --database-url.", file=sys.stderr)
        return 2

    secret = args.voter_hash_secret or os.environ.get("VOTER_HASH_SECRET")
    if not secret:
        print(
            "VOTER_HASH_SECRET is required. Set it in the environment or pass --voter-hash-secret.",
            file=sys.stderr,
        )
        return 2

    candidates = _load_candidates(args.candidate_id, args.candidate_file)
    candidate_by_hash = {
        hash_voter_id(candidate.user_id, secret): candidate for candidate in candidates
    }
    print(f"Loaded {len(candidates)} candidate ID(s).", file=sys.stderr)

    rows = _fetch_vote_rows(database_url, args.poll_id)
    if not rows:
        print(f"No ballot rows found for poll {args.poll_id}.")
        return 0

    _print_voters(rows, candidate_by_hash)
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect voter hashes and scores for a poll. HMAC hashes cannot be reversed; "
            "provide candidate Telegram user IDs to identify known voters."
        )
    )
    parser.add_argument("poll_id", type=UUID, help="Poll UUID to inspect.")
    parser.add_argument(
        "--candidate-id",
        type=int,
        action="append",
        default=[],
        help="Telegram user ID to match. Can be provided more than once.",
    )
    parser.add_argument(
        "--candidate-file",
        type=Path,
        help=(
            "File containing one Telegram user ID per line, or CSV rows with "
            "user_id,name. Blank lines and # comments are ignored."
        ),
    )
    parser.add_argument(
        "--database-url",
        help="Postgres URL. Defaults to DATABASE_URL from the environment or .env.",
    )
    parser.add_argument(
        "--voter-hash-secret",
        help="Hash secret. Defaults to VOTER_HASH_SECRET from the environment or .env.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Environment file to read before checking env vars. Defaults to .env.",
    )
    return parser.parse_args()


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def _load_candidates(
    candidate_ids: list[int],
    candidate_file: Path | None,
) -> list[Candidate]:
    candidates = [Candidate(user_id=candidate_id, name="") for candidate_id in candidate_ids]
    if candidate_file is None:
        return candidates

    with candidate_file.open(encoding="utf-8", newline="") as file:
        for line_number, row in enumerate(csv.reader(file), start=1):
            if not row:
                continue

            user_id_text = row[0].strip()
            if not user_id_text or user_id_text.startswith("#"):
                continue

            try:
                user_id = int(user_id_text)
            except ValueError as exc:
                if line_number == 1 and user_id_text.lower() in {"id", "user_id", "telegram_user_id"}:
                    continue
                raise SystemExit(
                    f"{candidate_file}:{line_number}: expected an integer Telegram user ID in column 1"
                ) from exc

            name = row[1].strip() if len(row) > 1 else ""
            candidates.append(Candidate(user_id=user_id, name=name))

    return candidates


def _fetch_vote_rows(database_url: str, poll_id: UUID) -> list[VoteRow]:
    query = """
        SELECT
            b.voter_hash,
            o.display_order,
            o.label,
            b.score,
            b.updated_at
        FROM ballots b
        JOIN poll_options o ON o.id = b.option_id
        WHERE b.poll_id = %s
        ORDER BY b.voter_hash, o.display_order
    """
    with psycopg.connect(for_psycopg(database_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (poll_id,))
            return [
                VoteRow(
                    voter_hash=str(row[0]),
                    display_order=int(row[1]),
                    label=str(row[2]),
                    score=int(row[3]),
                    updated_at=row[4],
                )
                for row in cursor.fetchall()
            ]


def _print_voters(
    rows: list[VoteRow],
    candidate_by_hash: dict[str, Candidate],
) -> None:
    rows_by_voter: dict[str, list[VoteRow]] = defaultdict(list)
    for row in rows:
        rows_by_voter[row.voter_hash].append(row)

    matched_voter_count = sum(1 for voter_hash in rows_by_voter if voter_hash in candidate_by_hash)
    print(
        f"Matched {matched_voter_count} of {len(rows_by_voter)} voter hash(es).",
        file=sys.stderr,
    )

    print(f"Voters with any score: {len(rows_by_voter)}")
    print()

    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "voter_hash",
            "matched_telegram_user_id",
            "matched_name",
            "display_order",
            "option",
            "score",
            "updated_at",
        ]
    )
    for voter_hash, voter_rows in rows_by_voter.items():
        candidate = candidate_by_hash.get(voter_hash)
        matched_id: int | str = candidate.user_id if candidate is not None else ""
        matched_name = candidate.name if candidate is not None else ""
        for row in voter_rows:
            writer.writerow(
                [
                    voter_hash,
                    matched_id,
                    matched_name,
                    row.display_order,
                    row.label,
                    row.score,
                    row.updated_at,
                ]
            )


if __name__ == "__main__":
    raise SystemExit(main())
