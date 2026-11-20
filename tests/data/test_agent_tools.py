"""Behavioral contracts for function calling, evidence integrity and routing."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from jsonschema import Draft202012Validator

from src.storage.duckdb_manager import DuckDBManager
from src.tools import AgentTools, get_function_calling_specs, metric_name_resolver
from src.tools.notes_retriever import HybridNotesRetriever, rrf_fusion
from src.tools.schemas import NotesSearchInput


class AgentToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.db = self.root / "facts.duckdb"
        self.write_doc(2022, 100)
        self.write_doc(2024, 150)
        self.reload()
        self.tools = AgentTools(self.db)

    def tearDown(self):
        self.tools.close()
        self.temp.cleanup()

    def write_doc(self, year, value, unit="VND", duplicate=False):
        fact = dict(report_type="INCOME_STATEMENT", code="10", stt=None,
                    label="Doanh thu thuần", note=None, current_year=value,
                    prior_year=80, raw_current=str(value), raw_prior="80", suspect=False,
                    suspect_reason=None, unit=unit, physical_page=12, printed_page="8")
        notes = [dict(chunk_id=f"ABC_{year}_{scope}", text="chính sách khấu hao",
                      section="NOTES", scope=scope, physical_pages=[12], printed_pages=["8"],
                      citation_tag=f"[Doc_ABC_{year}, p.12]")
                 for scope in ["consolidated"]]
        doc = dict(doc_id=f"ABC_{year}", ticker="ABC", fiscal_year=year,
                   scope="consolidated", source_file="source.txt", chunks=notes,
                   facts=[fact, dict(fact)] if duplicate else [fact])
        (self.source / f"{year}.json").write_text(json.dumps(doc), encoding="utf-8")

    def reload(self):
        with DuckDBManager(self.db, read_only=False) as manager:
            manager.ingest(self.source)

    def test_alias_resolution_and_ambiguity(self):
        r = metric_name_resolver({"metric_name": " TONG TAI SAN "})
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.candidates[0].code, "270")
        self.assertEqual(metric_name_resolver({"metric_name": "lợi nhuận"}).status, "ambiguous")
        self.assertEqual(metric_name_resolver({"metric_name": "unknown metric"}).status, "not_found")

    def test_fact_evidence(self):
        r = self.tools.execute("query_fact_tool", json.dumps(dict(
            ticker="abc", metric_name="doanh thu thuần", fiscal_year=2024)))
        self.assertEqual(r.status, "ok")
        f = r.facts[0]
        self.assertEqual((f.value, f.physical_page, f.printed_page), (150, 12, "8"))
        self.assertEqual(f.citation_tag, "[Doc_ABC_2024, p.12]")
        json.loads(r.model_dump_json())

    def test_missing_years_and_null_values_are_not_zero(self):
        args = dict(ticker="ABC", metric_name="doanh thu thuần", start_year=2022, end_year=2024)
        r = self.tools.execute("query_time_series_tool", args)
        self.assertEqual((r.status, r.missing_years, r.safe_for_calculation), ("partial", [2023], False))
        self.write_doc(2024, None)
        self.reload()
        r = self.tools.execute("query_time_series_tool", args)
        self.assertEqual(r.missing_years, [2023, 2024])
        self.assertIsNone(r.facts[-1].value)

    def test_conflicting_rows_and_units_block_calculation(self):
        self.write_doc(2024, 150, duplicate=True)
        self.reload()
        r = self.tools.execute("query_fact_tool", dict(ticker="ABC", metric_name="doanh thu thuần", fiscal_year=2024))
        self.assertEqual((r.status, len(r.facts), r.safe_for_calculation), ("ambiguous", 2, False))
        self.write_doc(2024, 150, unit="million_VND")
        self.reload()
        r = self.tools.execute("query_time_series_tool", dict(ticker="ABC", item_code="10",
            report_type="INCOME_STATEMENT", start_year=2022, end_year=2024))
        self.assertFalse(r.safe_for_calculation)
        self.assertTrue(any("Units" in warning for warning in r.warnings))

    def test_invalid_arguments_and_conflicting_metric(self):
        for args in [dict(ticker="ABC", item_code=10, fiscal_year=2024),
                     dict(ticker="ABC", metric_name="doanh thu thuần", fiscal_year=2026),
                     dict(ticker="ABC", metric_name="doanh thu thuần", fiscal_year=True),
                     dict(ticker="ABC", metric_name="doanh thu thuần", fiscal_year=2024, sql="SELECT 1"),
                     dict(ticker="ABC", metric_name="doanh thu thuần", item_code="60",
                          report_type="INCOME_STATEMENT", fiscal_year=2024)]:
            self.assertEqual(self.tools.execute("query_fact_tool", args).status, "invalid_input")
        self.assertEqual(self.tools.execute("unknown", {}).status, "invalid_input")
        self.assertEqual(self.tools.execute("query_fact_tool", "{").status, "invalid_input")

    def test_unavailable_backend_is_error_not_missing_evidence(self):
        with AgentTools(self.root / "absent.duckdb") as tools:
            with self.assertLogs("src.tools.agent_tools", level="ERROR"):
                r = tools.execute("query_fact_tool", dict(ticker="ABC", metric_name="doanh thu thuần", fiscal_year=2024))
        self.assertEqual(r.status, "error")

    def test_function_schemas(self):
        specs = get_function_calling_specs()
        self.assertEqual(len(specs), 4)
        for spec in specs:
            schema = spec["function"]["parameters"]
            Draft202012Validator.check_schema(schema)
            self.assertFalse(schema["additionalProperties"])

    def test_bm25_filters_and_empty_scope(self):
        retriever = HybridNotesRetriever(processed_dir=self.source)
        retriever._prepare_corpus()
        matches = retriever.bm25.search("khấu hao", filter_ticker="ABC", filter_year=2024,
                                       filter_scope="consolidated", filter_sections=["NOTES"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(retriever.bm25.search("khấu hao", filter_scope="separate"), [])
        self.assertEqual(retriever.search(NotesSearchInput(query="khấu hao", ticker="ABC",
                                                         fiscal_year=2024, scope="separate")), [])

    def test_notes_backend_failure_is_explicit(self):
        backend = Mock()
        backend.search.side_effect = RuntimeError("offline")
        with AgentTools(self.db, backend) as tools:
            with self.assertLogs("src.tools.agent_tools", level="ERROR"):
                r = tools.execute("search_notes_tool", dict(query="khấu hao", ticker="ABC", fiscal_year=2024))
            self.assertEqual(r.status, "error")
        backend.close.assert_called_once()

    def test_rrf_uses_ranks(self):
        self.assertEqual(rrf_fusion([("a", 0.9), ("b", 0.8)], [("b", 1000)]), ["b", "a"])

    def test_notes_search_returns_rrf_top_five_without_reranker(self):
        retriever = HybridNotesRetriever(processed_dir=self.source)
        retriever._prepare_corpus = Mock()
        retriever.chunks = {
            f"c{i}": dict(chunk_id=f"c{i}", doc_id="ABC_2024", ticker="ABC",
                         fiscal_year=2024, scope="consolidated", section="NOTES",
                         text="chính sách khấu hao", source_file="source.txt",
                         physical_pages=[12], printed_pages=["8"],
                         citation_tag="[Doc_ABC_2024, p.12]")
            for i in range(6)
        }
        retriever.bm25 = Mock()
        retriever.bm25.search.return_value = [(f"c{i}", 1.0) for i in range(6)]
        retriever.embedder = Mock()
        retriever.embedder._embed_batch_sorted.return_value = [Mock(tolist=lambda: [0.1])]
        retriever.manager = Mock()
        retriever.manager.get_client.return_value.query_points.return_value.points = [
            Mock(payload={"chunk_id": f"c{i}"}, score=1.0) for i in range(6)
        ]

        results = retriever.search(NotesSearchInput(
            query="khấu hao", ticker="ABC", fiscal_year=2024))

        self.assertEqual([item.chunk_id for item in results], [f"c{i}" for i in range(5)])
        self.assertTrue(all(item.rerank_score is None for item in results))
        expanded = retriever.search(NotesSearchInput(
            query="khấu hao", ticker="ABC", fiscal_year=2024), limit=6)
        self.assertEqual(len(expanded), 6)

    def test_audit_section_read_returns_all_chunks_without_ranking(self):
        retriever = HybridNotesRetriever(processed_dir=self.source)
        retriever._prepare_corpus = Mock()
        retriever.chunks = {f"c{i}": dict(chunk_id=f"c{i}", doc_id="ABC_2024",
            ticker="ABC", fiscal_year=2024, scope="consolidated",
            section="AUDIT_REPORT", text="Ý kiến kiểm toán", source_file="source.txt",
            physical_pages=[i], printed_pages=[str(i)],
            citation_tag=f"[Doc_ABC_2024, p.{i}]") for i in range(8)}
        retriever.chunks["other"] = {**retriever.chunks["c0"],
                                     "chunk_id": "other", "section": "NOTES"}
        with AgentTools(self.db, retriever) as tools:
            result = tools.read_audit_section("ABC", 2024, "consolidated")
        self.assertEqual(result.status, "ok")
        self.assertEqual([chunk.chunk_id for chunk in result.chunks],
                         [f"c{i}" for i in range(8)])
        self.assertTrue(all(chunk.topic_roles == ["context"] for chunk in result.chunks))


if __name__ == "__main__":
    unittest.main()
