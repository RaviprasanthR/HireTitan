"""What the panel shows for a ref (002m research R5): the person's own view of an item.

This goes to the person's browser only, never to the model, so it may hold private details
(a contact's name, an interview's date and feedback). Mikasa wrote ``[[contact:<id>]]``; the
panel asks for the card and shows it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from hiretitan.actions.refs import Ref
from hiretitan.drafts.infra.models import OutreachDraftRow, TailoredResumeRow
from hiretitan.profile.infra.repos import ResumeFilesRepo
from hiretitan.search.infra.interviews_repo import InterviewsRepo
from hiretitan.search.infra.models import (
    ContactRow,
    InterviewQuestionRow,
    InterviewRoundRow,
    JobRow,
    SearchRunRow,
)
from hiretitan.search.infra.repos import CompaniesRepo, NotesRepo


@dataclass(frozen=True, slots=True)
class RefCard:
    ref: str
    kind: str
    title: str
    subtitle: str | None = None
    lines: list[str] = field(default_factory=list)
    link: str | None = None


def _day(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return (
        value.strftime("%d %b %Y, %H:%M")
        if isinstance(value, datetime)
        else value.strftime("%d %b %Y")
    )


async def _job(session: AsyncSession, job_id: UUID) -> JobRow | None:
    row = await session.get(JobRow, job_id)
    return None if row is None or row.state == "deleted" else row


_DRAFT_TITLES = {
    "connection_request": "LinkedIn connection message",
    "referral_message": "LinkedIn message",
    "email": "Email",
}


async def describe(session: AsyncSession, text: str) -> RefCard | None:
    """The card for ``text`` (a ref), or None when it is not a ref or the item is gone."""
    try:
        ref = Ref.parse(text)
    except ValueError:
        return None
    key = str(ref)
    if ref.kind == "job":
        job = await _job(session, ref.id)
        if job is None:
            return None
        state = {
            "applied": f"Applied {_day(job.applied_on)}",
            "inquired": f"Inquired {_day(job.inquired_on)}",
        }
        lines = [state[job.state]] if job.state in state else []
        if job.location_text:
            lines.append(job.location_text)
        return RefCard(key, "job", job.title, job.company_name, lines, f"/jobs/{job.id}")
    if ref.kind == "company":
        company = await CompaniesRepo(session).get(ref.id)
        if company is None or company.deleted_at is not None:
            return None
        return RefCard(key, "company", company.name, company.city, [], "/companies")
    if ref.kind == "contact":
        contact = await session.get(ContactRow, ref.id)
        if contact is None:
            return None
        company = await CompaniesRepo(session).get(contact.company_id)
        lines = [v for v in (contact.email, contact.phone, contact.linkedin_url) if v]
        return RefCard(
            key,
            "contact",
            contact.name,
            " · ".join(v for v in (contact.role, company.name if company else None) if v) or None,
            lines,
            "/companies",
        )
    if ref.kind == "note":
        note = await NotesRepo(session).get(ref.id)
        company = await CompaniesRepo(session).get(ref.id)
        if note is None or company is None:
            return None
        return RefCard(key, "note", f"Your note on {company.name}", None, [note.body], "/companies")
    if ref.kind in ("interview", "round", "question"):
        return await _interview_card(session, ref)
    if ref.kind == "resume_file":
        file = await ResumeFilesRepo(session).get(ref.id)
        if file is None:
            return None
        return RefCard(key, "resume_file", file.original_name, "Resume file", [], "/profile")
    if ref.kind == "draft":
        draft = await session.get(OutreachDraftRow, ref.id)
        if draft is None:
            return None
        title = _DRAFT_TITLES.get(draft.kind, "Draft")
        who = f"For {draft.recipient_name}"
        if draft.status == "writing":
            return RefCard(key, "draft", title, f"{who} · writing…", [], f"/jobs/{draft.job_id}")
        if draft.status == "failed":
            return RefCard(
                key,
                "draft",
                title,
                f"{who} · could not be written",
                [draft.failure_reason or "You can write it again from the job's page."],
                f"/jobs/{draft.job_id}",
            )
        return RefCard(key, "draft", title, who, [draft.text or ""], f"/jobs/{draft.job_id}")
    if ref.kind == "tailored_resume":
        resume = await session.get(TailoredResumeRow, ref.id)
        if resume is None:
            return None
        job = await session.get(JobRow, resume.job_id)
        who = f"{job.title} at {job.company_name}" if job else "a job"
        link = f"/jobs/{resume.job_id}/resume"
        if resume.status == "writing":
            return RefCard(key, "tailored_resume", "Tailored resume", f"{who} · writing…", [], link)
        if resume.status == "failed":
            reason = resume.failure_reason or "You can tailor it again from the job's page."
            return RefCard(
                key,
                "tailored_resume",
                "Tailored resume",
                f"{who} · could not be made",
                [reason],
                link,
            )
        made = _day(resume.updated_at)
        return RefCard(key, "tailored_resume", "Tailored resume", f"{who} · {made}", [], link)
    if ref.kind == "search_run":
        run = await session.get(SearchRunRow, ref.id)
        if run is None:
            return None
        title = "Job-alert mail check" if run.mode == "mail_alerts" else "Search"
        lines = [f"{run.jobs_found} found, {run.added} new"]
        return RefCard(
            key, "search_run", title, _day(run.started_at), lines, f"/search/runs/{run.id}"
        )
    return None


async def _interview_card(session: AsyncSession, ref: Ref) -> RefCard | None:
    key = str(ref)
    if ref.kind == "interview":
        job = await _job(session, ref.id)
        if job is None:
            return None
        data = await InterviewsRepo(session).details(job.id)
        details = data.details
        lines = []
        if details is not None and details.contact_name:
            lines.append(f"Contact: {details.contact_name}")
        if details is not None and details.source:
            lines.append(f"Source: {details.firm_name or details.source}")
        lines.append(f"{len(data.rounds)} round(s)")
        return RefCard(
            key, "interview", f"Interview: {job.title}", job.company_name, lines, f"/jobs/{job.id}"
        )
    if ref.kind == "round":
        round_row = await session.get(InterviewRoundRow, ref.id)
        job = await _job(session, round_row.job_id) if round_row else None
        if round_row is None or job is None:
            return None
        lines = [f"{round_row.kind.title()} · {round_row.state}"]
        if round_row.scheduled_at:
            lines.insert(0, _day(round_row.scheduled_at) or "")
        if round_row.interviewers:
            lines.append(f"With {round_row.interviewers}")
        if round_row.feedback:
            lines.append(round_row.feedback)
        return RefCard(
            key,
            "round",
            f"Round {round_row.number}: {job.title}",
            job.company_name,
            lines,
            f"/jobs/{job.id}",
        )
    question = await session.get(InterviewQuestionRow, ref.id)
    if question is None:
        return None
    round_row = await session.get(InterviewRoundRow, question.round_id)
    job = await _job(session, round_row.job_id) if round_row else None
    if job is None:
        return None
    lines = [question.answer] if question.answer else []
    return RefCard(key, "question", question.question, job.title, lines, f"/jobs/{job.id}")
