"""T028 / constitution VIII: the compose stack is local-only and keeps secrets out of images."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def compose() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text("utf-8"))  # type: ignore[no-any-return]


def test_stack_has_the_expected_services(compose: dict[str, Any]) -> None:
    assert set(compose["services"]) == {"db", "migrate", "api", "worker"}


def test_constitution_VIII_ports_bound_to_localhost(compose: dict[str, Any]) -> None:
    published = [
        (name, str(port))
        for name, service in compose["services"].items()
        for port in service.get("ports", [])
    ]
    assert published, "the api must publish a port"
    for name, port in published:
        assert port.startswith("127.0.0.1:"), f"{name} publishes {port!r} beyond localhost"


def test_only_the_api_publishes_a_port(compose: dict[str, Any]) -> None:
    assert {n for n, s in compose["services"].items() if s.get("ports")} == {"api"}


def test_constitution_VIII_env_and_private_files_are_dockerignored() -> None:
    entries = {
        line.strip().rstrip("/")
        for line in (ROOT / ".dockerignore").read_text("utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert ".env" in entries
    assert "docs/private" in entries
    assert "data" in entries


def test_database_has_a_volume_and_a_healthcheck(compose: dict[str, Any]) -> None:
    db = compose["services"]["db"]
    assert db["image"] == "postgres:16"
    assert "healthcheck" in db
    assert any(str(v).endswith(":/var/lib/postgresql/data") for v in db["volumes"])
    assert "db-data" in compose["volumes"]


def test_api_and_worker_start_after_migrations_and_share_the_data_volume(
    compose: dict[str, Any],
) -> None:
    for name in ("api", "worker"):
        service = compose["services"][name]
        assert service["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
        assert service["depends_on"]["db"]["condition"] == "service_healthy"
        assert service["env_file"] == [".env"] or service["env_file"] == ".env"
        assert any(str(v).endswith(":/data") for v in service["volumes"])
    assert compose["services"]["migrate"]["command"][:3] == ["alembic", "upgrade", "head"]
    assert compose["services"]["worker"]["command"] == ["python", "-m", "hiretitan.worker_main"]


def test_containers_reach_the_database_by_service_name(compose: dict[str, Any]) -> None:
    for name in ("api", "worker", "migrate"):
        assert compose["services"][name]["environment"]["POSTGRES_HOST"] == "db"
