"""Regression checks for scope selection and non-fact heading rows."""
import unittest
from pathlib import Path

from src.agents.coverage import CoverageError, available_scopes, check_coverage
from src.ingestion.document_parser import DocumentParser, _is_empty_heading
from src.schemas.report_schema import ReportRequest


class ParserScopeTests(unittest.TestCase):
    def test_heading_filter_requires_empty_raw_cells(self):
        self.assertTrue(_is_empty_heading("Phân bổ cho:", "", "  "))
        self.assertFalse(_is_empty_heading("Phân bổ cho:", "bị đè con dấu", ""))
        self.assertFalse(_is_empty_heading("Phân bổ cho:", "", "(*)"))

    def test_available_scopes_for_non_consolidated_ticker(self):
        self.assertEqual(set(available_scopes("pap")), {"general"})
        self.assertIn("general", available_scopes("VCR"))
        self.assertIn("separate", available_scopes("VCR"))

    def test_coverage_suggests_scopes_and_marks_bank_codes(self):
        request = ReportRequest(ticker="PAP", start_year=2022, end_year=2025,
                                audience="demo")
        with self.assertRaises(CoverageError) as error:
            check_coverage(request)
        self.assertEqual(set(error.exception.result.available_scopes), {"general"})
        self.assertIn("general", str(error.exception))
        self.assertTrue(check_coverage(request.model_copy(update={"scope": "general"})).has_standard_codes)
        bank = request.model_copy(update={"ticker": "ACB"})
        self.assertFalse(check_coverage(bank).has_standard_codes)

    def test_fpt_heading_with_code_is_not_a_fact(self):
        root = Path(__file__).resolve().parents[2]
        path = root / "data/raw_docs/top_100/FPT/2023/FPT_2023_BCTC_Kiemtoan_Hopnhat_extracted.txt"
        doc = DocumentParser().parse_file(path)
        rows = [fact for fact in doc.facts if fact.report_type == "INCOME_STATEMENT"
                and fact.code == "61"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].label, "Cổ đông của công ty mẹ")


if __name__ == "__main__":
    unittest.main()
