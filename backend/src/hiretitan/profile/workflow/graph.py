"""The ``profile_ingest`` graph (contracts/profile-ingest-workflow.md).

parse -> sanitize/screen -> (pause on a high injection flag) -> mask contacts -> extract
(AI) -> validate and ground -> merge contacts -> compare with the current profile ->
open the review -> (pause for the user) -> save the version.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from hiretitan.platform.runtime.infra.runs_repo import Run
from hiretitan.platform.runtime.runner import WorkflowDef
from hiretitan.profile.workflow import nodes
from hiretitan.profile.workflow.nodes import IngestDeps, IngestState, State

WORKFLOW_NAME = "profile_ingest"

__all__ = ["WORKFLOW_NAME", "IngestDeps", "profile_ingest_workflow"]


def _bound(
    fn: Callable[[IngestDeps, State], Awaitable[State]], deps: IngestDeps
) -> Callable[[State], Awaitable[State]]:
    return partial(fn, deps)


def build_graph(deps: IngestDeps) -> StateGraph[Any]:
    graph = StateGraph(IngestState)
    graph.add_node("parse_document", cast(Any, _bound(nodes.parse_document, deps)))
    graph.add_node("sanitize_and_screen", cast(Any, _bound(nodes.sanitize_and_screen, deps)))
    graph.add_node("await_injection_decision", cast(Any, nodes.await_injection_decision))
    graph.add_node("manual_extraction", cast(Any, _bound(nodes.manual_extraction, deps)))
    graph.add_node("mask_contacts", cast(Any, _bound(nodes.mask_contacts_node, deps)))
    graph.add_node("extract_profile", cast(Any, _bound(nodes.extract_profile, deps)))
    graph.add_node("assemble_profile", cast(Any, _bound(nodes.assemble_profile, deps)))
    graph.add_node("compare_with_current", cast(Any, _bound(nodes.compare_with_current, deps)))
    graph.add_node("open_review", cast(Any, _bound(nodes.open_review, deps)))
    graph.add_node("await_review", cast(Any, nodes.await_review))
    graph.add_node("save_profile_version", cast(Any, _bound(nodes.save_profile_version, deps)))
    graph.add_node("discard_review", cast(Any, _bound(nodes.discard_review, deps)))
    graph.add_node("end_no_text", cast(Any, lambda state: {}))

    graph.add_edge(START, "parse_document")
    graph.add_conditional_edges(
        "parse_document",
        nodes.after_parse,
        {"sanitize_and_screen": "sanitize_and_screen", "end_no_text": "end_no_text"},
    )
    graph.add_edge("end_no_text", END)
    graph.add_conditional_edges(
        "sanitize_and_screen",
        nodes.after_screen,
        {"await_injection_decision": "await_injection_decision", "mask_contacts": "mask_contacts"},
    )
    graph.add_conditional_edges(
        "await_injection_decision",
        nodes.after_decision,
        {"manual_extraction": "manual_extraction", "mask_contacts": "mask_contacts"},
    )
    graph.add_edge("mask_contacts", "extract_profile")
    graph.add_edge("extract_profile", "assemble_profile")
    graph.add_edge("assemble_profile", "compare_with_current")
    graph.add_edge("manual_extraction", "compare_with_current")
    graph.add_edge("compare_with_current", "open_review")
    graph.add_edge("open_review", "await_review")
    graph.add_conditional_edges(
        "await_review",
        nodes.after_review,
        {"save_profile_version": "save_profile_version", "discard_review": "discard_review"},
    )
    graph.add_edge("save_profile_version", END)
    graph.add_edge("discard_review", END)
    return graph


def profile_ingest_workflow(deps: IngestDeps) -> WorkflowDef:
    def build(saver: BaseCheckpointSaver[Any]) -> Any:
        return build_graph(deps).compile(checkpointer=saver)

    def initial_input(run: Run) -> dict[str, Any]:
        return {"run_id": str(run.id), "resume_file_id": str(run.subject_id)}

    return WorkflowDef(build=build, initial_input=initial_input)
