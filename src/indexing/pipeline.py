"""
Pipeline tổng thể thực thi Vector Embedding & Sparse Indexing.
Phiên bản: v1.0

Cung cấp CLI hoàn chỉnh hỗ trợ:
--model: Chọn mô hình (bge-m3, multilingual-e5-base)
--dry-run: Rà soát cấu hình, kiểm tra toàn vẹn dữ liệu JSON mà không gọi model
--benchmark-200: Chạy đo đạc tốc độ trên 200 chunk mẫu và ước lượng thời gian chạy toàn corpus
--rebuild: Xóa tạo lại collection mới mà không ghi đè dữ liệu cũ
--reconcile-only: Kiểm tra đối chiếu số lượng giữa JSON, Parquet và Qdrant
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

# Đảm bảo import được module từ thư mục gốc
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.indexing.embedder import DocumentEmbedder, SUPPORTED_MODELS
from src.indexing.qdrant_manager import QdrantIndexManager, EMBED_TEXT_VERSION
from src.indexing.vietnamese_sparse_tokenizer import TOKENIZER_VERSION


def load_all_processed_documents(input_dir: Path) -> List[Dict[str, Any]]:
    """Đọc toàn bộ file JSON từ thư mục data/processed_chunks."""
    files = sorted(input_dir.glob("*.json"))
    files = [f for f in files if not f.name.startswith("_")]
    docs: List[Dict[str, Any]] = []
    for f in files:
        try:
            docs.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[Cảnh báo] Lỗi đọc {f.name}: {e}")
    return docs


def reconcile_vector_cache(docs: List[Dict[str, Any]], cache_dir: Path) -> Dict[str, Any]:
    """Verify candidate Parquet rows against each JSON chunk and its embed text."""
    mismatched_docs = []
    total_rows = 0
    for doc in docs:
        path = cache_dir / f"{doc['doc_id']}.parquet"
        if not path.exists():
            mismatched_docs.append(doc["doc_id"])
            continue
        frame = pd.read_parquet(path, columns=["chunk_id", "content_hash"])
        chunks = doc.get("chunks", [])
        expected_ids = [c["chunk_id"] for c in chunks]
        expected_hashes = [hashlib.sha256(
            (c.get("embed_text") or c.get("text", "")).encode("utf-8")
        ).hexdigest() for c in chunks]
        total_rows += len(frame)
        if frame["chunk_id"].tolist() != expected_ids or frame["content_hash"].tolist() != expected_hashes:
            mismatched_docs.append(doc["doc_id"])
    return {
        "status": "PASSED" if not mismatched_docs else "MISMATCH",
        "documents": len(docs), "parquet_rows": total_rows,
        "mismatched_docs": mismatched_docs,
    }


def run_pipeline(
    input_dir: Path,
    model_name: str = "bge-m3",
    batch_size: int = 32,
    dry_run: bool = False,
    benchmark_200: bool = False,
    rebuild: bool = False,
    reconcile_only: bool = False,
    qdrant_path: str = "data/qdrant_local",
    qdrant_url: str = "",
    use_cloud: bool = False,
    start_from: Optional[str] = None,
    index_version: str = "v1",
    parser_version: str = "v2.1",
    cache_dir: Optional[Path] = None,
    reuse_cache_dir: Optional[Path] = None,
) -> None:
    print("=" * 80)
    print("KHỞI CHẠY PIPELINE VECTOR EMBEDDING & SPARSE INDEXING")
    print(f"Mô hình: {model_name} | Batch size: {batch_size}")
    print(f"Thư mục nguồn JSON: {input_dir}")
    print("=" * 80)

    # 1. Đọc dữ liệu JSON
    docs = load_all_processed_documents(input_dir)
    total_docs = len(docs)
    all_chunks: List[Dict[str, Any]] = []
    for d in docs:
        all_chunks.extend(d.get("chunks", []))
    total_chunks = len(all_chunks)

    start_index = 1
    if start_from is not None:
        if start_from.isdigit():
            start_index = int(start_from)
        else:
            start_index = next((i for i, doc in enumerate(docs, 1)
                                if doc["doc_id"] == start_from), 0)
        if not 1 <= start_index <= total_docs:
            raise ValueError(f"Mốc --start-from không hợp lệ: {start_from!r}")
        if rebuild and start_index > 1:
            raise ValueError("Không thể --rebuild và bỏ qua tài liệu bằng --start-from")

    print(f"[Nguồn] Tổng số tài liệu: {total_docs} | Tổng số chunks: {total_chunks}")

    # Khởi tạo Quản lý Qdrant
    cfg = SUPPORTED_MODELS[model_name]
    
    # Xác định endpoint Qdrant: Cloud hay Local
    target_url = qdrant_url
    target_path = qdrant_path
    if use_cloud or target_url:
        target_path = None
        if not target_url:
            # Tự động lấy từ biến môi trường / .env
            from src.indexing.qdrant_manager import load_env_variables
            env = load_env_variables()
            target_url = env.get("QDRANT_ENDPOINT") or env.get("QDRANT_URL")
            if not target_url:
                raise ValueError("Không tìm thấy QDRANT_ENDPOINT hoặc QDRANT_URL trong .env để kết nối Cloud!")
            print(f"[Qdrant Cloud] Sử dụng endpoint từ .env: {target_url}")

    qdrant_mgr = QdrantIndexManager(
        model_slug=cfg["slug"],
        dimension=cfg["dimension"],
        distance_metric=cfg["distance"],
        embed_text_version=EMBED_TEXT_VERSION,
        index_version=index_version,
        qdrant_url=target_url,
        qdrant_path=target_path,
    )

    # Chế độ Reconcile Only
    if reconcile_only:
        print("\n--- KIỂM TRA ĐỐI CHIẾU SỐ LƯỢNG (RECONCILIATION) ---")
        recon = qdrant_mgr.reconcile_counts(
            expected_chunks_count=total_chunks,
            expected_docs_count=sum(bool(doc.get("chunks")) for doc in docs),
            expected_chunk_ids={chunk["chunk_id"] for chunk in all_chunks},
        )
        print(json.dumps(recon, indent=2, ensure_ascii=False))
        if cache_dir is not None:
            cache_recon = reconcile_vector_cache(docs, cache_dir)
            print(json.dumps(cache_recon, indent=2, ensure_ascii=False))
            if cache_recon["status"] != "PASSED" or recon["status"] != "PASSED":
                raise RuntimeError("JSON, Parquet và Qdrant chưa khớp")
        return

    # Chế độ Benchmark 200 chunk
    if benchmark_200:
        print("\n--- CHẠY THỬ NGHIỆM ĐO ĐẠC TỐC ĐỘ TRÊN 200 CHUNK MẪU ---")
        embedder = DocumentEmbedder(model_name=model_name, batch_size=batch_size)
        bench_result = embedder.benchmark_speed(all_chunks, sample_size=200)
        print("\nKẾT QUẢ BENCHMARK SUY LUẬN EMBEDDING:")
        print(json.dumps(bench_result, indent=2, ensure_ascii=False))
        return

    # Chế độ Dry Run
    if dry_run:
        print("\n--- CHẾ ĐỘ DRY-RUN (KIỂM TRA CẤU HÌNH & KHÔNG GỌI MÔ HÌNH) ---")
        print(f"Collection mục tiêu: {qdrant_mgr.collection_name}")
        print(f"Dimension: {cfg['dimension']} | Metric: {cfg['distance']}")
        print(f"Prefix passage: '{cfg['prefix_passage']}' | Prefix query: '{cfg['prefix_query']}'")
        print(f"Sparse tokenizer version: {TOKENIZER_VERSION}")
        print(f"Embed text version: {EMBED_TEXT_VERSION}")

        # Kiểm tra tính toàn vẹn của chunk
        missing_citation = sum(1 for c in all_chunks if not c.get("citation_tag"))
        missing_embed_txt = sum(1 for c in all_chunks if not c.get("embed_text"))
        print(f"Số chunk thiếu citation_tag: {missing_citation}")
        print(f"Số chunk thiếu embed_text: {missing_embed_txt}")
        print("\n[Dry Run PASSED] Sẵn sàng thực thi pipeline!")
        return

    # Khởi tạo Collection trong Qdrant
    qdrant_mgr.create_versioned_collection(recreate_if_exists=rebuild)

    # Khởi tạo Embedder
    embedder = DocumentEmbedder(
        model_name=model_name,
        batch_size=batch_size,
        cache_dir=cache_dir,
        reuse_cache_dir=reuse_cache_dir,
    )

    ckpt = embedder.get_checkpoint()
    completed_set = set(ckpt["completed_docs"])
    print(f"[Checkpoint] Đã hoàn thành trước đó: {len(completed_set)}/{total_docs} tài liệu.")

    total_indexed_points = 0
    uploaded_documents = 0
    t_start = time.perf_counter()

    for idx, doc in enumerate(docs, start=1):
        if idx < start_index:
            continue
        doc_id = doc["doc_id"]
        chunks = doc.get("chunks", [])

        if not chunks:
            continue

        if doc_id in completed_set and not rebuild:
            # Đọc từ cache
            vectors, hashes = embedder.embed_document_chunks(doc_id, chunks, force_recompute=False)
        else:
            print(f"[{idx:3d}/{total_docs:3d}] Đang embed '{doc_id}' ({len(chunks)} chunks)...")
            vectors, hashes = embedder.embed_document_chunks(doc_id, chunks, force_recompute=rebuild)

        # Upload vào Qdrant
        print(f"[{idx:3d}/{total_docs:3d}] Đang tải '{doc_id}' ({len(chunks)} chunks) lên Qdrant...")
        doc_meta = {
            "doc_id": doc_id,
            "ticker": doc.get("ticker", ""),
            "fiscal_year": doc.get("fiscal_year", 0),
            "scope": doc.get("scope", "consolidated"),
            "default_unit": doc.get("default_unit", "VND"),
        }
        n_up = qdrant_mgr.upload_document_points(
            chunks=chunks,
            doc_meta=doc_meta,
            embeddings=vectors,
            content_hashes=hashes,
            batch_size=64 if use_cloud else 128,
        )
        total_indexed_points += n_up
        uploaded_documents += 1

    elapsed_total = time.perf_counter() - t_start

    # Chỉ công bố hoàn tất sau khi đối soát toàn bộ collection, kể cả khi resume.
    recon = qdrant_mgr.reconcile_counts(
        expected_chunks_count=total_chunks,
        expected_docs_count=sum(bool(doc.get("chunks")) for doc in docs),
        expected_chunk_ids={chunk["chunk_id"] for chunk in all_chunks},
    )
    if recon["status"] != "PASSED":
        raise RuntimeError(f"Đối soát collection thất bại; không cập nhật manifest: {recon}")
    if cache_dir is not None:
        cache_recon = reconcile_vector_cache(docs, cache_dir)
        if cache_recon["status"] != "PASSED":
            raise RuntimeError(f"Đối soát Parquet thất bại; không cập nhật manifest: {cache_recon}")

    # Lưu Manifest
    manifest_dir = Path("configs/manifests")
    qdrant_mgr.save_manifest(
        output_dir=manifest_dir,
        parser_version=parser_version,
        model_name=cfg["model_id"],
        model_version=cfg["slug"],
        total_chunks=recon["actual_qdrant_points_count"],
        total_documents=recon["actual_documents_count"],
        additional_info={
            "elapsed_seconds": round(elapsed_total, 2),
            "tokenizer_version": TOKENIZER_VERSION,
            "qdrant_collection": qdrant_mgr.collection_name,
            "uploaded_chunks_this_run": total_indexed_points,
            "uploaded_documents_this_run": uploaded_documents,
            "reconciliation_status": recon["status"],
        },
    )

    print("\n" + "=" * 80)
    print(f"HOÀN THÀNH LẬP CHỈ MỤC: {total_indexed_points} chunks -> Collection '{qdrant_mgr.collection_name}'")
    print(f"Tổng thời gian: {elapsed_total:.2f} giây.")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline Vector Embedding & Sparse Indexing cho báo cáo tài chính."
    )
    parser.add_argument(
        "--model",
        type=str,
        default="bge-m3",
        choices=list(SUPPORTED_MODELS.keys()),
        help="Mô hình embedding (mặc định: bge-m3)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/processed_chunks"),
        help="Thư mục chứa các file JSON đã parse (mặc định: data/processed_chunks)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size cho forward model (mặc định: 32)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chạy kiểm tra cấu hình và tính toàn vẹn dữ liệu mà không gọi model",
    )
    parser.add_argument(
        "--benchmark-200",
        action="store_true",
        help="Đo đạc tốc độ thực tế trên 200 chunk đầu tiên rồi dừng lại",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Xóa tạo lại collection mới và tính toán lại vector",
    )
    parser.add_argument(
        "--reconcile-only",
        action="store_true",
        help="Kiểm tra đối chiếu số lượng giữa JSON và Qdrant",
    )
    parser.add_argument(
        "--qdrant-path",
        type=str,
        default="data/qdrant_local",
        help="Đường dẫn lưu trữ Qdrant cục bộ (mặc định: data/qdrant_local)",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default="",
        help="URL máy chủ Qdrant từ xa (nếu có, e.g. http://localhost:6333)",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Kết nối thẳng vào Qdrant Cloud (sử dụng QDRANT_ENDPOINT và QDRANT_API_KEY trong .env)",
    )
    parser.add_argument(
        "--start-from",
        type=str,
        default=None,
        help="Bỏ qua các tài liệu trước và bắt đầu upload từ doc_id hoặc số thứ tự (ví dụ: SSH_2023_Hopnhat hoặc 123)",
    )
    parser.add_argument("--index-version", default="v1")
    parser.add_argument("--parser-version", default="v2.1")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--reuse-cache-dir", type=Path)
    args = parser.parse_args()

    run_pipeline(
        input_dir=args.input_dir,
        model_name=args.model,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        benchmark_200=args.benchmark_200,
        rebuild=args.rebuild,
        reconcile_only=args.reconcile_only,
        qdrant_path=args.qdrant_path,
        qdrant_url=args.qdrant_url,
        use_cloud=args.cloud,
        start_from=args.start_from,
        index_version=args.index_version,
        parser_version=args.parser_version,
        cache_dir=args.cache_dir,
        reuse_cache_dir=args.reuse_cache_dir,
    )


if __name__ == "__main__":
    main()
