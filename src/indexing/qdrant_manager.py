"""
Module quản lý chỉ mục Qdrant Vector & Payload Index cho báo cáo tài chính Việt Nam.
Phiên bản: v1.0

Tuân thủ nghiêm ngặt các nguyên tắc:
1. Versioned Collection: vnfin_v1_<model_slug>_<embedtext_version>. Không sửa tại chỗ (Immutable).
2. Manifest đầy đủ: Lưu parser_version, model, embedtext_version, ngày chạy, tổng số chunk, dim, metric.
3. Point ID qua uuid5(NAMESPACE_URL, chunk_id) đảm bảo idempotency và tính lặp lại 100%.
4. Payload Indexes cho các trường bộ lọc cứng: ticker, fiscal_year, scope, section, chunk_type.
5. Đối chiếu số lượng (Reconciliation): Kiểm tra tính nhất quán giữa JSON, Parquet và Qdrant.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

QDRANT_MANAGER_VERSION = "v1.0"
EMBED_TEXT_VERSION = "v1"


def load_env_variables() -> Dict[str, str]:
    """Đọc file .env nếu tồn tại ở project root mà không cần thư viện ngoài."""
    env_vars: Dict[str, str] = {}
    candidates = [Path(".env"), Path(__file__).resolve().parent.parent.parent / ".env"]
    for p in candidates:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    val = v.strip().strip('"').strip("'")
                    key = k.strip()
                    env_vars[key] = val
                    if key not in os.environ:
                        os.environ[key] = val
            break
    return env_vars


def generate_point_id(chunk_id: str) -> str:
    """Sinh Point ID dạng UUID v5 chuẩn xác từ chunk_id qua NAMESPACE_URL."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantIndexManager:
    """
    Quản lý tạo collection, đánh chỉ mục payload và tải vector lên Qdrant Vector Database (Local & Cloud).
    """

    def __init__(
        self,
        model_slug: str = "bge_m3",
        dimension: int = 1024,
        distance_metric: str = "Cosine",
        embed_text_version: str = EMBED_TEXT_VERSION,
        index_version: str = "v1",
        qdrant_url: Optional[str] = None,
        api_key: Optional[str] = None,
        qdrant_path: Optional[str] = None,
        use_cloud: bool = False,
        prefer_grpc: bool = False,
    ) -> None:
        self.model_slug = model_slug
        self.dimension = dimension
        self.distance_metric = distance_metric
        self.embed_text_version = embed_text_version
        self.collection_name = f"vnfin_{index_version}_{model_slug}_{embed_text_version}"

        load_env_variables()
        self.use_cloud = use_cloud or bool(qdrant_url)
        if self.use_cloud:
            self.qdrant_url = qdrant_url or os.getenv("QDRANT_ENDPOINT") or os.getenv("QDRANT_URL")
            self.api_key = api_key or os.getenv("QDRANT_API_KEY")
            self.qdrant_path = None
        else:
            self.qdrant_url = None
            self.api_key = None
            self.qdrant_path = qdrant_path or "data/qdrant_local"
        self.prefer_grpc = prefer_grpc

        self._client = None

    def get_client(self):
        """Khởi tạo kết nối QdrantClient (hỗ trợ cả Qdrant Cloud và Local path)."""
        if self._client is not None:
            return self._client

        from qdrant_client import QdrantClient

        if self.qdrant_url:
            print(f"[Qdrant] Kết nối tới Qdrant Cloud: {self.qdrant_url} (timeout=60s)...")
            self._client = QdrantClient(
                url=self.qdrant_url,
                api_key=self.api_key,
                timeout=60.0,
                prefer_grpc=self.prefer_grpc,
            )
        else:
            print(f"[Qdrant] Chạy Qdrant Local Mode tại: {self.qdrant_path}...")
            Path(self.qdrant_path).mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=self.qdrant_path)

        return self._client

    def create_versioned_collection(self, recreate_if_exists: bool = False) -> None:
        """
        Khởi tạo Collection có phiên bản.
        Không sửa collection đang chạy; nếu recreate_if_exists=True thì xóa tạo mới.
        Đồng thời tạo đầy đủ Payload Indexes cho các trường bộ lọc Planner.
        """
        from qdrant_client.http import models as qmodels

        client = self.get_client()
        collections = [c.name for c in client.get_collections().collections]

        if self.collection_name in collections:
            if not recreate_if_exists:
                print(f"[Qdrant] Collection '{self.collection_name}' đã tồn tại. Giữ nguyên theo nguyên tắc bất biến.")
                return
            print(f"[Qdrant] Xóa collection cũ '{self.collection_name}' để tạo mới...")
            client.delete_collection(self.collection_name)

        distance_map = {
            "Cosine": qmodels.Distance.COSINE,
            "Dot": qmodels.Distance.DOT,
            "Euclid": qmodels.Distance.EUCLID,
        }
        dist = distance_map.get(self.distance_metric, qmodels.Distance.COSINE)

        print(f"[Qdrant] Đang tạo collection '{self.collection_name}' (dim={self.dimension}, metric={self.distance_metric})...")
        client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(size=self.dimension, distance=dist),
        )

        # Tạo Payload Indexes cho các trường lọc siêu dữ liệu cứng
        filter_indexes = [
            ("ticker", qmodels.PayloadSchemaType.KEYWORD),
            ("fiscal_year", qmodels.PayloadSchemaType.INTEGER),
            ("scope", qmodels.PayloadSchemaType.KEYWORD),
            ("section", qmodels.PayloadSchemaType.KEYWORD),
            ("chunk_type", qmodels.PayloadSchemaType.KEYWORD),
            ("doc_id", qmodels.PayloadSchemaType.KEYWORD),
        ]

        for field_name, schema_type in filter_indexes:
            client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=schema_type,
            )
        print(f"[Qdrant] Đã tạo thành công {len(filter_indexes)} Payload Indexes cho collection '{self.collection_name}'.")

    def build_point_payload(
        self,
        chunk: Dict[str, Any],
        doc_meta: Dict[str, Any],
        content_hash: str,
        chunk_index: int,
    ) -> Dict[str, Any]:
        """
        Xây dựng Payload lưu trong Qdrant Point theo nguyên tắc F.
        Lưu toàn văn `text` để Writer đọc, không làm loãng vector embedding.
        """
        return {
            "chunk_id": chunk["chunk_id"],
            "doc_id": doc_meta.get("doc_id", ""),
            "ticker": doc_meta.get("ticker", ""),
            "fiscal_year": int(doc_meta.get("fiscal_year", 0)),
            "scope": doc_meta.get("scope", "consolidated"),
            "section": chunk.get("section", "UNKNOWN"),
            "section_title": chunk.get("section_title", ""),
            "chunk_type": chunk.get("chunk_type", "text"),
            "unit": chunk.get("unit", doc_meta.get("default_unit", "VND")),
            "physical_pages": chunk.get("physical_pages", []),
            "citation_tag": chunk.get("citation_tag", ""),
            "chunk_index": chunk_index,
            "content_hash": content_hash,
            "text": chunk.get("text", ""),  # Payload gốc đầy đủ số cho Writer và Citation
            "embed_text": chunk.get("embed_text", ""),
            "table_rows_count": len(chunk.get("table_rows", [])) if chunk.get("chunk_type") == "table" else 0,
        }

    def upload_document_points(
        self,
        chunks: List[Dict[str, Any]],
        doc_meta: Dict[str, Any],
        embeddings: np.ndarray,
        content_hashes: List[str],
        batch_size: int = 64,
    ) -> int:
        """
        Tải các points của một tài liệu lên Qdrant theo từng mini-batch.
        Hỗ trợ retry tự động khi mạng quốc tế bị timeout.
        ID của điểm được sinh bằng uuid5 từ chunk_id.
        """
        from qdrant_client.http import models as qmodels

        client = self.get_client()
        points: List[qmodels.PointStruct] = []

        for idx, (chunk, hash_val) in enumerate(zip(chunks, content_hashes)):
            pt_id = generate_point_id(chunk["chunk_id"])
            payload = self.build_point_payload(
                chunk=chunk,
                doc_meta=doc_meta,
                content_hash=hash_val,
                chunk_index=idx,
            )
            vec = embeddings[idx].tolist()
            points.append(qmodels.PointStruct(id=pt_id, vector=vec, payload=payload))

        # Upload theo batch kèm retry thông minh khi gặp sự cố mạng
        total_uploaded = 0
        backoff_delays = [3, 6, 12, 20, 30]
        max_retries = len(backoff_delays)

        for i in range(0, len(points), batch_size):
            slice_pts = points[i : i + batch_size]
            for attempt in range(1, max_retries + 1):
                try:
                    client.upsert(collection_name=self.collection_name, points=slice_pts)
                    total_uploaded += len(slice_pts)
                    break
                except Exception as e:
                    if attempt < max_retries:
                        wait_sec = backoff_delays[attempt - 1]
                        print(f"    [Retry {attempt}/{max_retries}] Lỗi kết nối Cloud ({e}), tạm nghỉ {wait_sec}s rồi tự động thử lại...")
                        time.sleep(wait_sec)
                    else:
                        print(f"    [Lỗi] Không thể tải batch {i}-{i+len(slice_pts)} sau {max_retries} lần thử: {e}")
                        raise e

        return total_uploaded

    def save_manifest(
        self,
        output_dir: Path,
        parser_version: str,
        model_name: str,
        model_version: str,
        total_chunks: int,
        total_documents: int,
        additional_info: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Ghi file manifest.json cho collection theo nguyên tắc A (Nguyên tắc 3).
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / f"manifest_{self.collection_name}.json"

        manifest_data = {
            "collection_name": self.collection_name,
            "parser_version": parser_version,
            "embed_text_version": self.embed_text_version,
            "model_name": model_name,
            "model_slug": self.model_slug,
            "model_version": model_version,
            "dimension": self.dimension,
            "distance_metric": self.distance_metric,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "total_chunks_indexed": total_chunks,
            "total_documents_indexed": total_documents,
            "metadata": additional_info or {},
        }

        manifest_path.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[Manifest] Đã lưu file kê khai chỉ mục tại: {manifest_path}")
        return manifest_path

    def reconcile_counts(
        self,
        expected_chunks_count: int,
        expected_docs_count: int,
        expected_chunk_ids: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Đối chiếu số points, số tài liệu và tính duy nhất của chunk_id.
        Nếu có expected_chunk_ids, kiểm tra cả tập ID thay vì chỉ số lượng.
        Chỉ đọc metadata, không tải vector hay nội dung văn bản.
        """
        client = self.get_client()
        col_info = client.get_collection(self.collection_name)
        actual_points = col_info.points_count

        doc_ids = set()
        chunk_ids = set()
        missing_metadata = False
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=self.collection_name, limit=1024, offset=offset,
                with_payload=["doc_id", "chunk_id"], with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                if not payload.get("doc_id") or not payload.get("chunk_id"):
                    missing_metadata = True
                else:
                    doc_ids.add(payload["doc_id"])
                    chunk_ids.add(payload["chunk_id"])
            if offset is None:
                break

        passed_count = (actual_points == expected_chunks_count
                        and len(doc_ids) == expected_docs_count
                        and len(chunk_ids) == actual_points and not missing_metadata)
        ids_match = expected_chunk_ids is None or chunk_ids == expected_chunk_ids

        return {
            "collection_name": self.collection_name,
            "expected_chunks_count": expected_chunks_count,
            "actual_qdrant_points_count": actual_points,
            "expected_docs_count": expected_docs_count,
            "actual_documents_count": len(doc_ids),
            "chunk_ids_match": ids_match,
            "count_matches": passed_count,
            "status": "PASSED" if passed_count and ids_match else "MISMATCH",
        }
