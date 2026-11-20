"""Render an audited absence separately from a retrieval miss."""
import unittest

from src.agents.verification import _render_limitations
from src.schemas.report_schema import (DataGapLimitation, MissingItem, NotesTask,
                                       ResearchResult, SectionPlan)


class AuditEmphasisRenderingTests(unittest.TestCase):
    def test_partial_financial_risks_name_only_missing_subtopics(self):
        task = NotesTask(task_id="S7:financial_risks:2025",
                         query="Rủi ro thanh khoản tín dụng tỷ giá lãi suất",
                         fiscal_year=2025, sections=["NOTES"])
        section = SectionPlan(section_id="S7", title="Rủi ro",
                              objective="Rà soát rủi ro", research_tasks=[task])
        research = ResearchResult(research_task_id=task.task_id, status="partial",
            evidence_ids=["risk-note"], missing=[
                MissingItem(reason="not_found_yet", description="Rủi ro tín dụng"),
                MissingItem(reason="not_found_yet", description="Rủi ro lãi suất")])
        lines = _render_limitations([
            DataGapLimitation(research_task_id=task.task_id, block_id="b1")],
            {}, {}, {task.task_id: research}, section)
        self.assertEqual(len(lines), 1)
        self.assertIn("rủi ro tín dụng, rủi ro lãi suất", lines[0])
        self.assertNotIn("rủi ro thanh khoản", lines[0])

    def test_full_audit_survey_is_one_scoped_observation(self):
        tasks = [NotesTask(task_id=f"S2:emphasis:{year}", query="Vấn đề nhấn mạnh",
                           fiscal_year=year, sections=["AUDIT_REPORT"])
                 for year in range(2022, 2026)]
        section = SectionPlan(section_id="S2", title="Ý kiến kiểm toán",
                              objective="Rà soát kiểm toán", research_tasks=tasks)
        limitations = [DataGapLimitation(research_task_id=task.task_id, block_id="b1")
                       for task in tasks]
        results = {task.task_id: ResearchResult(
            research_task_id=task.task_id, status="no_evidence",
            missing=[MissingItem(reason="not_in_corpus",
                                 description="không tìm thấy trong toàn bộ mục kiểm toán đã trích xuất")])
            for task in tasks}

        lines = _render_limitations(limitations, {}, {}, results, section)
        self.assertEqual(len(lines), 1)
        self.assertIn("2022, 2023, 2024, 2025", lines[0])
        self.assertIn("chưa tìm thấy đoạn trình bày", lines[0])
        self.assertNotIn("Giới hạn truy xuất", lines[0])

        results[tasks[0].task_id].missing[0] = MissingItem(
            reason="not_found_yet", description="chưa tìm thấy trong các đoạn được truy xuất")
        lines = _render_limitations(limitations[:1], {}, {}, results, section)
        self.assertEqual(len(lines), 1)
        self.assertIn("Giới hạn truy xuất", lines[0])


if __name__ == "__main__":
    unittest.main()
