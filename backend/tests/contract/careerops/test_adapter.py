"""T013: the career-ops adapter against recorded runner output (no Node, no network).

The fixtures in ``tests/fixtures/careerops`` are the runner's real output for one public board of
each enabled provider (and two error cases), scrubbed to synthetic companies. A scripted process
runner stands in for ``node runner.mjs``, so the tests see exactly what the adapter would.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from hiretitan.search.application.ports import BoardRef, ScanError, ScanOk
from hiretitan.search.infra.careerops.adapter import (
    CareerOpsAdapter,
    ProcessOutput,
    ProcessTimeoutError,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "careerops"

# vendor -> (fixture file, board id the adapter is asked to read)
PROVIDERS = {
    "greenhouse": ("greenhouse.json", "examplecorp"),
    "lever": ("lever.json", "examplecorp"),
    "ashby": ("ashby.json", "examplecorp"),
    "workday": ("workday.json", "examplecorp.wd5/ExampleSite"),
    "smartrecruiters": ("smartrecruiters.json", "ExampleCorp"),
    "recruitee": ("recruitee.json", "examplecorp"),
    "zoho_recruit": ("zoho-recruit.json", "examplecorp"),
    "amazon": ("amazon.json", "software engineer"),
}


class Calls:
    """A scripted process runner that records how the adapter started it."""

    def __init__(
        self,
        stdout: str = "",
        *,
        exit_code: int = 0,
        stderr: str = "",
        raises: Exception | None = None,
    ):
        self.stdout, self.exit_code, self.stderr, self.raises = stdout, exit_code, stderr, raises
        self.commands: list[list[str]] = []
        self.requests: list[dict[str, Any]] = []
        self.cwds: list[Path] = []
        self.envs: list[dict[str, str]] = []
        self.timeouts: list[float] = []

    async def __call__(
        self, command: list[str], stdin: bytes, cwd: Path, env: dict[str, str], limit_seconds: float
    ) -> ProcessOutput:
        self.commands.append(command)
        self.requests.append(json.loads(stdin))
        self.cwds.append(cwd)
        self.envs.append(env)
        self.timeouts.append(limit_seconds)
        if self.raises:
            raise self.raises
        return ProcessOutput(self.exit_code, self.stdout, self.stderr)


def recorded(name: str, company_id: UUID) -> dict[str, Any]:
    """A recorded runner answer, with the fixture's company id swapped for the one asked about."""
    data = json.loads((FIXTURES / name).read_text("utf-8"))
    data["results"][0]["company_id"] = str(company_id)
    return data  # type: ignore[no-any-return]


def adapter(tmp_path: Path, calls: Calls) -> CareerOpsAdapter:
    return CareerOpsAdapter(
        career_ops_dir=tmp_path / "pinned",
        data_dir=tmp_path / "data",
        run_process=calls,
    )


def ref(vendor: str, board_id: str = "examplecorp", n: int = 1) -> BoardRef:
    return BoardRef(UUID(int=n), vendor, board_id)


@pytest.mark.parametrize("vendor", sorted(PROVIDERS))
async def test_R1_recorded_output_parses_per_provider(tmp_path: Path, vendor: str) -> None:
    fixture, board_id = PROVIDERS[vendor]
    board = ref(vendor, board_id)
    calls = Calls(json.dumps(recorded(fixture, board.company_id)))

    result = await adapter(tmp_path, calls).scan([board])

    scan = result[board.company_id]
    assert isinstance(scan, ScanOk)
    assert 2 <= len(scan.postings) <= 3  # SmartRecruiters' recorded board only had two
    first = scan.postings[0]
    assert first.title == "Backend Engineer"
    assert first.url.startswith("https://")
    assert first.posted_at is None or first.posted_at.tzinfo is UTC
    assert first.posted_at is None or isinstance(first.posted_at, datetime)


async def test_R1_times_are_utc_and_missing_fields_stay_none(tmp_path: Path) -> None:
    board = ref("lever")
    calls = Calls(json.dumps(recorded("lever.json", board.company_id)))

    postings = (await adapter(tmp_path, calls).scan([board]))[board.company_id].postings  # type: ignore[union-attr]

    assert postings[0].posted_at == datetime.fromtimestamp(1793000000, tz=UTC)
    assert postings[0].requisition_id == "REQ-1000"
    assert postings[2].description is None  # not stated, so not invented


