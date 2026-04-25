import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    log_level: str


def load_config() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    return Config(
        telegram_bot_token=token,
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
