"""Serializable LangGraph state and collision-safe reducers."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from src.schemas.report_schema import (
    CalculationResult, EvidenceRecord, OutlineDecision, PlannerNote, PlannerObservation,
    ReportOutline, ReportRequest, ResearchResult,
    SectionDraft, VerificationResult,
)
from src.agents.verifier_contract import VerifierRunLog
from src.agents.writer_contract import WriterRunLog

try:
    from langgraph.graph.message import add_messages
except ImportError:  # LangGraph is installed when the graph is built.
    def add_messages(left: list, right: list) -> list:
        return left + right


def merge_immutable(left: dict, right: dict) -> dict:
    merged = left.copy()
    for key, value in right.items():
        if key in merged and merged[key] != value:
            raise ValueError(f"Conflicting content for ID {key}")
        merged[key] = value
    return merged


def merge_research_results(left: dict[str, ResearchResult],
                           right: dict[str, ResearchResult]) -> dict[str, ResearchResult]:
    return {**left, **right}


def merge_revisions(left: dict[tuple[str, int], object],
                    right: dict[tuple[str, int], object]) -> dict[tuple[str, int], object]:
    merged = left.copy()
    for key, value in right.items():
        if key in merged and merged[key] != value:
            raise ValueError(f"Conflicting revision {key}")
        merged[key] = value
    return merged


FULL_SECTION_IDS = ("S1", "S2", "S3", "S4", "S5", "S6", "S7")


def _full_outline_sections_preserved(state: ReportState, outline: ReportOutline) -> bool:
    original = state.get("outlines_by_revision", {}).get(1)
    if original is None or tuple(section.section_id for section in original.sections) != FULL_SECTION_IDS:
        return True
    return all(
        (current.section_id, current.title, current.objective) ==
        (first.section_id, first.title, first.objective)
        for current, first in zip(outline.sections, original.sections)
    ) and len(outline.sections) == len(FULL_SECTION_IDS)


def install_outline_revision(state: ReportState, outline: ReportOutline) -> dict:
    """Keep earlier outlines and revoke approval when a new revision is installed."""
    version = state.get("outline_version", 0) + 1
    history = dict(state.get("outlines_by_revision", {}))
    if version in history:
        raise ValueError(f"Outline revision {version} already exists")
    if state.get("outline") and state["outline"].outline_id != outline.outline_id:
        raise ValueError("A revision must keep the outline ID")
    if not _full_outline_sections_preserved(state, outline):
        raise ValueError("A full report must keep S1–S7 and their main titles and objectives")
    history[version] = outline.model_copy(deep=True)
    return {"outline": outline, "outline_version": version,
            "outlines_by_revision": history, "outline_approved_version": None,
            "run_status": "needs_clarification"}


def approve_outline_revision(state: ReportState) -> dict[str, int]:
    if not state.get("outline") or not state.get("outline_version"):
        raise ValueError("No current outline to approve")
    return {"outline_approved_version": state["outline_version"]}


def approved_draft(state: ReportState, section_id: str) -> SectionDraft | None:
    """Only the current outline and exact verified revision may be published."""
    if state.get("outline_approved_version") != state.get("outline_version"):
        return None
    drafts = [draft for draft in state.get("section_drafts", {}).values()
              if draft.section_id == section_id and
              draft.outline_version == state["outline_version"]]
    if not drafts:
        return None
    draft = max(drafts, key=lambda item: item.revision)
    verification = state.get("verification_results", {}).get(
        (state["outline_version"], section_id, draft.revision))
    if verification is None and state["outline_version"] == 1:
        verification = state.get("verification_results", {}).get((section_id, draft.revision))
    if (verification is None or verification.status != "passed" or
            verification.level != "full" or
            verification.outline_version not in (None, state["outline_version"])):
        return None
    return draft


def can_complete(state: ReportState) -> bool:
    outline = state.get("outline")
    if state.get("full_outline_required") and (not outline or
            tuple(section.section_id for section in outline.sections) != FULL_SECTION_IDS):
        return False
    return bool(outline) and _full_outline_sections_preserved(state, outline) and all(
        approved_draft(state, section.section_id) is not None
        for section in outline.sections
    )


def complete_run(state: ReportState) -> dict[str, str]:
    """The only supported transition to completed for a graph node."""
    if not can_complete(state):
        raise ValueError("Cannot complete: a current section lacks passed verification")
    return {"run_status": "completed"}


def is_run_complete(state: ReportState) -> bool:
    return state.get("run_status") == "completed" and can_complete(state)


class StaleEvidenceError(ValueError):
    pass


def check_snapshot_on_resume(state: ReportState,
                             current_snapshot_version: str | dict[str, str]) -> None:
    """Compare fact and note snapshot versions before resuming a checkpoint."""
    versions = (current_snapshot_version if isinstance(current_snapshot_version, dict)
                else {"fact": current_snapshot_version, "note": current_snapshot_version})
    stale = [key for key, record in state.get("evidence_by_id", {}).items()
             if record.snapshot_version != versions.get(record.kind)]
    stale.extend(key for key, observation in state.get("planner_observations", {}).items()
                 if (observation.tool_name != "metric_name_resolver" and
                     observation.snapshot_version != versions.get(
                         "note" if observation.tool_name == "search_notes_tool" else "fact")))
    if stale:
        raise StaleEvidenceError(f"Stale evidence on resume: {', '.join(stale)}")


def snapshot_version_for_db(db_path: str | Path) -> str:
    """Read the stable ingestion ID, with a logical-row fallback for older DBs."""
    from src.storage.duckdb_manager import DuckDBManager

    with DuckDBManager(db_path) as manager:
        return manager.get_snapshot_id()


def snapshot_version_for_note_index(manifest_path: str | Path | None = None) -> str:
    """Use the published index manifest as the note snapshot identity."""
    if manifest_path is None:
        from src.storage.active_corpus import active_path
        manifest_path = active_path("manifest")
    return "note:" + hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()


def report_checkpoint_serde():
    """Allow only this project's typed contracts in LangGraph checkpoints."""
    import inspect

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from pydantic import BaseModel

    from src.agents import coverage, verifier_contract, writer_contract
    from src.schemas import report_schema
    from src.tools import schemas as tool_schemas

    models = []
    for module in (report_schema, tool_schemas, coverage, verifier_contract, writer_contract):
        models.extend(cls for _, cls in inspect.getmembers(module, inspect.isclass)
                      if cls.__module__ == module.__name__ and issubclass(cls, BaseModel))
    return JsonPlusSerializer(allowed_msgpack_modules=models)


