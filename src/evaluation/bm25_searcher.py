"""
Bộ tìm kiếm BM25 (Okapi BM25) thuần Python cho Báo cáo Tài chính Việt Nam.
Sử dụng chung 100% logic với src.indexing.vietnamese_sparse_tokenizer.
Không phụ thuộc vào thư viện ngoài.
"""

from __future__ import annotations

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Thêm thư mục gốc vào sys.path để tránh lỗi ModuleNotFoundError: No module named 'src'
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.indexing.vietnamese_sparse_tokenizer import tokenize_vietnamese_sparse


class VietnameseBM25Searcher:
    """
    Chỉ mục BM25 In-memory hỗ trợ lọc cứng siêu dữ liệu (Hard Filtering theo ticker, year).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avgdl = 0.0
        self.doc_lengths: List[int] = []
        self.doc_ids: List[str] = []
        self.doc_metas: List[Dict[str, Any]] = []
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        self.idf: Dict[str, float] = {}

    def index_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """Đánh chỉ mục cho danh sách các chunk."""
        self.corpus_size = len(chunks)
        self.doc_ids = []
        self.doc_metas = []
        self.doc_lengths = []
        self.inverted_index = defaultdict(list)
        
        total_len = 0
        df_counts: Counter[str] = Counter()

        for idx, c in enumerate(chunks):
            cid = c["chunk_id"]
            self.doc_ids.append(cid)
            self.doc_metas.append({
                "ticker": c.get("ticker", ""),
                "fiscal_year": int(c.get("fiscal_year", 0)),
                "scope": c.get("scope", "consolidated"),
                "section": c.get("section", ""),
            })

            tokens = tokenize_vietnamese_sparse(c.get("text", ""))
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            term_freqs = Counter(tokens)
            for term, freq in term_freqs.items():
                self.inverted_index[term].append((idx, freq))
                df_counts[term] += 1

        self.avgdl = total_len / max(1, self.corpus_size)

        # Tính IDF: ln(1 + (N - n + 0.5) / (n + 0.5))
        for term, df in df_counts.items():
            self.idf[term] = math.log(1.0 + (self.corpus_size - df + 0.5) / (df + 0.5))

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_ticker: Optional[str] = None,
        filter_year: Optional[int] = None,
        filter_scope: Optional[str] = None,
        filter_sections: Optional[List[str]] = None,
    ) -> List[Tuple[str, float]]:
        """
        Tìm kiếm BM25 có hỗ trợ lọc cứng (Hard filter).
        Trả về list of (chunk_id, bm25_score) xếp giảm dần.
        """
        query_tokens = tokenize_vietnamese_sparse(query)
        if not query_tokens:
            return []

        scores: Dict[int, float] = defaultdict(float)

        for term in query_tokens:
            if term not in self.inverted_index:
                continue
            idf_val = self.idf.get(term, 0.0)
            for doc_idx, freq in self.inverted_index[term]:
                # Áp dụng bộ lọc cứng metadata
                if filter_ticker is not None and self.doc_metas[doc_idx]["ticker"] != filter_ticker:
                    continue
                if filter_year is not None and self.doc_metas[doc_idx]["fiscal_year"] != filter_year:
                    continue
                if filter_scope is not None and self.doc_metas[doc_idx]["scope"] != filter_scope:
                    continue
                if filter_sections is not None and self.doc_metas[doc_idx]["section"] not in filter_sections:
                    continue

                dl = self.doc_lengths[doc_idx]
                denom = freq + self.k1 * (1.0 - self.b + self.b * (dl / self.avgdl))
                term_score = idf_val * ((freq * (self.k1 + 1.0)) / max(1e-9, denom))
                scores[doc_idx] += term_score

        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [(self.doc_ids[idx], float(sc)) for idx, sc in sorted_docs]
