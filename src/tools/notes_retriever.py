"""Production notes retrieval: filtered Qdrant dense + BM25, then RRF."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.indexing.vietnamese_sparse_tokenizer import normalize_vietnamese_sparse
from src.storage.active_corpus import ACTIVE_CORPUS, active_path

from .schemas import NoteEvidence, NotesSearchInput

ROOT = Path(__file__).resolve().parents[2]


def classify_audit_chunk(text: str) -> list[str]:
    """Tag audit paragraphs for later excerpt selection; preserve every chunk."""
    words = " ".join(normalize_vietnamese_sparse(text).split())
    roles = []
    if "theo y kien cua chung toi" in words and "phan anh trung thuc" in words:
        roles.append("opinion_conclusion")
    if any(phrase in words for phrase in ("van de can nhan manh", "van de nhan manh",
                                          "co so y kien ngoai tru")):
        roles.append("emphasis")
    if "trach nhiem" in words:
        roles.append("responsibility")
    if "co so cho y kien" in words or "co so y kien" in words:
        roles.append("opinion_basis")
    if "kiem toan vien" in words and "cndkhn" in words:
        roles.append("signature")
    return roles or ["context"]


def rrf_fusion(dense: list[tuple[str, float]], sparse: list[tuple[str, float]],
               limit: int = 30) -> list[str]:
    """Fuse ranks with k=60, without mixing incomparable raw scores."""
    scores: dict[str, float] = {}
    for ranking in (dense, sparse):
        for rank, (cid, _) in enumerate(ranking, 1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (60 + rank)
    return sorted(scores, key=lambda cid: (-scores[cid], cid))[:limit]


class HybridNotesRetriever:
    """Lazy heavyweight resources, reusable per agent runtime; close after use.

    Sparse search uses the project's Vietnamese BM25 index in memory. Qdrant
    supplies dense candidates; this is not Qdrant-native sparse-vector search.
    """

    def __init__(self, processed_dir: str | Path | None = None,
                 qdrant_path: str | Path = ROOT / "data/qdrant_local",
                 use_cloud: bool = False,
                 collection_name: str | None = None,
                 candidate_pool_size: int = 30) -> None:
        if candidate_pool_size < 5:
            raise ValueError("candidate_pool_size must be at least 5")
        self.processed_dir = Path(processed_dir) if processed_dir is not None else active_path("processed_dir")
        self.qdrant_path = str(qdrant_path)
        self.use_cloud = use_cloud
        self.collection_name = collection_name or ACTIVE_CORPUS["collection_name"]
        self.candidate_pool_size = candidate_pool_size
        self.chunks: dict[str, dict[str, Any]] = {}
        self.bm25 = None
        self.embedder = None
        self.manager = None

    def _prepare_corpus(self) -> None:
        if self.bm25 is not None:
            return
        from src.evaluation.bm25_searcher import VietnameseBM25Searcher

        chunks = {}
        for path in sorted(self.processed_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            doc = json.loads(path.read_text(encoding="utf-8"))
            for chunk in doc["chunks"]:
                if chunk["section"] not in {"NOTES", "AUDIT_REPORT", "MANAGEMENT_REPORT"}:
                    continue
                cid = chunk["chunk_id"]
                if cid in chunks:
                    raise ValueError(f"Duplicate chunk_id: {cid}")
                chunks[cid] = {**chunk, "doc_id": doc["doc_id"], "ticker": doc["ticker"],
                               "fiscal_year": doc["fiscal_year"], "scope": doc["scope"],
                               "source_file": doc["source_file"]}
        if not chunks:
            raise ValueError("No qualitative chunks found in the configured corpus")
        bm25 = VietnameseBM25Searcher()
        bm25.index_chunks(list(chunks.values()))
        self.chunks, self.bm25 = chunks, bm25

    def search(self, args: NotesSearchInput, *, limit: int = 5) -> list[NoteEvidence]:
        """Return ranked citation-bearing chunks; the public tool keeps its five-chunk cap."""
        if not 1 <= limit <= self.candidate_pool_size:
            raise ValueError("limit must be within the candidate pool")
        self._prepare_corpus()
        eligible = {
            cid for cid, c in self.chunks.items()
            if c["ticker"] == args.ticker and c["fiscal_year"] == args.fiscal_year
            and c["scope"] == args.scope and c["section"] in args.sections
        }
        if not eligible:
            return []
        from qdrant_client.http import models
        from src.indexing.embedder import DocumentEmbedder
        from src.indexing.qdrant_manager import QdrantIndexManager

        if self.manager is None:
            self.manager = QdrantIndexManager(qdrant_path=self.qdrant_path, use_cloud=self.use_cloud)
        if self.embedder is None:
            self.embedder = DocumentEmbedder(cache_dir=ROOT / "data/vector_cache/bge_m3")
        filters = models.Filter(must=[
            models.FieldCondition(key="ticker", match=models.MatchValue(value=args.ticker)),
            models.FieldCondition(key="fiscal_year", match=models.MatchValue(value=args.fiscal_year)),
            models.FieldCondition(key="scope", match=models.MatchValue(value=args.scope)),
            models.FieldCondition(key="section", match=models.MatchAny(any=args.sections)),
        ])
        vector = self.embedder._embed_batch_sorted([args.query])[0].tolist()
        response = self.manager.get_client().query_points(
            collection_name=self.collection_name, query=vector, query_filter=filters,
            limit=self.candidate_pool_size, with_payload=True)
        dense = [(hit.payload["chunk_id"], float(hit.score)) for hit in response.points
                 if hit.payload and hit.payload.get("chunk_id") in eligible]
        sparse = self.bm25.search(
            args.query, top_k=self.candidate_pool_size, filter_ticker=args.ticker,
            filter_year=args.fiscal_year, filter_scope=args.scope, filter_sections=args.sections)
        ranked_ids = rrf_fusion(dense, sparse, limit)
        if not ranked_ids:
            return []
        return [NoteEvidence(**{key: self.chunks[cid][key] for key in (
            "chunk_id", "doc_id", "ticker", "fiscal_year", "scope", "section", "text",
            "source_file", "physical_pages", "printed_pages", "citation_tag")},
            rerank_score=None) for cid in ranked_ids]

    def read_audit_section(self, ticker: str, fiscal_year: int, scope: str
                           ) -> list[NoteEvidence]:
        """Read every indexed audit chunk for one report without top-k ranking."""
        self._prepare_corpus()
        ids = sorted(cid for cid, chunk in self.chunks.items()
                     if chunk["ticker"] == ticker and chunk["fiscal_year"] == fiscal_year
                     and chunk["scope"] == scope and chunk["section"] == "AUDIT_REPORT")
        return [NoteEvidence(**{key: self.chunks[cid][key] for key in (
            "chunk_id", "doc_id", "ticker", "fiscal_year", "scope", "section", "text",
            "source_file", "physical_pages", "printed_pages", "citation_tag")},
            rerank_score=None, topic_roles=classify_audit_chunk(self.chunks[cid]["text"]))
            for cid in ids]

    def close(self) -> None:
        """Release Qdrant's local lock or cloud connection."""
        if self.manager is not None:
            client = getattr(self.manager, "_client", None)
            if client is not None:
                client.close()
            self.manager = None