def state_to_json(state: ReportState) -> str:
    """Encode tuple revision keys as arrays of model values for JSON checkpoints."""
    if state.get("run_status") == "completed" and not can_complete(state):
        raise ValueError("Completed state lacks current passed verification")

    def encode(value):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {key: encode(item) for key, item in value.items()}
        if isinstance(value, list):
            return [encode(item) for item in value]
        return value

    data = {key: encode(value) for key, value in state.items()
            if key not in ("section_drafts", "verification_results")}
    for field in ("section_drafts", "verification_results"):
        data[field] = [encode(value) for value in state.get(field, {}).values()]
    return json.dumps(data, ensure_ascii=False)


def state_from_json(source: str) -> ReportState:
    data = json.loads(source)
    models = {"request": ReportRequest, "outline": ReportOutline}
    for key, model in models.items():
        if key in data:
            data[key] = model.model_validate(data[key])
    data["planner_notes"] = [PlannerNote.model_validate(item)
                             for item in data.get("planner_notes", [])]
    data["outline_decisions"] = [OutlineDecision.model_validate(item)
                                 for item in data.get("outline_decisions", [])]
    data["planner_observations"] = {
        key: PlannerObservation.model_validate(item)
        for key, item in data.get("planner_observations", {}).items()}
    data["writer_run_logs"] = {
        key: WriterRunLog.model_validate(item)
        for key, item in data.get("writer_run_logs", {}).items()}
    if "verifier_run_logs" in data:
        data["verifier_run_logs"] = {
            key: VerifierRunLog.model_validate(item)
            for key, item in data["verifier_run_logs"].items()}
    data["outlines_by_revision"] = {
        int(version): ReportOutline.model_validate(outline)
        for version, outline in data.get("outlines_by_revision", {}).items()}
    for key, model in (("research_results", ResearchResult),
                       ("evidence_by_id", EvidenceRecord),
                       ("calculations_by_id", CalculationResult)):
        data[key] = {item_id: model.model_validate(value)
                     for item_id, value in data.get(key, {}).items()}
    for key, model in (("section_drafts", SectionDraft),
                       ("verification_results", VerificationResult)):
        values = [model.model_validate(value) for value in data.get(key, [])]
        keys = [((value.outline_version, value.section_id, value.revision)
                 if value.outline_version not in (None, 1) else
                 (value.section_id, value.revision)) for value in values]
        if len(set(keys)) != len(values):
            raise ValueError(f"Duplicate {key} revision")
        data[key] = dict(zip(keys, values))
    if data.get("run_status") == "completed" and not can_complete(data):
        raise ValueError("Completed state lacks current passed verification")
    return data


class ReportState(TypedDict, total=False):
    request: ReportRequest
    outline: ReportOutline
    full_outline_required: bool
    outline_version: int
    outline_approved_version: int | None
    outlines_by_revision: Annotated[dict[int, ReportOutline], merge_immutable]
    planner_notes: list[PlannerNote]
    planner_available_scopes: dict[str, list[int]]
    outline_decisions: list[OutlineDecision]
    planner_observations: Annotated[dict[str, PlannerObservation], merge_immutable]
    planner_prompt_version: str | None
    planner_used_fallback: bool
    writer_run_logs: Annotated[dict[str, WriterRunLog], merge_immutable]
    writer_completed: bool
    verifier_run_logs: Annotated[dict[str, VerifierRunLog], merge_immutable]
    research_results: Annotated[dict[str, ResearchResult], merge_research_results]
    research_completed: bool
    evidence_by_id: Annotated[dict[str, EvidenceRecord], merge_immutable]
    evidence_aliases: dict[str, str]
    calculations_by_id: Annotated[dict[str, CalculationResult], merge_immutable]
    section_drafts: Annotated[dict[tuple, SectionDraft], merge_revisions]
    verification_results: Annotated[dict[tuple, VerificationResult], merge_revisions]
    revision_counts: dict[str, int]
    tool_call_counts: dict[str, int]
    retry_counts: dict[str, int]
    run_status: Literal["pending", "running", "awaiting_approval", "needs_clarification", "rejected", "completed", "incomplete", "error"]
    errors: list[str]
    final_report: str | None
    messages: Annotated[list, add_messages]
