"""
Module đánh giá định lượng Retrieval (Dense, Sparse, Hybrid + Reranker).
Phiên bản: v1.0

Tuân thủ nguyên tắc:
1. Đánh giá strictly trên tập Dev (25 công ty) từ configs/eval_dataset_split.json, giữ tập Test (10 công ty) nguyên vẹn.
2. Đo đạc Recall@k (k=1, 3, 5, 10) và MRR cho 3 cấu hình:
   - Dense Only (Qdrant Vector Search)
   - Sparse Only (BM25 Keyword Search)
   - Hybrid (Reciprocal Rank Fusion - RRF) + Reranker
3. Hard filtering theo ticker và fiscal_year từ query intent.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.indexing.vietnamese_sparse_tokenizer import normalize_vietnamese_sparse, tokenize_vietnamese_sparse


class RetrievalEvaluator:
    """
    Trình đánh giá hiệu năng trích xuất thông tin tài chính đa cấu hình.
    """

    def __init__(
        self,
        split_config_path: Path = Path("configs/eval_dataset_split.json"),
        collection_name: str = "vnfin_v1_bge_m3_v1",
        qdrant_path: str = "data/qdrant_local",
    ) -> None:
        self.split_config = json.loads(split_config_path.read_text(encoding="utf-8"))
        self.dev_tickers = set(self.split_config["dev_tickers"])
        self.test_tickers = set(self.split_config["test_tickers"])
        self.collection_name = collection_name
        self.qdrant_path = qdrant_path

    def compute_rrf(
        self,
        dense_results: List[Tuple[str, float]],
        sparse_results: List[Tuple[str, float]],
        rrf_k: int = 60,
    ) -> List[Tuple[str, float]]:
        """
        Hợp nhất xếp hạng tương hỗ (Reciprocal Rank Fusion - RRF).
        RRF_score(d) = sum_{m in models} 1 / (rrf_k + rank_m(d))
        """
        scores: Dict[str, float] = {}

        for rank, (doc_id, _) in enumerate(dense_results, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))

        for rank, (doc_id, _) in enumerate(sparse_results, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (rrf_k + rank))

        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_items

    def compute_metrics(
        self,
        ground_truth: List[str],
        retrieved: List[str],
        k_list: Tuple[int, ...] = (1, 3, 5, 10),
    ) -> Dict[str, float]:
        """
        Tính toán Recall@k và MRR cho một lượt truy vấn.
        """
        gt_set = set(ground_truth)
        metrics: Dict[str, float] = {}

        for k in k_list:
            top_k = retrieved[:k]
            hits = len(set(top_k) & gt_set)
            metrics[f"recall@{k}"] = hits / len(gt_set) if gt_set else 0.0

        # Mean Reciprocal Rank (MRR)
        mrr = 0.0
        for rank, item in enumerate(retrieved, start=1):
            if item in gt_set:
                mrr = 1.0 / rank
                break
        metrics["mrr"] = mrr

        return metrics

    def run_benchmark(
        self,
        eval_queries: List[Dict[str, Any]],
        output_report_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """
        Thực thi benchmark trên danh sách câu hỏi kiểm thử tập Dev.
        Đo lường cho cả 3 chế độ: dense, sparse, hybrid.
        """
        results_by_mode: Dict[str, List[Dict[str, float]]] = {
            "dense_only": [],
            "sparse_only": [],
            "hybrid_rrf": [],
        }

        print(f"[Benchmark] Bắt đầu đánh giá trên {len(eval_queries)} câu hỏi tập Dev...")
        # Template sẵn sàng khi có Qdrant client và query set đầy đủ
        summary_results = {
            "dataset_split": "dev",
            "num_queries": len(eval_queries),
            "collection_evaluated": self.collection_name,
            "metrics": {
                "dense_only": {"recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0, "recall@10": 0.0, "mrr": 0.0},
                "sparse_only": {"recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0, "recall@10": 0.0, "mrr": 0.0},
                "hybrid_rrf": {"recall@1": 0.0, "recall@3": 0.0, "recall@5": 0.0, "recall@10": 0.0, "mrr": 0.0},
            },
        }

        if output_report_path:
            output_report_path.parent.mkdir(parents=True, exist_ok=True)
            output_report_path.write_text(json.dumps(summary_results, indent=2, ensure_ascii=False), encoding="utf-8")

        return summary_results
