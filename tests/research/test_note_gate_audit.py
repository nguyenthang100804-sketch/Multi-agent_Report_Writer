"""Fixed HUT and GMD note labels for the first W6 retrieval gate."""
import json
import unittest
from pathlib import Path

from src.agents.researcher import _note_matches_topic
from src.agents.state import state_from_json
from src.schemas.report_schema import NotesTask
from src.tools.notes_retriever import classify_audit_chunk


ROOT = Path(__file__).resolve().parents[2]


class NoteGateAuditTests(unittest.TestCase):
    def test_gmd_2025_loan_terms_survive_note_gate(self):
        source = json.loads((ROOT / "data/processed_chunks_v2_1/GMD_2025_Hopnhat.json")
                            .read_text(encoding="utf-8"))
        chunks = {chunk["chunk_id"]: chunk["text"] for chunk in source["chunks"]}
        task = NotesTask(task_id="S4:borrowings:2025",
                         query="Điều khoản và kỳ hạn các khoản vay",
                         fiscal_year=2025, sections=["NOTES"])
        for suffix in ("0163", "0166", "0167"):
            with self.subTest(chunk=suffix):
                self.assertTrue(_note_matches_topic(
                    task, chunks[f"GMD_2025_Hopnhat_chunk_{suffix}"]))
        self.assertFalse(_note_matches_topic(
            task, "Chính sách kế toán: các khoản vay được ghi nhận khi phát sinh."))

    def test_s7_gate_keeps_all_strict_direct_pairs(self):
        folder = ROOT / "data/report_output"
        labels = json.loads((folder / "s7_first_annotator_labels_v2_1.json")
                            .read_text(encoding="utf-8"))["records"]
        pairs = json.loads((folder / "s7_note_pairs_v2_1.json")
                           .read_text(encoding="utf-8"))["pairs"]
        sources = {(item["ticker"], item["topic"], item["chunk_id"]): item
                   for item in pairs}
        self.assertEqual(len(labels), 20)
        for item in labels:
            key = (item["ticker"], item["topic"], item["chunk_id"])
            task = NotesTask(task_id=f"S7:{item['topic']}:2025", query=sources[key]["query"],
                             fiscal_year=2025, sections=["NOTES"])
            if item["first_annotator_label"] == "direct":
                with self.subTest(pair=item["pair_number"]):
                    self.assertTrue(_note_matches_topic(task, sources[key]["text"]))

    def test_labeled_hut_and_gmd_pairs(self):
        for ticker, filename, minimum_precision in (
            ("hut", "hut_note_gate_11_query_audit.json", 1.0),
            ("gmd", "gmd_note_gate_11_query_holdout.json", 0.9),
        ):
            state = state_from_json((ROOT / f"data/report_output/{ticker}_research_state.json")
                                    .read_text(encoding="utf-8"))
            audit = json.loads((ROOT / "data/report_output" / filename)
                               .read_text(encoding="utf-8"))
            tasks = {task.task_id: task for section in state["outline"].sections
                     for task in section.research_tasks if isinstance(task, NotesTask)}
            ids = {record.payload.chunk_id: record.payload
                   for record in state["evidence_by_id"].values()
                   if record.kind == "note"}
            pairs = [(item["label"], _note_matches_topic(tasks[row["task_id"]],
                      ids[item["chunk_id"]].text)) for row in audit["tasks"]
                     for item in row["chunks"]]
            self.assertEqual(len(pairs), 55)
            direct = sum(label == "direct" for label, _ in pairs)
            kept = sum(passed for _, passed in pairs)
            direct_kept = sum(label == "direct" and passed for label, passed in pairs)
            self.assertEqual(direct_kept, direct)
            self.assertGreaterEqual(direct_kept / kept, minimum_precision)

    def test_complete_audit_sections_have_one_opinion_conclusion(self):
        audit = json.loads((ROOT / "data/report_output/audit_sections_hut_gmd_full_read.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(len(audit["reports"]), 8)
        for report in audit["reports"]:
            chunks = report["chunks"]
            self.assertGreaterEqual(len(chunks), 5)
            source = json.loads((ROOT / f"data/processed_chunks/"
                                 f"{report['ticker']}_{report['year']}_Hopnhat.json")
                                .read_text(encoding="utf-8"))
            texts = {chunk["chunk_id"]: chunk["text"] for chunk in source["chunks"]}
            classified = [classify_audit_chunk(texts[item["chunk_id"]]) for item in chunks]
            self.assertEqual(sum("opinion_conclusion" in roles for roles in classified), 1)


if __name__ == "__main__":
    unittest.main()
