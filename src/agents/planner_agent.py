"""Tool-using Planner LLM with structured repairs and template fallback."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from src.agents.planner import plan_report, preflight
from src.agents.planner_model import PlannerModel
from src.agents.planner_toolbox import PlannerToolbox
from src.schemas.report_schema import (
    FactTask, NotesTask, PlannerNote, PlannerOutput, PlannerProposal, PlannerTurn,
    ReportRequest, TimeSeriesTask,
)
from src.tools.agent_tools import AgentTools
from src.tools.metric_resolver import metric_name_resolver
from src.tools.schemas import MetricResolverInput
from src.tools.schemas import FactQueryInput, NotesSearchInput, TimeSeriesQueryInput

PROMPT_PATH = Path(__file__).parent / "prompts" / "planner_system.md"
PROMPT_VERSION = "v3"


def _tool_argument_schemas() -> dict:
    """Describe the Planner-facing arguments, excluding codes injected by the toolbox."""
    fields = {
        "metric_name_resolver": (MetricResolverInput, ("metric_name",)),
        "query_fact_tool": (FactQueryInput, ("metric_name", "fiscal_year")),
        "query_time_series_tool": (TimeSeriesQueryInput,
                                   ("metric_name", "start_year", "end_year")),
        "search_notes_tool": (NotesSearchInput, ("query", "fiscal_year", "sections")),
    }
    schemas = {}
    for name, (model, allowed) in fields.items():
        properties = model.model_json_schema()["properties"]
        schemas[name] = {"type": "object", "additionalProperties": False,
                         "properties": {key: properties[key] for key in allowed},
                         "required": list(allowed)}
    return schemas


def _template_context(outline) -> dict:
    """Keep the reference structure without repeating complete Pydantic objects."""
    return {"outline_id": outline.outline_id,
            "calculation_policy": outline.calculation_policy,
            "sections": [
                {"section_id": section.section_id, "title": section.title,
                 "objective": section.objective,
                 "research_tasks": [
                     {"task_type": task.task_type,
                      **task.model_dump(mode="json", exclude_none=True,
                                        exclude_defaults=True,
                                        exclude={"task_type"})}
                     for task in section.research_tasks],
                 "calculation_specs": [spec.model_dump(mode="json")
                                       for spec in section.calculation_specs]}
                for section in outline.sections]}


def _validate_proposal(proposal: PlannerProposal, toolbox: PlannerToolbox,
                       template=None) -> None:
    """Check tool provenance and request boundaries; content choices remain with LLM."""
    outline = proposal.outline
    if outline.calculation_policy != "explicit":
        raise ValueError("LLM outline must use explicit calculations")
    observed = list(toolbox.observations.values())
    if not observed:
        raise ValueError("Planner must inspect source data before proposing")
    observed_ids = set(toolbox.observations)
    section_ids = {section.section_id for section in outline.sections}
    template_ids = ({section.section_id for section in template.sections}
                    if template is not None else set())
    for decision in proposal.decisions:
        if decision.action in {"omit", "merge"}:
            if not decision.template_section_ids or (template is not None and
                not set(decision.template_section_ids) <= template_ids):
                raise ValueError("Omit/merge decision needs existing template source IDs")
            if decision.action == "merge" and (not decision.resulting_section_ids or
                not set(decision.resulting_section_ids) <= section_ids):
                raise ValueError("Merge decision needs existing destination section IDs")
            if decision.action == "omit" and decision.resulting_section_ids:
                raise ValueError("Omit decision must have no destination IDs")
        if not set(decision.observation_ids) <= observed_ids:
            raise ValueError("Outline decision cites an unknown observation")
        if decision.basis == "data" and all(
            toolbox.observations[key].result.status in {"error", "invalid_input"}
            for key in decision.observation_ids
        ):
            raise ValueError("Tool failure cannot justify a data-based outline change")
    represented = {sid for section in outline.sections
                   for sid in [section.section_id, *section.template_section_ids]}
    represented.update(sid for decision in proposal.decisions
                       for sid in decision.template_section_ids)
    for sid in ("S1", "S2", "S3", "S4", "S5"):
        if sid not in represented:
            raise ValueError(f"Reference domain {sid} has no section or explicit decision")
        if sid != "S1" and not any(
            (sid == section.section_id or sid in section.template_section_ids) and
            section.research_tasks for section in outline.sections
        ) and not any(sid in decision.template_section_ids for decision in proposal.decisions):
            raise ValueError(f"Reference domain {sid} has neither tasks nor a decision")
    if template is not None:
        for sid in (section.section_id for section in template.sections):
            if sid in section_ids:
                continue
            decisions = [decision for decision in proposal.decisions
                         if sid in decision.template_section_ids and
                         decision.action in {"omit", "merge"}]
            if not decisions:
                raise ValueError(f"Template section {sid} needs an omit/merge decision with source ID")
    unobserved, not_found, failed = [], [], []
    for section in outline.sections:
        for task in section.research_tasks:
            if isinstance(task, (FactTask, TimeSeriesTask)):
                if not task.metric_name or not task.item_code or not task.report_type:
                    raise ValueError(f"Task {task.task_id} needs a resolved name, code and report type")
                resolved = metric_name_resolver(MetricResolverInput(metric_name=task.metric_name))
                if (resolved.status != "ok" or len(resolved.candidates) != 1 or
                        (resolved.candidates[0].code, resolved.candidates[0].report_type) !=
                        (task.item_code, task.report_type)):
                    raise ValueError(f"Task {task.task_id} has no unique resolver match")
                wanted = "query_fact_tool" if isinstance(task, FactTask) else "query_time_series_tool"
                matching = [item for item in observed if item.tool_name == wanted and
                            item.arguments.get("item_code") == task.item_code and
                            item.arguments.get("report_type") == task.report_type and
                            (item.arguments.get("fiscal_year") == task.fiscal_year if isinstance(task, FactTask)
                             else item.arguments.get("start_year") <= task.start_year and
                                  item.arguments.get("end_year") >= task.end_year)]
            elif isinstance(task, NotesTask):
                matching = [item for item in observed if item.tool_name == "search_notes_tool" and
                            item.arguments.get("query") == task.query and
                            item.arguments.get("fiscal_year") == task.fiscal_year and
                            item.arguments.get("sections") == task.sections]
            else:
                continue
            if not matching:
                unobserved.append(task.task_id)
            elif all(item.result.status in {"error", "invalid_input"} for item in matching):
                failed.append(task.task_id)
            elif all(item.result.status == "not_found" for item in matching):
                not_found.append(task.task_id)
    if unobserved or failed:
        raise ValueError("Task observations: " + "; ".join([
            f"not queried={unobserved}", f"tool error/invalid_input={failed}",
            f"queried but not_found={not_found}"]))
    if not outline.outline_id:
        raise ValueError("Outline ID is required")


def build_planner_agent(model: PlannerModel, tools: AgentTools,
                        note_snapshot_version: str | None = None,
                        max_turns: int = 6, max_tool_calls: int = 64,
                        progress: Callable[[str, str], None] | None = None):
    """Return an injectable Planner callable; no network call occurs until invoked."""
    if max_turns < 1 or max_tool_calls < 1:
        raise ValueError("Planner limits must be positive")
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    def emit(stage: str, message: str) -> None:
        if progress is not None:
            progress(stage, message)

    def plan(request: ReportRequest) -> PlannerOutput:
        started = time.perf_counter()
        emit("preflight", "Đang kiểm tra phạm vi và dữ liệu hiện có")
        gate = preflight(request, tools.db_path)
        if isinstance(gate, PlannerOutput):
            emit(gate.status, "Yêu cầu cần được làm rõ trước khi lập dàn ý"
                 if gate.status == "needs_clarification" else "Không thể lập dàn ý cho yêu cầu này")
            return gate
        emit("preflight_done", "Đã xác nhận phạm vi và các năm có dữ liệu")
        emit("template", "Đang chuẩn bị cấu trúc báo cáo")
        template = plan_report(request, tools.db_path)
        emit("template_done", f"Đã chuẩn bị {len(template.outline.sections)} phần báo cáo tham chiếu")
        emit("tools", "Đang chuẩn bị công cụ tra cứu")
        toolbox = PlannerToolbox(request, tools, note_snapshot_version)
        emit("tools_done", "Công cụ tra cứu đã sẵn sàng")
        base = {"request": request.model_dump(mode="json"),
                "available_scopes": gate.available_scopes,
                "template_outline": _template_context(template.outline),
                "tool_argument_schemas": _tool_argument_schemas(),
                "turn_format": {"observe": {"action": "observe", "tool_calls": [
                    {"tool_name": "name", "arguments": {}}]},
                    "propose": {"action": "propose", "proposal": {
                        "outline": "ReportOutline", "decisions": [], "notes": []}}}}
        history = [base]
        call_count = 0
        repair_count = 0
        token_usage: dict[str, int] = {}
        observation_previews = {}
        last_error = "No valid proposal"
        for turn_number in range(1, max_turns + 1):
            try:
                emit("model", f"Gemini đang xử lý lượt lập dàn ý {turn_number}")
                raw = model.generate(system_prompt, json.dumps(history, ensure_ascii=False))
                emit("model_done", f"Gemini đã trả kết quả lượt {turn_number}")
                for key, value in getattr(model, "last_usage", {}).items():
                    token_usage[key] = token_usage.get(key, 0) + value
                turn = PlannerTurn.model_validate_json(raw)
                if turn.action == "observe":
                    emit("observe_plan", f"Gemini yêu cầu tra cứu {len(turn.tool_calls)} mục ở lượt {turn_number}")
                    if call_count + len(turn.tool_calls) > max_tool_calls:
                        raise ValueError("Planner tool-call limit exceeded")
                    previews = []
                    for index, call in enumerate(turn.tool_calls, start=1):
                        activity = {
                            "metric_name_resolver": "Đang đối chiếu tên chỉ tiêu",
                            "query_fact_tool": "Đang đọc số liệu tài chính",
                            "query_time_series_tool": "Đang đọc số liệu theo nhiều năm",
                            "search_notes_tool": "Đang tìm trong thuyết minh",
                        }.get(call.tool_name, "Đang tra cứu dữ liệu")
                        emit("observe", f"{activity} ({index}/{len(turn.tool_calls)} mục của lượt {turn_number})")
                        observation = toolbox.observe(call)
                        outcome = observation.result
                        status = {"ok": "có kết quả", "partial": "kết quả một phần",
                                  "not_found": "chưa tìm thấy", "ambiguous": "cần làm rõ",
                                  "invalid_input": "đầu vào không hợp lệ",
                                  "error": "tra cứu lỗi"}[outcome.status]
                        counts = [f"{len(outcome.facts)} số liệu" if outcome.facts else "",
                                  f"{len(outcome.chunks)} đoạn thuyết minh" if outcome.chunks else "",
                                  f"{len(outcome.candidates)} chỉ tiêu" if outcome.candidates else ""]
                        detail = ", ".join(item for item in counts if item)
                        emit("observe_done", f"Mục {index}/{len(turn.tool_calls)}: {status}"
                             + (f" · {detail}" if detail else ""))
                        previews.append(PlannerToolbox.preview(observation))
                    call_count += len(turn.tool_calls)
                    observation_previews.update((item["observation_id"], item)
                                                for item in previews)
                    history = [base, {"observations": list(observation_previews.values())}]
                    continue
                emit("validate", "Đang kiểm tra dàn ý và nguồn dữ liệu")
                _validate_proposal(turn.proposal, toolbox, template.outline)
                emit("validate_done", "Dàn ý và các tác vụ nghiên cứu đã qua kiểm tra")
                result = PlannerOutput(status="ready", outline=turn.proposal.outline,
                                       notes=turn.proposal.notes,
                                       decisions=turn.proposal.decisions,
                                       observations=list(toolbox.observations.values()),
                                       available_scopes=gate.available_scopes,
                                       prompt_version=PROMPT_VERSION,
                                       model_turns=turn_number, repair_count=repair_count,
                                       tool_call_count=call_count,
                                       token_usage=token_usage,
                                       elapsed_ms=round((time.perf_counter() - started) * 1000))
                emit("ready", "Dàn ý đã sẵn sàng để duyệt")
                return result
            except Exception as exc:
                repair_count += 1
                last_error = str(exc)
                emit("repair", "Đang điều chỉnh kết quả Planner để đáp ứng yêu cầu")
                history = [base, {"observations": list(observation_previews.values()),
                                  "validation_error": last_error,
                                  "instruction": "Correct the JSON or inspect missing tasks before proposing."}]
        result = template.model_copy(update={
            "observations": list(toolbox.observations.values()),
            "notes": [*template.notes, PlannerNote(
                code="planner_fallback", message=f"LLM Planner fallback: {last_error}")],
            "prompt_version": PROMPT_VERSION, "used_fallback": True,
            "model_turns": max_turns, "repair_count": repair_count,
            "tool_call_count": call_count,
            "token_usage": token_usage,
            "elapsed_ms": round((time.perf_counter() - started) * 1000)})
        emit("fallback", "Dàn ý tham chiếu đã sẵn sàng sau các lượt điều chỉnh")
        return result

    return plan
