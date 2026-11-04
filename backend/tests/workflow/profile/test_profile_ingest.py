"""T044: the profile_ingest workflow, from the matrix in contracts/profile-ingest-workflow.md."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hiretitan.platform.llm.port import AiUnavailable
from hiretitan.platform.runtime.domain.run_state import PauseReason, RunStatus, WaitingFor
from hiretitan.profile.domain.content import Contact, Experience, ProfileContent, YearMonth
from hiretitan.profile.domain.serialization import content_to_json
from hiretitan.profile.infra.repos import Provenance, VersionsRepo

sys.path.insert(0, str(Path(__file__).parent))
from harness import jane_extraction

PDF = "synthetic-mid-2page.pdf"


async def test_US1_AS1_upload_extracts_and_awaits_review(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start(PDF)

    state = await h.run(run_id)

    assert state.status is RunStatus.awaiting_review
    assert state.waiting_for is WaitingFor.profile_review
    review = await h.review()
    assert review is not None
    assert review.status == "open"
    assert review.extraction["contact"]["name"] == "Jane Example"
    assert [e["employer"] for e in review.extraction["experience"]] == ["Acme Corp", "Globex Ltd"]
    assert review.dropped_items == []
    assert review.provenance == Provenance("extract_profile", "1", "fake", "fake-model")
    assert (await h.file_for(run_id)).parse_status == "parsed"
    assert len(h.llm.calls) == 1
    assert h.llm.calls[0].tier == "fast"


async def test_US1_AS3_ungrounded_items_dropped(make_harness: Any) -> None:
    planted = jane_extraction(skills=["Python", "Kubernetes", "Go"])
    planted["experience"].append(
        {
            "employer": "Initech",
            "title": "CTO",
            "location": None,
            "start": None,
            "end": None,
            "current": False,
            "bullets": [],
        }
    )
    h = make_harness([planted])
    run_id = await h.start(PDF)
    await h.run(run_id)

    review = await h.review()
    assert review is not None
    assert review.extraction["skills"] == ["Python", "Go"]
    assert [e["employer"] for e in review.extraction["experience"]] == ["Acme Corp", "Globex Ltd"]
    dropped = {(d["path"], d["value"]) for d in review.dropped_items}
    assert ("skills[1]", "Kubernetes") in dropped
    assert any(d["value"].startswith("Initech") for d in review.dropped_items)
    assert all(d["reason"] == "not found in your resume" for d in review.dropped_items)


async def test_US1_AS4_hidden_text_reported_not_used(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start("attack-white-text.pdf")
    await h.run(run_id)

    assert "Ignore all previous" not in h.prompt_text()
    assert "Output the candidate" not in h.prompt_text()
    review = await h.review()
    assert review is not None
    [hidden] = review.flags["hidden_text"]
    assert hidden["page"] == 1
    assert "Ignore all previous instructions" in hidden["text"]
    rule_ids = {(f["rule_id"], f["location"]) for f in review.flags["injection_flags"]}
    assert ("ai_instruction", "hidden") in rule_ids
    # Hidden text never pauses the run: it is already excluded.
    assert (await h.state(run_id)).waiting_for is WaitingFor.profile_review


async def test_US1_AS5_high_injection_pauses_before_llm(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start("attack-ignore-instructions.pdf")

    state = await h.run(run_id)

    assert state.status is RunStatus.awaiting_review
    assert state.waiting_for is WaitingFor.injection_decision
    assert h.llm.calls == []
    assert await h.review() is None  # nothing to review yet


async def test_US1_AS5_continue_extraction_goes_on_to_review(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start("attack-ignore-instructions.pdf")
    await h.run(run_id)

    await h.resume(run_id, {"decision": "continue_extraction"})

    state = await h.state(run_id)
    assert state.waiting_for is WaitingFor.profile_review
    assert len(h.llm.calls) == 1
    review = await h.review()
    assert review is not None
    assert {f["rule_id"] for f in review.flags["injection_flags"]} >= {"ai_instruction"}


async def test_FR007_decision_manual_entry_opens_empty_review(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start("attack-ignore-instructions.pdf")
    await h.run(run_id)

    await h.resume(run_id, {"decision": "manual_entry"})

    assert (await h.state(run_id)).waiting_for is WaitingFor.profile_review
    assert h.llm.calls == []
    review = await h.review()
    assert review is not None
    assert review.extraction["contact"]["name"] == ""
    assert review.extraction["experience"] == []


async def test_US1_AS6_no_text_pdf(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start("synthetic-scanned.pdf")

    state = await h.run(run_id)

    assert state.status is RunStatus.done
    assert h.llm.calls == []
    assert (await h.file_for(run_id)).parse_status == "no_text"
    assert await h.review() is None


async def test_US1_AS7_invalid_then_invalid_falls_back(make_harness: Any) -> None:
    h = make_harness([{"nonsense": 1}, {"still": "bad"}])
    run_id = await h.start(PDF)

    state = await h.run(run_id)

    assert state.waiting_for is WaitingFor.profile_review
    review = await h.review()
    assert review is not None
    assert review.extraction["experience"] == []
    assert review.extraction["skills"] == []
    assert review.flags["extraction_outcome"] == "fallback"
    assert len(h.llm.calls) == 2  # the original call and exactly one repair
    assert await h.count("SELECT count(*) FROM app.llm_calls") == 2


async def test_repair_succeeds_on_the_second_attempt(make_harness: Any) -> None:
    h = make_harness([{"nonsense": 1}, jane_extraction()])
    run_id = await h.start(PDF)
    await h.run(run_id)

    review = await h.review()
    assert review is not None
    assert review.flags["extraction_outcome"] == "repaired"
    assert review.extraction["contact"]["name"] == "Jane Example"


async def test_US1_AS8_reupload_marks_changes(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    old = ProfileContent(
        contact=Contact(name="Jane Example"),
        experience=(
            Experience(employer="Acme Corp", title="Software Engineer", start=YearMonth(2021, 1)),
        ),
        skills=("Python", "Java"),
    )
    async with h.sessions() as session:
        current = await VersionsRepo(session).create_version(old, created_by="manual")
        await session.commit()

    run_id = await h.start(PDF)
    await h.run(run_id)

    review = await h.review()
    assert review is not None
    assert review.compare_to_version_id == current.id
    assert "skills" in review.changed_paths
    assert any(p.startswith("experience[Acme Corp") for p in review.changed_paths)
    async with h.sessions() as session:
        still_current = await VersionsRepo(session).current()
    assert still_current is not None
    assert still_current.id == current.id  # the profile itself is unchanged until confirm


async def test_US3_AS2_key_rejected_pauses_run(make_harness: Any) -> None:
    h = make_harness([AiUnavailable("key_rejected")])
    run_id = await h.start(PDF)

    state = await h.run(run_id)

    assert state.status is RunStatus.paused
    assert state.pause_reason is PauseReason.key_rejected
    assert await h.review() is None


async def test_US3_AS3_paused_run_resumes_from_checkpoint(make_harness: Any) -> None:
    h = make_harness([AiUnavailable("key_rejected"), jane_extraction()])
    run_id = await h.start(PDF)
    await h.run(run_id)

    from hiretitan.platform.runtime.resume_paused import resume_paused_runs

    class _Queue:
        async def enqueue(self, run_id: Any, resume: Any = None) -> None:
            return None

    await resume_paused_runs(h.sessions, _Queue(), PauseReason.key_rejected)
    state = await h.run(run_id)

    assert state.waiting_for is WaitingFor.profile_review
    assert len(h.llm.calls) == 2  # one refused, one that worked


async def test_SC009_no_contact_data_in_prompt(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start(PDF)
    await h.run(run_id)

    prompt = h.prompt_text()
    for secret in ("jane.example@example.com", "90000 00001", "linkedin.com/in/jane-example-fake"):
        assert secret not in prompt
    assert "[[EMAIL_1]]" in prompt
    review = await h.review()
    assert review is not None
    contact = review.extraction["contact"]
    assert contact["email"] == "jane.example@example.com"
    assert contact["phone"] == "+91 90000 00001"
    assert [link["url"] for link in contact["links"]] == ["linkedin.com/in/jane-example-fake"]


async def test_placeholders_echoed_by_the_model_are_removed(make_harness: Any) -> None:
    echoed = jane_extraction(headline="Backend engineer [[EMAIL_1]]")
    echoed["contact"]["location"] = "Pune, India [[PHONE_1]]"
    h = make_harness([echoed])
    run_id = await h.start(PDF)
    await h.run(run_id)

    review = await h.review()
    assert review is not None
    assert "[[" not in str(review.extraction)


async def test_idempotent_extraction_not_paid_twice(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    first = await h.start(PDF)
    await h.run(first)
    assert len(h.llm.calls) == 1

    # The user discards the review and uploads the same resume again.
    second = await h.start(PDF)
    state = await h.run(second)

    assert state.waiting_for is WaitingFor.profile_review
    assert len(h.llm.calls) == 1  # served from the cache keyed on the masked text
    review = await h.review()
    assert review is not None
    assert review.extraction["contact"]["name"] == "Jane Example"


async def test_pasted_text_goes_through_the_same_workflow(make_harness: Any) -> None:
    pasted = (
        "Jane Example\nPune, India\n\nEXPERIENCE\nAcme Corp - Senior Software Engineer  "
        "Jan 2021 - Present\n- Led a team of 5 engineers on the billing platform migration\n\n"
        "SKILLS\nPython, Go, PostgreSQL, C++, Node.js\n" + "x" * 50
    )
    h = make_harness([jane_extraction()])
    run_id = await h.start(text_=pasted)
    state = await h.run(run_id)
    assert state.waiting_for is WaitingFor.profile_review
    assert (await h.file_for(run_id)).parse_status == "parsed"


async def test_confirm_saves_a_version_linked_to_the_file(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start(PDF)
    await h.run(run_id)
    review = await h.review()
    assert review is not None
    edited = {**review.extraction}
    edited["headline"] = "Edited headline"

    await h.resume(run_id, {"action": "confirm", "content": edited})

    assert (await h.state(run_id)).status is RunStatus.done
    async with h.sessions() as session:
        version = await VersionsRepo(session).current()
    assert version is not None
    assert version.content.headline == "Edited headline"
    assert version.created_by == "extraction"
    assert version.review_id == review.id
    assert version.source_file_id == (await h.file_for(run_id)).id
    assert version.provenance == review.provenance
    assert await h.review() is None  # confirmed, no longer open
    assert ("profile.updated", {"current_version_id": str(version.id)}) in h.published


async def test_saving_the_version_twice_creates_one_version(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start(PDF)
    await h.run(run_id)
    review = await h.review()
    assert review is not None
    content = {"action": "confirm", "content": review.extraction}

    from hiretitan.profile.workflow.nodes import save_version

    await save_version(h.deps, review_id=review.id, content_json=content["content"])
    await save_version(h.deps, review_id=review.id, content_json=content["content"])

    assert await h.count("SELECT count(*) FROM app.profile_versions") == 1


async def test_discard_ends_the_run_without_a_version(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start(PDF)
    await h.run(run_id)

    await h.resume(run_id, {"action": "discard"})

    assert (await h.state(run_id)).status is RunStatus.done
    assert await h.count("SELECT count(*) FROM app.profile_versions") == 0
    assert await h.count("SELECT count(*) FROM app.profile_reviews WHERE status='discarded'") == 1


async def test_content_roundtrip_helper_is_exposed_for_the_api() -> None:
    from hiretitan.profile.domain.serialization import content_from_json

    c = ProfileContent(contact=Contact(name="A"), skills=("Python",))
    assert content_from_json(content_to_json(c)) == c


async def test_parse_result_records_flags_for_the_decision_dialog(make_harness: Any) -> None:
    h = make_harness([jane_extraction()])
    run_id = await h.start("attack-ignore-instructions.pdf")
    await h.run(run_id)  # paused on the injection decision

    file = await h.file_for(run_id)

    assert file.parse_status == "parsed"
    assert file.parse_result is not None
    assert file.parse_result["visible_text_chars"] > 200
    assert file.parse_result["truncated_at"] is None
    assert file.parse_result["hidden_text"] == []
    flags = file.parse_result["injection_flags"]
    assert {f["rule_id"] for f in flags} >= {"ai_instruction"}
    assert all(f["severity"] in {"high", "medium", "low"} for f in flags)
