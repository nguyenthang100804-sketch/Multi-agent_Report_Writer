"""
Module Cross-Encoder Reranker cho Báo cáo Tài chính Việt Nam.
Sử dụng mô hình BAAI/bge-reranker-v2-m3 để tái xếp hạng (Rerank)
tập ứng viên Top-K sinh ra từ Hybrid Retrieval (Dense + BM25).
Phiên bản: v1.0
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

DEFAULT_LOCAL_RERANKER_PATH = ROOT_DIR / "models" / "bge-reranker-v2-m3"
DEFAULT_HF_RERANKER_NAME = "BAAI/bge-reranker-v2-m3"


class FinancialCrossEncoderReranker:
    """
    Cross-Encoder Reranker chấm điểm tương quan toàn diện theo cặp (Query, Full_Chunk_Text).
    Sử dụng bge-reranker-v2-m3 với Full Text (max_length=1024), hỗ trợ tăng tốc GPU (CUDA FP16).
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: Optional[str] = None,
        max_length: int = 1024,
        batch_size: Optional[int] = None,
        use_fp16: bool = True,
    ) -> None:
        if model_path:
            self.model_path = model_path
        elif DEFAULT_LOCAL_RERANKER_PATH.exists() and (DEFAULT_LOCAL_RERANKER_PATH / "config.json").exists():
            self.model_path = str(DEFAULT_LOCAL_RERANKER_PATH)
        else:
            self.model_path = DEFAULT_HF_RERANKER_NAME

        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.max_length = max_length

        if self.device == "cuda":
            self.batch_size = batch_size or 32
            gpu_name = torch.cuda.get_device_name(0)
            print(f"[Reranker] Đang nạp mô hình từ '{self.model_path}' lên GPU ({gpu_name}) - max_length={self.max_length}, batch_size={self.batch_size}...")
        else:
            self.batch_size = batch_size or 16
            num_threads = min(8, os.cpu_count() or 4)
            torch.set_num_threads(num_threads)
            print(f"[Reranker] Đang nạp mô hình từ '{self.model_path}' lên CPU (threads={num_threads}) - max_length={self.max_length}, batch_size={self.batch_size}...")

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_path)
        self.model.to(self.device)

        if self.device == "cuda" and use_fp16:
            self.model.half()
            print("[Reranker] Đã kích hoạt chế độ tính toán FP16 Half Precision trên GPU.")

        self.model.eval()
        print(f"[Reranker] Đã nạp thành công Cross-Encoder Reranker (Full Text Mode).")

    def compute_scores(
        self,
        query: str,
        texts: List[str],
    ) -> List[float]:
        """Tính điểm tương quan logit cho danh sách văn bản đối với câu hỏi trên Full Text."""
        if not texts:
            return []

        all_scores: List[float] = []
        # Chấm điểm trực tiếp trên FULL TEXT trọn vẹn, không cắt bỏ ký tự nào
        pairs = [[query, txt] for txt in texts]

        for i in range(0, len(pairs), self.batch_size):
            batch_pairs = pairs[i : i + self.batch_size]
            with torch.no_grad():
                inputs = self.tokenizer(
                    batch_pairs,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                ).to(self.device)

                logits = self.model(**inputs, return_dict=True).logits.view(-1).float()
                all_scores.extend(logits.cpu().tolist())

        return all_scores

    def rerank(
        self,
        query: str,
        candidate_chunks: List[Dict[str, Any]],
        top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        """
        Tái xếp hạng danh sách ứng viên (mỗi ứng viên là dict chứa 'chunk_id' và 'text').
        Trả về danh sách top_k tuple (chunk_id, score) sắp xếp giảm dần theo điểm số.
        """
        if not candidate_chunks:
            return []

        texts = [c.get("text", "") for c in candidate_chunks]
        scores = self.compute_scores(query, texts)

        scored_candidates = []
        for c, score in zip(candidate_chunks, scores):
            scored_candidates.append((c["chunk_id"], float(score)))

        # Sắp xếp giảm dần theo điểm tương quan
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        return scored_candidates[:top_k]
