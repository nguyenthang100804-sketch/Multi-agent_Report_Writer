"""Smoke test the four-node LangGraph handoff with contract-shaped data."""
import unittest
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents.report_graph import build_report_graph
from src.agents.draft_rendering import render_block
from src.agents.state import is_run_complete, report_checkpoint_serde, state_from_json
from src.schemas.report_schema import ReportOutline, ReportRequest, SectionDraft, SectionPlan


class ReportGraphTests(unittest.TestCase):
    def test_outline_approval_interrupts_before_research(self):
        calls = []
        outline = ReportOutline(outline_id="approval-demo", sections=[SectionPlan(
            section_id="S1", title="Thông tin", objective="Phạm vi")])

        def research(_state):
            calls.append("research")
            return {}

        graph = build_report_graph(lambda _request: outline, research, lambda _state: {},
                                   require_outline_approval=True,
                                   checkpointer=InMemorySaver(serde=report_checkpoint_serde()))
        config = {"configurable": {"thread_id": "planner-approval-test"}}
        initial = graph.invoke({"request": ReportRequest(
            ticker="HUT", start_year=2022, end_year=2025, audience="demo")}, config)
        self.assertEqual(initial["run_status"], "awaiting_approval")
        self.assertIn("__interrupt__", initial)
        self.assertEqual(calls, [])
        revised = outline.model_copy(deep=True)
        revised.sections[0].objective = "Phạm vi và nguồn"
        pending = graph.invoke(Command(resume={"action": "revise", "outline_version": 1,
                                               "outline": revised.model_dump(mode="json")}), config)
        self.assertEqual(pending["outline_version"], 2)
        self.assertEqual(pending["run_status"], "awaiting_approval")
        self.assertEqual(calls, [])
        complete = graph.invoke(Command(resume={"action": "approve", "outline_version": 2}),
                                config)
        self.assertEqual(calls, ["research"])
        self.assertEqual(complete["outline_approved_version"], 2)

    def test_planner_researcher_writer_verifier_handoff(self):
        root = Path(__file__).resolve().parents[2]
        sample = state_from_json((root / "docs/examples/synthetic-report-state.json").read_text(
            encoding="utf-8"))
        calls = []

        def plan(request):
            calls.append("planner")
            self.assertEqual(request.ticker, "ABC")
            return sample["outline"]

        def research(state):
            calls.append("researcher")
            self.assertEqual(state["outline_version"], 1)
            final_id = next(key for key, record in sample["evidence_by_id"].items()
                            if record.payload.fiscal_year == 2024)
            return {"research_results": sample["research_results"],
                    "evidence_by_id": sample["evidence_by_id"],
                    "calculations_by_id": sample["calculations_by_id"],
                    "evidence_aliases": {"E1": final_id}}

        def write(state):
            calls.append("writer")
            self.assertEqual(len(state["evidence_by_id"]), 3)
            block = render_block("revenue_block", "Doanh thu đạt {{E1}}.",
                state["evidence_by_id"], state["calculations_by_id"],
                state["evidence_aliases"])
            draft = SectionDraft(section_id="revenue", outline_version=1,
                                 revision=1, blocks=[block])
            return {"section_drafts": {("revenue", 1): draft}}

        graph = build_report_graph(plan, research, write)
        result = graph.invoke({"request": sample["request"]})
        self.assertEqual(calls, ["planner", "researcher", "writer"])
        self.assertEqual(result["verification_results"][("revenue", 1)].level,
                         "deterministic")
        self.assertEqual(result["verification_results"][("revenue", 1)].status,
                         "passed")
        self.assertIn("[Doc_ABC_2024, p.12]", result["final_report"])
        self.assertEqual(result["run_status"], "incomplete")
        self.assertFalse(is_run_complete(result))


if __name__ == "__main__":
    unittest.main()
