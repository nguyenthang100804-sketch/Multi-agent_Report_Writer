"""Guard the small, source-checked Dev benchmark against gold drift."""
import json
import unittest

from src.evaluation.report_quality_benchmark import CASES_DIR, check_source, grade, pdf_audit_reference


class ReportQualityBenchmarkTests(unittest.TestCase):
    def test_dev_gold_has_eight_cases_and_source_checked_values(self):
        cases = [json.loads(path.read_text(encoding="utf-8"))
                 for path in CASES_DIR.glob("*.json")]
        self.assertEqual(len(cases), 8)
        self.assertNotIn("OIL", {case["request"]["ticker"] for case in cases})
        self.assertIn("abb_unsupported_bank", {case["case_id"] for case in cases})
        self.assertIn("dhg_general_2023_2025", {case["case_id"] for case in cases})
        self.assertIn("gmd_note_relevance_gap", {case["case_id"] for case in cases})
        values = [value for case in cases for point in case.get("required_points", [])
                  for value in point.get("expected_values", {}).values()]
        self.assertEqual(len(values), 17)
        self.assertTrue(all(check_source(value) for value in values))
        changed = {**values[0], "physical_page": values[0]["physical_page"] + 1}
        self.assertFalse(check_source(changed))

    def test_stop_requires_reason_and_no_downstream_work(self):
        case = json.loads((CASES_DIR / "fox_outside_corpus.json").read_text(encoding="utf-8"))
        stopped = {"run_status": "rejected", "planner_notes": [], "research_results": {}}
        result = grade(case, stopped)
        self.assertFalse(result["automatic_checks_pass"])
        self.assertIn("stop_reason", {item["code"] for item in result["findings"]})
        stopped["research_results"] = {"unexpected": object()}
        result = grade(case, stopped)
        self.assertIn("report_after_stop", {item["code"] for item in result["findings"]})

    def test_pdf_audit_is_tied_to_gold_and_source_files(self):
        cases = [json.loads(path.read_text(encoding="utf-8"))
                 for path in CASES_DIR.glob("*.json")]
        self.assertEqual(pdf_audit_reference(cases)["checked_values"], 4)


if __name__ == "__main__":
    unittest.main()
