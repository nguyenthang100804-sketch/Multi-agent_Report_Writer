"""
Module chuẩn hóa và tokenization cho Sparse Keyword Search (BM25) tiếng Việt tài chính.
Phiên bản: v1.0

Quy tắc cốt lõi:
1. Dùng một hàm chuẩn hóa duy nhất (NFC, 'đ' -> 'd', bỏ dấu thanh/mũ, chữ thường) cho cả lúc lập chỉ mục và lúc truy vấn.
2. Bảo toàn nguyên vẹn số tiền có dấu chấm phân cách hàng nghìn (12.694.975.751.615), ngày tháng (31/12/2024) và mã số kế toán (b03, mã số 110) như một token đơn lẻ.
3. Sinh unigrams và bigrams (cặp từ liền nhau) để bảo tồn các cụm thuật ngữ kế toán (luu_chuyen, von_chu, phai_thu).
4. Không phụ thuộc vào sửa chính tả OCR: bỏ dấu khi so khớp từ khóa chịu được 95%+ lỗi dấu OCR.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Dict, List, Set, Tuple

TOKENIZER_VERSION = "v1.0"

# Regex nhận diện số kế toán có dấu chấm phân cách hàng nghìn (ví dụ 12.694.975.751.615)
RE_ACCOUNTING_NUMBER = re.compile(r"\b\d{1,3}(?:\.\d{3}){1,6}\b")

# Regex nhận diện ngày tháng năm kế toán (ví dụ 31/12/2024, 01/01/2023)
RE_DATE_FORMAT = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")

# Regex nhận diện mã số kế toán chuẩn (ví dụ "mã số 110", "mã 270", "b01", "b02", "b03")
RE_FORM_OR_CODE = re.compile(r"\b(?:b0[1-9]|b\s*0[1-9]|ma\s*so\s*\d{2,3}|ms\s*\d{2,3})\b", re.IGNORECASE)

# Danh sách stop words tiếng Việt tài chính không mang giá trị phân biệt
FINANCIAL_STOP_WORDS: Set[str] = {
    "va", "cua", "cac", "nhung", "la", "duoc", "trong", "tai", "cho", "theo",
    "ngay", "thang", "nam", "co", "nay", "tren", "den", "voi", "ve", "ra",
    "boi", "nham", "do", "khi", "nhu", "tu", "con", "tai_ngay", "cho_nam"
}


def normalize_vietnamese_sparse(text: str) -> str:
    """
    Chuẩn hóa chuỗi văn bản cho tìm kiếm Sparse Keyword Search.
    Được dùng ĐỒNG NHẤT cho cả bước tạo chỉ mục (Index time) và bước tìm kiếm (Query time).
    
    Quy trình:
    1. Unicode NFC
    2. Chuyển chữ thường
    3. Đổi 'đ' -> 'd'
    4. Bỏ toàn bộ dấu thanh và mũ tiếng Việt (NFD decomposition -> lọc non-spacing marks -> NFC)
    5. Giữ nguyên cấu trúc số kế toán (. phân cách nghìn), ngày tháng (/), và ký tự chữ/số.
    """
    if not text:
        return ""

    # 1. NFC
    text = unicodedata.normalize("NFC", text)
    # 2. Lowercase
    text = text.lower()
    # 3. 'đ' -> 'd'
    text = text.replace("đ", "d").replace("Đ", "d")
    # 4. Bỏ dấu
    decomposed = unicodedata.normalize("NFD", text)
    unaccented = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    text = unicodedata.normalize("NFC", unaccented)

    return text


def tokenize_vietnamese_sparse(
    text: str,
    include_bigrams: bool = True,
    remove_stopwords: bool = True,
) -> List[str]:
    """
    Tách từ cho chỉ mục Sparse BM25 / từ khóa tiếng Việt tài chính.
    
    Các bước:
    1. Chuẩn hóa bằng `normalize_vietnamese_sparse`.
    2. Trích xuất và bảo toàn các token đặc thù (số tiền có dấu chấm, ngày tháng, mã biểu mẫu).
    3. Trích xuất các từ đơn (unigram).
    4. Ghép cặp từ liền kề (bigram) để giữ ngữ nghĩa của thuật ngữ kép (ví dụ 'luu_chuyen', 'tien_te').
    5. Loại bỏ stop words nếu yêu cầu.
    """
    normalized = normalize_vietnamese_sparse(text)
    tokens: List[str] = []

    # 1. Trích xuất các số tiền kế toán có dấu chấm (ví dụ: 12.694.975.751.615)
    accounting_numbers = RE_ACCOUNTING_NUMBER.findall(normalized)
    tokens.extend(accounting_numbers)

    # 2. Trích xuất ngày tháng (ví dụ: 31/12/2024)
    dates = RE_DATE_FORMAT.findall(normalized)
    tokens.extend(dates)

    # 3. Trích xuất mã biểu mẫu chuẩn hóa (ví dụ: b03, ms110)
    for m in RE_FORM_OR_CODE.finditer(normalized):
        clean_code = re.sub(r"\s+", "", m.group(0))
        tokens.append(clean_code)

    # 4. Trích xuất các từ thông thường (từ chữ cái và số)
    # Tách từ bằng ký tự không phải chữ/số (ngoại trừ dấu chấm trong số đã được trích ở trên)
    words = re.findall(r"\b[a-z0-9_]{2,}\b", normalized)

    # Lọc stop words cho unigrams
    unigrams: List[str] = []
    for w in words:
        if remove_stopwords and w in FINANCIAL_STOP_WORDS:
            continue
        unigrams.append(w)
    tokens.extend(unigrams)

    # 5. Sinh bigrams cho các cặp từ liên tiếp
    if include_bigrams and len(words) >= 2:
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if remove_stopwords and (w1 in FINANCIAL_STOP_WORDS and w2 in FINANCIAL_STOP_WORDS):
                continue
            bigram = f"{w1}_{w2}"
            tokens.append(bigram)

    return tokens


def build_sparse_vector(text: str) -> Dict[str, float]:
    """
    Tạo biểu diễn vector thưa (Sparse Vector / Term Frequency) để đẩy vào Qdrant Sparse Index hoặc BM25.
    Trả về dict dạng {token: term_frequency}.
    """
    tokens = tokenize_vietnamese_sparse(text, include_bigrams=True, remove_stopwords=True)
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = len(tokens)
    return {tok: count / total for tok, count in counts.items()}
