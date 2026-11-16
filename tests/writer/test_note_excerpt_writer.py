"""Excerpt-only qualitative drafts and source-bound note placeholders."""
import json
import unittest
from pathlib import Path

from src.agents.llm_writer import build_llm_writer
from src.agents.note_excerpts import excerpt_span
from src.agents.state import state_from_json
from src.agents.template_writer import build_template_writer
from src.agents.verification import render_section_citations, verify_section_deterministically
from src.agents.writer_menu import build_placeholder_menu, validate_template_menu
from src.schemas.report_schema import (
    EvidenceRecord, NotesTask, ReportOutline, ReportRequest, ResearchResult, SectionPlan,
)
from src.tools.schemas import NoteEvidence


ROOT = Path(__file__).resolve().parents[2] / "data/report_output"


class NoteExcerptWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pairs = json.loads((ROOT / "s7_note_pairs_v2_1.json").read_text(
            encoding="utf-8"))["pairs"]
        cls.labels = json.loads((ROOT / "s7_first_annotator_labels_v2_1.json").read_text(
            encoding="utf-8"))["records"]

    def test_labeled_s7_pairs_are_regression_checks(self):
        for label in self.labels:
            pair = next(item for item in self.pairs
                        if item["chunk_id"] == label["chunk_id"] and
                        item["topic"] == label["topic"])
            task = NotesTask(task_id=f"S7:{pair['topic']}:2025",
                             query=pair["query"], fiscal_year=2025)
            span = excerpt_span(task, pair["text"])
            with self.subTest(pair=label["pair_number"]):
                self.assertEqual(span is not None,
                                 label["first_annotator_label"] == "direct")
                if span:
                    self.assertIn(pair["text"][span[0]:span[1]], pair["text"])

    def test_s6_policy_requires_a_substantive_sentence(self):
        task = NotesTask(task_id="S6:revenue_policy:2025",
                         query="Nguyên tắc và thời điểm ghi nhận doanh thu",
                         fiscal_year=2025)
        heading = "2. Chính sách kế toán\nGhi nhận doanh thu:\n"
        self.assertIsNone(excerpt_span(task, heading))
        text = (heading + "Doanh thu được ghi nhận khi dịch vụ đã hoàn thành và "
                "khách hàng chấp nhận kết quả, theo điều khoản của hợp đồng đã ký.")
        span = excerpt_span(task, text)
        self.assertIsNotNone(span)
        self.assertEqual(text[span[0]:span[1]], text[len(heading):])
        note = NoteEvidence(chunk_id="FPT_2025_Hopnhat_chunk_policy",
                            doc_id="FPT_2025_Hopnhat", ticker="FPT",
                            fiscal_year=2025, scope="consolidated", section="NOTES",
                            text=text, source_file="fpt.pdf", physical_pages=[42],
                            printed_pages=["40"],
                            citation_tag="[Doc_FPT_2025_Hopnhat, p.42]")
        record = EvidenceRecord(evidence_id=note.chunk_id, kind="note",
                                snapshot_version="v2.1", payload=note)
        research = {task.task_id: ResearchResult(
            research_task_id=task.task_id, status="sufficient",
            evidence_ids=[note.chunk_id])}
        section = SectionPlan(section_id="S6", title="Chính sách kế toán",
                              objective="Trích đoạn", research_tasks=[task])
        request = ReportRequest(ticker="FPT", start_year=2025, end_year=2025,
                                audience="investors")
        state = {"request": request, "outline": ReportOutline(sections=[section]),
                 "outline_version": 1, "evidence_by_id": {note.chunk_id: record},
                 "evidence_aliases": {"E1": note.chunk_id},
                 "calculations_by_id": {}, "research_results": research}
        draft = next(iter(build_template_writer()(state)["section_drafts"].values()))
        self.assertEqual(len(draft.blocks), 2)
        self.assertEqual(draft.blocks[1].claims[0].evidence_ids, [note.chunk_id])
        self.assertEqual(verify_section_deterministically(
            draft, request, state["evidence_by_id"], {}, research,
            state["evidence_aliases"], section).status, "passed")

    def test_s7_renders_exact_excerpt_with_claim_and_citation(self):
        ids = {"FPT_2025_Hopnhat_chunk_0220", "FPT_2025_Hopnhat_chunk_0216",
               "FPT_2025_Hopnhat_chunk_0048", "FPT_2025_Hopnhat_chunk_0221"}
        selected = [pair for pair in self.pairs if pair["chunk_id"] in ids]
        evidence = {}
        aliases = {}
        for index, pair in enumerate(selected, 1):
            note = NoteEvidence(
                chunk_id=pair["chunk_id"], doc_id="FPT_2025_Hopnhat",
                ticker="FPT", fiscal_year=2025, scope="consolidated",
                section="NOTES", text=pair["text"], source_file="fpt.pdf",
                physical_pages=pair["physical_pages"],
                printed_pages=pair["printed_pages"], citation_tag=pair["citation_tag"])
            evidence[note.chunk_id] = EvidenceRecord(
                evidence_id=note.chunk_id, kind="note", snapshot_version="v2.1",
                payload=note)
            aliases[f"E{index}"] = note.chunk_id
        tasks = []
        research = {}
        for topic in ("commitments", "financial_risks", "subsequent_events"):
            found = [pair for pair in selected if pair["topic"] == topic]
            task = NotesTask(task_id=f"S7:{topic}:2025", query=found[0]["query"],
                             fiscal_year=2025)
            tasks.append(task)
            research[task.task_id] = ResearchResult(
                research_task_id=task.task_id, status="sufficient",
                evidence_ids=[pair["chunk_id"] for pair in found])
        section = SectionPlan(section_id="S7", title="Thuyết minh",
                              objective="Trích đoạn", research_tasks=tasks)
        request = ReportRequest(ticker="FPT", start_year=2025, end_year=2025,
                                audience="investors")
        state = {"request": request, "outline": ReportOutline(sections=[section]),
                 "outline_version": 1, "evidence_by_id": evidence,
                 "evidence_aliases": aliases, "calculations_by_id": {},
                 "research_results": research}
        draft = next(iter(build_template_writer()(state)["section_drafts"].values()))
        self.assertEqual(len([c for b in draft.blocks for c in b.claims]), 2)
        self.assertTrue(all(c.claim_type == "qualitative"
                            for b in draft.blocks for c in b.claims))
        self.assertIn("Chưa chọn được trích đoạn đủ nội dung", draft.blocks[-1].text)
        checked = verify_section_deterministically(
            draft, request, evidence, {}, research, aliases, section)
        self.assertEqual(checked.status, "passed", checked.issues)
        rendered = render_section_citations(draft, evidence, {}, research, section)
        self.assertIn("[Doc_FPT_2025_Hopnhat, p.65-66]", rendered)
        self.assertIn("[Doc_FPT_2025_Hopnhat, p.19-20]", rendered)
        self.assertNotIn("Thành lập công ty con:", rendered)
        menu = build_placeholder_menu(section, state)
        with self.assertRaisesRegex(ValueError, "outside section menu"):
            validate_template_menu("{{N:E2:0:20}}", menu)
        tampered = draft.model_copy(deep=True)
        tampered.blocks[1].text = tampered.blocks[1].text.replace("2025", "2024", 1)
        checked = verify_section_deterministically(
            tampered, request, evidence, {}, research, aliases, section)
        self.assertIn("render_mismatch", [issue.error_type for issue in checked.issues])

    def test_llm_writer_skips_model_when_no_note_evidence_exists(self):
        state = state_from_json((ROOT / "v2_1_fixtures/fpt_research_state.json")
                                .read_text(encoding="utf-8"))
        section = next(item for item in state["outline"].sections
                       if item.section_id == "S2")
        state["outline"] = state["outline"].model_copy(update={"sections": [section]})
        state["research_results"] = {
            task.task_id: ResearchResult(research_task_id=task.task_id,
                                         status="no_evidence")
            for task in section.research_tasks}

        class UnexpectedModel:
            def generate(self, _request):
                raise AssertionError("Quantitative LLM must not receive note excerpts")

        output = build_llm_writer(UnexpectedModel())(state)
        draft = next(iter(output["section_drafts"].values()))
        self.assertEqual(draft.section_id, "S2")
        log = next(iter(output["writer_run_logs"].values()))
        self.assertTrue(log.used_fallback)
        self.assertEqual(log.attempts, 0)
        self.assertEqual(verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"],
            state["evidence_aliases"], section).status, "passed")
        rendered = render_section_citations(
            draft, state["evidence_by_id"], state["calculations_by_id"],
            state["research_results"], section)
        self.assertIn("trong toàn bộ mục kiểm toán đã trích xuất", rendered)
        self.assertNotIn("chỉ tiêu và chỉ tiêu", rendered)

    def test_hut_real_s6_s7_drafts_pass(self):
        state = state_from_json((ROOT / "v2_1_fixtures/hut_w6_note_research_state.json")
                                .read_text(encoding="utf-8"))
        drafts = {draft.section_id: draft for draft in
                  build_template_writer()(state)["section_drafts"].values()}
        self.assertEqual(set(drafts), {"S6", "S7"})
        for section in state["outline"].sections:
            draft = drafts[section.section_id]
            checked = verify_section_deterministically(
                draft, state["request"], state["evidence_by_id"],
                state["calculations_by_id"], state["research_results"],
                state["evidence_aliases"], section)
            self.assertEqual(checked.status, "passed", checked.issues)
            self.assertFalse(any("7. Nguyên tắc kế toán" in block.text
                                 for block in draft.blocks))

    def test_sample_excerpts_answer_their_note_tasks(self):
        for ticker in ("gmd", "fpt"):
            state = state_from_json((ROOT / f"v2_1_fixtures/{ticker}_w6_note_research_state.json")
                                    .read_text(encoding="utf-8"))
            drafts = {draft.section_id: draft for draft in
                      build_template_writer()(state)["section_drafts"].values()}
            if ticker == "gmd":
                self.assertIn("không có công nợ", " ".join(
                    block.text for block in drafts["S7"].blocks))
                self.assertIn("Dự phòng phải thu khó đòi được lập", " ".join(
                    block.text for block in drafts["S6"].blocks))
            else:
                first_state = state_from_json(
                    (ROOT / "v2_1_fixtures/fpt_research_state.json")
                    .read_text(encoding="utf-8"))
                first_draft = next(draft for draft in
                    build_template_writer()(first_state)["section_drafts"].values()
                    if draft.section_id == "S1")
                self.assertIn("công nghệ thông tin và viễn thông", " ".join(
                    block.text for block in first_draft.blocks))
                self.assertNotIn("2.41103", " ".join(
                    block.text for block in drafts["S6"].blocks))


if __name__ == "__main__":
    unittest.main()
