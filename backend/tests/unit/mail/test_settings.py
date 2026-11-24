"""Mail settings (T010): FR-001, FR-003. The Google client is the persons own; nothing ships."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr

from hiretitan.platform.config.settings import Settings


def settings(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def test_FR001_mail_defaults_to_real_gmail_with_no_shipped_credentials(
    monkeypatch: object,
) -> None:
    for name in (
        "HIRETITAN_MAIL",
        "HIRETITAN_FAKE_GMAIL_DIR",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)  # type: ignore[attr-defined]

    s = settings()

    assert s.mail == "gmail"
    assert s.fake_gmail_dir is None
    assert s.google_oauth_client_id is None
    assert s.google_oauth_client_secret is None


def test_FR001_mail_can_be_scripted_for_the_e2e_stack(monkeypatch: object) -> None:
    monkeypatch.setenv("HIRETITAN_MAIL", "fake")  # type: ignore[attr-defined]
    monkeypatch.setenv("HIRETITAN_FAKE_GMAIL_DIR", "/fake-gmail")  # type: ignore[attr-defined]

    s = settings()

    assert s.mail == "fake"
    assert s.fake_gmail_dir == Path("/fake-gmail")


def test_FR003_google_secrets_are_secret_and_blank_is_missing(monkeypatch: object) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "  ")  # type: ignore[attr-defined]
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "GOCSPX-synthetic-secret-0001")  # type: ignore[attr-defined]

    s = settings()

    assert s.google_oauth_client_id is None
    assert isinstance(s.google_oauth_client_secret, SecretStr)
    assert "GOCSPX-synthetic-secret-0001" not in repr(s)
    assert "GOCSPX-synthetic-secret-0001" not in str(s.model_dump())
