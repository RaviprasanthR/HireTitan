"""T015 (R2, constitution VII): career-ops only makes the requests HireTitan has checked.

Three layers:

* the allowlist itself is exactly the enabled providers, and a request outside it is caught
  (planted violations, so a broken matcher cannot pass silently);
* a trace recorded from the real providers reading one public board each stays inside the list;
* with the pinned career-ops checkout (``CAREER_OPS_DIR``), the real providers are run through
  ``runner.mjs`` with every request intercepted, and what they actually send stays inside the list.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hiretitan.search.domain.vendors import ENABLED_VENDORS
from hiretitan.search.infra.careerops.allowlist import ALLOWED_REQUESTS, violations
from hiretitan.search.infra.careerops.boards import provider_id

FIXTURES = Path(__file__).parents[2] / "fixtures" / "careerops"
RUNNER = (
    Path(__file__).parents[3]
    / "src"
    / "hiretitan"
    / "search"
    / "infra"
    / "careerops"
    / "runner.mjs"
)
PROBE = Path(__file__).with_name("request_probe.cjs")
CAREER_OPS_DIR = os.environ.get("CAREER_OPS_DIR")


def test_R2_allowlist_covers_exactly_the_enabled_providers() -> None:
    assert set(ALLOWED_REQUESTS) == {provider_id(v) for v in ENABLED_VENDORS}


@pytest.mark.parametrize("provider", ["keka", "smartrecruiters"])
def test_R2_providers_that_fail_the_robots_check_are_not_listed(provider: str) -> None:
    assert provider not in ALLOWED_REQUESTS


@pytest.mark.parametrize(
    ("provider", "method", "url"),
    [
        ("greenhouse", "POST", "https://boards-api.greenhouse.io/v1/boards/acme/jobs"),
        ("greenhouse", "GET", "https://evil.example.test/v1/boards/acme/jobs"),
        ("greenhouse", "GET", "https://boards-api.greenhouse.io/v1/boards/acme/applications"),
        ("lever", "PUT", "https://api.lever.co/v0/postings/acme"),
        ("workday", "POST", "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Site/job/x"),
        ("workday", "GET", "https://acme.wd5.myworkdayjobs.com.attacker.test/wday/cxs/a/b/jobs"),
        ("workday", "GET", "https://myworkdayjobs.com/wday/cxs/a/b/jobs"),
        ("recruitee", "DELETE", "https://acme.recruitee.com/api/offers/"),
        ("recruitee", "GET", "https://acme.recruitee.com/api/candidates/"),
        ("zoho-recruit", "GET", "https://acme.zohorecruit.com/admin"),
        ("amazon", "GET", "https://www.amazon.jobs/en/profile"),
        ("amazon", "GET", "http://www.amazon.jobs/en/search.json"),  # not https
        ("ashby", "GET", "https://api.smartrecruiters.com/v1/companies/a/postings"),
        ("smartrecruiters", "GET", "https://api.smartrecruiters.com/v1/companies/a/postings"),
    ],
)
def test_R2_planted_request_outside_the_list_is_caught(
    provider: str, method: str, url: str
) -> None:
    assert violations(provider, [(method, url)])


@pytest.mark.parametrize(
    ("provider", "method", "url"),
    [
        ("greenhouse", "GET", "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"),
        ("lever", "GET", "https://api.lever.co/v0/postings/acme?mode=json"),
        ("ashby", "GET", "https://api.ashbyhq.com/posting-api/job-board/acme"),
        ("workday", "POST", "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Site/jobs"),
        ("workday", "GET", "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Site/job/Pune/R_1"),
        ("recruitee", "GET", "https://acme.recruitee.com/api/offers/"),
        ("zoho-recruit", "GET", "https://acme.zohorecruit.com/jobs/Careers"),
        ("amazon", "GET", "https://www.amazon.jobs/en/search.json?base_query=engineer&offset=0"),
    ],
)
def test_R2_expected_requests_pass(provider: str, method: str, url: str) -> None:
    assert violations(provider, [(method, url)]) == []


def test_R2_recorded_live_trace_stays_in_allowlist() -> None:
    trace = json.loads((FIXTURES / "request_trace.json").read_text("utf-8"))["requests"]
    assert {r["provider"] for r in trace} == set(ALLOWED_REQUESTS)  # every provider was recorded
    for row in trace:
        url = f"https://{row['host']}{row['path']}"
        assert violations(row["provider"], [(row["method"], url)]) == [], row


@pytest.mark.skipif(
    not CAREER_OPS_DIR or shutil.which("node") is None,
    reason="needs the pinned career-ops checkout (CAREER_OPS_DIR) and Node",
)
def test_R2_careerops_requests_stay_in_allowlist(tmp_path: Path) -> None:
    boards = [
        ("greenhouse", "https://job-boards.greenhouse.io/examplecorp", {}),
        ("lever", "https://jobs.lever.co/examplecorp", {}),
        ("ashby", "https://jobs.ashbyhq.com/examplecorp", {}),
        ("workday", "https://examplecorp.wd5.myworkdayjobs.com/ExampleSite", {"max_pages": 1}),
        ("recruitee", "https://examplecorp.recruitee.com", {}),
        ("zoho-recruit", "https://examplecorp.zohorecruit.com/jobs/Careers", {}),
        (
            "amazon",
            "https://www.amazon.jobs/en/search",
            {"amazon": {"base_query": "engineer"}},
        ),
    ]
    assert {name for name, _, _ in boards} == set(ALLOWED_REQUESTS)
    log = tmp_path / "requests.log"
    request = {
        "boards": [
            {"company_id": name, "provider": name, "careers_url": url, **extra}
            for name, url, extra in boards
        ]
    }
    env = {
        **os.environ,
        "CAREER_OPS_DIR": str(CAREER_OPS_DIR),
        "HIRETITAN_PROBE_LOG": str(log),
        "HIRETITAN_PROBE_MODE": "replay",
        "HIRETITAN_BOARD_TIMEOUT_MS": "20000",
    }
    done = subprocess.run(
        ["node", "--require", str(PROBE), str(RUNNER)],
        input=json.dumps(request),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert {r["company_id"] for r in json.loads(done.stdout)["results"]} == set(ALLOWED_REQUESTS)

    seen: dict[str, list[tuple[str, str]]] = {name: [] for name in ALLOWED_REQUESTS}
    unattributed: list[tuple[str, str]] = []
    for line in log.read_text("utf-8").splitlines():
        entry = json.loads(line)
        host = urlsplit(entry["url"]).hostname or ""
        owners = [
            name
            for name, rules in ALLOWED_REQUESTS.items()
            if any(fnmatch(host, rule.host) for rule in rules)
        ]
        if owners:
            seen[owners[0]].append((entry["method"], entry["url"]))
        else:
            unattributed.append((entry["method"], entry["url"]))

    assert unattributed == []  # nothing went to a host that is in no provider's list
    for name, requests in seen.items():
        assert requests, f"{name}: no request was intercepted, so nothing was checked"
        assert violations(name, requests) == [], name
