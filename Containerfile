FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md .python-version ./
COPY src ./src

RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY alembic ./alembic

CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync voting-bot"]
