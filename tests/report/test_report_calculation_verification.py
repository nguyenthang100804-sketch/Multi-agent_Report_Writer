"""Arithmetic, citation rendering and deterministic verification contracts."""
import json
import copy
import unittest
from decimal import Decimal
from pathlib import Path

from src.agents.calculations import calculate_cagr, calculate_difference, calculate_ratio, calculate_yoy
from src.agents.period_consistency import scan_period_consistency
from src.agents.state import approved_draft, state_from_json
from src.agents.verification import render_section_citations, verify_section_deterministically
from src.schemas.report_schema import (
    CalculationResult, Claim, DraftBlock, DraftLimitation, EvidenceRecord,
    ReportRequest, SectionDraft,
    TimeSeriesTask, evidence_id_for,
    note_citation_matches_source, record_tool_result,
)
from src.tools.schemas import NoteEvidence, ToolResult
from src.tools.metric_resolver import normalize_name
from tests.report.test_report_schema import fact


class ReportCalculationVerificationTests(unittest.TestCase):
    def test_footnote_marker_does_not_change_metric_name(self):
        self.assertEqual(normalize_name("Tiền trả nợ gốc vay (*)"),
                         normalize_name("Tiền trả nợ gốc vay"))

    def test_mixed_direction_phrase_is_not_read_as_two_directions(self):
        from src.agents.verification import _direction_matches
        self.assertTrue(_direction_matches("Doanh thu tăng giảm qua các năm.", "mixed"))
        self.assertFalse(_direction_matches("Doanh thu tăng giảm qua các năm.", "increasing"))

    def example_state(self):
        root = Path(__file__).resolve().parents[2]
        return state_from_json((root / "docs/examples/synthetic-report-state.json").read_text(
            encoding="utf-8"))

    def verify_state(self, state):
        return verify_section_deterministically(
            state["section_drafts"][("revenue", 1)], state["request"],
            state["evidence_by_id"], state["calculations_by_id"],
            state["research_results"])

    def series(self, values):
        years = list(range(2022, 2022 + len(values)))
        task = TimeSeriesTask(task_id="ts", item_code="10", report_type="INCOME_STATEMENT",
                              start_year=years[0], end_year=years[-1])
        return record_tool_result(task, ToolResult(status="ok", safe_for_calculation=True,
            facts=[fact(year, value) for year, value in zip(years, values)]), "s1")

    def test_yoy_cagr_difference_and_formula_guards(self):
        research, evidence = self.series([100, 120])
        self.assertEqual(calculate_yoy("y", research, evidence, 2022, 2023).value, 20)
        self.assertEqual(calculate_difference("d", research, evidence, 2022, 2023).value, 20)
        research.warnings.append("period_inconsistency:2024->2025")
        self.assertEqual(calculate_yoy("y", research, evidence, 2022, 2023).value, 20)
        research.warnings.append("period_inconsistency:2022->2023")
        self.assertEqual(calculate_yoy("y", research, evidence, 2022, 2023).status,
                         "cannot_compute")
        research.warnings.clear()
        self.assertEqual(calculate_yoy("y", research, evidence, 2022, 2024).status,
                         "cannot_compute")
        research, evidence = self.series([100, 110, 121])
        self.assertEqual(calculate_cagr("c", research, evidence, 2022, 2024).value, 10)
        research, evidence = self.series([0, 120])
        self.assertEqual(calculate_yoy("y", research, evidence, 2022, 2023).status,
                         "cannot_compute")
        self.assertEqual(calculate_cagr("c", research, evidence, 2022, 2023).status,
                         "cannot_compute")
        research.safe_for_calculation = False
        self.assertEqual(calculate_difference("d", research, evidence, 2022, 2023).status,
                         "cannot_compute")

    def test_ratio_and_negative_yoy_base(self):
        research, evidence = self.series([-100, 120])
        self.assertEqual(calculate_yoy("y", research, evidence, 2022, 2023).status,
                         "cannot_compute")
        self.assertEqual(calculate_difference("d", research, evidence, 2022, 2023).value,
                         220)
        first, second = research.evidence_ids
        row = evidence[second].payload
        denominator = row.model_copy(update={"code": "20", "label": "Lợi nhuận gộp",
                                              "value": 480})
        denominator_id = evidence_id_for(denominator)
        evidence[denominator_id] = EvidenceRecord(
            evidence_id=denominator_id, kind="fact", snapshot_version="s1",
            payload=denominator)
        self.assertEqual(calculate_ratio("margin", second, denominator_id, evidence).value,
                         25)
        self.assertEqual(calculate_ratio("bad", second, first, evidence).status,
                         "cannot_compute")
        self.assertEqual(calculate_ratio("warned", second, denominator_id, evidence,
            warnings=["period_inconsistency:2023->2024"]).status, "cannot_compute")
        incompatible = denominator.model_copy(update={"unit": "million_VND"})
        evidence[denominator_id] = EvidenceRecord(
            evidence_id=denominator_id, kind="fact", snapshot_version="s1",
            payload=incompatible)
        self.assertEqual(calculate_ratio("unit", second, denominator_id, evidence).status,
                         "cannot_compute")

    def test_real_note_range_citation(self):
        root = Path(__file__).resolve().parents[2]
        doc = json.loads((root / "data/processed_chunks/OIL_2023_Hopnhat.json").read_text(
            encoding="utf-8"))
        chunk = next(c for c in doc["chunks"]
                     if c["chunk_id"] == "OIL_2023_Hopnhat_chunk_0137")
        note = NoteEvidence(**{key: chunk[key] for key in (
            "chunk_id", "section", "text", "physical_pages", "printed_pages", "citation_tag")},
            doc_id=doc["doc_id"], ticker=doc["ticker"], fiscal_year=doc["fiscal_year"],
            scope=doc["scope"], source_file=doc["source_file"], rerank_score=0.0)
        self.assertEqual(note.citation_tag, "[Doc_OIL_2023_Hopnhat, p.39-40]")
        self.assertTrue(note_citation_matches_source(note))
        self.assertFalse(note_citation_matches_source(note.model_copy(
            update={"citation_tag": "[OIL-2025-Hopnhat-p14]"})))

    def test_renderer_and_deterministic_verifier(self):
        state = self.example_state()
        draft = state["section_drafts"][("revenue", 1)]
        text = render_section_citations(draft, state["evidence_by_id"])
        self.assertIn("[Doc_ABC_2024, p.12]", text)
        self.assertEqual(text.count("[Doc_ABC_2024, p.12]"), 1)
        result = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"])
        self.assertEqual((result.level, result.status, result.issues),
                         ("deterministic", "passed", []))
        state["verification_results"][("revenue", 1)] = result
        self.assertIsNone(approved_draft(state, "revenue"))
        bad = draft.model_copy(deep=True)
        bad.blocks[0].claims[0].value = 999
        result = verify_section_deterministically(
            bad, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"])
        self.assertIn("value_mismatch", [issue.error_type for issue in result.issues])
        state["calculations_by_id"]["revenue_trend"].input_evidence_ids.append("absent")
        self.assertIn("missing_evidence", [issue.error_type for issue in
            self.verify_state(state).issues])
        bad.blocks[0].claims[0].evidence_ids = ["absent"]
        with self.assertRaisesRegex(ValueError, "Unknown evidence ID"):
            render_section_citations(bad, state["evidence_by_id"])

    def test_trend_word_must_match_asserted_direction(self):
        state = self.example_state()
        block = state["section_drafts"][("revenue", 1)].blocks[0]
        block.text = block.text.replace("tăng liên tiếp", "giảm liên tiếp")
        result = self.verify_state(state)
        self.assertIn("unsupported_claim", [issue.error_type for issue in result.issues])

    def test_dot_decimal_and_qualitative_note_number(self):
        first, second = fact(2022, 100), fact(2023, 112.5)
        task = TimeSeriesTask(task_id="ts", item_code="10", report_type="INCOME_STATEMENT",
                              start_year=2022, end_year=2023)
        research, evidence = record_tool_result(task, ToolResult(status="ok",
            facts=[first, second], safe_for_calculation=True), "s1")
        claim = Claim(claim_id="growth", claim_type="calculated",
            evidence_ids=research.evidence_ids, calculation_id="yoy",
            asserted_value="12.5", asserted_unit="percent", display_value="12.5",
            display_unit="%", rounding_decimals=1)
        calculation = CalculationResult(calculation_id="yoy", operation="yoy",
            input_evidence_ids=research.evidence_ids, value="12.5", unit="percent",
            status="ok")
        draft = SectionDraft(section_id="s", outline_version=1, revision=1,
            blocks=[DraftBlock(block_id="b", text="Doanh thu tăng 12.5% trong năm 2023.",
                               claims=[claim])])
        request = ReportRequest(ticker="ABC", start_year=2022, end_year=2023,
                                audience="investors")
        result = verify_section_deterministically(draft, request, evidence,
                                                  {"yoy": calculation}, {"ts": research})
        self.assertEqual(result.issues, [])
        draft.blocks[0].text = "Doanh thu tăng 1.234.5% trong năm 2023."
        result = verify_section_deterministically(draft, request, evidence,
                                                  {"yoy": calculation}, {"ts": research})
        self.assertIn("number_format", [issue.error_type for issue in result.issues])

        note = NoteEvidence(chunk_id="ABC_note_2023", doc_id="ABC_2023", ticker="ABC",
            fiscal_year=2023, scope="consolidated", section="NOTES",
            text="Lãi suất vay khoảng 8%.", source_file="source.pdf", physical_pages=[3],
            printed_pages=[], citation_tag="[Doc_ABC_2023, p.3]", rerank_score=0.1)
        note_id = note.chunk_id
        note_record = EvidenceRecord(evidence_id=note_id, kind="note",
                                     snapshot_version="s1", payload=note)
        qualitative = Claim(claim_id="rate", claim_type="qualitative", evidence_ids=[note_id])
        note_draft = SectionDraft(section_id="s", outline_version=1, revision=1,
            blocks=[DraftBlock(block_id="b",
                text="Lãi suất vay khoảng 8% ngày 31/12/2023, quý 4.", claims=[qualitative])])
        result = verify_section_deterministically(note_draft, request,
            {note_id: note_record}, {}, {})
        self.assertEqual(result.issues, [])

    def test_prose_number_must_match_structured_display(self):
        state = self.example_state()
        block = state["section_drafts"][("revenue", 1)].blocks[0]
        block.text = block.text.replace("150 VND", "200 VND")
        result = self.verify_state(state)
        self.assertIn("value_mismatch", [issue.error_type for issue in result.issues])
        self.assertIn("unsupported_claim", [issue.error_type for issue in result.issues])

    def test_vietnamese_thousands_and_section_number_are_parsed(self):
        row = fact(2024, 1234.5)
        evidence_id = evidence_id_for(row)
        evidence = {evidence_id: EvidenceRecord(evidence_id=evidence_id,
            kind="fact", snapshot_version="s1", payload=row)}
        claim = Claim(claim_id="c", claim_type="direct_fact", evidence_ids=[evidence_id],
                      metric="Doanh thu thuần", fiscal_year=2024, value="1234.5",
                      unit="VND", display_value="1234.5", display_unit="VND")
        draft = SectionDraft(section_id="s", outline_version=1, revision=1,
            blocks=[DraftBlock(block_id="b",
                text="1. Doanh thu năm 2024 đạt 1.234,5 VND.", claims=[claim])])
        request = ReportRequest(ticker="ABC", start_year=2022, end_year=2025,
                                audience="investors")
        result = verify_section_deterministically(draft, request, evidence, {}, {})
        self.assertEqual(result.issues, [])

    def test_each_error_type_has_positive_and_clean_case(self):
        clean = self.example_state()
        self.assertEqual(self.verify_state(clean).issues, [])

        def changed(kind):
            state = copy.deepcopy(clean)
            draft = state["section_drafts"][("revenue", 1)]
            claim = draft.blocks[0].claims[0]
            evidence_id = claim.evidence_ids[0]
            fact_row = state["evidence_by_id"][evidence_id].payload
            if kind == "missing_evidence":
                claim.evidence_ids = ["absent"]
            elif kind == "invalid_citation":
                fact_row.citation_tag = "[Doc_fake, p.1]"
            elif kind == "value_mismatch":
                claim.value = 999
            elif kind == "period_mismatch":
                claim.fiscal_year = 2023  # Same numerical value, wrong period.
            elif kind == "unit_mismatch":
                claim.unit = "million_VND"
            elif kind == "scope_mismatch":
                fact_row.scope = "separate"
            elif kind == "conflicting_evidence":
                duplicate = fact(2024, 151, page=13)
                new_id = evidence_id_for(duplicate)
                state["evidence_by_id"][new_id] = EvidenceRecord(
                    evidence_id=new_id, kind="fact",
                    snapshot_version="example-snapshot-v1", payload=duplicate)
            elif kind == "calculation_error":
                draft.blocks[0].claims[1].asserted_direction = "mixed"
            elif kind == "unsupported_claim":
                claim.metric = "Lợi nhuận gộp"
            return state

        for kind in ("missing_evidence", "invalid_citation", "value_mismatch",
                     "period_mismatch", "unit_mismatch", "scope_mismatch",
                     "conflicting_evidence", "calculation_error", "unsupported_claim"):
            with self.subTest(kind=kind):
                result = self.verify_state(changed(kind))
                self.assertIn(kind, [issue.error_type for issue in result.issues])

    def test_period_warning_scoped_to_year_and_acknowledgeable(self):
        task = TimeSeriesTask(task_id="ts", item_code="10", report_type="INCOME_STATEMENT",
                              start_year=2024, end_year=2025)
        research, evidence = record_tool_result(task, ToolResult(status="ok",
            facts=[fact(2024, 100), fact(2025, 150)], safe_for_calculation=True), "s1")
        research.warnings.append("period_inconsistency:2024->2025")
        evidence_id = next(key for key, record in evidence.items()
                           if record.payload.fiscal_year == 2025)
        claim = Claim(claim_id="c", claim_type="direct_fact", evidence_ids=[evidence_id],
                      metric="Doanh thu thuần", fiscal_year=2025, value=150, unit="VND",
                      display_value=150, display_unit="VND")
        draft = SectionDraft(section_id="s", outline_version=1, revision=1,
                             blocks=[DraftBlock(block_id="b",
                                text="Doanh thu năm 2025 là 150 VND.",
                                claims=[claim])])
        request = ReportRequest(ticker="ABC", start_year=2022, end_year=2025,
                                audience="investors")
        result = verify_section_deterministically(draft, request, evidence, {}, {"ts": research})
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.issues[0].severity, "warning")
        draft.limitations = [DraftLimitation(warning_code="period_inconsistency:2024->2025",
            evidence_ids=[evidence_id], block_id="b")]
        with self.assertRaises(Exception):
            DraftLimitation(warning_code="period_inconsistency:2024->2025",
                            evidence_ids=[evidence_id], block_id="b", text="Lưu ý.")
        result = verify_section_deterministically(draft, request, evidence, {}, {"ts": research})
        self.assertEqual(result.status, "passed")
        self.assertEqual([(issue.error_type, issue.severity) for issue in result.issues],
                         [("period_mismatch", "warning")])
        self.assertIn("Giới hạn dữ liệu. Chỉ tiêu năm 2024", render_section_citations(draft, evidence))

        old_id = next(key for key, record in evidence.items()
                      if record.payload.fiscal_year == 2024)
        old_claim = claim.model_copy(update={"evidence_ids": [old_id], "fiscal_year": 2024,
                                      "value": 100, "display_value": 100})
        draft.blocks[0].text = "Doanh thu năm 2024 là 100 VND."
        draft.blocks[0].claims = [old_claim]
        result = verify_section_deterministically(draft, request, evidence, {}, {"ts": research})
        self.assertIn("period_mismatch", [issue.error_type for issue in result.issues])

    def test_calculated_period_warning_requires_rewrite_or_limitation(self):
        task = TimeSeriesTask(task_id="ts", item_code="10", report_type="INCOME_STATEMENT",
                              start_year=2024, end_year=2025)
        research, evidence = record_tool_result(task, ToolResult(status="ok",
            facts=[fact(2024, 100), fact(2025, 150)], safe_for_calculation=True), "s1")
        research.warnings.append("period_inconsistency:2024->2025")
        calculation = CalculationResult(calculation_id="y", operation="yoy",
            input_evidence_ids=research.evidence_ids, value=50, unit="percent", status="ok")
        claim = Claim(claim_id="growth", claim_type="calculated",
            evidence_ids=research.evidence_ids, calculation_id="y", asserted_value=50,
            asserted_unit="percent", display_value=50, display_unit="%")
        draft = SectionDraft(section_id="s", outline_version=1, revision=1,
            blocks=[DraftBlock(block_id="b", text="Doanh thu tăng 50% từ 2024 đến 2025.",
                               claims=[claim])])
        request = ReportRequest(ticker="ABC", start_year=2024, end_year=2025,
                                audience="investors")
        result = verify_section_deterministically(draft, request, evidence,
                                                  {"y": calculation}, {"ts": research})
        self.assertEqual(result.status, "needs_revision")
        self.assertTrue(all(issue.action == "rewrite" for issue in result.issues
                            if issue.error_type == "period_mismatch"))
        draft.limitations = [DraftLimitation(warning_code="period_inconsistency:2024->2025",
                                            evidence_ids=research.evidence_ids, block_id="b")]
        result = verify_section_deterministically(draft, request, evidence,
                                                  {"y": calculation}, {"ts": research})
        self.assertEqual(result.status, "passed")
        self.assertTrue(all(issue.severity == "warning" for issue in result.issues))

    def test_unrelated_oil_year_and_mixed_error_priority(self):
        root = Path(__file__).resolve().parents[2]
        state = state_from_json((root / "docs/examples/real-tool-report-state.json").read_text(
            encoding="utf-8"))
        evidence_id, record = next((key, record) for key, record in
            state["evidence_by_id"].items() if record.payload.fiscal_year == 2022)
        row = record.payload
        claim = Claim(claim_id="old", claim_type="direct_fact", evidence_ids=[evidence_id],
                      metric=row.label, fiscal_year=2022, value=str(row.value), unit=row.unit,
                      display_value=str(abs(row.value)), display_unit="VND",
                      display_sign="magnitude")
        text = f"Trả nợ năm 2022 là {int(abs(row.value)):,} VND.".replace(",", ".")
        draft = SectionDraft(section_id="financing_cash_flow", outline_version=1,
                             revision=1, blocks=[DraftBlock(block_id="b", text=text, claims=[claim])])
        result = verify_section_deterministically(draft, state["request"],
            state["evidence_by_id"], {}, state["research_results"])
        self.assertNotIn("period_mismatch", [issue.error_type for issue in result.issues])
        claim.value = 999
        result = verify_section_deterministically(draft, state["request"],
            state["evidence_by_id"], {}, state["research_results"])
        self.assertEqual(result.status, "needs_revision")

    def test_display_scale_magnitude_and_request_year_boundary(self):
        root = Path(__file__).resolve().parents[2]
        state = state_from_json((root / "docs/examples/real-tool-report-state.json").read_text(
            encoding="utf-8"))
        evidence_id, record = next((key, record) for key, record in
            state["evidence_by_id"].items() if record.payload.fiscal_year == 2022)
        row = record.payload
        claim = Claim(claim_id="spending", claim_type="direct_fact",
                      evidence_ids=[evidence_id], metric=row.label, fiscal_year=2022,
                      value=str(row.value), unit="VND", display_value="22.7",
                      display_unit="nghìn tỷ đồng", display_scale="1000000000000",
                      display_sign="magnitude", display_rounding_decimals=1)
        draft = SectionDraft(section_id="financing_cash_flow", outline_version=1,
            revision=1, blocks=[DraftBlock(block_id="b",
                text="Năm 2022, trả nợ gốc vay 22,7 nghìn tỷ đồng.", claims=[claim])])
        result = verify_section_deterministically(draft, state["request"],
            state["evidence_by_id"], {}, state["research_results"])
        self.assertEqual(result.status, "passed")
        claim.display_unit = "triệu đồng"
        draft.blocks[0].text = draft.blocks[0].text.replace("nghìn tỷ đồng", "triệu đồng")
        self.assertIn("unit_mismatch", [issue.error_type for issue in
            verify_section_deterministically(draft, state["request"],
                state["evidence_by_id"], {}, state["research_results"]).issues])
        claim.display_unit = "nghìn tỷ đồng"
        draft.blocks[0].text = draft.blocks[0].text.replace("triệu đồng", "nghìn tỷ đồng")
        claim.display_value = Decimal("22.8")
        self.assertIn("value_mismatch", [issue.error_type for issue in
            verify_section_deterministically(draft, state["request"],
                state["evidence_by_id"], {}, state["research_results"]).issues])
        claim.display_value = Decimal("22.7")
        claim.display_unit = "USD"
        draft.blocks[0].text = draft.blocks[0].text.replace("nghìn tỷ đồng", "USD")
        self.assertIn("unit_mismatch", [issue.error_type for issue in
            verify_section_deterministically(draft, state["request"],
                state["evidence_by_id"], {}, state["research_results"]).issues])
        claim.display_unit = "nghìn tỷ đồng"
        draft.blocks[0].text = draft.blocks[0].text.replace("USD", "nghìn tỷ đồng")
        narrow = state["request"].model_copy(update={"start_year": 2024})
        self.assertIn("period_mismatch", [issue.error_type for issue in
            verify_section_deterministically(draft, narrow,
                state["evidence_by_id"], {}, state["research_results"]).issues])

    def test_manual_citations_are_verifier_issues(self):
        for tag in ("[Doc_X, p.1]", "[1]", "[FPT-2024-Hopnhat-p12]"):
            with self.subTest(tag=tag):
                state = self.example_state()
                state["section_drafts"][("revenue", 1)].blocks[0].text += " " + tag
                result = self.verify_state(state)
                self.assertIn("invalid_citation", [issue.error_type for issue in result.issues])
                self.assertEqual(result.status, "needs_revision")

    def test_oil_duplicate_and_period_warning_block_claim(self):
        root = Path(__file__).resolve().parents[2]
        state = state_from_json((root / "docs/examples/real-tool-report-state.json").read_text(
            encoding="utf-8"))
        evidence_id, record = next((key, record) for key, record in
            state["evidence_by_id"].items() if record.payload.fiscal_year == 2025)
        fact_row = record.payload
        claim = Claim(claim_id="oil_2025", claim_type="direct_fact",
                      evidence_ids=[evidence_id], metric="Tiền trả nợ gốc vay",
                      fiscal_year=2025, value=str(fact_row.value), unit="VND",
                      display_value=str(abs(fact_row.value)), display_unit="VND",
                      display_sign="magnitude")
        draft = SectionDraft(section_id="financing_cash_flow", outline_version=1,
                             revision=1, blocks=[DraftBlock(block_id="b",
                                                             text=f"Tiền trả nợ năm 2025 là {int(abs(fact_row.value)):,} VND.".replace(",", "."),
                                                             claims=[claim])])
        result = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"], {},
            state["research_results"])
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertIn("conflicting_evidence", [issue.error_type for issue in result.issues])
        self.assertIn("period_mismatch", [issue.error_type for issue in result.issues])
        claim.value = 999
        result = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"], {},
            state["research_results"])
        self.assertEqual(result.status, "needs_revision")
        self.assertIn("value_mismatch", [issue.error_type for issue in result.issues])
        self.assertIn("conflicting_evidence", [issue.error_type for issue in result.issues])

    def test_period_scan_finds_oil_warning_without_rewriting_source(self):
        compared, issues = scan_period_consistency()
        self.assertGreater(compared, 10000)
        self.assertGreater(len(issues), 0)
        oil = [issue for issue in issues if issue["ticker"] == "OIL" and
               issue["report_type"] == "CASH_FLOW" and
               issue["item_code_or_label"] == "34" and issue["year"] == 2024]
        self.assertEqual(len(oil), 1)
        self.assertTrue(oil[0]["ambiguous_rows"])


if __name__ == "__main__":
    unittest.main()
