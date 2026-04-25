import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    database_url: str
    voter_hash_secret: str
    score_min: int
    score_max: int
    log_level: str


def load_config() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    voter_hash_secret = os.environ.get("VOTER_HASH_SECRET")
    if not voter_hash_secret:
        raise RuntimeError("VOTER_HASH_SECRET is required")

    score_min = _load_int("SCORE_MIN", default=0)
    score_max = _load_int("SCORE_MAX", default=5)
    if score_min > score_max:
        raise RuntimeError("SCORE_MIN must be less than or equal to SCORE_MAX")

    return Config(
        telegram_bot_token=token,
        database_url=database_url,
        voter_hash_secret=voter_hash_secret,
        score_min=score_min,
        score_max=score_max,
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )


def _load_int(name: str, *, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
