"""T025: contacts and notes never leave the person's own database (FR-021, FR-022, SC-006).

Three proofs: a full search with the AI on sends no contact or note text to the model; the
workflow, prompt and LLM code cannot import the contacts code; nothing shipped in the repo
(seed list, docs) holds a contact.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import grimp
import pytest
from tests.fakes.search_env import Env, add_company, go, new_search, posting

from hiretitan.platform.llm.port import LlmRequest, LlmResult, Usage
from hiretitan.search.application.ports import ScanOk
from hiretitan.search.domain.contacts import ContactFields
from hiretitan.search.infra.repos import ContactsRepo, NotesRepo

REPO = Path(__file__).parents[3]
# Unique strings: if any of them shows up where it should not, a leak is proven.
MARKERS = (
    "Zebulon Marker",
    "zebulon.marker@leak-check.example",
    "+91 90909 12121",
    "linkedin.com/in/zebulon-marker",
    "leak-check note about the hiring manager",
    "leak-check company note",
)
PLACEHOLDER_SLUG = re.compile(r"example|placeholder|your-|sample|jane-|john-", re.IGNORECASE)
LINKEDIN_PROFILE = re.compile(r"linkedin\.com/in/([A-Za-z0-9_%\-]+)", re.IGNORECASE)


class RecordingLlm:
    """Marks every job relevant and keeps every request it was sent."""

    provider = "fake"
    model = "recording"

    def __init__(self) -> None:
        self.requests: list[LlmRequest[Any]] = []

    async def generate(self, req: LlmRequest[Any]) -> LlmResult[Any]:
        self.requests.append(req)
        refs = re.findall(r'"ref":\s*"(j\d+)"', req.prompt.user)
        decisions = [{"ref": ref, "relevant": True, "reason": "Fits the profile"} for ref in refs]
        value = req.output_schema.model_validate({"decisions": decisions})
        return LlmResult(value, "ok", Usage(), self.provider, self.model)


async def test_FR022_no_ai_call_contains_contacts_or_notes(env: Env) -> None:
    ref = await add_company(env, "Acme")
    async with env.sessions() as session:
        await ContactsRepo(session).add(
            ref.company_id,
            ContactFields(
                name=MARKERS[0],
                role="Recruiter",
                email=MARKERS[1],
                phone=MARKERS[2],
                linkedin_url="https://www." + MARKERS[3],
                confidence="high",
                note=MARKERS[4],
            ),
            source="typed",
        )
        await NotesRepo(session).set(ref.company_id, MARKERS[5], source="typed")
        await session.commit()
    llm = RecordingLlm()
    assert env.deps.judge is not None
    env.deps.judge.llm = llm
    env.career_ops.script(ref, ScanOk([posting("Backend Engineer", company="acme")]))

    await go(env, await new_search(env, mode="rules_and_ai"))

    assert llm.requests, "the search made no AI call, so this test proved nothing"
    for request in llm.requests:
        sent = request.prompt.system + "\n" + request.prompt.user
        for marker in MARKERS:
            assert marker not in sent, f"{marker!r} reached the model"


def test_FR022_workflows_cannot_import_contacts() -> None:
    graph = grimp.build_graph("hiretitan")
    ai_paths = ("hiretitan.search.workflow", "hiretitan.prompts", "hiretitan.platform.llm")
    contacts_code = (
        "hiretitan.search.domain.contacts",
        "hiretitan.search.domain.contacts_cell",
        "hiretitan.search.domain.sheet",
        "hiretitan.search.application.contacts",
        "hiretitan.search.application.sheet_import",
    )
    found = [
        (importer, imported)
        for importer in ai_paths
        for imported in contacts_code
        if graph.direct_import_exists(importer=importer, imported=imported, as_packages=True)
    ]
    assert found == []


def test_FR021_shipped_files_contain_no_contacts() -> None:
    shipped = [
        path
        for folder in (REPO / "backend" / "seed", REPO / "docs")
        if folder.exists()
        for path in folder.rglob("*")
        if path.is_file()
        and "private" not in path.relative_to(REPO).parts
        and path.suffix in {".yaml", ".yml", ".md", ".csv", ".json", ".txt"}
    ]
    if not shipped:
        pytest.skip("no shipped files to scan")
    problems: list[str] = []
    for path in shipped:
        text = path.read_text(encoding="utf-8", errors="ignore")
        problems += [f"{path.name}: marker {m!r}" for m in MARKERS if m in text]
        problems += [
            f"{path.name}: linkedin.com/in/{slug}"
            for slug in LINKEDIN_PROFILE.findall(text)
            if not PLACEHOLDER_SLUG.search(slug)
        ]
    assert problems == []
