"""T014: the runtime image carries the pinned career-ops providers and a Node to run them.

Needs Docker and a built image, so it only runs when ``HIRETITAN_IMAGE_TESTS=1``:

    docker build -t hiretitan:test .
    HIRETITAN_IMAGE_TESTS=1 HIRETITAN_IMAGE=hiretitan:test pytest tests/integration/test_image_has_scanner.py
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

PINNED_COMMIT = "115bc9873e3d43e23883f3c8f16436617facc62c"  # career-ops-v1.38.0
IMAGE = os.environ.get("HIRETITAN_IMAGE", "hiretitan:test")

pytestmark = pytest.mark.skipif(
    os.environ.get("HIRETITAN_IMAGE_TESTS") != "1",
    reason="needs Docker and a built image (set HIRETITAN_IMAGE_TESTS=1)",
)


def in_image(script: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "run", "--rm", "-i", "--entrypoint", "sh", IMAGE, "-c", script],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_R1_pinned_career_ops_present_and_runs_help() -> None:
    result = in_image(
        'node --version && cat /opt/career-ops/PINNED_COMMIT && ls /opt/career-ops/providers/greenhouse.mjs'
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0].startswith("v22.")
    assert PINNED_COMMIT in result.stdout


def test_R1_runner_answers_with_no_boards() -> None:
    runner = (
        "$(python -c 'import hiretitan.search.infra.careerops as m, pathlib;"
        " print(pathlib.Path(m.__file__).with_name(\"runner.mjs\"))')"
    )
    result = in_image(f"CAREER_OPS_DIR=/opt/career-ops node {runner}", stdin='{"boards": []}')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"results": []}


def test_R1_every_enabled_provider_loads_in_the_image() -> None:
    """Pruning the checkout must not break a provider's imports. A board address that no provider
    accepts gives a normal error, never 'not installed'."""
    runner = (
        "$(python -c 'import hiretitan.search.infra.careerops as m, pathlib;"
        " print(pathlib.Path(m.__file__).with_name(\"runner.mjs\"))')"
    )
    providers = [
        "greenhouse",
        "lever",
        "ashby",
        "workday",
        "smartrecruiters",
        "recruitee",
        "zoho-recruit",
        "amazon",
    ]
    boards = [
        {"company_id": name, "provider": name, "careers_url": "https://not-a-board.invalid/"}
        for name in providers
    ]
    result = in_image(
        f"HIRETITAN_BOARD_TIMEOUT_MS=15000 CAREER_OPS_DIR=/opt/career-ops node {runner}",
        stdin=json.dumps({"boards": boards}),
    )
    assert result.returncode == 0, result.stderr
    answers = {r["company_id"]: r for r in json.loads(result.stdout)["results"]}
    assert set(answers) == set(providers)
    for name, answer in answers.items():
        assert "not installed" not in str(answer.get("error")), name


def test_R1_licence_and_notice_are_kept() -> None:
    result = in_image("cat /usr/share/doc/career-ops/LICENSE")
    assert result.returncode == 0, result.stderr
    assert "MIT License" in result.stdout
    assert "Santiago Fern" in result.stdout  # the copyright holder's name stays in the image


def test_R1_no_browser_is_installed() -> None:
    result = in_image(
        'test ! -d /opt/career-ops/node_modules/playwright-core && '
        'test ! -d "$HOME/.cache/ms-playwright" && echo clean'
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_R1_runtime_packages_are_the_locked_ones() -> None:
    result = in_image(
        "cd /opt/career-ops && node -p \"['undici','js-yaml','dotenv']"
        ".map(n => n + ' ' + require('./node_modules/' + n + '/package.json').version).join(',')\""
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "undici 6.29.1,js-yaml 5.5.0,dotenv 18.0.9"
