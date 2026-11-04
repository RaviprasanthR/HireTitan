"""Nodes of the ``profile_ingest`` workflow (contracts/profile-ingest-workflow.md).

Each node is a small function over the workflow state and ``IngestDeps``. State holds only
plain JSON values so LangGraph can checkpoint it. Nodes before an interrupt are idempotent:
resuming re-runs the interrupting node from its start, never an earlier one.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Final, TypedDict
from uuid import UUID

from langgraph.types import interrupt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiretitan.platform.llm.infra.calls_repo import CallsRepo, LlmCallRecord
from hiretitan.platform.llm.port import LlmPort, LlmRequest
from hiretitan.platform.llm.prompts import PromptRegistry
from hiretitan.platform.llm.validation import Dropped, TaskSpec, ValidatedLlm
from hiretitan.platform.runtime.events import run_payload
from hiretitan.platform.runtime.infra.runs_repo import RunsRepo
from hiretitan.platform.storage.port import FileStoragePort
from hiretitan.platform.untrusted.delimit import delimit
from hiretitan.platform.untrusted.mask_contacts import Contacts, mask_contacts
from hiretitan.platform.untrusted.sanitize import sanitize
from hiretitan.platform.untrusted.screen import Flag, screen
from hiretitan.profile.domain.content import Contact, ProfileContent
from hiretitan.profile.domain.diff import changed_paths
from hiretitan.profile.domain.grounding import ground
from hiretitan.profile.domain.rules import confirm_errors
from hiretitan.profile.domain.serialization import content_from_json, content_to_json
from hiretitan.profile.infra.parsing.docx import parse_docx
from hiretitan.profile.infra.parsing.pdf import parse_pdf
from hiretitan.profile.infra.parsing.types import ParsedDocument, status_for
from hiretitan.profile.infra.repos import (
    Provenance,
    ResumeFilesRepo,
    ReviewsRepo,
    VersionsRepo,
)
from hiretitan.profile.workflow.mapping import (
    content_to_extracted,
    extracted_to_content,
    merge_contacts,
    strip_all_placeholders,
)

PROMPT_NAME: Final = "extract_profile"
CACHE_SUFFIX: Final = "extract.json"
Publish = Callable[[str, dict[str, Any]], Awaitable[None]]
State = dict[str, Any]


class IngestState(TypedDict, total=False):
    """Every key the nodes read or write; LangGraph keeps only the keys declared here."""

    run_id: str
    resume_file_id: str
    visible_text: str
    hidden_runs: list[dict[str, Any]]
    parse_status: str
    clean_text: str
    truncated_at: dict[str, Any] | None
    flags: list[dict[str, str]]
    decision: str
    masked_text: str
    contacts: dict[str, list[str]]
    extraction: dict[str, Any]
    dropped: list[dict[str, Any]]
    outcome: str
    prompt_version: str
    content: dict[str, Any]
    compare_to_version_id: str | None
    changed_paths: list[str]
    review_id: str
    answer: dict[str, Any]


async def _default_country() -> str:
    return "IN"  # replaced by the preferences module's default country at the composition roots


@dataclass
class IngestDeps:
    sessions: async_sessionmaker[AsyncSession]
    storage: FileStoragePort
    llm: LlmPort
    provider: str
    model: str
    prompts: PromptRegistry
    publish: Publish | None = None
    default_country: Callable[[], Awaitable[str]] = field(default=_default_country)


# ---- helpers ---------------------------------------------------------------------------------
def _flag_json(flag: Flag) -> dict[str, str]:
    return {
        "rule_id": flag.rule_id,
        "severity": flag.severity,
        "excerpt": flag.excerpt,
        "location": flag.location,
    }


async def _step(deps: IngestDeps, state: State, name: str) -> None:
    """Record the current step (for the progress display) and tell the browser."""
    async with deps.sessions() as session:
        run = await RunsRepo(session).set_step(UUID(state["run_id"]), name)
        await session.commit()
    if deps.publish is not None:
        await deps.publish("run.updated", run_payload(run))


async def _record_call(deps: IngestDeps, call: LlmCallRecord) -> None:
    async with deps.sessions() as session:
        await CallsRepo(session).record(call)
        await session.commit()


def _empty_content() -> ProfileContent:
    return ProfileContent(contact=Contact(name=""))


# ---- nodes -----------------------------------------------------------------------------------
async def parse_document(deps: IngestDeps, state: State) -> State:
    await _step(deps, state, "parsing")
    file_id = UUID(state["resume_file_id"])
    async with deps.sessions() as session:
        file = await ResumeFilesRepo(session).get(file_id)
    if file is None:
        raise LookupError(f"Resume file {file_id} not found")
    data = deps.storage.get(file.sha256)
    doc: ParsedDocument
    if file.kind == "pasted_text":
        text = data.decode("utf-8")
        doc = ParsedDocument(text, [], None, status_for(text))
    elif file.kind == "upload_pdf":
        doc = await asyncio.to_thread(parse_pdf, data)
    else:
        doc = await asyncio.to_thread(parse_docx, data)
    async with deps.sessions() as session:
        await ResumeFilesRepo(session).set_parse_result(
            file_id,
            doc.status,
            {
                "visible_text_chars": len(doc.visible_text),
                "hidden_runs": len(doc.hidden_runs),
            },
        )
        await session.commit()
    return {
        "visible_text": doc.visible_text,
        "hidden_runs": [{"page": r.page, "text": r.text} for r in doc.hidden_runs],
        "parse_status": doc.status,
    }


def after_parse(state: State) -> str:
    return "sanitize_and_screen" if state["parse_status"] == "parsed" else "end_no_text"


async def sanitize_and_screen(deps: IngestDeps, state: State) -> State:
    await _step(deps, state, "screening")
    clean = sanitize(state["visible_text"])
    flags = screen(clean.text, "visible")
    hidden_text = "\n".join(run["text"] for run in state["hidden_runs"])
    if hidden_text:
        flags += screen(hidden_text, "hidden")
    truncated = (
        {"offset": clean.truncated.offset, "heading": clean.truncated.heading}
        if clean.truncated
        else None
    )
    flag_json = [_flag_json(f) for f in flags]
    async with deps.sessions() as session:
        await ResumeFilesRepo(session).set_parse_result(
            UUID(state["resume_file_id"]),
            "parsed",
            {
                "visible_text_chars": len(clean.text),
                "truncated_at": truncated,
                "hidden_text": state["hidden_runs"],
                "injection_flags": flag_json,
            },
        )
        await session.commit()
    return {"clean_text": clean.text, "truncated_at": truncated, "flags": flag_json}


def after_screen(state: State) -> str:
    high_in_visible = any(
        f["severity"] == "high" and f["location"] == "visible" for f in state["flags"]
    )
    return "await_injection_decision" if high_in_visible else "mask_contacts"


def await_injection_decision(state: State) -> State:
    """Pauses for the user: carry on with extraction, or fill the profile in by hand."""
    visible_high = [
        f for f in state["flags"] if f["severity"] == "high" and f["location"] == "visible"
    ]
    answer = interrupt({"waiting_for": "injection_decision", "flags": visible_high})
    return {"decision": answer["decision"]}


def after_decision(state: State) -> str:
    return "manual_extraction" if state["decision"] == "manual_entry" else "mask_contacts"


async def manual_extraction(deps: IngestDeps, state: State) -> State:
    """The user chose to fill the profile in by hand: an empty profile, no AI call."""
    return {
        "content": content_to_json(_empty_content()),
        "dropped": [],
        "outcome": "manual",
        "prompt_version": "1",
    }


async def mask_contacts_node(deps: IngestDeps, state: State) -> State:
    region = await deps.default_country()
    masked = mask_contacts(state["clean_text"], default_region=region)
    return {
        "masked_text": masked.text,
        "contacts": {
            "emails": list(masked.contacts.emails),
            "phones": list(masked.contacts.phones),
            "links": list(masked.contacts.links),
        },
    }


def _cache_key(masked_text: str, prompt_version: int, model: str) -> str:
    raw = f"{masked_text}\x00{prompt_version}\x00{model}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_cache(deps: IngestDeps, key: str) -> dict[str, Any] | None:
    try:
        cached: dict[str, Any] = json.loads(deps.storage.get_text(key, CACHE_SUFFIX))
    except (FileNotFoundError, ValueError):
        return None
    return cached


def extraction_task_spec(schema: type[BaseModel], source: str) -> TaskSpec[BaseModel]:
    """The checks every extraction answer goes through: date rules, then grounding in ``source``.

    Shared with the extraction eval so it measures exactly what the app would keep.
    """

    def empty() -> BaseModel:
        return schema.model_validate(content_to_extracted(_empty_content()))

    def rules(value: BaseModel) -> list[str]:
        content = extracted_to_content(value.model_dump())
        return [e.message for e in confirm_errors(content) if e.path.endswith(".end")]

    def check(value: BaseModel) -> tuple[BaseModel, list[Dropped]]:
        grounded = ground(extracted_to_content(value.model_dump()), source)
        kept = schema.model_validate(content_to_extracted(grounded.profile))
        return kept, [Dropped(d.path, d.reason, d.value) for d in grounded.dropped]

    return TaskSpec(fallback=empty, rules=rules, check=check)


async def extract_profile(deps: IngestDeps, state: State) -> State:
    await _step(deps, state, "extracting")
    prompt = deps.prompts.load(PROMPT_NAME)
    version = prompt.version.version
    key = _cache_key(state["masked_text"], version, deps.model)
    cached = _read_cache(deps, key)
    if cached is not None:  # a retried or repeated run never pays twice
        return {**cached, "prompt_version": str(version)}

    schema: type[BaseModel] = prompt.output_schema
    block = delimit("resume", state["masked_text"])
    request = LlmRequest(
        task=PROMPT_NAME,
        prompt=prompt.render(resume_block=block.text),
        output_schema=schema,
        tier=prompt.version.tier,
        max_output_tokens=prompt.version.max_output_tokens,
        # The block is already inside the rendered prompt; passing it again would send it twice.
        untrusted_blocks=[],
    )
    spec = extraction_task_spec(schema, state["clean_text"])

    async def record(call: LlmCallRecord) -> None:
        await _record_call(deps, call)

    chain = ValidatedLlm(deps.llm, record, provider=deps.provider)
    result = await chain.run(
        request,
        spec,
        run_id=UUID(state["run_id"]),
    )
    payload = {
        "extraction": result.value.model_dump(),
        "dropped": [{"path": d.path, "value": d.item, "reason": d.reason} for d in result.dropped],
        "outcome": result.outcome,
    }
    if result.outcome != "fallback":  # a fallback is not worth caching
        deps.storage.put_text(key, CACHE_SUFFIX, json.dumps(payload))
    return {**payload, "prompt_version": str(version)}


async def assemble_profile(deps: IngestDeps, state: State) -> State:
    """merge_contacts: the masked-out details go back in; stray placeholders come out."""
    content = extracted_to_content(state["extraction"])
    contacts = Contacts(
        tuple(state["contacts"]["emails"]),
        tuple(state["contacts"]["phones"]),
        tuple(state["contacts"]["links"]),
    )
    merged = strip_all_placeholders(merge_contacts(content, contacts))
    return {"content": content_to_json(merged)}


async def compare_with_current(deps: IngestDeps, state: State) -> State:
    async with deps.sessions() as session:
        current = await VersionsRepo(session).current()
    if current is None:
        return {"compare_to_version_id": None, "changed_paths": []}
    new = content_from_json(state["content"])
    return {
        "compare_to_version_id": str(current.id),
        "changed_paths": changed_paths(current.content, new),
    }


async def open_review(deps: IngestDeps, state: State) -> State:
    """Write the review row the user will edit. Idempotent by run id."""
    await _step(deps, state, "ready_for_review")
    run_id = UUID(state["run_id"])
    manual = state.get("outcome") == "manual"
    provenance = Provenance(
        PROMPT_NAME,
        state.get("prompt_version", "1"),
        "none" if manual else deps.provider,
        "none" if manual else deps.model,
    )
    flags = {
        "hidden_text": state["hidden_runs"],
        "injection_flags": state["flags"],
        "truncated_at": state["truncated_at"],
        "extraction_outcome": state.get("outcome", "ok"),
    }
    compare_to = (
        UUID(state["compare_to_version_id"]) if state.get("compare_to_version_id") else None
    )
    async with deps.sessions() as session:
        reviews = ReviewsRepo(session)
        review = await reviews.get_by_run(run_id)
        if review is None:
            review = await reviews.create(
                run_id=run_id,
                resume_file_id=UUID(state["resume_file_id"]),
                extraction=state["content"],
                dropped_items=state.get("dropped", []),
                flags=flags,
                provenance=provenance,
                compare_to_version_id=compare_to,
                changed_paths=state.get("changed_paths", []),
            )
            await session.commit()
    return {"review_id": str(review.id)}


def await_review(state: State) -> State:
    """Pauses for the user to confirm (with their edits) or discard."""
    answer = interrupt({"waiting_for": "profile_review", "review_id": state["review_id"]})
    return {"answer": answer}


def after_review(state: State) -> str:
    return (
        "save_profile_version" if state["answer"].get("action") == "confirm" else "discard_review"
    )


async def save_version(deps: IngestDeps, *, review_id: UUID, content_json: dict[str, Any]) -> UUID:
    """Create the version for a review in one transaction. Idempotent by review id."""
    async with deps.sessions() as session:
        versions = VersionsRepo(session)
        existing = await versions.get_by_review(review_id)
        if existing is not None:
            return existing.id
        review = await ReviewsRepo(session).get(review_id)
        if review is None:
            raise LookupError(f"Review {review_id} not found")
        manual = review.flags.get("extraction_outcome") == "manual"
        version = await versions.create_version(
            content_from_json(content_json),
            created_by="manual" if manual else "extraction",
            source_file_id=review.resume_file_id,
            review_id=review_id,
            provenance=None if manual else review.provenance,
        )
        await ReviewsRepo(session).set_status(review_id, "confirmed")
        await session.commit()
    if deps.publish is not None:
        await deps.publish("profile.updated", {"current_version_id": str(version.id)})
    return version.id


async def save_profile_version(deps: IngestDeps, state: State) -> State:
    await save_version(
        deps,
        review_id=UUID(state["review_id"]),
        content_json=state["answer"]["content"],
    )
    return {}


async def discard_review(deps: IngestDeps, state: State) -> State:
    async with deps.sessions() as session:
        await ReviewsRepo(session).set_status(UUID(state["review_id"]), "discarded")
        await session.commit()
    return {}
