import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd

from src.indexing.embedder import DocumentEmbedder
from src.indexing.qdrant_manager import QdrantIndexManager
from src.indexing.pipeline import reconcile_vector_cache


class HashReuseTests(unittest.TestCase):
    def test_reuses_existing_vector_bit_for_bit_and_embeds_only_new_hash(self):
        with tempfile.TemporaryDirectory() as root:
            old = Path(root) / "old"
            new = Path(root) / "new"
            old.mkdir()
            source = DocumentEmbedder(cache_dir=old)
            known_hash = source.compute_content_hash("same text")
            known_vector = np.array([0.125, -0.75], dtype=np.float32)
            pd.DataFrame({
                "chunk_id": ["old_1"], "doc_id": ["old"],
                "content_hash": [known_hash], "embedding": [known_vector],
            }).to_parquet(old / "old.parquet", index=False)

            target = DocumentEmbedder(cache_dir=new, reuse_cache_dir=old)
            target._embed_batch_sorted = Mock(return_value=np.array([[0.5, 0.25]], dtype=np.float32))
            chunks = [
                {"chunk_id": "new_1", "embed_text": "same text"},
                {"chunk_id": "new_2", "embed_text": "new text"},
                {"chunk_id": "new_3", "embed_text": "same text"},
            ]
            vectors, hashes = target.embed_document_chunks("candidate", chunks)
            target._embed_batch_sorted.assert_called_once_with(["new text"])
            self.assertTrue(np.array_equal(vectors[0], known_vector))
            self.assertTrue(np.array_equal(vectors[2], known_vector))
            saved = pd.read_parquet(new / "candidate.parquet")
            self.assertEqual(saved["content_hash"].tolist(), hashes)
            self.assertTrue(np.array_equal(saved["embedding"][0], known_vector))

    def test_new_index_has_distinct_collection_name(self):
        self.assertEqual(QdrantIndexManager(index_version="v2_1").collection_name,
                         "vnfin_v2_1_bge_m3_v1")

    def test_parquet_reconciliation_checks_ids_and_hashes(self):
        with tempfile.TemporaryDirectory() as root:
            cache = Path(root)
            chunk = {"chunk_id": "D_1", "embed_text": "text"}
            content_hash = hashlib.sha256(b"text").hexdigest()
            docs = [{"doc_id": "D", "chunks": [chunk]}]
            pd.DataFrame({"chunk_id": ["D_1"], "content_hash": [content_hash]}).to_parquet(
                cache / "D.parquet", index=False)
            self.assertEqual(reconcile_vector_cache(docs, cache)["status"], "PASSED")
            docs[0]["chunks"][0]["embed_text"] = "changed"
            self.assertEqual(reconcile_vector_cache(docs, cache)["status"], "MISMATCH")
