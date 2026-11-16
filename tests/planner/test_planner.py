"""Template planner gates, deterministic routing and real fact handoff."""
import unittest

from pydantic import ValidationError

from src.agents.planner import plan_report
from src.agents.researcher import build_researcher
from src.agents.report_graph import build_report_graph
from src.agents.state import (
    approve_outline_revision, can_complete, install_outline_revision,
    state_from_json, state_to_json,
)
from src.schemas.report_schema import CalculationSpec, ReportRequest
from src.tools.agent_tools import AgentTools


def request(ticker="HUT", scope="consolidated", audience="Nhà đầu tư"):
    return ReportRequest(ticker=ticker, start_year=2022, end_year=2025,
                         scope=scope, audience=audience)


class EmptyNotes:
    def search(self, _args):
        return []

    def read_audit_section(self, _ticker, _year, _scope):
        return []

    def close(self):
        pass


class PlannerTests(unittest.TestCase):
    def test_hut_gmd_are_deterministic_and_resolved(self):
        for ticker in ("HUT", "GMD"):
            first = plan_report(request(ticker))
            second = plan_report(request(ticker))
            self.assertEqual(first, second)
            self.assertEqual(first.status, "ready")
            outline = first.outline
            self.assertEqual([section.section_id for section in outline.sections],
                             ["S1", "S2", "S3", "S4", "S5"])
            self.assertEqual(outline.calculation_policy, "explicit")
            series = [task for section in outline.sections for task in section.research_tasks
                      if task.task_type == "time_series"]
            self.assertEqual(len(series), 12)
            self.assertTrue(all(task.item_code and task.report_type for task in series))
            self.assertEqual(len([task for task in outline.sections[1].research_tasks
                                  if task.task_type == "notes"]), 12)
            self.assertEqual(first, type(first).model_validate_json(first.model_dump_json()))

    def test_preflight_refuses_or_requests_scope_confirmation(self):
        for ticker in ("ABB", "ACB", "BAB", "MSB", "NAB", "NVB"):
            result = plan_report(request(ticker))
            self.assertEqual(result.status, "rejected")
            self.assertEqual(result.notes[0].code, "unsupported_bank_codes")
        for ticker in ("FOX", "DPM", "VCB"):
            self.assertEqual(plan_report(request(ticker)).notes[0].code,
                             "ticker_not_in_corpus")
        self.assertEqual(plan_report(request("PVI")).notes[0].code,
                         "unreviewed_financial_template")
        self.assertEqual(plan_report(request("PAP", "general")).status, "ready")
        for ticker, scope in (("PAP", "consolidated"), ("DHG", "consolidated"),
                              ("VCR", "general")):
            result = plan_report(request(ticker, scope))
            self.assertEqual(result.status, "needs_clarification")
            self.assertIsNone(result.outline)
            self.assertTrue(result.available_scopes)

    def test_menu_and_optional_sections(self):
        output = plan_report(request(audience="Kiểm toán/tuân thủ"))
        self.assertEqual([s.section_id for s in output.outline.sections][-2:], ["S6", "S7"])
        specs = [spec for section in output.outline.sections
                 for spec in section.calculation_specs]
        self.assertEqual({spec.operation for spec in specs},
                         {"yoy", "cagr", "difference", "trend"})
        self.assertEqual(sum(spec.operation == "cagr" for spec in specs), 1)
        self.assertEqual({spec.source_task_id for spec in specs if spec.operation == "yoy"},
                         {"revenue", "assets"})
        with self.assertRaises(ValidationError):
            CalculationSpec(calculation_id="bad", operation="yoy",
                            source_task_id="revenue", start_year=2022, end_year=2024)

    def test_real_duckdb_handoff_obeys_calculation_menu(self):
        output = plan_report(request())
        with AgentTools(notes_retriever=EmptyNotes()) as tools:
            result = build_researcher(tools, note_snapshot_version="test-notes")({
                "request": request(), "outline": output.outline})
        self.assertEqual(result["research_results"]["revenue"].status, "sufficient")
        self.assertEqual(result["calculations_by_id"]["revenue:cagr:2025"].status, "ok")
        self.assertNotIn("revenue:trend", result["calculations_by_id"])
        self.assertNotIn("net_income:cagr:2025", result["calculations_by_id"])
        self.assertEqual(result["calculations_by_id"]["gross_margin:2025"].status, "ok")
        self.assertIn(result["calculations_by_id"]["cfo_to_net_income:2025"].status,
                      {"ok", "cannot_compute"})

    def test_graph_stops_before_research_on_rejection(self):
        calls = []

        def research(_state):
            calls.append("research")
            return {}

        def write(_state):
            calls.append("write")
            return {}

        graph = build_report_graph(None, research, write)
        result = graph.invoke({"request": request("FOX")})
        self.assertEqual(result["run_status"], "rejected")
        self.assertEqual(calls, [])
        self.assertEqual(result["planner_notes"][0].code, "ticker_not_in_corpus")

    def test_graph_runs_real_planner_and_researcher(self):
        with AgentTools(notes_retriever=EmptyNotes()) as tools:
            graph = build_report_graph(None,
                                       build_researcher(tools, note_snapshot_version="test-notes"),
                                       lambda _state: {})
            result = graph.invoke({"request": request("HUT")})
        self.assertEqual(result["outline"].calculation_policy, "explicit")
        self.assertEqual(result["research_results"]["revenue"].status, "sufficient")
        self.assertEqual(result["calculations_by_id"]["gross_margin:2025"].status, "ok")
        self.assertEqual(result["run_status"], "incomplete")

    def test_outline_revision_revokes_approval_and_round_trips(self):
        outline = plan_report(request()).outline
        state = {"request": request()}
        state.update(install_outline_revision(state, outline))
        state.update(approve_outline_revision(state))
        self.assertEqual(state["outline_approved_version"], 1)
        revised = outline.model_copy(deep=True)
        revised.sections[0].objective = "Đã sửa mục tiêu"
        state.update(install_outline_revision(state, revised))
        self.assertEqual(state["outline_version"], 2)
        self.assertIsNone(state["outline_approved_version"])
        self.assertFalse(can_complete(state))
        self.assertEqual(state["outlines_by_revision"][1], outline)
        restored = state_from_json(state_to_json(state))
        self.assertEqual(restored["outline_version"], 2)
        self.assertEqual(restored["outlines_by_revision"], state["outlines_by_revision"])
        self.assertEqual(restored["outline_approved_version"], None)


if __name__ == "__main__":
    unittest.main()
