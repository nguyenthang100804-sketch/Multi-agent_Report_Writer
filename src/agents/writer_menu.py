"""Section-scoped placeholder vocabulary for Writer prompts and validation."""
from __future__ import annotations

import re

from src.agents.draft_rendering import TOKEN
from src.agents.note_excerpts import excerpt_span
from src.schemas.report_schema import NotesTask, SectionPlan
from src.tools.metric_resolver import METRICS
from src.tools.schemas import FactEvidence, NoteEvidence


def build_placeholder_menu(section: SectionPlan, state: dict) -> dict:
    """Expose only section evidence and explicitly allowed successful calculations."""
    evidence = state.get("evidence_by_id", {})
    research = state.get("research_results", {})
    calculations = state.get("calculations_by_id", {})
    aliases = state.get("evidence_aliases", {})
    task_ids = {task.task_id for task in section.research_tasks}
    allowed_ids = {evidence_id for task_id in task_ids if task_id in research
                   for evidence_id in research[task_id].evidence_ids}
    available_calculations = {}
    trends = {}
    for calculation_id in section.calculations_allowed:
        calculation = calculations.get(calculation_id)
        if calculation is None or calculation.status != "ok":
            continue
        if any(key not in evidence for key in calculation.input_evidence_ids):
            continue
        allowed_ids.update(calculation.input_evidence_ids)
        item = {"operation": calculation.operation, "unit": calculation.unit}
        if calculation.operation == "trend":
            item["direction"] = calculation.direction
            item["start_year"] = calculation.parameters.get("start_year")
            item["end_year"] = calculation.parameters.get("end_year")
        (trends if calculation.operation == "trend" else available_calculations)[
            calculation_id] = item
    facts = {}
    notes = {}
    note_sources = {}
    for alias, evidence_id in sorted(aliases.items(),
                                     key=lambda item: int(item[0][1:])):
        if evidence_id not in allowed_ids or evidence_id not in evidence:
            continue
        payload = evidence[evidence_id].payload
        if not isinstance(payload, FactEvidence) or payload.value is None or payload.suspect:
            continue
        label = next((name for name, code, report_type, _ in METRICS
                      if (code, report_type) == (payload.code, payload.report_type)),
                     payload.label)
        facts[alias] = {"label": label, "fiscal_year": payload.fiscal_year,
                        "unit": payload.unit}
    for task in section.research_tasks:
        if section.section_id not in {"S1", "S2", "S6", "S7"} or not isinstance(task, NotesTask):
            continue
        result = research.get(task.task_id)
        if result is None:
            continue
        for evidence_id in result.evidence_ids:
            record = evidence.get(evidence_id)
            if record is None or not isinstance(record.payload, NoteEvidence):
                continue
            alias = next((key for key, value in aliases.items()
                          if value == evidence_id), None)
            if alias is None:
                continue
            note_sources[alias] = record.payload.text
            span = excerpt_span(task, record.payload.text)
            if span is None:
                continue
            token = f"{{{{N:{alias}:{span[0]}:{span[1]}}}}}"
            notes.setdefault(task.task_id, []).append({
                "token": token, "year_token": f"{{{{Y:{alias}}}}}",
                "citation_tag": record.payload.citation_tag,
                "excerpt": record.payload.text[span[0]:span[1]],
            })
    tokens = [token for alias in facts for token in (f"{{{{{alias}}}}}",
                                                      f"{{{{{alias}|abs}}}}",
                                                      f"{{{{Y:{alias}}}}}")]
    tokens.extend(token for key, item in available_calculations.items()
                  for token in ((f"{{{{C:{key}}}}}", f"{{{{P:C:{key}}}}}",
                                 f"{{{{D:{key}}}}}") if item["operation"] in
                                ("difference", "yoy") else
                                (f"{{{{C:{key}}}}}", f"{{{{P:C:{key}}}}}")))
    tokens.extend(token for key in trends
                  for token in (f"{{{{T:{key}}}}}", f"{{{{P:C:{key}}}}}"))
    tokens.extend(token for matches in notes.values() for item in matches
                  for token in (item["token"], item["year_token"]))
    return {"section_id": section.section_id, "facts": facts,
            "calculations": available_calculations, "trends": trends, "notes": notes,
            "note_sources": note_sources, "allowed_tokens": tokens}


def validate_template_menu(template: str, menu: dict) -> None:
    """Reject tokens unavailable to this section, including globally valid aliases."""
    tokens = [match.group() for match in TOKEN.finditer(template)]
    if "{{" in TOKEN.sub("", template) or "}}" in TOKEN.sub("", template):
        raise ValueError("Unknown placeholder")
    allowed = set(menu["allowed_tokens"])
    for token in tokens:
        if token in allowed:
            continue
        year = re.fullmatch(r"\{\{Y:(E[1-9]\d*)\}\}", token)
        if year and year.group(1) in menu.get("note_sources", {}):
            allowed.add(token)
            continue
        note = re.fullmatch(r"\{\{N:(E[1-9]\d*):(\d+):(\d+)\}\}", token)
        if note:
            source = menu.get("note_sources", {}).get(note.group(1), "")
            start, end = int(note.group(2)), int(note.group(3))
            quote = source[start:end]
            if (start < end <= len(source) and 30 <= len(quote) <= 650 and
                    len(quote.split()) >= 8 and not quote.endswith(":")):
                allowed.add(token)
    outside = sorted(set(tokens) - allowed)
    if outside:
        raise ValueError("Placeholder outside section menu: " + ", ".join(outside))