async def test_R1_error_for_one_company_does_not_fail_the_rest(tmp_path: Path) -> None:
    good, bad = ref("lever", n=1), ref("recruitee", "nosuchboard", n=2)
    answer = {
        "results": [
            recorded("lever.json", good.company_id)["results"][0],
            {
                **json.loads((FIXTURES / "error_bad_board.json").read_text("utf-8"))["results"][0],
                "company_id": str(bad.company_id),
            },
        ]
    }
    calls = Calls(json.dumps(answer))

    result = await adapter(tmp_path, calls).scan([good, bad])

    assert isinstance(result[good.company_id], ScanOk)
    assert result[bad.company_id] == ScanError("HTTP 404 Not Found")


async def test_R2_disabled_provider_never_sent_to_the_runner(tmp_path: Path) -> None:
    keka, ok = ref("keka", n=1), ref("lever", n=2)
    calls = Calls(json.dumps(recorded("lever.json", ok.company_id)))

    result = await adapter(tmp_path, calls).scan([keka, ok])

    sent = [b["company_id"] for b in calls.requests[0]["boards"]]
    assert sent == [str(ok.company_id)]
    assert isinstance(result[keka.company_id], ScanError)
    assert "not enabled" in result[keka.company_id].message  # type: ignore[union-attr]
    assert isinstance(result[ok.company_id], ScanOk)


async def test_R2_only_disabled_providers_never_start_the_runner(tmp_path: Path) -> None:
    calls = Calls("")
    result = await adapter(tmp_path, calls).scan([ref("keka")])
    assert calls.commands == []
    assert isinstance(result[UUID(int=1)], ScanError)


async def test_R1_timeout_is_reported_as_error(tmp_path: Path) -> None:
    boards = [ref("lever", n=1), ref("ashby", n=2)]
    calls = Calls(raises=ProcessTimeoutError())

    result = await adapter(tmp_path, calls).scan(boards)

    assert calls.timeouts == [120.0]
    for board in boards:
        scan = result[board.company_id]
        assert isinstance(scan, ScanError)
        assert "120" in scan.message


async def test_R1_uses_its_own_data_folder(tmp_path: Path) -> None:
    board = ref("lever")
    calls = Calls(json.dumps(recorded("lever.json", board.company_id)))

    await adapter(tmp_path, calls).scan([board])

    own = tmp_path / "data" / "career-ops"
    assert own.is_dir()
    assert calls.cwds == [own]
    assert calls.envs[0]["CAREER_OPS_ROOT"] == str(own)
    assert calls.envs[0]["CAREER_OPS_DIR"] == str(tmp_path / "pinned")
    assert calls.commands[0][0] == "node"
    assert calls.commands[0][1].endswith("runner.mjs")


async def test_R1_runner_environment_carries_no_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    board = ref("lever")
    calls = Calls(json.dumps(recorded("lever.json", board.company_id)))

    await adapter(tmp_path, calls).scan([board])

    assert "OPENAI_API_KEY" not in calls.envs[0]
    assert "DATABASE_URL" not in calls.envs[0]


@pytest.mark.parametrize(
    ("vendor", "board_id", "url"),
    [
        ("greenhouse", "acme", "https://job-boards.greenhouse.io/acme"),
        ("lever", "acme", "https://jobs.lever.co/acme"),
        ("ashby", "acme", "https://jobs.ashbyhq.com/acme"),
        ("smartrecruiters", "Acme", "https://jobs.smartrecruiters.com/Acme"),
        ("recruitee", "acme", "https://acme.recruitee.com"),
        ("zoho_recruit", "acme", "https://acme.zohorecruit.com/jobs/Careers"),
        ("workday", "acme.wd5/Careers", "https://acme.wd5.myworkdayjobs.com/Careers"),
    ],
)
async def test_board_address_is_built_from_vendor_and_board_id(
    tmp_path: Path, vendor: str, board_id: str, url: str
) -> None:
    board = ref(vendor, board_id)
    calls = Calls(
        json.dumps({"results": [{"company_id": str(board.company_id), "ok": True, "postings": []}]})
    )

    await adapter(tmp_path, calls).scan([board])

    sent = calls.requests[0]["boards"][0]
    assert sent["careers_url"] == url
    assert sent["provider"] == vendor.replace("_", "-")


