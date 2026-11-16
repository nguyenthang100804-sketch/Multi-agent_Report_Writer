"""Deliberately damage saved reports to test the benchmark, not the Writer."""
import copy
import json
import unittest

from src.agents.state import state_from_json
from src.evaluation.report_quality_benchmark import ROOT, grade


class ReportQualityMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {}
        cls.states = {}
        for ticker, case_id in (("hut", "hut_full"), ("fpt", "fpt_partial")):
            case = json.loads((ROOT / "configs/report_quality_dev" / f"{case_id}.json")
                              .read_text(encoding="utf-8"))
            case["required_sections"] = ["S3", "S4", "S5"]
            cls.cases[ticker] = case
            cls.states[ticker] = state_from_json((ROOT / "data/report_output/v2_1_fixtures"
                                                  / f"{ticker}_research_state.json")
                                                 .read_text(encoding="utf-8"))

    def test_clean_saved_states_pass(self):
        for ticker in self.cases:
            with self.subTest(ticker=ticker):
                self.assertTrue(grade(self.cases[ticker], self.states[ticker])["automatic_checks_pass"])

    def test_each_output_mutation_is_detected(self):
        mutations = (
            ("digit", "hut", "missing_output_value", "36.317,44 [Doc_HUT_2025_Hopnhat, p.11]",
             "36.317,45 [Doc_HUT_2025_Hopnhat, p.11]"),
            ("year_header", "hut", "table_period", "| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |",
             "| Chỉ tiêu | 2022 | 2023 | 2024 | 2026 |"),
            ("year_prose", "hut", "calculation_output", "Mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024",
             "Mức thay đổi của Doanh thu thuần năm 2026 so với năm 2024"),
            ("unit", "hut", "table_unit", "### Số liệu theo năm (tỷ đồng)",
             "### Số liệu theo năm (triệu đồng)"),
            ("citation_page", "hut", "output_citation_mismatch", "36.317,44 [Doc_HUT_2025_Hopnhat, p.11]",
             "36.317,44 [Doc_HUT_2025_Hopnhat, p.12]"),
            ("missing_limitation_text", "fpt", "missing_limitation_text",
             "Giới hạn dữ liệu. Lợi nhuận sau thuế của cổ đông công ty mẹ (mã 61) chưa tìm thấy số liệu năm 2024, 2025.",
             ""),
            ("invented_cause", "hut", "causal_claim_without_note_support", "## Kết quả kinh doanh",
             "## Kết quả kinh doanh\n\nDoanh thu tăng do thương vụ sáp nhập."),
            ("cause_with_table_citation", "hut", "causal_claim_without_note_support", "## Kết quả kinh doanh",
             "## Kết quả kinh doanh\n\nDoanh thu tăng do thương vụ sáp nhập. [Doc_HUT_2025_Hopnhat, p.11]"),
            ("absolute_absence", "hut", "absolute_absence_claim", "## Kết quả kinh doanh",
             "## Kết quả kinh doanh\n\nBáo cáo kiểm toán không có vấn đề nhấn mạnh."),
        )
        for name, ticker, expected_code, before, after in mutations:
            with self.subTest(mutation=name):
                state = copy.deepcopy(self.states[ticker])
                self.assertIn(before, state["final_report"])
                state["final_report"] = state["final_report"].replace(before, after, 1)
                result = grade(self.cases[ticker], state)
                self.assertFalse(result["automatic_checks_pass"])
                self.assertIn(expected_code, {item["code"] for item in result["findings"]})

    def test_missing_limitation_contract_is_detected(self):
        state = copy.deepcopy(self.states["fpt"])
        for draft in state["section_drafts"].values():
            draft.limitations = [item for item in draft.limitations
                                 if getattr(item, "research_task_id", None) != "parent_profit"]
        self.assertFalse(grade(self.cases["fpt"], state)["automatic_checks_pass"])


if __name__ == "__main__":
    unittest.main()
