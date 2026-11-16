"""
Module định nghĩa các chỉ số đo lường hiệu năng Retrieval và Citation.
Phiên bản: v1.0

Các chỉ số Retrieval (trước khi có Writer):
1. Precision@k: Tỷ lệ chunk đúng trong top-k kết quả.
2. Context Precision@k: Đánh giá vị trí xếp hạng của chunk đúng (thưởng vị trí cao).
3. Recall@k: Tỷ lệ chunk đúng tìm thấy so với tổng số chunk bằng chứng cần thiết.
4. MRR (Mean Reciprocal Rank): Nghịch đảo của thứ hạng chunk đúng đầu tiên.

Các chỉ số Citation (sau khi Writer viết báo cáo):
1. Citation Validity: Định dạng trích dẫn [Doc_X, p.Y] có hợp lệ, Doc_X có tồn tại và trang Y có thực sự nằm trong tài liệu không.
2. Citation Precision: Trích dẫn đưa ra có thực sự chứa dữ kiện/bằng chứng cho câu khẳng định đi kèm hay không.
3. Citation Recall: Tỷ lệ câu có khẳng định số liệu/sự kiện kinh tế được gắn trích dẫn nguồn kiểm chứng.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np


# =============================================================================
# 1. RETRIEVAL EVALUATION METRICS
# =============================================================================

def hit_at_k(retrieved_ids: List[str], gold_ids: List[str], k: int = 10) -> float:
    """
    Tính Hit@k (Success@k):
    Trả về 1.0 nếu có ít nhất 1 chunk đúng nằm trong top-k, ngược lại 0.0.
    Nếu gold_ids rỗng (TRAP), trả về 1.0 nếu retrieved_ids rỗng, ngược lại 0.0.
    """
    if not gold_ids:
        return 1.0 if not retrieved_ids else 0.0
    top = retrieved_ids[:k]
    gold_set = set(gold_ids)
    return 1.0 if any(cid in gold_set for cid in top) else 0.0


def bootstrap_ci(
    data: List[float],
    num_samples: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """
    Tính khoảng tin cậy Bootstrap 95% (Percentile Bootstrap CI) cho giá trị trung bình.
    Trả về: (low, high, mean)
    """
    if not data:
        return (0.0, 0.0, 0.0)
    arr = np.array(data, dtype=float)
    mean_val = float(np.mean(arr))
    if len(arr) < 2:
        return (mean_val, mean_val, mean_val)

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(arr), size=(num_samples, len(arr)))
    boot_means = np.mean(arr[indices], axis=1)

    alpha = (1.0 - confidence_level) / 2.0
    low = float(np.percentile(boot_means, alpha * 100))
    high = float(np.percentile(boot_means, (1.0 - alpha) * 100))
    return (low, high, mean_val)

def precision_at_k(retrieved_ids: List[str], gold_ids: List[str], k: int = 10) -> float:
    """
    Tính Precision@k: Trong k chunk đầu, có bao nhiêu chunk là đúng (chứa bằng chứng).
    Precision@k = (số chunk đúng trong top-k) / k
    """
    if k <= 0:
        return 0.0
    top = retrieved_ids[:k]
    gold_set = set(gold_ids)
    hits = sum(1 for cid in top if cid in gold_set)
    return hits / k


def context_precision_at_k(retrieved_ids: List[str], gold_ids: List[str], k: int = 10) -> float:
    """
    Tính Context Precision@k:
    Đo lường xem các chunk đúng có được ưu tiên xếp ở thứ hạng trên cùng hay không.
    Công thức: Trung bình của Precision@i tại các vị trí i có chunk đúng, chia cho tổng số chunk đúng trong top-k.
    
    Nếu không có chunk đúng nào trong top-k -> trả về 0.0.
    """
    if k <= 0:
        return 0.0
    top = retrieved_ids[:k]
    gold_set = set(gold_ids)
    rel = [1 if cid in gold_set else 0 for cid in top]
    n_rel = sum(rel)
    if n_rel == 0:
        return 0.0

    hits = 0
    precision_sum = 0.0
    for i, is_relevant in enumerate(rel, start=1):
        if is_relevant:
            hits += 1
            precision_sum += hits / i

    return precision_sum / n_rel


def recall_at_k(retrieved_ids: List[str], gold_ids: List[str], k: int = 10) -> float:
    """
    Tính Recall@k:
    Trong tổng số các chunk bằng chứng cần thiết (gold_ids), hệ thống đã lấy được bao nhiêu chunk trong top-k.
    Recall@k = (số chunk đúng trong top-k) / len(gold_ids)
    """
    if not gold_ids:
        return 1.0  # Nếu câu hỏi không yêu cầu bằng chứng (bẫy out-of-domain), rỗng là đạt
    top = retrieved_ids[:k]
    gold_set = set(gold_ids)
    hits = len(set(top) & gold_set)
    return hits / len(gold_set)


def mrr(retrieved_ids: List[str], gold_ids: List[str]) -> float:
    """
    Tính Mean Reciprocal Rank (MRR):
    Nghịch đảo của vị trí xuất hiện của chunk đúng đầu tiên.
    MRR = 1 / rank_first_hit (nếu không có hit nào -> 0.0)
    """
    gold_set = set(gold_ids)
    for rank, cid in enumerate(retrieved_ids, start=1):
        if cid in gold_set:
            return 1.0 / rank
    return 0.0


def evaluate_retrieval_query(
    retrieved_ids: List[str],
    gold_ids: List[str],
    k_cutoffs: Tuple[int, ...] = (3, 5, 10),
) -> Dict[str, float]:
    """
    Tính toán trọn bộ chỉ số Retrieval cho một câu truy vấn tại các điểm cắt k khác nhau.
    """
    results: Dict[str, float] = {}
    for k in k_cutoffs:
        results[f"precision@{k}"] = precision_at_k(retrieved_ids, gold_ids, k=k)
        results[f"context_precision@{k}"] = context_precision_at_k(retrieved_ids, gold_ids, k=k)
        results[f"recall@{k}"] = recall_at_k(retrieved_ids, gold_ids, k=k)
        results[f"hit@{k}"] = hit_at_k(retrieved_ids, gold_ids, k=k)
    results["mrr"] = mrr(retrieved_ids, gold_ids)
    return results


# =============================================================================
# 2. CITATION EVALUATION METRICS (Sau khi Writer Agent viết báo cáo)
# =============================================================================

RE_CITATION_TAG = re.compile(r"\[([A-Za-z0-9_]+)[,\s\-]+(?:trang\s*số|trang|p)?\.?\s*(\d+)(?:\s*[-–]\s*(\d+))?\]", re.IGNORECASE)
RE_CLAIM_WITH_NUMBERS = re.compile(r"(?:\d{1,3}(?:\.\d{3})+|\b\d+[\.,]\d+\s*%|\b\d+\s*tỷ\b|\b\d+\s*triệu\b)", re.IGNORECASE)


class CitationEvaluator:
    """
    Kiểm tra và đánh giá độ chính xác của trích dẫn học thuật trong báo cáo do Writer Agent sinh ra.
    """

    def __init__(self, doc_page_catalog: Dict[str, Set[int]]) -> None:
        """
        doc_page_catalog: Mapping {doc_id: set_of_valid_physical_pages}
        Ví dụ: {"FPT_2024_Hopnhat": {1, 2, ..., 85}}
        """
        self.doc_page_catalog = doc_page_catalog

    def extract_citations_from_text(self, text: str) -> List[Tuple[str, int, str]]:
        """
        Trích xuất tất cả các tag trích dẫn dạng [Doc_X, p.Y] hoặc [FPT_2024_Hopnhat, p.10].
        Trả về list of (doc_id, page_number, raw_matched_tag).
        Với khoảng trang, page_number là trang đầu; raw_matched_tag giữ cả khoảng.
        """
        matches = []
        for m in RE_CITATION_TAG.finditer(text):
            doc_id_raw = m.group(1).strip()
            page_str = m.group(2).strip()
            raw_tag = m.group(0)
            try:
                page_num = int(page_str)
                matches.append((doc_id_raw, page_num, raw_tag))
            except ValueError:
                continue
        return matches

    def check_citation_validity(self, text: str) -> Dict[str, Any]:
        """
        Chỉ số 1: Citation Validity (Tính hợp lệ của trích dẫn)
        - Doc_X có tồn tại trong hệ thống tài liệu hay không?
        - Trang p.Y có thực sự nằm trong các trang của tài liệu đó không?
        """
        citations = self.extract_citations_from_text(text)
        if not citations:
            return {
                "total_citations": 0,
                "valid_citations": 0,
                "invalid_citations": 0,
                "validity_rate": 1.0,
                "errors": [],
            }

        valid_count = 0
        errors = []

        for doc_id, page_num, raw_tag in citations:
            # Chuẩn hóa tiền tố, sau đó so khớp chính xác cả năm và phạm vi.
            normalized_id = doc_id.lower().removeprefix("doc_")
            matching_docs = [cat_doc for cat_doc in self.doc_page_catalog
                             if cat_doc.lower().removeprefix("doc_") == normalized_id]
            matched_doc = matching_docs[0] if len(matching_docs) == 1 else None

            if not matched_doc:
                errors.append(f"Tài liệu không tồn tại: '{doc_id}' trong trích dẫn '{raw_tag}'")
                continue

            # 2. Kiểm tra số trang
            valid_pages = self.doc_page_catalog[matched_doc]
            end_page = int(RE_CITATION_TAG.fullmatch(raw_tag).group(3) or page_num)
            # Đếm các trang có thật, không tạo range lớn từ đầu vào không tin cậy.
            pages_present = sum(page_num <= page <= end_page for page in valid_pages)
            if page_num < 1 or end_page < page_num or pages_present != end_page - page_num + 1:
                errors.append(
                    f"Trang/khoảng trang {page_num}-{end_page} không hợp lệ trong tài liệu '{matched_doc}'"
                )
                continue

            valid_count += 1

        total = len(citations)
        return {
            "total_citations": total,
            "valid_citations": valid_count,
            "invalid_citations": total - valid_count,
            "validity_rate": valid_count / total if total > 0 else 1.0,
            "errors": errors,
        }

    def check_citation_recall(self, sentences: List[str]) -> Dict[str, Any]:
        """
        Chỉ số 2: Citation Recall (Độ bao phủ trích dẫn của các câu chứa số liệu)
        Trong các câu văn có khẳng định số liệu kế toán hoặc tỷ lệ %, bao nhiêu câu có trích dẫn kèm theo?
        """
        claim_sentences = []
        cited_claims = []
        uncited_claims = []

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            # Kiểm tra câu có chứa số liệu kế toán hoặc phần trăm
            has_number_claim = bool(RE_CLAIM_WITH_NUMBERS.search(s_clean))
            if has_number_claim:
                claim_sentences.append(s_clean)
                has_tag = bool(RE_CITATION_TAG.search(s_clean))
                if has_tag:
                    cited_claims.append(s_clean)
                else:
                    uncited_claims.append(s_clean)

        total_claims = len(claim_sentences)
        recall = len(cited_claims) / total_claims if total_claims > 0 else 1.0

        return {
            "total_numeric_claims": total_claims,
            "cited_claims_count": len(cited_claims),
            "uncited_claims_count": len(uncited_claims),
            "citation_recall": recall,
            "uncited_samples": uncited_claims[:5],
        }

    def check_citation_precision(
        self,
        claim_with_tag: str,
        cited_chunk_text: str,
    ) -> bool:
        """
        Chỉ số 3: Citation Precision (Độ xác thực của trích dẫn)
        Kiểm tra xem chunk được trích dẫn có thực sự chứa các con số/từ khóa quan trọng trong câu khẳng định hay không.
        """
        # Trích xuất các số tiền hoặc % trong câu claim
        numbers = re.findall(r"\b\d{1,3}(?:\.\d{3})+\b|\b\d+[\.,]\d+\b", claim_with_tag)
        if not numbers:
            # Nếu không có số, so khớp các từ khóa chính
            words = [w for w in re.findall(r"[A-Za-zÀ-ỹ]{4,}", claim_with_tag.lower()) if len(w) > 3]
            match_hits = sum(1 for w in words if w in cited_chunk_text.lower())
            return (match_hits / len(words)) >= 0.5 if words else True

        # Nếu có số liệu, ít nhất 1 con số cốt lõi phải xuất hiện trong cited_chunk_text
        found_num = any(num in cited_chunk_text for num in numbers)
        return found_num
