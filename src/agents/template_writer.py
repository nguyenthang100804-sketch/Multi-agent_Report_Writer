"""Short, deterministic quantitative prose from section-scoped source data."""
from __future__ import annotations

import re

from src.agents.draft_rendering import render_block
from src.agents.planner_rules import RATIO_LABELS
from src.agents.verification import attach_code_limitations
from src.agents.writer_menu import build_placeholder_menu, validate_template_menu
from src.schemas.report_schema import DraftLimitation, FactTask, NotesTask, RatioTask, SectionDraft, TimeSeriesTask


FACT_PRIORITIES = {
    "S3": ("revenue", "net_income"),
    "S4": ("assets", "liabilities"),
    "S5": ("operating_cash_flow", "financing_cash_flow"),
}
CALCULATION_PRIORITIES = {
    "S3": (("revenue", "yoy"), ("gross_margin", "ratio"),
           ("revenue", "cagr"), ("revenue", "trend")),
    "S4": (("assets", "yoy"), ("debt_to_assets", "ratio"),
           ("equity_to_assets", "ratio")),
    "S5": (("operating_cash_flow", "difference"),
           ("financing_cash_flow", "difference"), ("cfo_to_net_income", "ratio")),
}


def _calculation_source(section, calculation_id: str) -> str | None:
    spec = next((item for item in section.calculation_specs
                 if item.calculation_id == calculation_id), None)
    if spec is not None:
        return spec.source_task_id
    return next((task.task_id for task in section.research_tasks
                 if isinstance(task, RatioTask) and
                 calculation_id.startswith(task.task_id + ":")), None)


def _latest_key(ids: list[str], calculations: dict) -> str | None:
    if not ids:
        return None
    def end_year(key):
        params = calculations[key].parameters
        return int(params.get("current_year", params.get("end_year", params.get("year", 0))))
    return max(ids, key=lambda key: (end_year(key), key))