async def test_big_boards_are_capped(tmp_path: Path) -> None:
    boards = [ref("workday", "acme.wd5/Careers", 1), ref("amazon", "engineer", 2)]
    answer = {
        "results": [{"company_id": str(b.company_id), "ok": True, "postings": []} for b in boards]
    }
    calls = Calls(json.dumps(answer))

    await adapter(tmp_path, calls).scan(boards)

    sent = {b["provider"]: b for b in calls.requests[0]["boards"]}
    assert sent["workday"]["max_pages"] == 5
    assert sent["amazon"]["amazon"] == {"base_query": "engineer"}


@pytest.mark.parametrize(
    ("vendor", "board_id"),
    [
        ("lever", "acme/../../etc"),
        ("lever", "acme?x=1"),
        ("lever", "evil.example.test#"),
        ("greenhouse", ""),
        ("recruitee", "a b"),
        ("workday", "no-slash"),
        ("workday", "acme.wd5/../x"),
    ],
)
async def test_unsafe_board_ids_are_refused_without_running_anything(
    tmp_path: Path, vendor: str, board_id: str
) -> None:
    board = ref(vendor, board_id)
    calls = Calls("")

    result = await adapter(tmp_path, calls).scan([board])

    assert calls.commands == []
    assert isinstance(result[board.company_id], ScanError)


async def test_runner_crash_is_an_error_for_every_board(tmp_path: Path) -> None:
    boards = [ref("lever", n=1), ref("ashby", n=2)]
    calls = Calls("", exit_code=1, stderr="Error: boom\n at somewhere")

    result = await adapter(tmp_path, calls).scan(boards)

    assert all(isinstance(result[b.company_id], ScanError) for b in boards)
    assert "boom" in result[boards[0].company_id].message  # type: ignore[union-attr]


async def test_garbage_output_is_an_error_not_a_crash(tmp_path: Path) -> None:
    board = ref("lever")
    result = await adapter(tmp_path, Calls("not json at all")).scan([board])
    assert isinstance(result[board.company_id], ScanError)


async def test_a_board_missing_from_the_answer_is_an_error(tmp_path: Path) -> None:
    one, two = ref("lever", n=1), ref("ashby", n=2)
    calls = Calls(json.dumps(recorded("lever.json", one.company_id)))

    result = await adapter(tmp_path, calls).scan([one, two])

    assert isinstance(result[one.company_id], ScanOk)
    assert isinstance(result[two.company_id], ScanError)


async def test_postings_without_a_title_or_url_are_dropped(tmp_path: Path) -> None:
    board = ref("lever")
    answer = recorded("lever.json", board.company_id)
    answer["results"][0]["postings"][0]["title"] = ""
    answer["results"][0]["postings"][1]["url"] = ""
    calls = Calls(json.dumps(answer))

    scan = (await adapter(tmp_path, calls).scan([board]))[board.company_id]

    assert isinstance(scan, ScanOk)
    assert [p.title for p in scan.postings] == ["Product Designer"]


@pytest.mark.parametrize(
    ("url", "found"),
    [
        ("https://job-boards.greenhouse.io/acme", ("greenhouse", "acme")),
        ("https://boards.greenhouse.io/acme/jobs/123", ("greenhouse", "acme")),
        ("https://jobs.lever.co/acme/abc", ("lever", "acme")),
        ("https://jobs.ashbyhq.com/acme", ("ashby", "acme")),
        ("https://jobs.smartrecruiters.com/Acme", ("smartrecruiters", "Acme")),
        ("https://acme.recruitee.com/o/role", ("recruitee", "acme")),
        ("https://acme.zohorecruit.com/jobs/Careers", ("zoho_recruit", "acme")),
        ("https://acme.wd5.myworkdayjobs.com/en-US/Careers/job/x", ("workday", "acme.wd5/Careers")),
        ("https://acme.example.test/careers", None),
        ("not a url", None),
    ],
)
async def test_discover_recognises_known_board_addresses(
    tmp_path: Path, url: str, found: tuple[str, str] | None
) -> None:
    result = await adapter(tmp_path, Calls("")).discover(url)
    assert (None if result is None else (result.vendor, result.board_id)) == found
