"""Read-only checks against the committed DuckDB corpus and tool output."""
import unittest
from pathlib import Path

from src.agents.coverage import CoverageError, check_coverage
from src.agents.state import snapshot_version_for_db, state_from_json
from src.schemas.report_schema import (FactTask, ReportRequest, fact_citation_matches_source,
                                       record_tool_result)
from src.storage.duckdb_manager import DEFAULT_DB_PATH
from src.tools.agent_tools import AgentTools


class ReportIntegrationTests(unittest.TestCase):
    def test_bank_metric_absence_becomes_limitation(self):
        request = ReportRequest(ticker="ACB", start_year=2024, end_year=2024,
                                scope="consolidated", audience="investors")
        check_coverage(request)
        task = FactTask(task_id="bank_revenue", item_code="10",
                        report_type="INCOME_STATEMENT", fiscal_year=2024)
        with AgentTools(DEFAULT_DB_PATH) as tools:
            tool_result = tools.execute("query_fact_tool", dict(
                ticker="ACB", item_code="10", report_type="INCOME_STATEMENT",
                fiscal_year=2024, scope="consolidated"))
        research, evidence = record_tool_result(task, tool_result, "snapshot")
        self.assertEqual(tool_result.status, "not_found")
        self.assertEqual(research.missing[0].reason, "not_in_corpus")
        self.assertEqual(research.next_action, "declare_limitation")
        self.assertEqual(evidence, {})

    def test_coverage_gate_uses_actual_ticker_year_scope(self):
        request = ReportRequest(ticker="OIL", start_year=2022, end_year=2025,
                                scope="consolidated", audience="investors")
        self.assertEqual(check_coverage(request).available_years, [2022, 2023, 2024, 2025])
        with self.assertRaises(CoverageError) as missing:
            check_coverage(request.model_copy(update={"ticker": "FOX"}))
        self.assertEqual(missing.exception.result.missing_years, [2022, 2023, 2024, 2025])
        with self.assertRaises(CoverageError):
            check_coverage(request.model_copy(update={"scope": "separate"}))
        with self.assertRaises(CoverageError) as partial:
            check_coverage(request.model_copy(update={"ticker": "DHG"}))
        self.assertEqual(partial.exception.result.available_years, [2022])
        self.assertEqual(partial.exception.result.missing_years, [2023, 2024, 2025])

    def test_real_tool_state_preserves_ambiguity_and_source_metadata(self):
        path = Path(__file__).resolve().parents[2] / "docs" / "examples" / "real-tool-report-state.json"
        historical_db = Path(__file__).resolve().parents[2] / "data" / "facts_storage" / "financial_facts.duckdb"
        state = state_from_json(path.read_text(encoding="utf-8"))
        with AgentTools(historical_db) as tools:
            result = tools.execute("query_time_series_tool", dict(
                ticker="OIL", item_code="34", report_type="CASH_FLOW",
                start_year=2022, end_year=2025, scope="consolidated"))
        self.assertEqual((result.status, len(result.facts), result.safe_for_calculation),
                         ("ambiguous", 5, False))
        self.assertEqual(len(state["evidence_by_id"]), 5)
        self.assertEqual(state["research_results"]["oil_cash_flow_34_2022_2025"].status,
                         "ambiguous")
        self.assertEqual(state["run_status"], "incomplete")
        self.assertEqual(state["research_results"]["oil_cash_flow_34_2022_2025"].next_action,
                         "declare_limitation")
        self.assertIn("period_inconsistency:2024->2025",
                      state["research_results"]["oil_cash_flow_34_2022_2025"].warnings)
        self.assertIn("(39.144.671.502.995)",
                      next(f.raw_value for f in result.facts if f.value == -39144671502995))
        self.assertIn("-39144671502995", state["final_report"])
        self.assertEqual({record.snapshot_version for record in state["evidence_by_id"].values()},
                         {snapshot_version_for_db(historical_db)})
        facts = [record.payload for record in state["evidence_by_id"].values()]
        self.assertEqual([fact.model_dump() for fact in facts],
                         [fact.model_dump() for fact in result.facts])
        self.assertEqual(sum(fact.fiscal_year == 2025 for fact in facts), 2)
        self.assertTrue(any(fact.printed_page is None for fact in facts))
        self.assertTrue(all(fact.chunk_ids for fact in facts))
        self.assertTrue(all(fact_citation_matches_source(fact) for fact in facts))
        self.assertEqual({fact.citation_tag for fact in facts},
                         {fact.citation_tag for fact in result.facts})


if __name__ == "__main__":
    unittest.main()
