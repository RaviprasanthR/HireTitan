"""T007: configuration from the environment and ``.env`` (FR-029: keys only in .env)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hiretitan.platform.config.settings import Settings

ENV_VARS = (
    "OPENAI_API_KEY",
    "HIRETITAN_DATA_DIR",
    "HIRETITAN_HOST",
    "HIRETITAN_PORT",
    "HIRETITAN_LLM",
    "DATABASE_URL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def load(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def test_FR029_key_never_in_repr_or_dump() -> None:
    settings = load(OPENAI_API_KEY="sk-test-abc123", POSTGRES_PASSWORD="pg-secret-xyz")

    rendered = [
        repr(settings),
        str(settings),
        settings.model_dump_json(),
        str(settings.model_dump()),
    ]
    for text in rendered:
        assert "sk-test-abc123" not in text
        assert "pg-secret-xyz" not in text
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-test-abc123"


@pytest.mark.parametrize("value", ["", "   ", "\t"])
def test_FR029_empty_key_reads_as_missing(value: str) -> None:
    assert load(OPENAI_API_KEY=value).openai_api_key is None


def test_FR029_key_is_trimmed() -> None:
    settings = load(OPENAI_API_KEY="  sk-test-abc  ")
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-test-abc"


def test_defaults_bind_localhost() -> None:
    settings = load()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.llm == "openai"
    assert settings.data_dir == Path("./data")
    assert settings.openai_api_key is None


def test_reads_dotenv_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=sk-from-file\nHIRETITAN_LLM=fake\nHIRETITAN_PORT=9000\n")
    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-from-file"
    assert settings.llm == "fake"
    assert settings.port == 9000


def test_environment_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("HIRETITAN_LLM=openai\n")
    monkeypatch.setenv("HIRETITAN_LLM", "fake")
    assert Settings(_env_file=env_file).llm == "fake"  # type: ignore[call-arg]


def test_database_url_built_from_postgres_variables() -> None:
    settings = load(
        POSTGRES_USER="ht",
        POSTGRES_PASSWORD="p@ss/word",
        POSTGRES_DB="htdb",
        POSTGRES_HOST="db",
        POSTGRES_PORT="5433",
    )
    assert settings.database_url == "postgresql+psycopg://ht:p%40ss%2Fword@db:5433/htdb"


def test_database_url_defaults_to_local_postgres() -> None:
    assert load().database_url == (
        "postgresql+psycopg://hiretitan:hiretitan@127.0.0.1:5432/hiretitan"
    )


def test_explicit_database_url_wins() -> None:
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert load(DATABASE_URL=url, POSTGRES_HOST="ignored").database_url == url
    assert "u:p@" not in repr(load(DATABASE_URL=url))


def test_unknown_llm_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        load(HIRETITAN_LLM="anthropic")
