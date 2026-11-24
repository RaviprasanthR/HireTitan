"""The chat's post-to-draft flow (002m quick flow, Ravi 2026-11-24).

The person chooses a draft (LinkedIn connection message, LinkedIn message, email) and pastes a job
post or a link, in either order. HireTitan writes the draft and only then asks whether to save the
job. Until the yes, the post is a hidden ``staged`` job that no list shows; no loses it and its
draft. This is composition code: it joins the assistant, search and drafts modules (contract 9).

The pasted text never reaches the chat history and reaches the AI only inside a data block, to read
the title and the company (the keyword reader later takes the same bounded path).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.assistant.application.ports import (
    DraftRefusedError,
    DraftStarter,
    StagedRefusedError,
    StagedStep,
    StagedView,
    StartedDraft,
)
from hiretitan.assistant.domain.quick import DRAFT_LABEL
from hiretitan.assistant.infra.models import StagedRow
from hiretitan.assistant.infra.repos import MessagesRepo
from hiretitan.drafts.api.drafts import DraftIn, DraftsApiDeps, RecipientIn, start_draft
from hiretitan.drafts.domain.recipient import HIRING_TEAM
from hiretitan.drafts.infra.repos import DraftsRepo
from hiretitan.drafts_wiring import SqlContacts, SqlJobs, SqlProfileFacts
from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.port import AiUnavailable, LlmPort, LlmRequest, RetryableLlmError
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.runtime.runner import RunQueue
from hiretitan.platform.untrusted.delimit import delimit
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.platform.web.problems import ProblemError
from hiretitan.search.application.paste import (
    DESCRIPTION_MIN,
    PasteError,
    PasteInput,
    paste_job,
)
from hiretitan.search.infra.models import JobRow
from hiretitan.search.infra.paste_store import SqlPasteStore

STAGED: Final = "staged"
_URL: Final = re.compile(r"https?://[^\s<>\"')\]]+")
_POSTING_MAX: Final = 12_000  # what the AI reads of a post; the whole text is kept on the job
PASTE_HINT: Final = "Paste the job post, or a link to it, and I will write it."
Publish = Callable[[list[list[str]]], Awaitable[None]]


def draft_starter(
    sessions: async_sessionmaker[AsyncSession], queue: RunQueue, provider: str
) -> DraftStarter:
    """The quick actions' drafts (002m FR-029): the same use case as the job page's Write button,
    always writing afresh. No name means the hiring team, greeted as "there"."""
    drafts = DraftsApiDeps(
        sessions=sessions,
        queue=queue,
        jobs=SqlJobs(sessions),
        profile=SqlProfileFacts(sessions),
        contacts=SqlContacts(sessions),
        provider=provider,
    )

    async def start(
        job_id: UUID, kind: str, name: str | None, recipient_kind: str | None
    ) -> StartedDraft:
        job = await drafts.jobs.get(job_id)
        if job is None:
            raise DraftRefusedError("That job is no longer in your list.")
        body = DraftIn.model_validate(
            {
                "kind": kind,
                "recipient": RecipientIn(name=name or HIRING_TEAM),
                "recipient_kind": recipient_kind or ("hiring_manager" if name is None else None),
                "regenerate": True,
            }
        )
        try:
            started = await start_draft(drafts, job_id, body)
        except ProblemError as error:
            raise DraftRefusedError(error.detail) from error
        draft_id = started.id
        return StartedDraft(draft_id, f"{job.title} at {job.company_name}")

    return start


def _what(kind: str) -> str:
    label = DRAFT_LABEL[kind]
    return label if label.startswith("LinkedIn") else label.lower()


class StagedFlowImpl:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        llm: LlmPort,
        prompts: PromptRegistry,
        queue: RunQueue,
        provider: str,
        now: Callable[[], datetime],
        publish: Publish,
    ) -> None:
        self._sessions = sessions
        self._llm = llm
        self._prompt = prompts.load("extract_posting_identity")
        self._start = draft_starter(sessions, queue, provider)
        self._now = now
        self._publish = publish

    # --- reading -----------------------------------------------------------------------------

    async def view(self, conversation_id: UUID) -> StagedView | None:
        async with self._sessions() as session:
            row = await session.get(StagedRow, conversation_id)
            if row is None:
                return None
            if row.job_id is None:
                return StagedView("need_post", kind=row.kind)
            job = await session.get(JobRow, row.job_id)
            if job is None:  # deleted elsewhere
                await session.delete(row)
                await session.commit()
                return None
            label = f"{job.title} at {job.company_name}"
            ref = f"job:{job.id}"
            saved = job.state != STAGED
            if row.needs_details:
                return StagedView("need_details", row.kind, label, ref, None, saved)
            drafts = await DraftsRepo(session).list_for_job(job.id)
            found = next((d for d in drafts if d.kind == row.kind), None) if row.kind else None
            if found is None:
                return StagedView("need_kind", None, label, ref, None, saved)
            draft_ref = f"draft:{found.id}"
            if found.status == "writing":
                return StagedView("drafting", row.kind, label, ref, draft_ref, saved)
            step: StagedStep = "done" if saved else "ask_save"
            return StagedView(step, row.kind, label, ref, draft_ref, saved)

    # --- steps -------------------------------------------------------------------------------

    async def begin(self, conversation_id: UUID, kind: str) -> StagedView:
        at = self._now()
        async with self._sessions() as session:
            await self._drop_held(session, conversation_id)
            await session.execute(
                delete(StagedRow).where(StagedRow.conversation_id == conversation_id)
            )
            session.add(StagedRow(conversation_id=conversation_id, kind=kind))
            messages = MessagesRepo(session)
            await messages.append(conversation_id, author="person", text=DRAFT_LABEL[kind], now=at)
            await messages.append(conversation_id, author="mikasa", text=PASTE_HINT, now=at)
            await session.commit()
        return StagedView("need_post", kind=kind)

    async def hold_post(self, conversation_id: UUID, text: str) -> StagedView:
        text = text.strip()
        match = _URL.search(text)
        link = match.group(0).rstrip(".,;:") if match else None
        remainder = text.replace(link, " ").strip() if link else text
        description = remainder if len(sanitize(remainder).text) >= DESCRIPTION_MIN else ""
        if not description and link is None:
            raise StagedRefusedError(
                "That is too short to be a job post. Paste the post or a link."
            )
        title, company = await self._identity(description) if description else ("", "")
        return await self._stage(conversation_id, link, description, title, company)

    async def details(self, conversation_id: UUID, title: str, company: str) -> StagedView:
        async with self._sessions() as session:
            row = await session.get(StagedRow, conversation_id)
            job = await session.get(JobRow, row.job_id) if row and row.job_id else None
            if row is None or job is None:
                raise StagedRefusedError("Paste a job post first.")
            link, description = job.canonical_url, job.description
        return await self._stage(
            conversation_id, link, description, title.strip(), company.strip(), edited=True
        )

    async def choose(self, conversation_id: UUID, kind: str) -> StagedView:
        at = self._now()
        async with self._sessions() as session:
            row = await session.get(StagedRow, conversation_id)
            if row is None or row.job_id is None:
                raise StagedRefusedError("Paste a job post first.")
            if row.needs_details:
                raise StagedRefusedError("Add the job title and company first.")
            job = await session.get(JobRow, row.job_id)
            if job is None:
                raise StagedRefusedError("Paste a job post first.")
            row.kind = kind
            job_id, label = job.id, f"{job.title} at {job.company_name}"
            await MessagesRepo(session).append(
                conversation_id, author="person", text=DRAFT_LABEL[kind], now=at
            )
            await session.commit()
        await self._write(conversation_id, job_id, kind, label)
        view = await self.view(conversation_id)
        assert view is not None
        return view

    async def save(self, conversation_id: UUID) -> str:
        at = self._now()
        async with self._sessions() as session:
            row = await session.get(StagedRow, conversation_id)
            job = await session.get(JobRow, row.job_id) if row and row.job_id else None
            if row is None or job is None:
                raise StagedRefusedError("There is nothing to save.")
            label = f"{job.title} at {job.company_name}"
            fresh = job.state == STAGED
            if fresh:
                job.state = "explore"
            said = f"Saved {label} to your list." if fresh else "Okay, all done."
            await session.delete(row)
            await MessagesRepo(session).append(
                conversation_id, author="mikasa", text=said, now=at, refs=[f"job:{job.id}"]
            )
            await session.commit()
        await self._publish([["jobs"]])
        return said

    async def discard(self, conversation_id: UUID) -> None:
        at = self._now()
        async with self._sessions() as session:
            row = await session.get(StagedRow, conversation_id)
            if row is None:
                return
            await self._drop_held(session, conversation_id)
            await session.delete(row)
            await MessagesRepo(session).append(
                conversation_id,
                author="mikasa",
                text="Okay, I did not save the job, and the draft is gone too.",
                now=at,
            )
            await session.commit()

    # --- helpers -----------------------------------------------------------------------------

    async def _drop_held(self, session: AsyncSession, conversation_id: UUID) -> None:
        """Delete the post this conversation is holding, if it is still only held."""
        row = await session.get(StagedRow, conversation_id)
        if row is None or row.job_id is None:
            return
        await session.execute(delete(JobRow).where(JobRow.id == row.job_id, JobRow.state == STAGED))
        row.job_id = None  # the database clears it too; the loaded row must agree

    async def _identity(self, description: str) -> tuple[str, str]:
        """The title and company the post names; empty strings when it does not say, or when the
        AI cannot be asked (the person is asked instead)."""
        request = LlmRequest(
            task="extract_posting_identity",
            prompt=self._prompt.render(),
            output_schema=self._prompt.output_schema,
            tier=self._prompt.version.tier,
            max_output_tokens=self._prompt.version.max_output_tokens,
            untrusted_blocks=[delimit("job_posting", sanitize(description[:_POSTING_MAX]).text)],
        )
        try:
            result = await self._llm.generate(request)
        except (AiUnavailable, RetryableLlmError):
            return "", ""
        async with self._sessions() as session:
            await CallsRepo(session).record(
                LlmCallRecord(
                    task="extract_posting_identity",
                    prompt_name=self._prompt.version.name,
                    prompt_version=str(self._prompt.version.version),
                    provider=result.provider,
                    model=result.model,
                    input_tokens=result.usage.input_tokens,
                    cached_input_tokens=result.usage.cached_input_tokens,
                    output_tokens=result.usage.output_tokens,
                    latency_ms=result.usage.latency_ms,
                    outcome=result.outcome,
                )
            )
            await session.commit()
        value: Any = result.value
        title = " ".join(sanitize(value.title).text.split())
        company = " ".join(sanitize(value.company).text.split())
        return title, company

    async def _stage(
        self,
        conversation_id: UUID,
        link: str | None,
        description: str,
        title: str,
        company: str,
        *,
        edited: bool = False,
    ) -> StagedView:
        at = self._now()
        link_only = not description
        known = bool(title and company)
        async with self._sessions() as session:
            row = await session.get(StagedRow, conversation_id)
            kind = row.kind if row else None
            await self._drop_held(session, conversation_id)
            host = "post"
            try:
                result = await paste_job(
                    SqlPasteStore(session),
                    PasteInput(
                        url=link or f"https://hiretitan.invalid/pasted/{uuid4()}",
                        description=description,
                        title=title or ("Job post" if link_only else None),
                        company=company or (host if link_only else None),
                        link_only=link_only,
                    ),
                    now=at,
                )
            except PasteError as error:
                raise StagedRefusedError(" ".join(e.message for e in error.errors)) from error
            job = await session.get(JobRow, result.job_id)
            assert job is not None
            already = result.merged_into is not None
            if not already:
                job.state = STAGED
            needs = False if (already or edited) else not known
            if row is None:
                row = StagedRow(conversation_id=conversation_id, kind=kind)
                session.add(row)
            row.job_id = job.id
            row.needs_details = needs
            label = f"{job.title} at {job.company_name}"
            job_id = job.id
            messages = MessagesRepo(session)
            if not edited:
                await messages.append(
                    conversation_id,
                    author="person",
                    text=f"Pasted a job post: {label}" if known or already else "Pasted a job post",
                    now=at,
                )
            if needs:
                ask = "I could not read the job title and company from that. What are they?"
            elif kind is None:
                ask = f"Got it: {label}. What would you like me to write?"
            else:
                ask = ""
            if ask:
                await messages.append(conversation_id, author="mikasa", text=ask, now=at)
            await session.commit()
        if not needs and kind is not None:
            await self._write(conversation_id, job_id, kind, label)
        view = await self.view(conversation_id)
        assert view is not None
        return view

    async def _write(self, conversation_id: UUID, job_id: UUID, kind: str, label: str) -> None:
        """Start the draft; the chat says what is being written. A refusal leaves the post held."""
        started = await self._start(job_id, kind, None, None)
        async with self._sessions() as session:
            await MessagesRepo(session).append(
                conversation_id,
                author="mikasa",
                text=(
                    f"Writing your {_what(kind)} for {label}. Nothing is sent: copy it when it "
                    "is ready."
                ),
                now=self._now(),
                refs=[f"job:{job_id}", f"draft:{started.draft_id}"],
            )
            await session.commit()
