"""Minimal LangGraph wiring for one pass through the report stages."""
from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from src.agents.state import (
    ReportState, approve_outline_revision, can_complete, complete_run,
    install_outline_revision,
)
from src.agents.planner import plan_report
from src.agents.planner_agent import build_planner_agent
from src.agents.planner_model import PlannerModel
from src.agents.researcher import build_researcher
from src.agents.report_tables import render_section_tables
from src.agents.verification import (
    attach_code_limitations, render_section_citations,
    verify_section_deterministically, verify_section_full,
)
from src.agents.verifier_contract import VerifierModel
from src.schemas.report_schema import PlannerOutput, ReportOutline, ReportRequest
from src.tools.agent_tools import AgentTools


def build_report_graph(
    plan: Callable[[ReportRequest], ReportOutline | PlannerOutput] | None,
    research: Callable[[ReportState], dict],
    write: Callable[[ReportState], dict],
    *, verifier_model: VerifierModel | None = None,
    verifier_mode: Literal["blocking", "shadow"] = "blocking",
    require_outline_approval: bool = False, checkpointer=None,
    progress: Callable[[str, str], None] | None = None,
):
    """Run injected planning/research/writing steps, then deterministic checks.

    The injected functions return state updates. A semantic reviewer must later
    issue level='full' before the report can be marked completed.
    """
    def planner_node(state: ReportState) -> dict:
        planned = (plan or plan_report)(state["request"])
        if isinstance(planned, PlannerOutput):
            if planned.status != "ready":
                return {"planner_notes": planned.notes,
                        "planner_available_scopes": planned.available_scopes,
                        "run_status": planned.status}
            outline = planned.outline
            notes = planned.notes
        else:
            outline, notes = planned, []
        return {"outline": outline, "outline_version": 1,
                "outlines_by_revision": {1: outline.model_copy(deep=True)},
                "planner_notes": notes,
                "planner_available_scopes": (planned.available_scopes
                                             if isinstance(planned, PlannerOutput) else {}),
                "planner_observations": ({item.observation_id: item for item in planned.observations}
                                         if isinstance(planned, PlannerOutput) else {}),
                "outline_decisions": planned.decisions if isinstance(planned, PlannerOutput) else [],
                "planner_prompt_version": (planned.prompt_version
                                           if isinstance(planned, PlannerOutput) else None),
                "planner_used_fallback": (planned.used_fallback
                                          if isinstance(planned, PlannerOutput) else False),
                "run_status": "awaiting_approval" if require_outline_approval else "running"}

    def approval_node(state: ReportState) -> dict:
        response = interrupt({
            "outline": state["outline"].model_dump(mode="json"),
            "outline_version": state["outline_version"],
            "decisions": [item.model_dump(mode="json")
                          for item in state.get("outline_decisions", [])],
            "planner_notes": [item.model_dump(mode="json")
                              for item in state.get("planner_notes", [])],
        })
        if not isinstance(response, dict) or response.get("outline_version") != state["outline_version"]:
            raise ValueError("Approval must reference the current outline revision")
        if response.get("action") == "approve":
            return {**approve_outline_revision(state), "run_status": "running"}
        if response.get("action") == "revise":
            revised = ReportOutline.model_validate(response.get("outline"))
            return {**install_outline_revision(state, revised),
                    "run_status": "awaiting_approval"}
        if response.get("action") == "reject":
            return {"run_status": "needs_clarification"}
        raise ValueError("Approval action must be approve, revise or reject")

    def writer_node(state: ReportState) -> dict:
        update = write(state)
        for draft in update.get("section_drafts", {}).values():
            for block in draft.blocks:
                if block.template is None:
                    raise ValueError(f"missing_template: {draft.section_id}/{block.block_id}")
        sections = {section.section_id: section for section in state["outline"].sections}
        drafts = {key: attach_code_limitations(
            draft, sections[draft.section_id], state.get("calculations_by_id", {}),
            state.get("research_results", {}))
            for key, draft in update.get("section_drafts", {}).items()}
        return {**update, "section_drafts": drafts} if drafts else update

    def verifier_node(state: ReportState) -> dict:
        def emit(stage: str, message: str) -> None:
            if progress is not None:
                progress(stage, message)

        results = {}
        logs = {}
        rendered = []
        for section in state["outline"].sections:
            drafts = [draft for draft in state.get("section_drafts", {}).values()
                      if draft.section_id == section.section_id and
                      draft.outline_version == state["outline_version"]]
            if not drafts:
                continue
            draft = max(drafts, key=lambda item: item.revision)
            emit("verifier_section", f"Đang kiểm chứng {section.section_id} · {section.title}")
            if verifier_model is None:
                result = verify_section_deterministically(
                    draft, state["request"], state.get("evidence_by_id", {}),
                    state.get("calculations_by_id", {}), state.get("research_results", {}),
                    state.get("evidence_aliases", {}), section)
                result = result.model_copy(update={"outline_version": state["outline_version"]})
            else:
                result, run_log = verify_section_full(
                    draft, state["request"], state.get("evidence_by_id", {}),
                    state.get("calculations_by_id", {}), state.get("research_results", {}),
                    verifier_model, state.get("evidence_aliases", {}), section,
                    mode=verifier_mode)
                log_key = f"{state['outline_version']}:{section.section_id}:{draft.revision}"
                logs[log_key] = run_log
            key = ((state["outline_version"], section.section_id, draft.revision)
                   if require_outline_approval or state["outline_version"] > 1 else
                   (section.section_id, draft.revision))
            results[key] = result
            outcome = ("đạt kiểm chứng đầy đủ" if result.status == "passed" and result.level == "full"
                       else "chỉ đạt kiểm tra quy tắc" if result.status == "passed"
                       else "cần sửa" if result.status == "needs_revision"
                       else "chưa đủ bằng chứng")
            emit("verifier_section_done", f"{section.section_id}: {outcome}")
            if result.status == "passed":
                prose = render_section_citations(
                    draft, state.get("evidence_by_id", {}),
                    state.get("calculations_by_id", {}), state.get("research_results", {}),
                    section)
                tables = render_section_tables(section, state)
                if tables and prose.startswith("## "):
                    heading, separator, remainder = prose.partition("\n\n")
                    prose = heading + "\n\n" + tables + (separator + remainder if remainder else "")
                rendered.append(prose)
        candidate_state = {
            **state,
            "verification_results": {**state.get("verification_results", {}), **results},
        }
        status_update = (complete_run(candidate_state)
                         if verifier_model is not None and can_complete(candidate_state)
                         else {"run_status": "incomplete"})
        emit("verifier_done", "Tất cả phần đã đạt Verifier; báo cáo sẵn sàng"
             if status_update["run_status"] == "completed"
             else "Đã kiểm chứng xong; báo cáo còn phần chưa đạt đầy đủ")
        update = {"verification_results": results, "final_report": "\n\n".join(rendered) or None,
                  **status_update}
        if logs:
            update["verifier_run_logs"] = logs
        return update

    graph = StateGraph(ReportState)
    graph.add_node("planner", planner_node)
    if require_outline_approval:
        if checkpointer is None:
            raise ValueError("Outline approval requires a LangGraph checkpointer")
        graph.add_node("approval", approval_node)
    graph.add_node("researcher", research)
    graph.add_node("writer", writer_node)
    graph.add_node("verifier", verifier_node)
    graph.add_edge(START, "planner")
    planner_routes = (
        {"approval": "approval", "researcher": "researcher", END: END}
        if require_outline_approval
        else {"researcher": "researcher", END: END}
    )
    graph.add_conditional_edges("planner", lambda state: (
        "approval" if state["run_status"] == "awaiting_approval" else
        "researcher" if state["run_status"] == "running" else END),
        planner_routes)
    if require_outline_approval:
        graph.add_conditional_edges("approval", lambda state: (
            "approval" if state["run_status"] == "awaiting_approval" else
            "researcher" if state["run_status"] == "running" else END),
            {"approval": "approval", "researcher": "researcher", END: END})
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", "verifier")
    graph.add_edge("verifier", END)
    return graph.compile(checkpointer=checkpointer)


def build_agent_report_graph(model: PlannerModel, tools: AgentTools,
                             write: Callable[[ReportState], dict], *,
                             verifier_model: VerifierModel | None = None,
                             verifier_mode: Literal["blocking", "shadow"] = "blocking",
                             checkpointer):
    """Compose the tool-using Planner and Researcher with mandatory outline review."""
    return build_report_graph(build_planner_agent(model, tools),
                              build_researcher(tools), write,
                              verifier_model=verifier_model,
                              verifier_mode=verifier_mode,
                              require_outline_approval=True, checkpointer=checkpointer)
