from __future__ import annotations

import re

from voting_bot.hashing import hash_voter_id


def test_hash_voter_id_is_deterministic() -> None:
    assert hash_voter_id(12345, "secret") == hash_voter_id(12345, "secret")


def test_hash_voter_id_changes_when_secret_changes() -> None:
    assert hash_voter_id(12345, "secret-a") != hash_voter_id(12345, "secret-b")


def test_hash_voter_id_changes_when_user_id_changes() -> None:
    assert hash_voter_id(12345, "secret") != hash_voter_id(67890, "secret")


def test_hash_voter_id_returns_sha256_hex_digest() -> None:
    voter_hash = hash_voter_id(12345, "secret")

    assert re.fullmatch(r"[0-9a-f]{64}", voter_hash) is not None
