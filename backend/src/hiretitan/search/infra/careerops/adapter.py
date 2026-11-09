"""The career-ops adapter: reads company job boards through the pinned career-ops providers.

It starts HireTitan's own ``runner.mjs`` (Node) with the boards to read and gets back, per
company, either the postings or an error. One board failing never fails the others, and a crash,
a timeout or garbled output becomes an error for the affected boards instead of an exception.

Safety (constitution VII): only enabled providers are ever sent to the runner; the runner starts
with a minimal environment (no API key, no database URL) and runs inside HireTitan's own data
folder, never the person's own career-ops folder.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from hiretitan.search.application.ports import (
    BoardRef,
    DiscoveryResult,
    Posting,
    ScanError,
    ScanOk,
    ScanResult,
)
from hiretitan.search.domain.vendors import ENABLED_VENDORS
from hiretitan.search.infra.careerops.boards import (
    BoardAddressError,
    board_request,
    discover_board,
)

BATCH_TIMEOUT_SECONDS: Final = 120.0
RUNNER: Final = Path(__file__).with_name("runner.mjs")
OWN_FOLDER: Final = "career-ops"
_KEPT_ENV: Final = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "HOME", "LANG")


@dataclass(frozen=True, slots=True)
class ProcessOutput:
    exit_code: int
    stdout: str
    stderr: str


class ProcessTimeoutError(Exception):
    """The runner did not finish in time and was stopped."""


RunProcess = Callable[[list[str], bytes, Path, dict[str, str], float], Awaitable[ProcessOutput]]


async def run_subprocess(
    command: list[str], stdin: bytes, cwd: Path, env: dict[str, str], limit_seconds: float
) -> ProcessOutput:
    """Run a command to completion in a worker thread (portable, unlike asyncio subprocesses on
    Windows' selector loop)."""

    def run() -> ProcessOutput:
        try:
            done = subprocess.run(  # noqa: S603 - fixed command, no shell
                command,
                input=stdin,
                cwd=cwd,
                env=env,
                capture_output=True,
                timeout=limit_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise ProcessTimeoutError from error
        return ProcessOutput(
            done.returncode,
            done.stdout.decode("utf-8", "replace"),
            done.stderr.decode("utf-8", "replace"),
        )

    return await asyncio.to_thread(run)


class CareerOpsAdapter:
    def __init__(
        self,
        *,
        career_ops_dir: Path,
        data_dir: Path,
        node: str = "node",
        run_process: RunProcess = run_subprocess,
        timeout_seconds: float = BATCH_TIMEOUT_SECONDS,
    ) -> None:
        self._career_ops_dir = career_ops_dir
        self._own_folder = data_dir / OWN_FOLDER
        self._node = node
        self._run = run_process
        self._timeout = timeout_seconds

    async def scan(self, refs: list[BoardRef]) -> ScanResult:
        results: ScanResult = {}
        requests = []
        for ref in refs:
            if ref.vendor not in ENABLED_VENDORS:
                results[ref.company_id] = ScanError(f"Provider {ref.vendor} is not enabled.")
                continue
            try:
                requests.append(board_request(ref))
            except BoardAddressError as error:
                results[ref.company_id] = ScanError(str(error))
        if not requests:
            return results

        self._own_folder.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"boards": [r.as_json() for r in requests]}).encode()
        try:
            output = await self._run(
                [self._node, str(RUNNER)],
                payload,
                self._own_folder,
                self._environment(),
                self._timeout,
            )
        except ProcessTimeoutError:
            message = f"The job boards did not answer within {int(self._timeout)} seconds."
            return results | {UUID(r.company_id): ScanError(message) for r in requests}
        except OSError as error:
            message = f"The job-board reader could not start: {error.strerror or error}"
            return results | {UUID(r.company_id): ScanError(message) for r in requests}

        answers = self._parse(output)
        for request in requests:
            company_id = UUID(request.company_id)
            results[company_id] = (
                answers[request.company_id]
                if isinstance(answers, dict) and request.company_id in answers
                else ScanError(answers if isinstance(answers, str) else "The board gave no answer.")
            )
        return results

    async def discover(self, careers_url: str) -> DiscoveryResult | None:
        return discover_board(careers_url)

    def _environment(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in _KEPT_ENV if k in os.environ}
        env["CAREER_OPS_ROOT"] = str(self._own_folder)
        env["CAREER_OPS_DIR"] = str(self._career_ops_dir)
        return env

    @staticmethod
    def _parse(output: ProcessOutput) -> dict[str, ScanOk | ScanError] | str:
        """Per-company answers, or one message that applies to every board."""
        if output.exit_code != 0:
            lines = [line for line in output.stderr.strip().splitlines() if line.strip()]
            detail = lines[0][:200] if lines else f"exit code {output.exit_code}"
            return f"The job-board reader stopped: {detail}"
        try:
            results = json.loads(output.stdout)["results"]
            answers: dict[str, ScanOk | ScanError] = {}
            for item in results:
                answers[str(item["company_id"])] = (
                    ScanOk(_postings(item["postings"]))
                    if item.get("ok")
                    else ScanError(str(item.get("error") or "The board did not answer.")[:300])
                )
        except (ValueError, KeyError, TypeError, AttributeError):
            return "The job-board reader gave an answer that could not be read."
        return answers


def _postings(raw: list[dict[str, Any]]) -> list[Posting]:
    postings = []
    for item in raw:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue  # without these a posting cannot be shown or de-duplicated
        posted = item.get("posted_at")
        postings.append(
            Posting(
                title=title,
                url=url,
                location=item.get("location") or None,
                posted_at=datetime.fromtimestamp(posted / 1000, tz=UTC)
                if isinstance(posted, int | float)
                else None,
                description=item.get("description") or None,
                requisition_id=item.get("requisition_id") or None,
            )
        )
    return postings
