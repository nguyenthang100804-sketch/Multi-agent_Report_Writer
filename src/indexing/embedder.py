"""
Module Vector Embedding chuyên biệt cho báo cáo tài chính Việt Nam.
Hỗ trợ:
- Đa mô hình: BAAI/bge-m3 (1024-dim) và intfloat/multilingual-e5-base / multilingual-e5-large.
- Length-sorted batching: Tối ưu hóa padding khi forward model.
- Vector Parquet Cache theo từng file tài liệu, kèm SHA-256 content_hash.
- Checkpointing & Khả năng tiếp tục (Resumability) khi bị ngắt.
- Chuẩn hóa Cosine (L2 normalize) và lưu trữ metadata vector.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

EMBEDDER_VERSION = "v1.0"

SUPPORTED_MODELS: Dict[str, Dict[str, Any]] = {
    "bge-m3": {
        "model_id": "BAAI/bge-m3",
        "slug": "bge_m3",
        "dimension": 1024,
        "max_seq_length": 1024,
        "prefix_passage": "",
        "prefix_query": "",
        "distance": "Cosine",
        "normalize_embeddings": True,
    },
    "multilingual-e5-base": {
        "model_id": "intfloat/multilingual-e5-base",
        "slug": "e5_base",
        "dimension": 768,
        "max_seq_length": 512,
        "prefix_passage": "passage: ",
        "prefix_query": "query: ",
        "distance": "Cosine",
        "normalize_embeddings": True,
    },
    "multilingual-e5-large": {
        "model_id": "intfloat/multilingual-e5-large",
        "slug": "e5_large",
        "dimension": 1024,
        "max_seq_length": 512,
        "prefix_passage": "passage: ",
        "prefix_query": "query: ",
        "distance": "Cosine",
        "normalize_embeddings": True,
    },
}


class DocumentEmbedder:
    """
    Trình quản lý và tính toán Vector Dense Embedding có checkpointing và cache.
    """

    def __init__(
        self,
        model_name: str = "bge-m3",
        cache_dir: Optional[Path] = None,
        reuse_cache_dir: Optional[Path] = None,
        batch_size: int = 32,
        device: Optional[str] = None,
    ) -> None:
        if model_name not in SUPPORTED_MODELS:
            raise ValueError(
                f"Model '{model_name}' không được hỗ trợ. Các model khả dụng: {list(SUPPORTED_MODELS.keys())}"
            )
        self.config = SUPPORTED_MODELS[model_name]
        self.model_name = model_name
        self.model_slug = self.config["slug"]
        self.dimension = self.config["dimension"]
        self.max_seq_length = self.config["max_seq_length"]
        self.prefix_passage = self.config["prefix_passage"]
        self.prefix_query = self.config["prefix_query"]
        self.batch_size = batch_size

        self.cache_dir = cache_dir or Path(f"data/vector_cache/{self.model_slug}")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file = self.cache_dir / "_checkpoint.json"
        self.reuse_cache_dir = Path(reuse_cache_dir) if reuse_cache_dir else None
        self._reuse_vectors: Optional[Dict[str, np.ndarray]] = None

        self.device = device
        self._model = None
        self._tokenizer = None

    def _lazy_load_model(self) -> None:
        """Khởi tạo mô hình Transformer khi có yêu cầu tính toán thực tế."""
        if self._model is not None:
            return

        import torch
        from transformers import AutoModel, AutoTokenizer

        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Ưu tiên nạp từ thư mục local models/<model_name> nếu người dùng đã tải thủ công về
        local_candidates = [
            Path(__file__).resolve().parents[2] / "models" / self.model_name,
            Path("models") / self.model_name,
            Path("models") / self.model_slug,
            Path("models/bge-m3"),
        ]
        model_path = self.config["model_id"]
        for cand in local_candidates:
            if cand.exists() and (cand / "config.json").exists():
                model_path = str(cand.resolve())
                break

        print(f"[{self.model_name}] Đang nạp mô hình từ {model_path} lên thiết bị {self.device}...")
        self._tokenizer = AutoTokenizer.from_pretrained(model_path)
        self._model = AutoModel.from_pretrained(model_path)
        self._model.to(self.device)
        self._model.eval()

    def compute_content_hash(self, text: str) -> str:
        """Tính SHA-256 hash của văn bản để phát hiện thay đổi nội dung."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_checkpoint(self) -> Dict[str, Any]:
        """Đọc trạng thái checkpoint hiện tại."""
        if self.checkpoint_file.exists():
            try:
                return json.loads(self.checkpoint_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "completed_docs": [],
            "last_updated": None,
        }

    def update_checkpoint(self, doc_id: str) -> None:
        """Ghi nhận tài liệu đã hoàn thành vào checkpoint."""
        ckpt = self.get_checkpoint()
        if doc_id not in ckpt["completed_docs"]:
            ckpt["completed_docs"].append(doc_id)
        ckpt["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.checkpoint_file.write_text(json.dumps(ckpt, indent=2, ensure_ascii=False), encoding="utf-8")

    def _embed_batch_sorted(self, texts: List[str]) -> np.ndarray:
        """
        Thực hiện embedding theo lô có sắp xếp độ dài (Length-sorted batching)
        để giảm lượng token đệm (padding) lãng phí trên GPU/CPU.
        """
        import torch

        self._lazy_load_model()
        n = len(texts)
        if n == 0:
            return np.empty((0, self.dimension), dtype=np.float32)

        # Thêm tiền tố theo quy chuẩn mô hình (nếu có, ví dụ "passage: " cho e5)
        prefixed_texts = [f"{self.prefix_passage}{t}" for t in texts]

        # 1. Sắp xếp theo độ dài ký tự
        sorted_indices = sorted(range(n), key=lambda i: len(prefixed_texts[i]))
        sorted_texts = [prefixed_texts[i] for i in sorted_indices]

        all_embeddings: List[np.ndarray] = []

        # 2. Forward model theo từng mini-batch
        for start_idx in range(0, n, self.batch_size):
            batch_slice = sorted_texts[start_idx : start_idx + self.batch_size]
            encoded = self._tokenizer(
                batch_slice,
                padding=True,
                truncation=True,
                max_length=self.max_seq_length,
                return_tensors="pt",
            ).to(self.device)

            with torch.no_grad():
                outputs = self._model(**encoded)
                # Mean pooling hoặc CLS token tùy kiến trúc
                if hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
                    batch_vecs = outputs.pooler_output
                else:
                    # Mean pooling với attention mask
                    mask = encoded["attention_mask"].unsqueeze(-1).expand(outputs.last_hidden_state.size()).float()
                    sum_embeddings = torch.sum(outputs.last_hidden_state * mask, 1)
                    sum_mask = torch.clamp(mask.sum(1), min=1e-9)
                    batch_vecs = sum_embeddings / sum_mask

                # Chuẩn hóa L2 (Cosine similarity)
                if self.config["normalize_embeddings"]:
                    batch_vecs = torch.nn.functional.normalize(batch_vecs, p=2, dim=1)

                all_embeddings.append(batch_vecs.cpu().numpy().astype(np.float32))

        stacked = np.vstack(all_embeddings)

        # 3. Phục hồi thứ tự ban đầu
        original_order = np.empty_like(stacked)
        for sorted_pos, orig_pos in enumerate(sorted_indices):
            original_order[orig_pos] = stacked[sorted_pos]

        return original_order

    def embed_document_chunks(
        self,
        doc_id: str,
        chunks: List[Dict[str, Any]],
        force_recompute: bool = False,
    ) -> Tuple[np.ndarray, List[str]]:
        """
        Tính toán hoặc nạp từ cache vector embedding cho tất cả chunk của một tài liệu.
        Trả về (embeddings_matrix, list_content_hashes).
        """
        parquet_path = self.cache_dir / f"{doc_id}.parquet"
        content_hashes = [self.compute_content_hash(c.get("embed_text", c.get("text", ""))) for c in chunks]

        # Kiểm tra cache
        if parquet_path.exists() and not force_recompute:
            try:
                df = pd.read_parquet(parquet_path)
                cached_hashes = df["content_hash"].tolist()
                if cached_hashes == content_hashes:
                    vectors = np.vstack(df["embedding"].to_numpy())
                    return vectors, content_hashes
            except Exception:
                pass

        if self.reuse_cache_dir is not None and not force_recompute:
            if self._reuse_vectors is None:
                self._reuse_vectors = {}
                for source in sorted(self.reuse_cache_dir.glob("*.parquet")):
                    cached = pd.read_parquet(source, columns=["content_hash", "embedding"])
                    for content_hash, vector in zip(cached["content_hash"], cached["embedding"]):
                        self._reuse_vectors.setdefault(content_hash, vector)
            missing = {}
            for content_hash, chunk in zip(content_hashes, chunks):
                if content_hash not in self._reuse_vectors:
                    missing.setdefault(content_hash, chunk.get("embed_text") or chunk.get("text", ""))
            if missing:
                new_vectors = self._embed_batch_sorted(list(missing.values()))
                self._reuse_vectors.update(zip(missing, new_vectors))
            vectors = np.vstack([self._reuse_vectors[h] for h in content_hashes])
            df_save = pd.DataFrame({
                "chunk_id": [c["chunk_id"] for c in chunks],
                "doc_id": doc_id,
                "content_hash": content_hashes,
                "embedding": list(vectors),
            })
            df_save.to_parquet(parquet_path, index=False)
            self.update_checkpoint(doc_id)
            return vectors, content_hashes

        # Tính toán embedding mới
        texts_to_embed = [c.get("embed_text") or c.get("text", "") for c in chunks]
        vectors = self._embed_batch_sorted(texts_to_embed)

        # Lưu vector vào Parquet
        chunk_ids = [c["chunk_id"] for c in chunks]
        df_save = pd.DataFrame(
            {
                "chunk_id": chunk_ids,
                "doc_id": doc_id,
                "content_hash": content_hashes,
                "embedding": list(vectors),
            }
        )
        df_save.to_parquet(parquet_path, index=False)
        self.update_checkpoint(doc_id)

        return vectors, content_hashes

    def benchmark_speed(self, sample_chunks: List[Dict[str, Any]], sample_size: int = 200) -> Dict[str, Any]:
        """
        Đo đạc tốc độ suy luận thực tế trên 200 chunk đầu tiên trước khi chạy toàn bộ corpus.
        Ước lượng thời gian hoàn thành và thông lượng (tokens/sec, chunks/sec).
        """
        sample = sample_chunks[:sample_size]
        texts = [c.get("embed_text") or c.get("text", "") for c in sample]
        self._lazy_load_model()

        # Đếm tổng token
        total_tokens = sum(len(self._tokenizer.encode(t, add_special_tokens=False)) for t in texts)

        # Chạy warm up 5 chunk
        _ = self._embed_batch_sorted(texts[:min(5, len(texts))])

        t0 = time.perf_counter()
        _ = self._embed_batch_sorted(texts)
        elapsed = time.perf_counter() - t0

        chunks_per_sec = len(texts) / elapsed if elapsed > 0 else 0
        tokens_per_sec = total_tokens / elapsed if elapsed > 0 else 0

        # Ước lượng cho 30.000 chunk (khoảng 6.000.000 tokens)
        estimated_total_seconds = (30000 / chunks_per_sec) if chunks_per_sec > 0 else 0

        return {
            "model_name": self.model_name,
            "device": str(self.device),
            "sample_chunks_count": len(texts),
            "sample_total_tokens": total_tokens,
            "elapsed_seconds": round(elapsed, 2),
            "chunks_per_second": round(chunks_per_sec, 2),
            "tokens_per_second": round(tokens_per_sec, 2),
            "estimated_full_corpus_minutes": round(estimated_total_seconds / 60, 2),
            "estimated_full_corpus_hours": round(estimated_total_seconds / 3600, 2),
        }