def build_template_writer():
    """Return a Writer node that writes up to five sourced observations per section."""
    def write(state: dict) -> dict:
        drafts = {}
        evidence = state["evidence_by_id"]
        calculations = state["calculations_by_id"]
        aliases = state["evidence_aliases"]
        aliases_by_id = {evidence_id: alias for alias, evidence_id in aliases.items()}
        for section in state["outline"].sections:
            numeric_tasks = [task for task in section.research_tasks
                             if isinstance(task, (FactTask, TimeSeriesTask))]
            note_tasks = ([task for task in section.research_tasks
                           if isinstance(task, NotesTask)]
                          if section.section_id in {"S1", "S2", "S6", "S7"} else [])
            if not numeric_tasks and not section.calculations_allowed and not note_tasks:
                continue
            menu = build_placeholder_menu(section, state)
            blocks = []

            def add(template: str) -> None:
                validate_template_menu(template, menu)
                blocks.append(render_block(f"{section.section_id}:b{len(blocks) + 1}",
                    template, evidence, calculations, aliases))

            add("## " + section.title)
            skipped_notes = []
            for task in note_tasks:
                matches = menu["notes"].get(task.task_id, [])
                if matches:
                    excerpt = max(matches, key=lambda item: (
                        item["excerpt"].rstrip().endswith((".", "!", "?")),
                        -len(item["excerpt"])))
                    add(f"Trích từ tài liệu {excerpt['year_token']}: “{excerpt['token']}”")
                elif state["research_results"].get(task.task_id) and \
                        state["research_results"][task.task_id].evidence_ids:
                    skipped_notes.append(task.query.lower())
            if skipped_notes:
                topics = "; ".join(dict.fromkeys(skipped_notes))
                if re.search(r"\d", topics):
                    topics = "các truy vấn định tính"
                add(f"Chưa chọn được trích đoạn đủ nội dung cho {topics} "
                    "trong các đoạn đã truy xuất.")
            group_id = next((key for key in (section.section_id, *section.template_section_ids)
                             if key in FACT_PRIORITIES), None)
            fact_order = FACT_PRIORITIES.get(group_id, tuple(task.task_id for task in numeric_tasks))
            selected_facts = []
            for task_id in (() if group_id in CALCULATION_PRIORITIES else fact_order):
                task = next((item for item in numeric_tasks if item.task_id == task_id), None)
                research = state["research_results"].get(task_id)
                if task is None or research is None:
                    continue
                candidates = [key for key in research.evidence_ids
                              if key in aliases_by_id and aliases_by_id[key] in menu["facts"]]
                if not candidates:
                    continue
                key = max(candidates, key=lambda item: evidence[item].payload.fiscal_year)
                selected_facts.append((task, aliases_by_id[key]))
                if len(selected_facts) == 2:
                    break
            for task, alias in selected_facts:
                label = task.metric_name or menu["facts"][alias]["label"]
                add(f"{label} {{{{Y:{alias}}}}} là {{{{{alias}}}}}.")

            selected_calculations = []
            priorities = CALCULATION_PRIORITIES.get(group_id, ())
            for source, operation in priorities:
                candidates = [key for key in section.calculations_allowed
                              if key in calculations and calculations[key].status == "ok" and
                              calculations[key].operation == operation and
                              _calculation_source(section, key) == source]
                key = _latest_key(candidates, calculations)
                if key is None:
                    continue
                selected_calculations.append(key)
            if not priorities:
                candidates = [key for key in section.calculations_allowed
                              if key in calculations and calculations[key].status == "ok"]
                selected_calculations = sorted(candidates,
                    key=lambda key: int(calculations[key].parameters.get("end_year", 0)),
                    reverse=True)[:max(0, 5 - len(selected_facts))]
            selected_calculations = selected_calculations[:max(0, 5 - len(selected_facts))]
            tasks = {task.task_id: task for task in section.research_tasks}
            for key in selected_calculations:
                calculation = calculations[key]
                source = _calculation_source(section, key)
                label = (RATIO_LABELS.get(source, "Tỷ lệ")
                         if calculation.operation == "ratio" else
                         getattr(tasks.get(source), "metric_name", None) or "Chỉ tiêu")
                period = f"{{{{P:C:{key}}}}}"
                if calculation.operation == "trend":
                    add(f"{label} {{{{T:{key}}}}} trong {period}.")
                else:
                    prefix = {"yoy": "Mức thay đổi của ",
                              "cagr": "Tốc độ tăng trưởng kép hằng năm của ",
                              "difference": "Chênh lệch của ", "ratio": ""}[
                                  calculation.operation]
                    add(f"{prefix}{label} {period} là {{{{C:{key}}}}}.")

            if group_id == "S4":
                cash = [(alias, item) for alias, item in menu["facts"].items()
                        if item["label"] == "Tiền và các khoản tương đương tiền"]
                if cash:
                    alias, _ = max(cash, key=lambda pair: pair[1]["fiscal_year"])
                    add(f"Tiền và các khoản tương đương tiền {{{{Y:{alias}}}}} "
                        f"đạt {{{{{alias}}}}}.")

            current = [draft.revision for draft in state.get("section_drafts", {}).values()
                       if draft.section_id == section.section_id and
                       draft.outline_version == state.get("outline_version", 1)]
            revision = max(current, default=0) + 1
            draft = SectionDraft(section_id=section.section_id,
                                 outline_version=state.get("outline_version", 1),
                                 revision=revision, blocks=blocks)
            for task in section.research_tasks:
                research = state["research_results"].get(task.task_id)
                if research is None:
                    continue
                for warning in research.warnings:
                    match = re.fullmatch(r"period_inconsistency:(\d{4})->(\d{4})", warning)
                    if match is None:
                        continue
                    related = [key for key in research.evidence_ids
                               if key in evidence and evidence[key].payload.fiscal_year
                               in (int(match[1]), int(match[2]))]
                    if related:
                        draft.limitations.append(DraftLimitation(
                            warning_code=warning, evidence_ids=related,
                            block_id=draft.blocks[-1].block_id))
            draft = attach_code_limitations(draft, section,
                calculations, state["research_results"])
            key = ((draft.section_id, revision) if draft.outline_version == 1 else
                   (draft.outline_version, draft.section_id, revision))
            drafts[key] = draft
        return {"section_drafts": drafts}

    return write
