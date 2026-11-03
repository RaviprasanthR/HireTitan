"""Settings read from the environment and ``.env`` (FR-029).

API keys live only in ``.env`` / the environment, never in the database, and are
held as ``SecretStr`` so they never appear in ``repr``, logs or dumps. An empty
key counts as missing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LlmMode = Literal["openai", "fake"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        frozen=True,
    )

    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    data_dir: Path = Field(default=Path("./data"), validation_alias="HIRETITAN_DATA_DIR")
    host: str = Field(default="127.0.0.1", validation_alias="HIRETITAN_HOST")
    port: int = Field(default=8000, ge=1, le=65535, validation_alias="HIRETITAN_PORT")
    llm: LlmMode = Field(default="openai", validation_alias="HIRETITAN_LLM")

    explicit_database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    postgres_user: str = Field(default="hiretitan", validation_alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(
        default=SecretStr("hiretitan"), validation_alias="POSTGRES_PASSWORD"
    )
    postgres_db: str = Field(default="hiretitan", validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="127.0.0.1", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, ge=1, le=65535, validation_alias="POSTGRES_PORT")

    @field_validator("openai_api_key", "explicit_database_url", mode="before")
    @classmethod
    def _blank_is_missing(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL (psycopg 3). Contains the password: never log it."""
        if self.explicit_database_url is not None:
            return self.explicit_database_url.get_secret_value()
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password.get_secret_value(), safe="")
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings, read once. Tests build ``Settings`` directly."""
    return Settings()
