"""Reader-facing meaning checks for dated prose, tables, and limitations."""
import re
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from src.agents.draft_rendering import render_block
from src.agents.report_graph import build_report_graph
from src.agents.report_tables import render_section_tables
from src.agents.planner_rules import RATIO_LABELS
from src.agents.state import state_from_json
from src.agents.template_writer import build_template_writer
from src.agents.verification import verify_section_deterministically
from src.agents.writer_menu import build_placeholder_menu, validate_template_menu
from src.schemas.report_schema import SectionDraft


ROOT = Path(__file__).resolve().parents[2]


def fixture(ticker):
    return state_from_json((ROOT / f"data/report_output/{ticker}_research_state.json")
                           .read_text(encoding="utf-8"))


def report(state):
    graph = build_report_graph(
        lambda _request: state["outline"],
        lambda _state: {key: state[key] for key in (
            "research_results", "evidence_by_id", "evidence_aliases",
            "calculations_by_id")},
        build_template_writer())
    return graph.invoke({"request": state["request"]})


class WriterW3Tests(unittest.TestCase):
    def test_year_and_period_placeholders_are_scoped_and_checked(self):
        state = fixture("hut")
        section = next(s for s in state["outline"].sections if s.section_id == "S3")
        menu = build_placeholder_menu(section, state)
        alias = next(alias for alias, metadata in menu["facts"].items()
                     if metadata["label"] == "Doanh thu thuần" and
                     metadata["fiscal_year"] == 2025)
        calculation = "revenue:yoy:2025"
        template = (f"Doanh thu {{{{Y:{alias}}}}} là {{{{{alias}}}}}; "
                    f"mức thay đổi {{{{P:C:{calculation}}}}} là "
                    f"{{{{C:{calculation}}}}}.")
        validate_template_menu(template, menu)
        block = render_block("b", template, state["evidence_by_id"],
                             state["calculations_by_id"], state["evidence_aliases"])
        self.assertIn("năm 2025", block.text)
        self.assertNotIn("năm năm", block.text)
        self.assertIn("năm 2025 so với năm 2024", block.text)
        draft = SectionDraft(section_id="S3", outline_version=1, revision=1,
                             blocks=[block])
        checked = verify_section_deterministically(draft, state["request"],
            state["evidence_by_id"], state["calculations_by_id"],
            state["research_results"], state["evidence_aliases"], section)
        self.assertEqual(checked.status, "passed", checked.issues)
        draft.blocks[0].text = draft.blocks[0].text.replace("2025", "2024", 1)
        checked = verify_section_deterministically(draft, state["request"],
            state["evidence_by_id"], state["calculations_by_id"],
            state["research_results"], state["evidence_aliases"], section)
        self.assertIn("render_mismatch", [issue.error_type for issue in checked.issues])

    def test_reader_reports_have_short_dated_prose_and_no_internal_ids(self):
        for ticker in ("hut", "gmd", "fpt"):
            with self.subTest(ticker=ticker):
                state = fixture(ticker)
                result = report(state)
                self.assertEqual(result["run_status"], "incomplete")
                self.assertTrue(all(value.status == "passed" for value in
                                    result["verification_results"].values()))
                self.assertEqual(result["final_report"].count("### Số liệu theo năm"), 3)
                for draft in result["section_drafts"].values():
                    if draft.section_id not in {"S3", "S4", "S5"}:
                        continue
                    claims = [block for block in draft.blocks if block.claims]
                    self.assertGreaterEqual(len(claims), 3)
                    self.assertLessEqual(len(claims), 5)
                    for block in claims:
                        self.assertRegex(block.text, r"\b20\d{2}\b")
                        self.assertRegex(block.template, r"\{\{(?:Y:|P:C:)")
                no_citations = re.sub(r"\[Doc_[^\]]+\]", "", result["final_report"])
                self.assertNotRegex(no_citations, r"\b[a-z]+(?:_[a-z]+)+(?::\d+)?\b")
                reader_lines = "\n".join(line for line in no_citations.splitlines()
                                         if not line.startswith("|---"))
                self.assertNotRegex(reader_lines, r"\b[a-z_]+:[a-z_]+")
                self.assertNotIn("Phần này trình bày", no_citations)
                self.assertNotIn("Nguồn của từng nhận định", no_citations)
                self.assertNotIn("năm 0 ", no_citations)

    def test_fpt_missing_data_cites_affected_rows_only_and_groups_effects(self):
        result = report(fixture("fpt"))
        lines = result["final_report"].splitlines()
        absent = next(line for line in lines if "mã 61" in line and
                      "chưa tìm thấy số liệu" in line)
        self.assertIn("2024, 2025", absent)
        self.assertNotIn("[Doc_", absent)
        self.assertEqual(sum("Dữ liệu trích xuất không có giá trị cho" in line for line in lines), 1)
        self.assertEqual(sum("hai giá trị không khớp" in line for line in lines), 2)
        self.assertTrue(any("Lưu chuyển tiền thuần từ hoạt động kinh doanh năm 2024 là 9.517,10 tỷ đồng" in line for line in lines))
        self.assertTrue(any("Lưu chuyển tiền thuần từ hoạt động đầu tư năm 2024 là -6.548,37 tỷ đồng" in line for line in lines))
        self.assertTrue(any("Vì vậy không tính được" in line for line in lines))
        self.assertFalse(any("thiếu giá trị hoặc nghi vấn" in line for line in lines))

    def test_null_and_suspect_sources_get_distinct_limitations(self):
        state = fixture("fpt")
        for key in state["research_results"]["operating_cash_flow"].evidence_ids:
            fact = state["evidence_by_id"][key].payload
            if fact.fiscal_year in (2022, 2025):
                fact.value = 1
                fact.suspect = True
        text = report(state)["final_report"]
        self.assertIn("có số liệu bị đánh dấu nghi vấn năm 2022, 2025", text)
        self.assertIn("Dữ liệu trích xuất không có giá trị", text)

    def test_same_presentation_rules_for_all_three_tickers(self):
        rows_by_ticker = {}
        for ticker in ("hut", "gmd", "fpt"):
            state = fixture(ticker)
            text = report(state)["final_report"]
            self.assertNotIn("Lưu ý.", text)
            self.assertIn("Tốc độ tăng trưởng kép hằng năm của Doanh thu thuần", text)
            self.assertIn("{{T:revenue:trend:2025}}", "\n".join(
                block.template for draft in build_template_writer()(state)["section_drafts"].values()
                for block in draft.blocks))
            rows_by_ticker[ticker] = {
                line.split(" | ")[0] for line in text.splitlines()
                if line.startswith("| ") and (" — YoY (%)" in line or
                                               " — chênh lệch (tỷ đồng)" in line)}
        self.assertEqual(rows_by_ticker["hut"], rows_by_ticker["gmd"])
        self.assertEqual(rows_by_ticker["gmd"], rows_by_ticker["fpt"])

    def test_every_allowed_calculation_has_value_or_explanation(self):
        for ticker in ("hut", "gmd", "fpt"):
            with self.subTest(ticker=ticker):
                state = fixture(ticker)
                result = report(state)
                for section in state["outline"].sections:
                    if section.section_id not in ("S3", "S4", "S5"):
                        continue
                    draft = next(d for d in result["section_drafts"].values()
                                 if d.section_id == section.section_id)
                    table = render_section_tables(section, state)
                    prose = "\n".join(block.template for block in draft.blocks)
                    rows = [line.split("|")[1:-1] for line in table.splitlines()
                            if line.startswith("| ")]
                    for key in section.calculations_allowed:
                        calc = state["calculations_by_id"][key]
                        if calc.operation in ("yoy", "difference"):
                            spec = next(x for x in section.calculation_specs
                                        if x.calculation_id == key)
                            task = next(x for x in section.research_tasks
                                        if x.task_id == spec.source_task_id)
                            suffix = " — YoY (%)" if calc.operation == "yoy" else " — chênh lệch (tỷ đồng)"
                            row = next(row for row in rows
                                       if row[0].strip() == task.metric_name + suffix)
                            cell = row[spec.end_year - state["request"].start_year].strip()
                        elif calc.operation == "ratio":
                            label = RATIO_LABELS[key.rsplit(":", 1)[0]]
                            row = next(row for row in rows if row[0].strip() == label)
                            year = int(key.rsplit(":", 1)[1])
                            cell = row[year - state["request"].start_year + 1].strip()
                        else:
                            cell = None
                        if calc.status == "cannot_compute":
                            self.assertTrue(any(l.kind == "cannot_compute" and
                                                l.calculation_id == key
                                                for l in draft.limitations), key)
                            if cell is not None:
                                self.assertEqual(cell, "—", key)
                        elif calc.operation in ("cagr", "trend"):
                            self.assertIn(f"{{{{{'T' if calc.operation == 'trend' else 'C'}:{key}}}}}", prose)
                        else:
                            self.assertNotEqual(cell, "—", key)
                            self.assertIn("[Doc_", cell, key)

    def test_fpt_raw_cells_and_rounded_assets_are_distinct(self):
        state = fixture("fpt")
        for task_id in ("operating_cash_flow", "investing_cash_flow"):
            rows = [state["evidence_by_id"][key].payload for key in
                    state["research_results"][task_id].evidence_ids]
            for year in (2022, 2025):
                row = next(row for row in rows if row.fiscal_year == year)
                self.assertEqual(row.raw_value, "")
                self.assertIs(row.suspect, False)
        assets = [state["evidence_by_id"][key].payload for key in
                  state["research_results"]["assets"].evidence_ids]
        row = next(row for row in assets if row.fiscal_year == 2024)
        self.assertEqual(row.raw_value, "71.999.995.678.620")
        self.assertNotEqual(Decimal(str(row.value)), Decimal("72000000000000"))
        self.assertIn("72.000,00", render_section_tables(
            next(s for s in state["outline"].sections if s.section_id == "S4"), state))
        for year, expected in ((2024, Decimal("19.44")),
                               (2025, Decimal("22.42"))):
            calculation = state["calculations_by_id"][f"assets:yoy:{year}"]
            by_year = {state["evidence_by_id"][key].payload.fiscal_year:
                       Decimal(str(state["evidence_by_id"][key].payload.value))
                       for key in calculation.input_evidence_ids}
            exact = ((by_year[year] - by_year[year - 1]) / by_year[year - 1] *
                     100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self.assertEqual(calculation.value, exact)
            self.assertEqual(calculation.value, expected)

    def test_gmd_two_monetary_claims_share_scale_in_one_sentence(self):
        state = fixture("gmd")
        alias = next(alias for alias, key in state["evidence_aliases"].items()
                     if (state["evidence_by_id"][key].kind == "fact" and
                         state["evidence_by_id"][key].payload.code == "20" and
                         state["evidence_by_id"][key].payload.fiscal_year == 2023 and
                         state["evidence_by_id"][key].payload.report_type == "CASH_FLOW"))
        key = "operating_cash_flow:difference:2023"
        block = render_block("gmd", f"Chênh lệch {{{{P:C:{key}}}}} là "
            f"{{{{C:{key}}}}}, còn mức {{{{Y:{alias}}}}} là {{{{{alias}}}}}.",
            state["evidence_by_id"], state["calculations_by_id"],
            state["evidence_aliases"])
        self.assertEqual({claim.display_unit for claim in block.claims}, {"tỷ đồng"})
        self.assertNotIn("nghìn tỷ đồng", block.text)
        self.assertIn("-2.302,1 tỷ đồng", block.text)
        self.assertIn("-2,9 tỷ đồng", block.text)

    def test_table_uses_one_scale_and_preserves_source_values(self):
        hut = fixture("hut")
        s3 = next(s for s in hut["outline"].sections if s.section_id == "S3")
        table = render_section_tables(s3, hut)
        revenue = next(line for line in table.splitlines() if line.startswith("| Doanh thu thuần |"))
        self.assertIn("1.073,16 [Doc_HUT_2022_Hopnhat, p.11]", revenue)
        self.assertIn("10.981,75 [Doc_HUT_2023_Hopnhat, p.11]", revenue)
        self.assertIn("### Biến động theo kỳ", table)
        self.assertIn("923,31%", table)
        gmd = fixture("gmd")
        s5 = next(s for s in gmd["outline"].sections if s.section_id == "S5")
        table = render_section_tables(s5, gmd)
        self.assertIn("### Số liệu theo năm (tỷ đồng)", table)
        self.assertNotIn("nghìn tỷ đồng", table)
        self.assertIn("-2,87 [Doc_GMD_2023_Hopnhat, p.11]", table)
        self.assertIn("2.142,02 [Doc_GMD_2025_Hopnhat, p.11]", table)


if __name__ == "__main__":
    unittest.main()
