from __future__ import annotations

import pytest

from voting_bot.config import load_config


REQUIRED_ENV = {
    "TELEGRAM_BOT_TOKEN": "token",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
    "VOTER_HASH_SECRET": "secret",
}


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "DATABASE_URL",
        "VOTER_HASH_SECRET",
        "SCORE_MIN",
        "SCORE_MAX",
        "LOG_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)

    for name, value in REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)


def test_load_config_reads_required_values(valid_env: None) -> None:
    config = load_config()

    assert config.telegram_bot_token == "token"
    assert config.database_url == "postgresql://user:pass@localhost:5432/db"
    assert config.voter_hash_secret == "secret"
    assert config.score_min == 0
    assert config.score_max == 5
    assert config.log_level == "INFO"


@pytest.mark.parametrize(
    ("env_name", "message"),
    [
        ("TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN is required"),
        ("DATABASE_URL", "DATABASE_URL is required"),
        ("VOTER_HASH_SECRET", "VOTER_HASH_SECRET is required"),
    ],
)
def test_load_config_rejects_missing_required_values(
    valid_env: None,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    message: str,
) -> None:
    monkeypatch.delenv(env_name)

    with pytest.raises(RuntimeError, match=message):
        load_config()


def test_load_config_reads_optional_values(
    valid_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORE_MIN", "1")
    monkeypatch.setenv("SCORE_MAX", "10")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    config = load_config()

    assert config.score_min == 1
    assert config.score_max == 10
    assert config.log_level == "DEBUG"


@pytest.mark.parametrize("env_name", ["SCORE_MIN", "SCORE_MAX"])
def test_load_config_rejects_non_integer_score_bounds(
    valid_env: None,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
) -> None:
    monkeypatch.setenv(env_name, "abc")

    with pytest.raises(RuntimeError, match=f"{env_name} must be an integer"):
        load_config()


def test_load_config_rejects_invalid_score_bounds(
    valid_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORE_MIN", "10")
    monkeypatch.setenv("SCORE_MAX", "1")

    with pytest.raises(
        RuntimeError,
        match="SCORE_MIN must be less than or equal to SCORE_MAX",
    ):
        load_config()
