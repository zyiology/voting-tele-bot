import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse


WEBHOOK_SECRET_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    database_url: str
    voter_hash_secret: str
    score_min: int
    score_max: int
    log_level: str
    webhook_url: str | None
    webhook_listen_host: str
    webhook_listen_port: int
    webhook_url_path: str
    webhook_secret_token: str | None


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

    webhook_url_path = os.environ.get("WEBHOOK_URL_PATH") or f"/telegram/{token}"
    if not webhook_url_path.startswith("/"):
        webhook_url_path = f"/{webhook_url_path}"

    webhook_url = os.environ.get("WEBHOOK_URL") or None
    webhook_secret_token = os.environ.get("WEBHOOK_SECRET_TOKEN") or None
    webhook_listen_host = os.environ.get("WEBHOOK_LISTEN_HOST", "0.0.0.0")
    webhook_listen_port = _load_int("WEBHOOK_LISTEN_PORT", default=8080)

    if webhook_url:
        _validate_webhook_config(
            webhook_url=webhook_url,
            webhook_url_path=webhook_url_path,
            webhook_secret_token=webhook_secret_token,
        )

    return Config(
        telegram_bot_token=token,
        database_url=database_url,
        voter_hash_secret=voter_hash_secret,
        score_min=score_min,
        score_max=score_max,
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        webhook_url=webhook_url,
        webhook_listen_host=webhook_listen_host,
        webhook_listen_port=webhook_listen_port,
        webhook_url_path=webhook_url_path,
        webhook_secret_token=webhook_secret_token,
    )


def _load_int(name: str, *, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _validate_webhook_config(
    *,
    webhook_url: str,
    webhook_url_path: str,
    webhook_secret_token: str | None,
) -> None:
    parsed_url = urlparse(webhook_url)
    if parsed_url.scheme != "https":
        raise RuntimeError("WEBHOOK_URL must start with https://")

    if parsed_url.path != webhook_url_path:
        raise RuntimeError("WEBHOOK_URL path must match WEBHOOK_URL_PATH")

    if not webhook_secret_token:
        raise RuntimeError("WEBHOOK_SECRET_TOKEN is required when WEBHOOK_URL is set")

    if not WEBHOOK_SECRET_TOKEN_PATTERN.fullmatch(webhook_secret_token):
        raise RuntimeError(
            "WEBHOOK_SECRET_TOKEN must contain only A-Z, a-z, 0-9, _, or - "
            "and be 1-256 characters long"
        )
