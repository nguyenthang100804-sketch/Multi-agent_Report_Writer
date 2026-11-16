"""Storage/tool contracts: provenance, ambiguity, missing years and atomic reloads."""

import json
from pathlib import Path
import tempfile
import unittest

from src.storage.duckdb_manager import DuckDBManager, get_time_series


class FactsStorageTests(unittest.TestCase):
    def test_query_and_reload_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input"
            source.mkdir()
            fact = dict(report_type="INCOME_STATEMENT", code="01", label="Revenue",
                        current_year=123.0, prior_year=100.0, raw_current="123",
                        raw_prior="100", unit="million_VND", physical_page=9,
                        printed_page="5", suspect=False)
            doc = dict(doc_id="ABC_2024", ticker="ABC", fiscal_year=2024,
                       scope="consolidated", source_file="original.txt", facts=[fact],
                       chunks=[dict(section="INCOME_STATEMENT", physical_pages=[9],
                                    chunk_id="evidence")])
            path = source / "ABC.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            database = root / "facts.duckdb"
            with DuckDBManager(database, read_only=False) as manager:
                self.assertEqual(manager.ingest(source), {"documents": 1, "facts": 1})
                snapshot_id = manager.get_snapshot_id()
                manager.ingest(source)
                self.assertEqual(manager.get_snapshot_id(), snapshot_id)
                rows = manager.get_time_series("abc", "01", 2022, 2025)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["value"], 123)
                self.assertEqual(rows[0]["unit"], "million_VND")
                self.assertEqual(rows[0]["prior_year"], 100)
                self.assertEqual(manager.get_fact("ABC", "1", 2024), [])
                self.assertEqual(rows[0]["physical_page"], 9)
                self.assertEqual(rows[0]["printed_page"], "5")
                self.assertEqual(rows[0]["chunk_ids"], ["evidence"])
                self.assertEqual(rows[0]["citation_tag"], "[Doc_ABC_2024, p.9]")
                self.assertEqual(manager.get_fact("ABC", "01", 2023), [])
                self.assertEqual(manager.get_fact("ABC' OR 1=1 --", "01", 2024), [])
                with self.assertRaises(ValueError):
                    manager.get_time_series("ABC", "01", 2025, 2022)
                self.assertEqual(len(manager.get_fact("ABC", None, 2024,
                                                     label="Revenue")), 1)

                # A different statement uses the same code; never silently pick one.
                doc["facts"].append({**fact, "report_type": "CASH_FLOW", "suspect": True})
                path.write_text(json.dumps(doc), encoding="utf-8")
                manager.ingest(source)
                self.assertEqual(len(manager.get_fact("ABC", "01", 2024)), 1)
                with self.assertRaises(ValueError):
                    manager.get_fact("ABC", "01", 2024, include_suspect=True)
                self.assertEqual(len(manager.get_fact("ABC", "01", 2024,
                                 report_type="CASH_FLOW", include_suspect=True)), 1)

                # Multiple source rows are kept, rather than silently deduplicated.
                doc["facts"].append({**fact, "current_year": 456.0})
                path.write_text(json.dumps(doc), encoding="utf-8")
                manager.ingest(source)
                self.assertNotEqual(manager.get_snapshot_id(), snapshot_id)
                self.assertEqual(len(manager.get_fact("ABC", "01", 2024)), 2)

                # Constraint failure after DELETE must roll back to the previous snapshot.
                doc["facts"][0]["report_type"] = None
                path.write_text(json.dumps(doc), encoding="utf-8")
                with self.assertRaises(Exception):
                    manager.ingest(source)
                self.assertEqual(len(manager.get_fact("ABC", "01", 2024)), 2)

            self.assertEqual(len(get_time_series("ABC", "01", 2022, 2025,
                                                db_path=database)), 2)


if __name__ == "__main__":
    unittest.main()
