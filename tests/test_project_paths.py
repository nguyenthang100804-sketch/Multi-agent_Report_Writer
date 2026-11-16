"""Regression checks for project data paths."""
from pathlib import Path
import unittest


class ProjectPathTests(unittest.TestCase):
    def test_relocated_inspection_inputs_exist(self):
        root = Path(__file__).resolve().parents[1]
        for relative in [
            "data/backup_data/raw_docs_top_100_backup/QNS/2025",
            "data/raw_docs/top_100/ABB/2024/ABB_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt",
            "data/raw_docs/top_100/QNS/2025/QNS_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt",
        ]:
            self.assertTrue((root / relative).exists(), relative)
