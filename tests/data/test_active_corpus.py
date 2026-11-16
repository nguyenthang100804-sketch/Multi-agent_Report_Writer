import unittest

from src.storage.active_corpus import ACTIVE_CORPUS, active_path
from src.storage.duckdb_manager import DEFAULT_DB_PATH, DEFAULT_INPUT_DIR
from src.tools.notes_retriever import HybridNotesRetriever


class ActiveCorpusTests(unittest.TestCase):
    def test_runtime_sources_share_active_snapshot(self):
        retriever = HybridNotesRetriever()
        self.assertEqual(DEFAULT_INPUT_DIR, active_path("processed_dir"))
        self.assertEqual(DEFAULT_DB_PATH, active_path("facts_db"))
        self.assertEqual(retriever.processed_dir, active_path("processed_dir"))
        self.assertEqual(retriever.collection_name, ACTIVE_CORPUS["collection_name"])
        self.assertTrue(active_path("manifest").is_file())


if __name__ == "__main__":
    unittest.main()
