"""Contract checks for report requests, research and calculations."""
import unittest

from pydantic import ValidationError

from src.schemas.report_schema import (
    CalculationResult, Claim, FactTask, MissingItem, ReportRequest, TimeSeriesTask,
    VerificationIssue, calculate_trend, calculated_claim_matches,
    VerificationResult,
    action_for_missing, evidence_id_for, fact_citation_matches_source, record_tool_result,
    research_limitation_text,
)
from src.tools.schemas import FactEvidence, ToolResult


def fact(year=2024, value=150, index=0, page=12):
    return FactEvidence(doc_id=f"ABC_{year}", fact_index=index, ticker="ABC",
                        fiscal_year=year, scope="consolidated", report_type="INCOME_STATEMENT",
                        code="10", label="Doanh thu thuần", value=value, raw_value=str(value),
                        unit="VND", prior_year=None, raw_prior=None, suspect=False,
                        source_file="source.pdf", physical_page=page, printed_page="8",
                        citation_tag=f"[Doc_ABC_{year}, p.{page}]", chunk_ids=[])


class ReportSchemaTests(unittest.TestCase):
    def test_request_and_tasks_reject_invalid_tool_constraints(self):
        ReportRequest(ticker="abc", start_year=2022, end_year=2025, audience="investors")
        for data in [dict(ticker="ABC", start_year=2026, end_year=2026, audience="x"),
                     dict(ticker="ABC", start_year=2024, end_year=2022, audience="x"),
                     dict(ticker="ABC", start_year=2022, end_year=2024, audience="x", scope="Hopnhat")]:
            with self.assertRaises(ValidationError):
                ReportRequest(**data)
        with self.assertRaises(ValidationError):
            FactTask(task_id="f", metric_name="Doanh thu thuần", item_code="60",
                     report_type="INCOME_STATEMENT", fiscal_year=2024)
        with self.assertRaises(ValidationError):
            FactTask(task_id="f", item_code=10, report_type="INCOME_STATEMENT", fiscal_year=2024)

    def test_fact_id_ignores_ingestion_order_and_keeps_duplicate_rows(self):
        original = fact(index=0)
        self.assertEqual(evidence_id_for(original), evidence_id_for(fact(index=99)))
        task = FactTask(task_id="f", item_code="10", report_type="INCOME_STATEMENT",
                        fiscal_year=2024)
        result, records = record_tool_result(task, ToolResult(status="ambiguous",
            facts=[original, fact(index=1, value=151)]), "snapshot-1")
        self.assertEqual(len(records), 2)
        self.assertEqual(result.status, "ambiguous")
        self.assertIn("multiple_matching_rows", result.warnings)

    def test_missing_and_backend_error_are_distinct(self):
        task = FactTask(task_id="f", metric_name="Doanh thu thuần", fiscal_year=2024)
        missing, _ = record_tool_result(task, ToolResult(status="not_found"), "s1")
        error, _ = record_tool_result(task, ToolResult(status="error", message="offline"), "s1")
        self.assertEqual(missing.missing[0].reason, "not_in_corpus")
        self.assertEqual(missing.next_action, "declare_limitation")
        self.assertIn("not_in_corpus", research_limitation_text(missing, {}))
        self.assertEqual(error.status, "error")
        self.assertEqual(error.missing, [])
        null, _ = record_tool_result(task, ToolResult(status="partial",
            facts=[fact(value=None)], missing_years=[2024]), "s1")
        self.assertEqual(null.missing[0].reason, "null_or_suspect")

    def test_trend_requires_tool_safety_and_every_year(self):
        task = TimeSeriesTask(task_id="ts", item_code="10", report_type="INCOME_STATEMENT",
                              start_year=2022, end_year=2024)
        research, records = record_tool_result(task, ToolResult(status="partial",
            facts=[fact(2022, 100), fact(2024, 150)], missing_years=[2023],
            safe_for_calculation=False), "s1")
        calculation = calculate_trend("c1", research, records, 2022, 2024)
        self.assertEqual(calculation.status, "cannot_compute")
        research.safe_for_calculation = True
        calculation = calculate_trend("c1", research, records, 2022, 2024)
        self.assertEqual(calculation.status, "cannot_compute")
        research, records = record_tool_result(task, ToolResult(status="ok",
            facts=[fact(2022, 100), fact(2023, 120), fact(2024, 150)],
            safe_for_calculation=True), "s1")
        calculation = calculate_trend("c1", research, records, 2022, 2024)
        self.assertEqual(calculation.direction, "increasing")
        claim = Claim(claim_id="growth", claim_type="calculated", evidence_ids=list(records),
                      calculation_id="c1", asserted_direction="increasing")
        self.assertTrue(calculated_claim_matches(claim, calculation))
        failed = CalculationResult(calculation_id="y1", operation="yoy",
            input_evidence_ids=["e1", "e2"], status="cannot_compute", reason="unsafe")
        self.assertFalse(calculated_claim_matches(claim, failed))
        self.assertFalse(calculated_claim_matches(claim.model_copy(update={"asserted_direction": "mixed"}),
                                                  calculation))

    def test_trend_distinguishes_flat_and_mixed(self):
        task = TimeSeriesTask(task_id="ts", item_code="10", report_type="INCOME_STATEMENT",
                              start_year=2022, end_year=2024)
        for values, expected in [([100, 100, 100], "flat"), ([100, 120, 110], "mixed")]:
            research, records = record_tool_result(task, ToolResult(status="ok",
                facts=[fact(year, value) for year, value in zip(range(2022, 2025), values)],
                safe_for_calculation=True), "s1")
            self.assertEqual(calculate_trend("c1", research, records, 2022, 2024).direction,
                             expected)

    def test_trend_ignores_warning_ending_after_its_range(self):
        task = TimeSeriesTask(task_id="ts", item_code="10", report_type="INCOME_STATEMENT",
                              start_year=2022, end_year=2024)
        research, evidence = record_tool_result(task, ToolResult(status="ok",
            facts=[fact(2022, 100), fact(2023, 120), fact(2024, 150)],
            safe_for_calculation=True), "s1")
        research.warnings.append("period_inconsistency:2024->2025")
        self.assertEqual(calculate_trend("trend", research, evidence, 2022, 2024).status,
                         "ok")

    def test_numeric_calculated_claim_has_typed_assertion_and_rounding(self):
        calculation = CalculationResult(calculation_id="y1", operation="yoy",
            input_evidence_ids=["e1", "e2"], value="12.345", unit="percent", status="ok")
        claim = Claim(claim_id="c1", claim_type="calculated", evidence_ids=["e1", "e2"],
                      calculation_id="y1", asserted_value="12.35", asserted_unit="percent",
                      rounding_decimals=2, display_value="12.35", display_unit="%")
        self.assertTrue(calculated_claim_matches(claim, calculation))
        self.assertFalse(calculated_claim_matches(claim.model_copy(update={"asserted_value": 12}),
                                                  calculation))
        with self.assertRaises(ValidationError):
            Claim(claim_id="c1", claim_type="calculated", evidence_ids=["e1"],
                  calculation_id="y1")

    def test_fact_citation_matches_storage_format(self):
        self.assertTrue(fact_citation_matches_source(fact()))
        self.assertFalse(fact_citation_matches_source(fact().model_copy(
            update={"citation_tag": "[ABC_2024, p.12]"})))

    def test_limitation_action_is_in_schema(self):
        issue = VerificationIssue(claim_id="c1", error_type="missing_evidence",
                                  reason="not_in_corpus", action="declare_limitation")
        self.assertEqual(issue.action, "declare_limitation")
        self.assertEqual(action_for_missing(MissingItem(description="x", reason="not_in_corpus")),
                         "declare_limitation")
        self.assertEqual(action_for_missing(MissingItem(description="x", reason="null_or_suspect")),
                         "declare_limitation")
        self.assertEqual(action_for_missing(MissingItem(description="x", reason="not_found_yet")),
                         "retrieve_more")
        with self.assertRaises(ValidationError):
            VerificationResult(section_id="s", revision=1, status="passed")


if __name__ == "__main__":
    unittest.main()
