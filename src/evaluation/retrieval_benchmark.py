"""
Module thực thi đánh giá khả năng Retrieval (Hit@k, Context Precision, Recall, MRR)
trên bộ câu hỏi kiểm chuẩn Golden Set.
Phiên bản: v2.0 (Hỗ trợ Cross-Encoder Reranker & Bootstrap CI 95%)

So sánh đối đầu 5 cấu hình:
1. Dense Only: Baseline ngữ nghĩa (Vector search với BGE-M3 + Hard filter)
2. Sparse Only: Baseline từ khóa (BM25 Tiếng Việt + Hard filter)
3. Hybrid No-Filter: Hợp nhất RRF Dense + Sparse không có bộ lọc (đo độ nhiễu)
4. Hybrid Filtered: Hợp nhất RRF Dense + Sparse + Hard filter (Ticker, Year)
5. Hybrid Rerank: Top 30 từ Hybrid Filtered -> Tái xếp hạng bằng BAAI/bge-reranker-v2-m3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

# Thêm thư mục gốc vào sys.path để tránh lỗi ModuleNotFoundError: No module named 'src'
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.evaluation.bm25_searcher import VietnameseBM25Searcher
from src.evaluation.metrics import bootstrap_ci, evaluate_retrieval_query
from src.evaluation.reranker import FinancialCrossEncoderReranker
from src.indexing.embedder import DocumentEmbedder, SUPPORTED_MODELS
from src.indexing.qdrant_manager import QdrantIndexManager

GOLDEN_DATASET_FILE = Path("configs/golden_evaluation_dataset.json")
SPLIT_FILE = Path("configs/eval_dataset_split.json")
OUTPUT_DIR = Path("evaluation/benchmarks")


def compute_rrf_fusion(
    ranked_list_1: List[Tuple[str, float]],
    ranked_list_2: List[Tuple[str, float]],
    top_k: int = 10,
    rrf_k: int = 60,
) -> List[Tuple[str, float]]:
    """
    Hợp nhất thứ hạng tương hỗ (Reciprocal Rank Fusion - RRF).
    score(d) = sum( 1 / (rrf_k + rank(d)) )
    """
    scores: Dict[str, float] = defaultdict(float)

    for rank, (doc_id, _) in enumerate(ranked_list_1, start=1):
        scores[doc_id] += 1.0 / (rrf_k + rank)

    for rank, (doc_id, _) in enumerate(ranked_list_2, start=1):
        scores[doc_id] += 1.0 / (rrf_k + rank)

    sorted_res = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return sorted_res


class RetrievalBenchmarkRunner:
    """
    Điều phối đánh giá Retrieval qua các cấu hình và trích xuất báo cáo.
    """

    def __init__(
        self,
        collection_name: str = "vnfin_v1_bge_m3_v1",
        use_cloud: bool = False,
        qdrant_path: str = "data/qdrant_local",
    ) -> None:
        self.collection_name = collection_name
        self.use_cloud = use_cloud
        self.qdrant_path = qdrant_path

        # Khởi tạo Qdrant Manager
        cfg = SUPPORTED_MODELS["bge-m3"]
        self.qdrant_mgr = QdrantIndexManager(
            model_slug=cfg["slug"],
            dimension=cfg["dimension"],
            distance_metric=cfg["distance"],
            qdrant_path=qdrant_path,
            use_cloud=use_cloud,
        )
        self.client = self.qdrant_mgr.get_client()

        # Khởi tạo BM25 Searcher
        self.bm25 = VietnameseBM25Searcher()
        self.all_chunks: List[Dict[str, Any]] = []
        self.chunk_map: Dict[str, Dict[str, Any]] = {}

        # Khởi tạo Embedder để mã hóa câu hỏi truy vấn
        self.embedder = DocumentEmbedder(model_name="bge-m3")

        # Reranker (nạp lười khi cần cấu hình rerank)
        self.reranker: Optional[FinancialCrossEncoderReranker] = None

    def prepare_bm25_index(self, processed_dir: Path = Path("data/processed_chunks")) -> None:
        """Đọc toàn bộ chunks từ JSON và xây dựng chỉ mục BM25 in-memory và chunk mapping."""
        print("[Setup] Đang tải toàn bộ chunks để dựng chỉ mục BM25 và mapping...")
        files = sorted([f for f in processed_dir.glob("*.json") if not f.name.startswith("_")])
        self.all_chunks = []
        for f in files:
            doc = json.loads(f.read_text(encoding="utf-8"))
            for c in doc.get("chunks", []):
                chunk_obj = {
                    "chunk_id": c["chunk_id"],
                    "text": c.get("text", ""),
                    "embed_text": c.get("embed_text", ""),
                    "ticker": doc.get("ticker", ""),
                    "fiscal_year": int(doc.get("fiscal_year", 0)),
                    "scope": doc.get("scope", "consolidated"),
                    "section": c.get("section", ""),
                    "citation_tag": c.get("citation_tag", ""),
                }
                self.all_chunks.append(chunk_obj)
                self.chunk_map[c["chunk_id"]] = chunk_obj

        self.bm25.index_chunks(self.all_chunks)
        print(f"[Setup] Đã lập chỉ mục BM25 và mapping cho {len(self.all_chunks):,} chunks.")

    def search_qdrant_dense(
        self,
        query: str,
        top_k: int = 10,
        filter_ticker: Optional[str] = None,
        filter_year: Optional[int] = None,
    ) -> List[Tuple[str, float]]:
        """Tìm kiếm vector ngữ nghĩa trên Qdrant."""
        from qdrant_client.http import models as qmodels

        query_vec = self.embedder._embed_batch_sorted([query])[0].tolist()

        filter_conditions = []
        if filter_ticker:
            filter_conditions.append(
                qmodels.FieldCondition(key="ticker", match=qmodels.MatchValue(value=filter_ticker))
            )
        if filter_year:
            filter_conditions.append(
                qmodels.FieldCondition(key="fiscal_year", match=qmodels.MatchValue(value=filter_year))
            )

        qdrant_filter = qmodels.Filter(must=filter_conditions) if filter_conditions else None

        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vec,
                query_filter=qdrant_filter,
                limit=top_k,
            )
            hits = response.points
        else:
            hits = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vec,
                query_filter=qdrant_filter,
                limit=top_k,
            )
        return [(hit.payload["chunk_id"], hit.score) for hit in hits if hit.payload and "chunk_id" in hit.payload]

    def search_hybrid_rerank(
        self,
        query: str,
        top_k: int = 10,
        filter_ticker: Optional[str] = None,
        filter_year: Optional[int] = None,
        candidate_pool_size: int = 30,
    ) -> List[Tuple[str, float]]:
        """
        Quy trình 2 giai đoạn (Full Text Cross-Encoder Rerank):
        Giai đoạn 1: Lấy candidate_pool_size (mặc định 30) từ Hybrid Filtered (RRF Dense + Sparse).
        Giai đoạn 2: Tái xếp hạng bằng Cross-Encoder Reranker trên Full Text (max_length=1024, GPU FP16).
        """
        # 1. Thu thập candidate pool
        r_dense = self.search_qdrant_dense(query, top_k=candidate_pool_size, filter_ticker=filter_ticker, filter_year=filter_year)
        r_sparse = self.bm25.search(query, top_k=candidate_pool_size, filter_ticker=filter_ticker, filter_year=filter_year)
        candidates_rrf = compute_rrf_fusion(r_dense, r_sparse, top_k=candidate_pool_size)

        candidate_chunks = []
        for cid, _ in candidates_rrf:
            if cid in self.chunk_map:
                candidate_chunks.append(self.chunk_map[cid])

        if not candidate_chunks:
            return []

        # 2. Khởi tạo Reranker (nếu chưa nạp)
        if self.reranker is None:
            self.reranker = FinancialCrossEncoderReranker(max_length=1024)

        # 3. Tái xếp hạng trên Full Text
        reranked = self.reranker.rerank(query, candidate_chunks, top_k=top_k)
        return reranked

    def evaluate_configuration(
        self,
        questions: List[Dict[str, Any]],
        mode: str = "hybrid_filtered",
        top_k: int = 10,
        candidate_pool_size: int = 30,
    ) -> Tuple[Dict[str, float], List[Dict[str, Any]]]:
        """
        Đánh giá một cấu hình cụ thể trên danh sách câu hỏi.
        mode in ['dense_only', 'sparse_only', 'hybrid_no_filter', 'hybrid_filtered', 'hybrid_rerank']
        """
        query_results = []
        aggregated_metrics = defaultdict(list)

        for q_idx, q in enumerate(questions, 1):
            q_text = q["question"]
            ticker = q.get("ticker")
            year = q.get("fiscal_year")
            gold_ids = q.get("gold_chunk_ids", [])

            if mode == "hybrid_rerank":
                print(f"\r     [Rerank Tiến độ] Đang xử lý {q_idx}/{len(questions)} ({q['question_id']})...", end="", flush=True)

            # Nếu là Loại C (đa năm), bỏ filter năm đơn lẻ
            if q.get("type") == "C":
                year = None

            # Xác định kết quả retrieval theo mode
            if mode == "dense_only":
                retrieved = self.search_qdrant_dense(q_text, top_k=top_k, filter_ticker=ticker, filter_year=year)
            elif mode == "sparse_only":
                retrieved = self.bm25.search(q_text, top_k=top_k, filter_ticker=ticker, filter_year=year)
            elif mode == "hybrid_no_filter":
                r_dense = self.search_qdrant_dense(q_text, top_k=top_k * 2, filter_ticker=None, filter_year=None)
                r_sparse = self.bm25.search(q_text, top_k=top_k * 2, filter_ticker=None, filter_year=None)
                retrieved = compute_rrf_fusion(r_dense, r_sparse, top_k=top_k)
            elif mode == "hybrid_filtered":
                r_dense = self.search_qdrant_dense(q_text, top_k=top_k * 2, filter_ticker=ticker, filter_year=year)
                r_sparse = self.bm25.search(q_text, top_k=top_k * 2, filter_ticker=ticker, filter_year=year)
                retrieved = compute_rrf_fusion(r_dense, r_sparse, top_k=top_k)
            elif mode == "hybrid_rerank":
                retrieved = self.search_hybrid_rerank(
                    query=q_text,
                    top_k=top_k,
                    filter_ticker=ticker,
                    filter_year=year,
                    candidate_pool_size=candidate_pool_size,
                )
            else:
                raise ValueError(f"Mode '{mode}' không hợp lệ.")

            retrieved_cids = [item[0] for item in retrieved]
            metrics = evaluate_retrieval_query(retrieved_cids, gold_ids, k_cutoffs=(1, 3, 5, 10))

            for m_key, m_val in metrics.items():
                aggregated_metrics[m_key].append(m_val)

            first_hit_rank = None
            gold_set = set(gold_ids)
            for r_idx, c_id in enumerate(retrieved_cids, start=1):
                if c_id in gold_set:
                    first_hit_rank = float(r_idx)
                    break

            query_results.append({
                "question_id": q["question_id"],
                "question": q_text,
                "type": q.get("type", "A"),
                "ticker": ticker,
                "fiscal_year": q.get("fiscal_year"),
                "retrieved_chunk_ids": retrieved_cids,
                "gold_chunk_ids": gold_ids,
                "metrics": metrics,
                "first_hit_rank": first_hit_rank,
            })

        if mode == "hybrid_rerank":
            print()

        mean_metrics = {k: float(np.mean(vals)) for k, vals in aggregated_metrics.items()}
        return mean_metrics, query_results


def run_retrieval_test(
    use_cloud: bool = False,
    include_test_set: bool = False,
    candidate_pool_size: int = 30,
    only_rerank: bool = False,
    processed_dir: Path = Path("data/processed_chunks"),
    golden_file: Path = GOLDEN_DATASET_FILE,
    output_dir: Path = OUTPUT_DIR,
    collection_name: str = "vnfin_v1_bge_m3_v1",
) -> None:
    print("=" * 80)
    print("KHỞI CHẠY BÀI TEST RETRIEVAL BENCHMARK & FULL TEXT CROSS-ENCODER RERANK (v2.1)")
    print("=" * 80)

    # 1. Đọc Golden Set
    golden_data = json.loads(golden_file.read_text(encoding="utf-8"))
    questions = golden_data["questions"]

    target_split = "dev" if not include_test_set else None
    if target_split:
        active_questions = [q for q in questions if q["split"] == target_split]
        print(f"[Phân vùng] Chạy trên tập: DEV ({len(active_questions)} câu hỏi)")
    else:
        active_questions = questions
        print(f"[Phân vùng] Chạy trên TOÀN BỘ ({len(active_questions)} câu hỏi Dev + Test)")

    # 2. Khởi tạo Benchmark Runner
    runner = RetrievalBenchmarkRunner(use_cloud=use_cloud, collection_name=collection_name)
    runner.prepare_bm25_index(processed_dir)

    # 3. Đánh giá qua các cấu hình đối đầu
    modes = ["hybrid_rerank"] if only_rerank else ["dense_only", "sparse_only", "hybrid_no_filter", "hybrid_filtered", "hybrid_rerank"]
    overall_summary = {}
    detailed_reports = {}

    if only_rerank:
        existing_report_file = output_dir / "retrieval_benchmark_report.json"
        if existing_report_file.exists():
            try:
                old_data = json.loads(existing_report_file.read_text(encoding="utf-8"))
                overall_summary = old_data.get("overall_summary", {})
                detailed_reports = old_data.get("detailed_results", {})
                print(f"[Tối ưu] Đã nạp kết quả 4 mode cơ sở từ cache, chỉ chạy lại cấu hình HYBRID_RERANK Full Text.")
            except Exception:
                pass

    for mode in modes:
        print(f"\n---> Đang đánh giá cấu hình: [{mode.upper()}] (Candidate Pool = {candidate_pool_size}) ...")
        t0 = time.perf_counter()
        metrics, q_details = runner.evaluate_configuration(
            active_questions,
            mode=mode,
            top_k=10,
            candidate_pool_size=candidate_pool_size,
        )
        elapsed = time.perf_counter() - t0

        # Lọc riêng 78 câu đơn năm (A + B) để báo cáo trung thực
        ab_metrics = [q["metrics"] for q in q_details if q["type"] in ["A", "B"]]
        r10_ab = np.mean([m["recall@10"] for m in ab_metrics])
        mrr_ab = np.mean([m["mrr"] for m in ab_metrics])
        h1_ab = np.mean([m["hit@1"] for m in ab_metrics])
        h5_ab = np.mean([m["hit@5"] for m in ab_metrics])

        print(f"     Hoàn thành sau {elapsed:.2f}s | (A+B: {len(ab_metrics)} câu) -> Hit@1: {h1_ab:.1%} | Hit@5: {h5_ab:.1%} | Recall@10: {r10_ab:.1%} | MRR: {mrr_ab:.4f}")
        overall_summary[mode] = metrics
        detailed_reports[mode] = q_details

    # 4. Phân tích thống kê chuyên sâu & Bootstrap CI cho cấu hình Hybrid Rerank
    print("\n" + "=" * 80)
    print("BÁO CÁO CHI TIẾT & KHOẢNG TIN CẬY BOOTSTRAP 95% (CẤU HÌNH HYBRID + RERANK FULL TEXT)")
    print("=" * 80)

    best_details = detailed_reports["hybrid_rerank"]
    by_type = defaultdict(list)
    for q_res in best_details:
        by_type[q_res["type"]].append(q_res)

    def print_group_stats(group_name: str, qs: List[Dict[str, Any]]) -> Dict[str, Any]:
        h1_vals = [q["metrics"]["hit@1"] for q in qs]
        h3_vals = [q["metrics"]["hit@3"] for q in qs]
        h5_vals = [q["metrics"]["hit@5"] for q in qs]
        h10_vals = [q["metrics"]["hit@10"] for q in qs]
        r10_vals = [q["metrics"]["recall@10"] for q in qs]
        cp10_vals = [q["metrics"]["context_precision@10"] for q in qs]
        mrr_vals = [q["metrics"]["mrr"] for q in qs]

        h1_low, h1_high, h1_m = bootstrap_ci(h1_vals)
        h5_low, h5_high, h5_m = bootstrap_ci(h5_vals)
        mrr_low, mrr_high, mrr_m = bootstrap_ci(mrr_vals)

        print(f"\n[{group_name} - {len(qs)} câu]")
        print(f"  Hit@1:  {h1_m:.1%}  (95% CI: [{h1_low:.1%} - {h1_high:.1%}])")
        print(f"  Hit@3:  {np.mean(h3_vals):.1%}")
        print(f"  Hit@5:  {h5_m:.1%}  (95% CI: [{h5_low:.1%} - {h5_high:.1%}])")
        print(f"  Hit@10: {np.mean(h10_vals):.1%}")
        print(f"  Recall@10: {np.mean(r10_vals):.4f} | Context Precision@10: {np.mean(cp10_vals):.4f}")
        print(f"  MRR:    {mrr_m:.4f} (95% CI: [{mrr_low:.4f} - {mrr_high:.4f}])")

        return {
            "count": len(qs),
            "hit@1": h1_m, "hit@1_ci": [h1_low, h1_high],
            "hit@3": float(np.mean(h3_vals)),
            "hit@5": h5_m, "hit@5_ci": [h5_low, h5_high],
            "hit@10": float(np.mean(h10_vals)),
            "recall@10": float(np.mean(r10_vals)),
            "context_precision@10": float(np.mean(cp10_vals)),
            "mrr": mrr_m, "mrr_ci": [mrr_low, mrr_high],
        }

    stats_ab = print_group_stats("TẬP ĐƠN NĂM (A + B)", by_type["A"] + by_type["B"])
    stats_a = print_group_stats("LOẠI A (SỐ LIỆU FACTS)", by_type["A"])
    stats_b = print_group_stats("LOẠI B (VĂN BẢN THUYẾT MINH)", by_type["B"])

    print(f"\n[LOẠI C - ĐA NĂM ({len(by_type['C'])} câu)]: Đo ở cấp độ Planner (Decomposition), điểm retrieval đơn lẻ: 0%")
    print(f"[LOẠI TRAP - BẪY ({len(by_type['TRAP'])} câu)]: Đo ở cấp độ Writer (Refusal), Recall quy ước: 1.0")

    # 5. Lưu báo cáo hoàn chỉnh
    output_dir.mkdir(parents=True, exist_ok=True)
    report_file = output_dir / "retrieval_benchmark_report.json"
    full_report = {
        "benchmark_date": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "target_split": target_split or "all",
        "total_questions_evaluated": len(active_questions),
        "single_year_count": len(by_type["A"] + by_type["B"]),
        "statistical_summary_ab": stats_ab,
        "statistical_summary_a": stats_a,
        "statistical_summary_b": stats_b,
        "overall_summary": overall_summary,
        "detailed_results": detailed_reports,
    }
    report_file.write_text(json.dumps(full_report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[Báo cáo] Kết quả benchmark đầy đủ đã lưu tại: {report_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy kiểm thử đánh giá Retrieval Benchmark có Cross-Encoder Rerank.")
    parser.add_argument("--cloud", action="store_true", help="Chạy đánh giá trên Qdrant Cloud cluster")
    parser.add_argument("--eval-test", action="store_true", help="Chạy trên toàn bộ bao gồm cả tập TEST (Mặc định chỉ chạy DEV)")
    parser.add_argument("--candidate-pool", type=int, default=30, help="Số lượng ứng viên đưa vào Reranker (mặc định 30)")
    parser.add_argument("--only-rerank", action="store_true", help="Chỉ chạy riêng cấu hình Hybrid Rerank trên Full Text")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed_chunks"))
    parser.add_argument("--golden-file", type=Path, default=GOLDEN_DATASET_FILE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--collection-name", default="vnfin_v1_bge_m3_v1")
    args = parser.parse_args()

    run_retrieval_test(
        use_cloud=args.cloud,
        include_test_set=args.eval_test,
        candidate_pool_size=args.candidate_pool,
        only_rerank=args.only_rerank,
        processed_dir=args.processed_dir,
        golden_file=args.golden_file,
        output_dir=args.output_dir,
        collection_name=args.collection_name,
    )


if __name__ == "__main__":
    main()
