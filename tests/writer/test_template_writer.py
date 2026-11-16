"""Section menus, strict new drafts, and deterministic quantitative writing."""
import re
import unittest
from pathlib import Path

from src.agents.draft_rendering import TOKEN, render_block, render_template
from src.agents.report_graph import build_report_graph
from src.agents.report_tables import render_section_tables
from src.agents.state import state_from_json
from src.agents.template_writer import build_template_writer
from src.agents.verification import render_section_citations, verify_section_deterministically
from src.agents.writer_menu import build_placeholder_menu, validate_template_menu
from src.schemas.report_schema import DraftBlock, SectionDraft, SectionPlan


ROOT = Path(__file__).resolve().parents[2]


def fixture(ticker):
    return state_from_json((ROOT / f"data/report_output/{ticker}_research_state.json")
                           .read_text(encoding="utf-8"))


def assert_number_lineage(test, block, state):
    """Every digit span in text must lie inside a rendered placeholder span."""
    template = block.template
    cursor = 0
    rebuilt = ""
    spans = []
    for match in TOKEN.finditer(template):
        rebuilt += template[cursor:match.start()]
        value, _ = render_template(match.group(), block.block_id,
            state["evidence_by_id"], state["calculations_by_id"],
            state["evidence_aliases"])
        start = len(rebuilt)
        rebuilt += value
        spans.append((start, len(rebuilt)))
        cursor = match.end()
    rebuilt += template[cursor:]
    test.assertEqual(rebuilt, block.text)
    for number in re.finditer(r"\d(?:[\d.,]*\d)?", block.text):
        test.assertTrue(any(start <= number.start() and number.end() <= end
                            for start, end in spans),
                        f"Untraceable number {number.group()} in {block.block_id}")


