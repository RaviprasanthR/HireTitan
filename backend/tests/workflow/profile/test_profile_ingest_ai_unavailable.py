"""T059: the profile import when the AI is unavailable (US3, FR-030, SC-006).

The real budget guard and provider-status service sit in front of a scripted model, so these
tests cover the same path a missing key or an empty budget takes in the running app.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from hiretitan.platform.clock import SystemClock
from hiretitan.platform.llm.budget import BudgetGuard
from hiretitan.platform.llm.fake import FakeLlm
from hiretitan.platform.llm.infra.provider_status_repo import ProviderStatusRepo
from hiretitan.platform.llm.models import ModelCatalog
from hiretitan.platform.llm.port import AiUnavailable, LlmRequest, LlmResult
from hiretitan.platform.llm.provider_status import ProviderStatusService
from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus, WaitingFor
from hiretitan.platform.runtime.resume_paused import resume_paused_runs
from hiretitan.profile.domain.content import Contact, ProfileContent
from hiretitan.profile.infra.repos import ResumeFilesRepo, VersionsRepo
from hiretitan.profile.workflow import nodes

sys.path.insert(0, str(Path(__file__).parent))
from harness import Harness, jane_extraction

PDF = "synthetic-mid-2page.pdf"


class _Queue:
    async def enqueue(self, run_id: UUID, resume: Any = None) -> None:
        return None


class _NoNetwork:
    async def check_key(self) -> str:
        raise AssertionError("no key check is expected here")


class RejectingLlm:
    """The provider answers 401: the adapter tells the status service, then refuses."""

    provider = "openai"
    model = "gpt-5.4-mini"

    def __init__(self, status: ProviderStatusService) -> None:
        self._status = status
        self.calls = 0

    async def generate(self, req: LlmRequest[Any]) -> LlmResult[Any]:
        self.calls += 1
        await self._status.mark_rejected()
        raise AiUnavailable("key_rejected")


def use_llm(h: Harness, llm: Any) -> None:
    h.deps.llm = llm


def status_service(h: Harness) -> ProviderStatusService:
    async def _publish(event: str, data: dict[str, Any]) -> None:
        return None

    return ProviderStatusService(
        h.sessions,
        _NoNetwork(),
        has_key=True,
        publish=_publish,
        provider="openai",  # type: ignore[arg-type]
    )


def budget_guard(h: Harness, inner: FakeLlm, cap: list[Decimal]) -> BudgetGuard:
    async def cap_provider() -> Decimal:
        return cap[0]

    return BudgetGuard(
        inner,
        sessions=h.sessions,
        cap_provider=cap_provider,
        catalog=ModelCatalog.load(),
        provider="openai",
        clock=SystemClock(),
    )


async def test_US3_AS2_key_rejected_pauses_run(make_harness: Any) -> None:
    h = make_harness([])
    llm = RejectingLlm(status_service(h))
    use_llm(h, llm)
    run_id = await h.start(PDF)

    state = await h.run(run_id)

    assert state.status is RunStatus.paused
    assert state.pause_reason is PauseReason.key_rejected
    assert await h.review() is None
    async with h.sessions() as session:
        row = await ProviderStatusRepo(session).get("openai")
    assert row is not None
    assert row.status == "rejected"
    assert "OPENAI_API_KEY" in (row.message or "")


async def test_US3_AS3_paused_run_resumes_from_checkpoint(
    make_harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = make_harness([])
    use_llm(h, RejectingLlm(status_service(h)))
    parses: list[int] = []
    real_parse = nodes.parse_pdf
    monkeypatch.setattr(nodes, "parse_pdf", lambda data: parses.append(1) or real_parse(data))
    run_id = await h.start(PDF)
    await h.run(run_id)
    assert len(parses) == 1

    fixed = FakeLlm([jane_extraction()])
    use_llm(h, fixed)  # the key was replaced and the worker restarted
    assert await resume_paused_runs(h.sessions, _Queue(), PauseReason.key_rejected) == 1
    state = await h.run(run_id)

    assert state.status is RunStatus.awaiting_review
    assert state.waiting_for is WaitingFor.profile_review
    assert len(parses) == 1  # the file was not parsed again
    assert len(fixed.calls) == 1


async def test_US3_AS5_budget_blocked_pauses_run(make_harness: Any) -> None:
    h = make_harness([])
    provider_model = FakeLlm([jane_extraction()])
    cap = [Decimal("0.000001")]  # far below the estimated cost of one extraction
    use_llm(h, budget_guard(h, provider_model, cap))
    run_id = await h.start(PDF)

    state = await h.run(run_id)

    assert state.status is RunStatus.paused
    assert state.pause_reason is PauseReason.budget_reached
    assert provider_model.calls == []  # the provider was never called
    async with h.sessions() as session:
        outcomes = (
            await session.execute(text("SELECT outcome, cost_usd FROM app.llm_calls"))
        ).all()
    assert [(o, Decimal(c)) for o, c in outcomes] == [("budget_blocked", Decimal(0))]

    # The key being fine does not wake a budget pause ...
    assert await resume_paused_runs(h.sessions, _Queue(), PauseReason.key_rejected) == 0
    # ... raising the cap does.
    cap[0] = Decimal("25")
    assert await resume_paused_runs(h.sessions, _Queue(), PauseReason.budget_reached) == 1
    state = await h.run(run_id)
    assert state.waiting_for is WaitingFor.profile_review
    assert len(provider_model.calls) == 1


async def test_SC006_no_upload_or_edit_lost(make_harness: Any) -> None:
    h = make_harness([])
    async with h.sessions() as session:
        await VersionsRepo(session).create_version(
            ProfileContent(contact=Contact(name="Jane Example"), skills=("Python",)),
            created_by="manual",
        )
        await session.commit()

    for llm in (
        RejectingLlm(status_service(h)),
        budget_guard(h, FakeLlm([jane_extraction()]), [Decimal("0.000001")]),
    ):
        use_llm(h, llm)
        run_id = await h.start(PDF)
        state = await h.run(run_id)
        assert state.status is RunStatus.paused

        file = await h.file_for(run_id)
        assert file.parse_status == "parsed"
        assert h.storage.get(file.sha256)  # the uploaded bytes are still stored

    async with h.sessions() as session:
        assert len(await ResumeFilesRepo(session).list()) == 2  # both uploads kept
        current = await VersionsRepo(session).current()
        versions = await VersionsRepo(session).list_versions()
    assert current is not None
    assert current.content.contact.name == "Jane Example"  # the confirmed profile is untouched
    assert len(versions) == 1
