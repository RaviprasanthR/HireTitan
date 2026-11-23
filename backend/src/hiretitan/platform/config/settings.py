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
CareerOpsMode = Literal["real", "fake"]
MailMode = Literal["gmail", "fake"]


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
    # The names the API answers to (the Host header). There is no login and the port is published
    # on localhost only; refusing any other name stops a web page that points its own name at
    # 127.0.0.1 ("DNS rebinding") from reaching the API. "test" is the reserved name tests use.
    allowed_hosts: str = Field(
        default="127.0.0.1,localhost,[::1],::1,test", validation_alias="HIRETITAN_ALLOWED_HOSTS"
    )
    port: int = Field(default=8000, ge=1, le=65535, validation_alias="HIRETITAN_PORT")
    llm: LlmMode = Field(default="openai", validation_alias="HIRETITAN_LLM")
    frontend_dist: Path | None = Field(default=None, validation_alias="HIRETITAN_FRONTEND_DIST")
    fake_llm_dir: Path | None = Field(default=None, validation_alias="HIRETITAN_FAKE_LLM_DIR")
    career_ops: CareerOpsMode = Field(default="real", validation_alias="HIRETITAN_CAREER_OPS")
    career_ops_dir: Path = Field(
        default=Path("/opt/career-ops"), validation_alias="HIRETITAN_CAREER_OPS_DIR"
    )
    fake_career_ops_dir: Path | None = Field(
        default=None, validation_alias="HIRETITAN_FAKE_CAREER_OPS_DIR"
    )
    # feature 002c: the read-only mail reader. ``fake`` serves synthetic mail from a folder (the
    # e2e stack). The Google client id and secret are the person's own and may come from the
    # environment instead of the secrets file; nothing is shipped (FR-001).
    mail: MailMode = Field(default="gmail", validation_alias="HIRETITAN_MAIL")
    fake_gmail_dir: Path | None = Field(default=None, validation_alias="HIRETITAN_FAKE_GMAIL_DIR")
    google_oauth_client_id: SecretStr | None = Field(
        default=None, validation_alias="GOOGLE_OAUTH_CLIENT_ID"
    )
    google_oauth_client_secret: SecretStr | None = Field(
        default=None, validation_alias="GOOGLE_OAUTH_CLIENT_SECRET"
    )

    explicit_database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    postgres_user: str = Field(default="hiretitan", validation_alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(
        default=SecretStr("hiretitan"), validation_alias="POSTGRES_PASSWORD"
    )
    postgres_db: str = Field(default="hiretitan", validation_alias="POSTGRES_DB")
    postgres_host: str = Field(default="127.0.0.1", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, ge=1, le=65535, validation_alias="POSTGRES_PORT")

    @field_validator(
        "openai_api_key",
        "explicit_database_url",
        "fake_llm_dir",
        "fake_career_ops_dir",
        "frontend_dist",
        "fake_gmail_dir",
        "google_oauth_client_id",
        "google_oauth_client_secret",
        mode="before",
    )
    @classmethod
    def _blank_is_missing(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    def secrets(self) -> list[SecretStr | None]:
        """Every configured secret, so the logger can scrub it wherever it shows up."""
        return [
            self.openai_api_key,
            self.explicit_database_url,
            self.postgres_password,
            self.google_oauth_client_id,
            self.google_oauth_client_secret,
        ]

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
