"""LLM Planner contract tests with no network or API key."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google.genai import types
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents.planner import plan_report
from src.agents.planner_agent import _validate_proposal, build_planner_agent
from src.agents.planner_model import GeminiPlannerModel, _read_api_key
from src.agents.planner_toolbox import PlannerToolbox
from src.agents.researcher import build_researcher
from src.agents.report_graph import build_agent_report_graph, build_report_graph
from src.agents.state import report_checkpoint_serde, state_from_json, state_to_json
from src.schemas.report_schema import (
    PlannerProposal, PlannerToolCall, ReportOutline, ReportRequest, SectionPlan,
    TimeSeriesTask,
)
from src.storage.duckdb_manager import DEFAULT_DB_PATH
from src.tools.agent_tools import AgentTools
from src.tools.schemas import ToolResult


REQUEST = ReportRequest(ticker="HUT", start_year=2022, end_year=2025,
                        audience="Nhà đầu tư")


class FakeTools:
    db_path = DEFAULT_DB_PATH

    def execute(self, name, args):
        if name == "search_notes_tool":
            return ToolResult(status="ok")
        return ToolResult(status="not_found" if args.get("item_code") in {"270", "20"}
                          else "ok", safe_for_calculation=args.get("item_code") == "10")


class AdaptiveModel:
    def __init__(self):
        self.calls = 0

    def generate(self, system_prompt, context):
        self.calls += 1
        assert "B01" in system_prompt and "period_inconsistency" in system_prompt
        if self.calls == 1:
            return json.dumps({"action": "observe", "tool_calls": [
                {"tool_name": "query_time_series_tool", "arguments": {
                    "metric_name": name, "start_year": 2022, "end_year": 2025}}
                for name in ("Doanh thu thuần", "Tổng tài sản",
                             "Lưu chuyển tiền thuần từ hoạt động kinh doanh")]
                + [{"tool_name": "search_notes_tool", "arguments": {
                    "query": "Loại ý kiến kiểm toán", "fiscal_year": 2025,
                    "sections": ["AUDIT_REPORT"]}}]
                + [{"tool_name": "search_notes_tool", "arguments": {
                    "query": query, "fiscal_year": 2025, "sections": ["NOTES"]}}
                   for query in ("Nguyên tắc và thời điểm ghi nhận doanh thu",
                                 "Các giao dịch và số dư với bên liên quan")]})
        return json.dumps({"action": "propose", "proposal": {
            "outline": {"outline_id": "adaptive-hut", "calculation_policy": "explicit",
                        "sections": [
                            {"section_id": sid, "title": sid, "objective": sid,
                             "research_tasks": ([{"task_type": "time_series", "task_id": "revenue",
                                                  "metric_name": "Doanh thu thuần", "item_code": "10",
                                                  "report_type": "INCOME_STATEMENT",
                                                  "start_year": 2022, "end_year": 2025}]
                                                if sid == "S3" else
                                                [{"task_type": "notes", "task_id": "audit_2025",
                                                  "query": "Loại ý kiến kiểm toán", "fiscal_year": 2025,
                                                  "sections": ["AUDIT_REPORT"]}]
                                                if sid == "S2" else
                                                [{"task_type": "time_series", "task_id": task_id,
                                                  "metric_name": name, "item_code": code,
                                                  "report_type": report_type,
                                                  "start_year": 2022, "end_year": 2025}]
                                                if sid in ("S4", "S5") else
                                                [{"task_type": "notes", "task_id": f"{sid}:note:2025",
                                                  "query": query, "fiscal_year": 2025,
                                                  "sections": ["NOTES"]}]
                                                if sid in ("S6", "S7") else [])}
                            for sid, query, task_id, name, code, report_type in (
                                               ("S1", "", "", "", "", ""),
                                               ("S2", "", "", "", "", ""),
                                               ("S3", "", "", "", "", ""),
                                               ("S4", "", "assets", "Tổng tài sản", "270", "BALANCE_SHEET"),
                                               ("S5", "", "operating_cash_flow", "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "20", "CASH_FLOW"),
                                               ("S6", "Nguyên tắc và thời điểm ghi nhận doanh thu", "", "", "", ""),
                                               ("S7", "Các giao dịch và số dư với bên liên quan", "", "", "", ""))]},
            "decisions": []}})


class InvalidModel:
    def generate(self, _system_prompt, _context):
        return '{"action":"propose","proposal":{}}'


class RepairingModel:
    def __init__(self):
        self.calls = 0
        self.adaptive = AdaptiveModel()

    def generate(self, system_prompt, context):
        self.calls += 1
        if self.calls == 1:
            return "{invalid"
        return self.adaptive.generate(system_prompt, context)


class ErrorOmissionModel:
    def __init__(self):
        self.calls = 0

    def generate(self, _system_prompt, context):
        self.calls += 1
        if self.calls == 1:
            return json.dumps({"action": "observe", "tool_calls": [{
                "tool_name": "search_notes_tool", "arguments": {
                    "query": "Ý kiến kiểm toán", "fiscal_year": 2025,
                    "sections": ["AUDIT_REPORT"]}}]})
        observation_id = json.loads(context)[-1]["observations"][0]["observation_id"]
        return json.dumps({"action": "propose", "proposal": {
            "outline": {"outline_id": "bad-omit", "calculation_policy": "explicit",
                        "sections": [{"section_id": sid, "title": sid, "objective": sid,
                                      "research_tasks": ([{"task_type": "notes",
                                                          "task_id": f"{sid}:note:2025",
                                                          "query": "Thuyết minh", "fiscal_year": 2025,
                                                          "sections": ["NOTES"]}]
                                                         if sid in ("S6", "S7") else [])}
                                     for sid in ("S1", "S3", "S4", "S5", "S6", "S7")]},
            "decisions": [{"action": "omit", "basis": "data",
                           "template_section_ids": ["S2"],
                           "reason": "No audit evidence", "observation_ids": [observation_id]}]}})


class FakeResponse:
    text = '{"action":"observe","tool_calls":[]}'


class FakeModels:
    def __init__(self):
        self.kwargs = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        return FakeResponse()


class PlannerAgentTests(unittest.TestCase):
    def test_model_receives_planner_tool_schemas_without_code_or_max_chunks(self):
        class InspectModel:
            def generate(self, _prompt, context):
                schemas = json.loads(context)[0]["tool_argument_schemas"]
                self_test.assertEqual(set(schemas), {"metric_name_resolver",
                    "query_fact_tool", "query_time_series_tool", "search_notes_tool"})
                self_test.assertEqual(schemas["search_notes_tool"]["required"],
                                      ["query", "fiscal_year", "sections"])
                self_test.assertNotIn("max_chunks", str(schemas))
                self_test.assertNotIn("item_code", str(schemas))
                return '{"action":"propose","proposal":{}}'

        self_test = self
        build_planner_agent(InspectModel(), FakeTools(), max_turns=1)(REQUEST)

    def test_validator_reports_all_unobserved_tasks_in_one_error(self):
        template = plan_report(REQUEST).outline
        box = PlannerToolbox(REQUEST, FakeTools(), "notes-v1")
        box.observe(PlannerToolCall(tool_name="metric_name_resolver",
                                    arguments={"metric_name": "Doanh thu thuần"}))
        with self.assertRaisesRegex(ValueError, "not queried") as raised:
            _validate_proposal(PlannerProposal(outline=template, decisions=[]),
                               box, template)
        self.assertIn("S1:business:2025", str(raised.exception))
        self.assertIn("revenue", str(raised.exception))

    def test_validator_feedback_distinguishes_missing_not_found_and_error(self):
        class StatusTools(FakeTools):
            def execute(self, name, args):
                return ToolResult(status="not_found" if name == "search_notes_tool"
                                  else "error")

        template = plan_report(REQUEST).outline
        box = PlannerToolbox(REQUEST, StatusTools(), "notes-v1")
        box.observe(PlannerToolCall(tool_name="search_notes_tool", arguments={
            "query": "Ngành nghề hoạt động và cơ cấu doanh nghiệp",
            "fiscal_year": 2025, "sections": ["NOTES", "MANAGEMENT_REPORT"]}))
        box.observe(PlannerToolCall(tool_name="query_time_series_tool", arguments={
            "metric_name": "Doanh thu thuần", "start_year": 2022,
            "end_year": 2025}))
        with self.assertRaises(ValueError) as raised:
            _validate_proposal(PlannerProposal(outline=template, decisions=[]),
                               box, template)
        message = str(raised.exception)
        self.assertIn("not queried=", message)
        self.assertIn("tool error/invalid_input=['revenue']", message)
        self.assertIn("queried but not_found=['S1:business:2025']", message)

    def test_required_section_cannot_disappear_even_with_decision(self):
        request = REQUEST
        template = plan_report(request).outline
        self.assertIn("S7", [section.section_id for section in template.sections])
        outline = template.model_copy(update={
            "sections": [section for section in template.sections
                         if section.section_id != "S7"]})
        box = PlannerToolbox(request, FakeTools(), "notes-v1")
        box.observe(PlannerToolCall(tool_name="metric_name_resolver",
                                    arguments={"metric_name": "Doanh thu thuần"}))
        with self.assertRaisesRegex(ValueError, "Full report requires section S7"):
            _validate_proposal(PlannerProposal(outline=outline, decisions=[]),
                               box, template)
        implicit_merge = outline.model_copy(update={
            "sections": [section.model_copy(update={
                "template_section_ids": ["S4", "S7"]})
                if section.section_id == "S4" else section
                for section in outline.sections]})
        with self.assertRaisesRegex(ValueError, "Full report requires section S7"):
            _validate_proposal(PlannerProposal(outline=implicit_merge, decisions=[]),
                               box, template)
        with self.assertRaisesRegex(ValueError, "Full report requires section S7"):
            _validate_proposal(PlannerProposal(outline=outline, decisions=[{
                "action": "merge", "basis": "audience",
                "template_section_ids": ["S7"], "resulting_section_ids": ["S4"],
                "reason": "Gộp nội dung liên quan"}]), box, template)
        empty_s7 = template.model_copy(deep=True)
        empty_s7.sections[-1].research_tasks = []
        with self.assertRaisesRegex(ValueError, "section S7 needs a notes research task"):
            _validate_proposal(PlannerProposal(outline=empty_s7, decisions=[]),
                               box, template)
        with self.assertRaisesRegex(ValueError, "cannot omit or merge S1–S7"):
            _validate_proposal(PlannerProposal(outline=template, decisions=[{
                "action": "omit", "basis": "audience",
                "template_section_ids": ["S6"], "reason": "Không cần mục này"}]),
                box, template)

    def test_agent_graph_requires_review_before_research(self):
        graph = build_agent_report_graph(AdaptiveModel(), FakeTools(),
                                         lambda _state: {},
                                         checkpointer=InMemorySaver(
                                             serde=report_checkpoint_serde()))
        pending = graph.invoke({"request": REQUEST},
                               {"configurable": {"thread_id": "agent-graph-review"}})
        self.assertEqual(pending["run_status"], "awaiting_approval")
        self.assertIsNone(pending.get("outline_approved_version"))

    def test_llm_keeps_seven_sections_using_tool_observations(self):
        result = build_planner_agent(AdaptiveModel(), FakeTools(),
                                     note_snapshot_version="notes-v1", max_turns=3)(REQUEST)
        self.assertEqual(result.status, "ready")
        self.assertFalse(result.used_fallback)
        self.assertEqual([s.section_id for s in result.outline.sections],
                         ["S1", "S2", "S3", "S4", "S5", "S6", "S7"])
        self.assertEqual(result.decisions, [])
        self.assertEqual(len(result.observations), 6)
        state = {"request": REQUEST, "outline": result.outline,
                 "planner_observations": {x.observation_id: x for x in result.observations},
                 "outline_decisions": result.decisions}
        restored = state_from_json(state_to_json(state))
        self.assertEqual(restored["planner_observations"], state["planner_observations"])
        self.assertEqual(restored["outline_decisions"], state["outline_decisions"])

    def test_invalid_llm_output_falls_back_with_visible_reason(self):
        result = build_planner_agent(InvalidModel(), FakeTools(), max_turns=2)(REQUEST)
        self.assertTrue(result.used_fallback)
        self.assertEqual(len(result.outline.sections), 7)
        self.assertEqual(result.notes[-1].code, "planner_fallback")

    def test_llm_repairs_invalid_json_before_human_review(self):
        result = build_planner_agent(RepairingModel(), FakeTools(),
                                     note_snapshot_version="notes-v1", max_turns=3)(REQUEST)
        self.assertFalse(result.used_fallback)
        self.assertEqual(len(result.observations), 6)

    def test_backend_error_cannot_justify_omitting_a_main_section(self):
        class BrokenNotes(FakeTools):
            def execute(self, name, args):
                if name == "search_notes_tool":
                    return ToolResult(status="error", message="Index unavailable")
                return super().execute(name, args)

        result = build_planner_agent(ErrorOmissionModel(), BrokenNotes(),
                                     note_snapshot_version="notes-v1", max_turns=2)(REQUEST)
        self.assertTrue(result.used_fallback)
        self.assertIn("Full report requires section S2", result.notes[-1].message)

    def test_toolbox_rejects_scope_or_code_bypass(self):
        box = PlannerToolbox(REQUEST, FakeTools(), "notes-v1")
        for arguments in ({"metric_name": "Doanh thu thuần", "scope": "separate",
                           "start_year": 2022, "end_year": 2025},
                          {"metric_name": "Doanh thu thuần", "item_code": "10",
                           "start_year": 2022, "end_year": 2025},
                          {"metric_name": "Doanh thu thuần",
                           "start_year": 2021, "end_year": 2025}):
            with self.assertRaises(ValueError):
                box.observe(PlannerToolCall(tool_name="query_time_series_tool",
                                            arguments=arguments))

    def test_gemini_adapter_uses_requested_model_and_reasoning(self):
        fake = FakeModels()
        client = type("Client", (), {"models": fake})()
        output = GeminiPlannerModel(client=client).generate("system", "context")
        self.assertEqual(output, FakeResponse.text)
        self.assertEqual(fake.kwargs["model"], "gemini-3.8-flash")
        self.assertEqual(fake.kwargs["config"].thinking_config.thinking_level,
                         types.ThinkingLevel.MEDIUM)

    def test_api_key_can_be_loaded_from_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('GEMINI_API_KEY="demo-key"\n', encoding="utf-8")
            with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
                self.assertEqual(_read_api_key(path), "demo-key")

    def test_langsmith_wraps_real_gemini_client_from_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("LANGSMITH_TRACING=true\nLANGSMITH_API_KEY=test-key\n"
                            "LANGSMITH_AGENT_ID=test-agent\n", encoding="utf-8")
            raw_client = object()
            wrapped_client = object()
            with patch.dict(os.environ, {}, clear=True), \
                 patch("src.agents.planner_model.genai.Client", return_value=raw_client), \
                 patch("langsmith.wrappers.wrap_gemini", return_value=wrapped_client) as wrap:
                model = GeminiPlannerModel(api_key="gemini-key", env_path=path)
                self.assertIs(model.client, wrapped_client)
                self.assertEqual(os.environ["LANGSMITH_AGENT_ID"], "test-agent")
                wrap.assert_called_once_with(raw_client)

    def test_langsmith_disabled_keeps_raw_client(self):
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "false"}), \
             patch("src.agents.planner_model.genai.Client", return_value=object()) as create, \
             patch("langsmith.wrappers.wrap_gemini") as wrap:
            model = GeminiPlannerModel(api_key="gemini-key", env_path="missing.env")
            self.assertIs(model.client, create.return_value)
            wrap.assert_not_called()

    def test_researcher_reuses_matching_fact_snapshot(self):
        with AgentTools() as tools:
            observation = PlannerToolbox(REQUEST, tools).observe(PlannerToolCall(
                tool_name="query_time_series_tool", arguments={
                    "metric_name": "Doanh thu thuần", "start_year": 2022,
                    "end_year": 2025}))

        class NoCalls(AgentTools):
            def execute(self, _name, _args):
                raise AssertionError("Researcher repeated a matching Planner read")

        outline = ReportOutline(calculation_policy="explicit", sections=[SectionPlan(
            section_id="S3", title="Doanh thu", objective="Doanh thu",
            research_tasks=[TimeSeriesTask(task_id="revenue", metric_name="Doanh thu thuần",
                                           item_code="10", report_type="INCOME_STATEMENT",
                                           start_year=2022, end_year=2025)])])
        result = build_researcher(NoCalls())({"request": REQUEST, "outline": outline,
                                              "planner_observations": {
                                                  observation.observation_id: observation}})
        self.assertEqual(result["research_results"]["revenue"].status, "sufficient")

    def test_llm_outline_reaches_human_before_research(self):
        calls = []

        def research(_state):
            calls.append("research")
            return {}

        graph = build_report_graph(
            build_planner_agent(AdaptiveModel(), FakeTools(), "notes-v1", max_turns=3),
            research, lambda _state: {}, require_outline_approval=True,
            checkpointer=InMemorySaver(serde=report_checkpoint_serde()))
        config = {"configurable": {"thread_id": "llm-planner-hitl-test"}}
        pending = graph.invoke({"request": REQUEST}, config)
        self.assertEqual(calls, [])
        self.assertEqual([s.section_id for s in pending["outline"].sections],
                         ["S1", "S2", "S3", "S4", "S5", "S6", "S7"])
        self.assertEqual(len(pending["outline_decisions"]), 0)
        completed = graph.invoke(Command(resume={"action": "approve", "outline_version": 1}),
                                 config)
        self.assertEqual(calls, ["research"])
        self.assertEqual(completed["outline_approved_version"], 1)


if __name__ == "__main__":
    unittest.main()
