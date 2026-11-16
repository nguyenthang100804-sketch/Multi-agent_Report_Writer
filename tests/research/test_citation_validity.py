import unittest

from src.evaluation.metrics import CitationEvaluator


class CitationValidityTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = CitationEvaluator({"FPT_2024_Hopnhat": {1, 2, 3, 5}})

    def test_single_page_and_optional_prefix(self):
        for name in ["Doc_FPT_2024_Hopnhat", "FPT_2024_Hopnhat", "doc_fpt_2024_hopnhat"]:
            self.assertEqual(self.evaluator.check_citation_validity(f"[{name}, p.2]")["valid_citations"], 1)

    def test_range_is_one_citation_and_all_pages_must_exist(self):
        result = self.evaluator.check_citation_validity("[Doc_FPT_2024_Hopnhat, p.1-3]")
        self.assertEqual((result["total_citations"], result["valid_citations"]), (1, 1))
        for pages in ["3-5", "5-3", "0", "1-999999999"]:
            result = self.evaluator.check_citation_validity(f"[Doc_FPT_2024_Hopnhat, p.{pages}]")
            self.assertEqual(result["invalid_citations"], 1)

    def test_no_substring_document_match(self):
        for name in ["FPT", "FPT_2024", "FPT_2024_Hopnhat_extra", "FPT_2023_Hopnhat"]:
            self.assertEqual(self.evaluator.check_citation_validity(f"[{name}, p.1]")["invalid_citations"], 1)

    def test_empty_catalog_pages_and_mixed_tags(self):
        evaluator = CitationEvaluator({"FPT_2024_Hopnhat": set()})
        self.assertEqual(evaluator.check_citation_validity("[FPT_2024_Hopnhat, p.1]")["invalid_citations"], 1)
        result = self.evaluator.check_citation_validity("[FPT_2024_Hopnhat, p.1-3] [FPT, p.1]")
        self.assertEqual((result["total_citations"], result["valid_citations"]), (2, 1))

    def test_range_counts_for_recall(self):
        self.assertEqual(self.evaluator.check_citation_recall(
            ["Doanh thu 100.000 [Doc_FPT_2024_Hopnhat, p.1-3]"])["citation_recall"], 1)
