"""Reducers and approval must preserve provenance and revision boundaries."""
import unittest
from pathlib import Path

from src.agents.state import (
    StaleEvidenceError, approved_draft, can_complete, check_snapshot_on_resume,
    complete_run, is_run_complete, merge_immutable, merge_revisions,
    state_from_json, state_to_json,
)
from src.schemas.report_schema import FactTask, TimeSeriesTask, record_tool_result
from src.tools.schemas import ToolResult
from tests.report.test_report_schema import fact
from src.schemas.report_schema import (
    DraftBlock, ReportOutline, ReportRequest, SectionDraft, SectionPlan,
    VerificationResult,
)


class ReportStateTests(unittest.TestCase):
    def test_two_tasks_can_share_one_fact_record(self):
        row = fact(2024, 150)
        fact_task = FactTask(task_id="single", item_code="10",
                             report_type="INCOME_STATEMENT", fiscal_year=2024)
        series_task = TimeSeriesTask(task_id="series", item_code="10",
                                     report_type="INCOME_STATEMENT",
                                     start_year=2024, end_year=2024)
        first, first_records = record_tool_result(fact_task, ToolResult(
            status="ok", facts=[row]), "snapshot")
        second, second_records = record_tool_result(series_task, ToolResult(
            status="ok", facts=[row]), "snapshot")
        self.assertEqual(first.evidence_ids, second.evidence_ids)
        self.assertEqual(len(merge_immutable(first_records, second_records)), 1)

    def test_complete_example_round_trips_with_evidence(self):
        path = Path(__file__).resolve().parents[2] / "docs" / "examples" / "synthetic-report-state.json"
        state = state_from_json(path.read_text(encoding="utf-8"))
        self.assertTrue(can_complete(state))
        self.assertEqual(len(state["evidence_by_id"]), 3)
        self.assertEqual(state_from_json(state_to_json(state)), state)
        check_snapshot_on_resume(state, "example-snapshot-v1")
        check_snapshot_on_resume(state, {"fact": "example-snapshot-v1", "note": "index-v1"})
        with self.assertRaises(StaleEvidenceError):
            check_snapshot_on_resume(state, "new-snapshot")

    def test_conflicting_evidence_cannot_overwrite(self):
        with self.assertRaises(ValueError):
            merge_immutable({"e1": "old"}, {"e1": "new"})

    def test_old_verification_cannot_approve_new_draft(self):
        outline = ReportOutline(sections=[SectionPlan(section_id="revenue", title="Revenue",
                                                      objective="Explain revenue")])
        first = SectionDraft(section_id="revenue", outline_version=1, revision=1,
                             blocks=[DraftBlock(block_id="b1", text="First")])
        second = SectionDraft(section_id="revenue", outline_version=1, revision=2,
                              blocks=[DraftBlock(block_id="b1", text="Second")])
        state = {"request": ReportRequest(ticker="ABC", start_year=2022, end_year=2024,
                                           audience="investors"),
                 "outline": outline, "outline_version": 1, "outline_approved_version": 1,
                 "section_drafts": {("revenue", 1): first, ("revenue", 2): second},
                 "verification_results": {("revenue", 1): VerificationResult(
                     section_id="revenue", revision=1, level="full", status="passed")}}
        self.assertIsNone(approved_draft(state, "revenue"))
        self.assertFalse(can_complete(state))
        state["verification_results"][("revenue", 2)] = VerificationResult(
            section_id="revenue", revision=2, level="full", status="passed")
        self.assertTrue(can_complete(state))
        state["outline_version"] = 2
        self.assertFalse(can_complete(state))
        with self.assertRaises(ValueError):
            complete_run(state)
        state["run_status"] = "completed"
        self.assertFalse(is_run_complete(state))
        with self.assertRaises(ValueError):
            state_to_json(state)
        state["run_status"] = "running"
        restored = state_from_json(state_to_json(state))
        self.assertEqual(restored["section_drafts"][("revenue", 2)], second)
        self.assertEqual(restored["request"], state["request"])

    def test_completion_requires_current_verification(self):
        state = state_from_json((Path(__file__).resolve().parents[2] / "docs" / "examples" /
                                 "synthetic-report-state.json").read_text(encoding="utf-8"))
        self.assertEqual(complete_run(state), {"run_status": "completed"})

    def test_full_report_cannot_complete_after_main_section_is_removed(self):
        outline = ReportOutline(sections=[SectionPlan(
            section_id=f"S{number}", title=f"Mục {number}", objective="Phân tích")
            for number in range(1, 8)])
        state = {"outline": outline, "outline_version": 1,
                 "outline_approved_version": 1,
                 "full_outline_required": True,
                 "outlines_by_revision": {1: outline.model_copy(deep=True)},
                 "section_drafts": {(f"S{number}", 1): SectionDraft(
                     section_id=f"S{number}", outline_version=1, revision=1,
                     blocks=[DraftBlock(block_id="b", text="Bản nháp")])
                     for number in range(1, 8)},
                 "verification_results": {(f"S{number}", 1): VerificationResult(
                     section_id=f"S{number}", revision=1, level="full", status="passed")
                     for number in range(1, 8)}}
        self.assertTrue(can_complete(state))
        state["outline"] = outline.model_copy(deep=True)
        state["outline"].sections.pop()
        self.assertFalse(can_complete(state))
        with self.assertRaises(ValueError):
            complete_run(state)

    def test_revision_conflict(self):
        with self.assertRaises(ValueError):
            merge_revisions({("a", 1): "old"}, {("a", 1): "new"})

    def test_old_outline_verification_cannot_approve_new_outline(self):
        outline = ReportOutline(outline_id="same", sections=[SectionPlan(
            section_id="S1", title="Title", objective="Objective")])
        draft = SectionDraft(section_id="S1", outline_version=2, revision=1,
                             blocks=[DraftBlock(block_id="b", text="text")])
        state = {"outline": outline, "outline_version": 2,
                 "outline_approved_version": 2,
                 "section_drafts": {(2, "S1", 1): draft},
                 "verification_results": {("S1", 1): VerificationResult(
                     section_id="S1", revision=1, outline_version=1,
                     level="full", status="passed")}}
        self.assertFalse(can_complete(state))
        current = VerificationResult(section_id="S1", revision=1, outline_version=2,
                                     level="full", status="passed")
        state["verification_results"][(2, "S1", 1)] = current
        self.assertTrue(can_complete(state))
        restored = state_from_json(state_to_json(state))
        self.assertEqual(restored["verification_results"][(2, "S1", 1)], current)


if __name__ == "__main__":
    unittest.main()