class TemplateWriterTests(unittest.TestCase):
    def test_new_writer_draft_requires_template_but_legacy_fixture_loads(self):
        old = state_from_json((ROOT / "docs/examples/synthetic-report-state.json")
                              .read_text(encoding="utf-8"))
        self.assertIsNone(next(iter(old["section_drafts"].values())).blocks[0].template)
        outline = old["outline"]

        def fake_writer(_state):
            return {"section_drafts": {("revenue", 1): SectionDraft(
                section_id="revenue", outline_version=1, revision=1,
                blocks=[DraftBlock(block_id="b", text="Số tự gõ 100.")])}}

        graph = build_report_graph(lambda _request: outline, lambda _state: {}, fake_writer)
        with self.assertRaisesRegex(ValueError, "missing_template"):
            graph.invoke({"request": old["request"]})

    def test_menu_is_scoped_and_aliases_are_stable(self):
        state = fixture("hut")
        sections = {section.section_id: section for section in state["outline"].sections}
        s3 = build_placeholder_menu(sections["S3"], state)
        s4 = build_placeholder_menu(sections["S4"], state)
        self.assertTrue(s3["facts"] and s4["facts"])
        self.assertFalse(set(s3["facts"]) & set(s4["facts"]))
        self.assertEqual(set(s3["calculations"]) | set(s3["trends"]),
                         set(sections["S3"].calculations_allowed))
        first = next(iter(s3["facts"]))
        self.assertIn("label", s3["facts"][first])
        self.assertIn("fiscal_year", s3["facts"][first])
        self.assertIn("unit", s3["facts"][first])
        other = next(iter(s4["facts"]))
        with self.assertRaisesRegex(ValueError, "outside section menu"):
            validate_template_menu(f"{{{{{other}}}}}", s3)
        wrong_block = render_block("b", f"Chỉ tiêu đạt {{{{{other}}}}}.",
            state["evidence_by_id"], state["calculations_by_id"],
            state["evidence_aliases"])
        wrong_draft = SectionDraft(section_id="S3", outline_version=1, revision=1,
                                   blocks=[wrong_block])
        verified = verify_section_deterministically(
            wrong_draft, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"],
            state["evidence_aliases"], sections["S3"])
        self.assertIn("placeholder_out_of_menu",
                      [issue.error_type for issue in verified.issues])
        calc = next(iter(s4["calculations"]))
        with self.assertRaisesRegex(ValueError, "outside section menu"):
            validate_template_menu(f"{{{{C:{calc}}}}}", s3)
        shared_task = next(task for task in sections["S3"].research_tasks
                           if task.task_id == "revenue")
        shared = SectionPlan(section_id="X", title="Shared", objective="Shared",
                             research_tasks=[shared_task])
        self.assertEqual(set(build_placeholder_menu(shared, state)["facts"]),
                         {alias for alias, evidence_id in state["evidence_aliases"].items()
                          if evidence_id in state["research_results"]["revenue"].evidence_ids})
        extended = dict(state)
        extended["evidence_by_id"] = {**state["evidence_by_id"],
                                       "new": next(iter(state["evidence_by_id"].values()))}
        extended["evidence_aliases"] = {**state["evidence_aliases"], "E999": "new"}
        self.assertEqual(build_placeholder_menu(sections["S3"], extended), s3)
        fpt = fixture("fpt")
        fpt_s5 = next(s for s in fpt["outline"].sections if s.section_id == "S5")
        fpt_menu = build_placeholder_menu(fpt_s5, fpt)
        self.assertFalse(set(fpt_menu["calculations"]) & {
            key for key, value in fpt["calculations_by_id"].items()
            if value.status == "cannot_compute"})

    def test_hut_gmd_fpt_drafts_pass_and_all_numbers_have_sources(self):
        for ticker in ("hut", "gmd", "fpt"):
            with self.subTest(ticker=ticker):
                state = fixture(ticker)
                drafts = build_template_writer()(state)["section_drafts"]
                self.assertEqual({draft.section_id for draft in drafts.values()},
                                 {"S1", "S2", "S3", "S4", "S5"})
                for section in state["outline"].sections:
                    if section.section_id not in {"S3", "S4", "S5"}:
                        continue
                    draft = next(draft for draft in drafts.values()
                                 if draft.section_id == section.section_id)
                    for block in draft.blocks:
                        self.assertIsNotNone(block.template)
                        assert_number_lineage(self, block, state)
                        if block.claims:
                            self.assertRegex(block.text, r"\b20\d{2}\b")
                            self.assertRegex(block.template, r"\{\{(?:Y:|P:C:)")
                    self.assertGreaterEqual(sum(bool(b.claims) for b in draft.blocks), 3)
                    self.assertLessEqual(sum(bool(b.claims) for b in draft.blocks), 5)
                    result = verify_section_deterministically(
                        draft, state["request"], state["evidence_by_id"],
                        state["calculations_by_id"], state["research_results"],
                        state["evidence_aliases"], section)
                    self.assertEqual(result.status, "passed", result.issues)
                if ticker == "fpt":
                    s3 = next(d for d in drafts.values() if d.section_id == "S3")
                    s5 = next(d for d in drafts.values() if d.section_id == "S5")
                    s3_text = render_section_citations(s3, state["evidence_by_id"],
                        state["calculations_by_id"], state["research_results"],
                        next(s for s in state["outline"].sections if s.section_id == "S3"))
                    s5_text = render_section_citations(s5, state["evidence_by_id"],
                        state["calculations_by_id"], state["research_results"],
                        next(s for s in state["outline"].sections if s.section_id == "S5"))
                    self.assertIn("mã 61", s3_text)
                    self.assertIn("2024, 2025", s3_text)
                    missing_line = next(line for line in s3_text.splitlines()
                                        if "mã 61" in line)
                    self.assertNotIn("[Doc_", missing_line)
                    self.assertEqual(s5_text.count("Dữ liệu trích xuất không có giá trị cho"), 1)
                    self.assertIn("Vì vậy không tính được", s5_text)
                    self.assertIn("hai giá trị không khớp", s5_text)
                    prose = re.sub(r"\[Doc_[^\]]+\]", "", s3_text + s5_text)
                    self.assertNotRegex(prose, r"[_:]")

    def test_zero_denominator_reason_reaches_limitation_sentence(self):
        state = fixture("fpt")
        section = next(s for s in state["outline"].sections if s.section_id == "S5")
        key = "cfo_to_net_income:2025"
        state["calculations_by_id"][key] = state["calculations_by_id"][key].model_copy(
            update={"reason": "Ratio denominator is zero"})
        draft = next(d for d in build_template_writer()(state)["section_drafts"].values()
                     if d.section_id == section.section_id)
        text = render_section_citations(draft, state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"])
        self.assertIn("mẫu số bằng không", text)

    def test_synthetic_negative_fact_has_number_lineage(self):
        state = fixture("hut")
        source = next(record for record in state["evidence_by_id"].values()
                      if record.kind == "fact" and record.payload.unit == "VND")
        source = source.model_copy(deep=True)
        source.evidence_id = "synthetic"
        source.payload.value = -1_200_000_000
        synthetic = {"evidence_by_id": {"synthetic": source},
                     "calculations_by_id": {}, "evidence_aliases": {"E1": "synthetic"}}
        block = render_block("b", "Quy mô tuyệt đối {{E1|abs}}.",
            synthetic["evidence_by_id"], {}, synthetic["evidence_aliases"])
        assert_number_lineage(self, block, synthetic)

    def test_no_filler_and_period_change_table(self):
        state = fixture("hut")
        sections = {s.section_id: s for s in state["outline"].sections}
        draft = next(d for d in build_template_writer()(state)["section_drafts"].values()
                     if d.section_id == "S3")
        text = "\n".join(block.text for block in draft.blocks)
        self.assertIn("Tốc độ tăng trưởng kép", text)
        self.assertIn("{{T:revenue:trend:2025}}", "\n".join(
            block.template for block in draft.blocks))
        self.assertNotIn("Phần này trình bày", text)
        self.assertNotIn("Nguồn của từng nhận định", text)
        table = render_section_tables(sections["S5"], state)
        self.assertIn("Số liệu theo năm (tỷ đồng)", table)
        self.assertIn("Biến động theo kỳ", table)
        self.assertIn("2.825,46%", table)


if __name__ == "__main__":
    unittest.main()
