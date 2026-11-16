"""Model-selected, source-bound prose for qualitative report sections."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from src.agents.draft_rendering import render_block
from src.agents.verification import attach_code_limitations, verify_section_deterministically
from src.agents.writer_contract import (
    QualitativeOutput, WriterModel, WriterRequest, WriterResponse, WriterRunLog,
)
from src.schemas.report_schema import NotesTask, SectionDraft
from src.tools.schemas import NoteEvidence


PROMPT_PATH = Path(__file__).parent / "prompts" / "qualitative_writer_system.md"
PROMPT_VERSION = "w6-v1"


def build_qualitative_view(section, state: dict) -> dict:
    """Give the model only notes retrieved for this section's planned tasks."""
    aliases = state["evidence_aliases"]
    aliases_by_id = {evidence_id: alias for alias, evidence_id in aliases.items()}
    evidence = state["evidence_by_id"]
    tasks = []
    chunks = {}
    for task in section.research_tasks:
        if not isinstance(task, NotesTask):
            continue
        result = state["research_results"].get(task.task_id)
        available = []
        for evidence_id in result.evidence_ids if result else []:
            record = evidence.get(evidence_id)
            alias = aliases_by_id.get(evidence_id)
            if alias is None or record is None or not isinstance(record.payload, NoteEvidence):
                continue
            available.append(alias)
            note = record.payload
            chunks[alias] = {"text": note.text, "fiscal_year": note.fiscal_year,
                             "citation_tag": note.citation_tag,
                             "section": note.section}
        tasks.append({"task_id": task.task_id, "query": task.query,
                      "fiscal_year": task.fiscal_year,
                      "research_status": result.status if result else "no_evidence",
                      "evidence_aliases": available})
    return {"section_id": section.section_id, "title": section.title,
            "objective": section.objective, "tasks": tasks, "chunks": chunks}


def _compose(output: QualitativeOutput, section, state: dict,
             fallback: SectionDraft) -> SectionDraft:
    evidence = state["evidence_by_id"]
    aliases = state["evidence_aliases"]
    research = state["research_results"]
    calculations = state["calculations_by_id"]
    tasks = {task.task_id: task for task in section.research_tasks
             if isinstance(task, NotesTask)}
    blocks = [fallback.blocks[0].model_copy(deep=True)]
    seen = set()
    used_tasks = set()
    for item in output.blocks:
        if item.block_id in seen:
            raise ValueError("duplicate_block_id")
        seen.add(item.block_id)
        if item.task_id in used_tasks:
            raise ValueError("duplicate_task_id")
        used_tasks.add(item.task_id)
        task = tasks.get(item.task_id)
        result = research.get(item.task_id)
        evidence_id = aliases.get(item.evidence_alias)
        if task is None or result is None or evidence_id not in result.evidence_ids:
            raise ValueError("evidence_outside_task")
        record = evidence.get(evidence_id)
        if record is None or not isinstance(record.payload, NoteEvidence):
            raise ValueError("not_note_evidence")
        quote = item.quote.strip()
        start = record.payload.text.find(quote)
        if (start < 0 or len(quote.split()) < 8 or quote.endswith(":") or
                quote.count("|") >= 2 or re.match(r"^\d+[.]\s", quote)):
            raise ValueError("quote_not_substantive_or_not_verbatim")
        observation = item.observation.strip()
        if (re.search(r"\d|\{\{|\}\}|\[Doc_", observation) or
                "\n" in observation or len(re.findall(r"[.!?](?=\s|$)", observation)) > 1):
            raise ValueError("invalid_observation")
        observation = observation.rstrip(". ")
        template = (f"{observation}. Trích từ tài liệu {{{{Y:{item.evidence_alias}}}}}: "
                    f"“{{{{N:{item.evidence_alias}:{start}:{start + len(quote)}}}}}”")
        blocks.append(render_block(f"{section.section_id}:q:{item.block_id}",
                                   template, evidence, calculations, aliases))
    draft = SectionDraft(section_id=section.section_id,
                         outline_version=fallback.outline_version,
                         revision=fallback.revision, blocks=blocks)
    return attach_code_limitations(draft, section, calculations, research)


def write_qualitative_section(model: WriterModel, section, state: dict,
                              fallback: SectionDraft, *, max_repairs: int,
                              record_raw_outputs: bool) -> tuple[SectionDraft, WriterRunLog]:
    view = build_qualitative_view(section, state)
    started = time.perf_counter()
    errors_by_attempt, warnings_by_attempt, raw_outputs = [], [], []
    block_counts, attempt_times = [], []
    token_usage: dict[str, int] = {}
    accepted = None
    feedback = []
    if view["chunks"]:
        for _ in range(max_repairs + 1):
            attempt_started = time.perf_counter()
            request = WriterRequest(
                system=PROMPT_PATH.read_text(encoding="utf-8"),
                section_view=json.dumps(view, ensure_ascii=False),
                feedback=feedback,
                response_schema=QualitativeOutput.model_json_schema())
            try:
                response = WriterResponse.model_validate(model.generate(request))
            except Exception as exc:
                errors_by_attempt.append([f"model_error: {exc}"])
                warnings_by_attempt.append([])
                raw_outputs.append(None)
                block_counts.append(None)
                attempt_times.append(round((time.perf_counter() - attempt_started) * 1000))
                break
            raw_outputs.append(response.text if record_raw_outputs else None)
            for name, count in response.token_usage.items():
                token_usage[name] = token_usage.get(name, 0) + count
            try:
                output = QualitativeOutput.model_validate_json(response.text)
                block_counts.append(len(output.blocks))
                if not output.blocks:
                    raise ValueError("no_qualitative_blocks")
                candidate = _compose(output, section, state, fallback)
                checked = verify_section_deterministically(
                    candidate, state["request"], state["evidence_by_id"],
                    state["calculations_by_id"], state["research_results"],
                    state["evidence_aliases"], section)
                errors = [f"{issue.error_type}: {issue.reason}"
                          for issue in checked.issues if issue.severity == "error"]
                warnings = [f"{issue.error_type}: {issue.reason}"
                            for issue in checked.issues if issue.severity == "warning"]
                if checked.status == "passed" and not errors:
                    accepted = candidate
            except Exception as exc:
                errors, warnings = [str(exc)], []
                if len(raw_outputs) < len(errors_by_attempt) + 1:
                    raw_outputs.append(None)
                if len(block_counts) < len(errors_by_attempt) + 1:
                    block_counts.append(None)
            errors_by_attempt.append(errors)
            warnings_by_attempt.append(warnings)
            attempt_times.append(round((time.perf_counter() - attempt_started) * 1000))
            if accepted is not None:
                break
            feedback = errors
    log = WriterRunLog(
        section_id=section.section_id, revision=fallback.revision,
        attempts=len(errors_by_attempt), errors_by_attempt=errors_by_attempt,
        warnings_by_attempt=warnings_by_attempt,
        block_counts_by_attempt=block_counts, raw_outputs_by_attempt=raw_outputs,
        attempt_elapsed_ms=attempt_times, used_fallback=accepted is None,
        prompt_version=PROMPT_VERSION, token_usage=token_usage,
        elapsed_ms=round((time.perf_counter() - started) * 1000))
    return accepted or fallback, log
