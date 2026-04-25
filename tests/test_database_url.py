from voting_bot.database_url import for_psycopg, for_sqlalchemy


def test_for_sqlalchemy_uses_psycopg_driver_for_plain_postgresql_url() -> None:
    assert (
        for_sqlalchemy("postgresql://user:pass@db:5432/voting_bot")
        == "postgresql+psycopg://user:pass@db:5432/voting_bot"
    )


def test_for_sqlalchemy_preserves_explicit_driver_url() -> None:
    url = "postgresql+psycopg://user:pass@db:5432/voting_bot"

    assert for_sqlalchemy(url) == url


def test_for_psycopg_removes_sqlalchemy_driver_name() -> None:
    assert (
        for_psycopg("postgresql+psycopg://user:pass@db:5432/voting_bot")
        == "postgresql://user:pass@db:5432/voting_bot"
    )


def test_for_psycopg_preserves_plain_postgresql_url() -> None:
    url = "postgresql://user:pass@db:5432/voting_bot"

    assert for_psycopg(url) == url
