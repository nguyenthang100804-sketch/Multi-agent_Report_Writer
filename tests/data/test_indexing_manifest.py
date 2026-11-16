import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from src.indexing.pipeline import run_pipeline
from src.indexing.qdrant_manager import QdrantIndexManager


class IndexingManifestTests(unittest.TestCase):
    def run_mocked(self, **kwargs):
        docs = [{"doc_id": name, "chunks": [{"chunk_id": name + "_1"}]} for name in ["A", "B"]]
        manager = Mock()
        manager.upload_document_points.return_value = 1
        manager.reconcile_counts.return_value = {
            "status": "PASSED", "actual_qdrant_points_count": 2, "actual_documents_count": 2}
        embedder = Mock()
        embedder.get_checkpoint.return_value = {"completed_docs": []}
        embedder.embed_document_chunks.return_value = ([], [])
        with patch("src.indexing.pipeline.load_all_processed_documents", return_value=docs), \
             patch("src.indexing.pipeline.QdrantIndexManager", return_value=manager), \
             patch("src.indexing.pipeline.DocumentEmbedder", return_value=embedder), \
             contextlib.redirect_stdout(io.StringIO()):
            if kwargs.pop("mismatch", False):
                manager.reconcile_counts.return_value["status"] = "MISMATCH"
            try:
                run_pipeline(Path("unused"), **kwargs)
            except ValueError:
                manager.create_versioned_collection.assert_not_called()
                manager.save_manifest.assert_not_called()
                raise
            except RuntimeError:
                manager.save_manifest.assert_not_called()
                raise
        return manager

    def test_invalid_start_does_not_modify_collection_or_manifest(self):
        for start in ["missing", "0", "3", ""]:
            with self.assertRaises(ValueError):
                self.run_mocked(start_from=start)

    def test_resume_verifies_full_collection_and_records_run_counts(self):
        for start in ["B", "2"]:
            manager = self.run_mocked(start_from=start)
            self.assertEqual(manager.upload_document_points.call_count, 1)
            saved = manager.save_manifest.call_args.kwargs
            self.assertEqual((saved["total_chunks"], saved["total_documents"]), (2, 2))
            self.assertEqual(saved["additional_info"]["uploaded_chunks_this_run"], 1)

    def test_incomplete_collection_does_not_publish_manifest(self):
        with self.assertRaises(RuntimeError):
            self.run_mocked(start_from="B", mismatch=True)

    def test_rebuild_cannot_skip_documents(self):
        with self.assertRaises(ValueError):
            self.run_mocked(start_from="B", rebuild=True)

    def test_full_upload_still_works(self):
        self.assertEqual(self.run_mocked().upload_document_points.call_count, 2)

    def test_reconciliation_detects_same_count_wrong_ids(self):
        manager = QdrantIndexManager()
        client = Mock()
        client.get_collection.return_value.points_count = 2
        client.scroll.return_value = ([Mock(payload={"doc_id": "A", "chunk_id": "A_1"}),
                                       Mock(payload={"doc_id": "X", "chunk_id": "X_1"})], None)
        manager._client = client
        result = manager.reconcile_counts(2, 2, expected_chunk_ids={"A_1", "B_1"})
        self.assertEqual(result["status"], "MISMATCH")

    def test_reconciliation_with_temporary_qdrant(self):
        from qdrant_client import QdrantClient, models

        client = QdrantClient(location=":memory:")
        try:
            manager = QdrantIndexManager()
            manager._client = client
            client.create_collection(manager.collection_name,
                vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
            client.upsert(manager.collection_name, points=[
                models.PointStruct(id=i, vector=[1.0, 0.0],
                                   payload={"doc_id": name, "chunk_id": name + "_1"})
                for i, name in enumerate(["A", "B"])
            ])
            result = manager.reconcile_counts(2, 2, {"A_1", "B_1"})
            self.assertEqual(result["status"], "PASSED")
            self.assertEqual(result["actual_documents_count"], 2)
            self.assertEqual(manager.reconcile_counts(2, 1)["status"], "MISMATCH")
        finally:
            client.close()
