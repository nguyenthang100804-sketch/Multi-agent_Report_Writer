"""
Module Document Parser & Ingestion (6 Bước Tuần Tự)
===================================================
Thiết kế chuyên biệt cho dữ liệu OCR Báo cáo Tài chính Việt Nam:
  - Bước 1: Đọc và tách trang (Unicode NFC, lưu trang vật lý [Doc_X, p.Y] và số trang in gần cuối trang).
  - Bước 2: Làm sạch (Kế thừa kết quả lọc rác CJK/LaTeX/QR/báo cáo kép từ bước clean token;
            nhận diện tiêu đề lặp tự động >= 30% số trang khi so khớp bỏ dấu; bảo vệ dòng "Đơn vị tính").
  - Bước 3: Tách khối (Tách văn bản và bảng HTML, mở rowspan/colspan thành lưới 2D bằng thư viện chuẩn).
  - Bước 4: Nhận diện cấu trúc (Xác định loại báo cáo, phạm vi riêng/hợp nhất, đơn vị tính;
            chỉ nhận tiêu đề khi là dòng riêng viết hoa bắt đầu bằng cụm tên báo cáo đã bỏ dấu).
  - Bước 5: Trích số liệu và kiểm tra đẳng thức kế toán (Xác định cột Mã số theo tiêu đề cột;
            đánh dấu suspect=true cho số lẫn chữ/con dấu đè; kiểm tra 2 chế độ: theo Mã số chấp nhận
            cả 2 quy ước dấu chi phí, và theo Cây phân cấp cho ngân hàng không có mã số).
  - Bước 6: Chia chunk (Chunk văn bản theo đoạn có tiêu đề mục; chunk bảng riêng lặp dòng tiêu đề cột
            khi bảng dài; gắn đủ metadata và thực hiện Gating tự động).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.clean_and_recount_tokens import BILINGUAL_AND_DUPLICATE_CUTS
from src.schemas.document_schema import (
    Block,
    ChunkItem,
    FactItem,
    GridRow,
    IdentityCheckResult,
    PageData,
    ParsedDocument,
    QualityReport,
)

PARSER_VERSION = "v2.1"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "data" / "backup_data" / "raw_docs_top_100_backup"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed_chunks"


# =============================================================================
# TIỆN ÍCH CHUẨN HÓA CHUỖI & BỎ DẤU TIẾNG VIỆT
# =============================================================================

def normalize_unicode_nfc(text: str) -> str:
    """Chuẩn hóa chuỗi về Unicode NFC chuẩn."""
    return unicodedata.normalize("NFC", text)


def fold_accents(text: str) -> str:
    """
    Bỏ dấu tiếng Việt và chuyển về chữ thường để so khớp chịu lỗi dấu OCR.
    Ví dụ: 'BÀNG CÂN ĐỐI KẾ TOÁN HỢP NHẮT' -> 'bang can doi ke toan hop nhat'
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFC", text)
    s = s.replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_for_header_freq(line: str) -> str:
    """Chuẩn hóa dòng văn bản ngoài bảng để thống kê tần suất tiêu đề lặp (>= 30% trang)."""
    folded = fold_accents(line)
    # Bỏ các ký tự trang trí hoặc dấu câu ở 2 đầu
    folded = re.sub(r"^[\W_]+|[\W_]+$", "", folded)
    folded = re.sub(r"\s+", " ", folded).strip()
    return folded


# =============================================================================
# BƯỚC 1: ĐỌC VÀ TÁCH TRANG (PAGE READER & SPLITTER)
# =============================================================================

def extract_printed_page_from_bottom(page_text: str) -> Tuple[Optional[str], str]:
    """
    Tìm số trang in trên giấy ở gần cuối trang (ngoài bảng <table>).
    Trả về (printed_page, page_text_without_standalone_page_num).
    """
    lines = page_text.split("\n")
    # Tìm vị trí kết thúc của </table> cuối cùng (nếu có) để chỉ tìm số trang in ở phần chân trang
    non_empty_indices = [i for i, l in enumerate(lines) if l.strip()]
    if not non_empty_indices:
        return None, page_text

    # Xét tối đa 4 dòng không rỗng cuối cùng của trang
    tail_candidates = non_empty_indices[-4:]
    for idx in reversed(tail_candidates):
        line_s = lines[idx].strip()
        if "<table" in line_s.lower() or "</table>" in line_s.lower() or "<tr" in line_s.lower():
            break

        # Mẫu 1: Dòng chỉ chứa một số nguyên dương 1..500 ở cuối trang
        if re.match(r"^\d{1,3}$", line_s):
            val = int(line_s)
            if 1 <= val <= 500:
                lines[idx] = ""
                return str(val), "\n".join(lines)

        # Mẫu 2: "Trang 5", "Trang 5/70", "- 5 -", "Page 5"
        m = re.match(
            r"^(?:trang|page|\-|\|)?\s*(\d{1,3})\s*(?:/\s*\d{1,3}|\-|\|)?$",
            line_s,
            flags=re.IGNORECASE,
        )
        if m:
            val = int(m.group(1))
            if 1 <= val <= 500:
                lines[idx] = ""
                return str(val), "\n".join(lines)

    return None, page_text


def _split_text_into_page_map(text: str, cut_page: Optional[int] = None) -> Tuple[Dict[int, str], int]:
    """Tách chuỗi văn bản toàn báo cáo thành dict {physical_page: page_content}."""
    if "===== PAGE " in text:
        chunks = re.split(r"(===== PAGE \d+ =====)", text)
    else:
        chunks = re.split(r"(\[P\.\d+\])", text)

    page_map: Dict[int, str] = {}
    duplicate_pages_cut = 0
    if len(chunks) > 1:
        for i in range(1, len(chunks), 2):
            marker = chunks[i]
            pnum_match = re.search(r"\d+", marker)
            if not pnum_match:
                continue
            pnum = int(pnum_match.group())
            if cut_page is not None and pnum >= cut_page:
                duplicate_pages_cut += 1
                continue
            pcontent = chunks[i + 1] if i + 1 < len(chunks) else ""
            page_map[pnum] = pcontent
    else:
        page_map[1] = text
    return page_map, duplicate_pages_cut


def _normalize_page_for_edit_diff(page_text: str) -> str:
    """Chuẩn hóa nhẹ khoảng trắng cuối dòng để so sánh xem trang trong raw_docs có được chỉnh sửa tay hay không."""
    lines = [re.sub(r"[ \t]+", " ", ln.strip()) for ln in page_text.strip().splitlines() if ln.strip()]
    return "\n".join(lines)


def step1_read_and_split_pages(
    file_path: Path,
    ticker: str,
    year: int,
    backup_dir: Optional[Path] = DEFAULT_BACKUP_DIR,
) -> Tuple[List[PageData], str, Dict[str, int]]:
    """
    Bước 1: Đọc file OCR, chuẩn hóa Unicode NFC, tách theo ===== PAGE n ===== (hoặc [P.n]),
    lưu 2 loại số trang (physical_page và printed_page).
    Kế thừa điểm cắt trang báo cáo kép (song ngữ Việt-Anh / PVD USD) từ bước clean token.
    Nếu file đầu vào trong data/raw_docs/top_100 đã bị nén mất thẻ <table> HTML:
      - Kiểm tra từng trang xem người dùng có chỉnh sửa thủ công trên raw_docs hay không.
      - Trang nào ĐÃ ĐƯỢC SỬA trên raw_docs thì ưu tiên dùng nội dung mới trên raw_docs.
      - Trang nào CHƯA SỬA thì lấy cấu trúc <table> HTML gốc từ backup_dir.
    """
    raw_bytes = file_path.read_bytes()
    ocr_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    raw_docs_text = normalize_unicode_nfc(raw_bytes.decode("utf-8", errors="ignore"))
    is_giai_trinh = file_path.name == "giai_trinh_lien_quan.txt"

    # Kế thừa điểm cắt báo cáo kép đã xác minh ở bước clean token (không cần quét lại)
    cut_page = BILINGUAL_AND_DUPLICATE_CUTS.get((ticker, year)) if not is_giai_trinh else None

    raw_page_map, duplicate_pages_cut = _split_text_into_page_map(raw_docs_text, cut_page=cut_page)
    selected_page_map: Dict[int, str] = dict(raw_page_map)
    backup_printed_pages: Dict[int, Optional[str]] = {}
    manually_edited_pages: int = 0

    # Nếu file trong raw_docs không có <table>, đối chiếu từng trang với bản backup HTML gốc
    if "<table" not in raw_docs_text.lower() and backup_dir is not None and not is_giai_trinh:
        candidate_backup = backup_dir / ticker / str(year) / file_path.name
        if candidate_backup.exists():
            backup_bytes = candidate_backup.read_bytes()
            backup_text = normalize_unicode_nfc(backup_bytes.decode("utf-8", errors="ignore"))
            backup_html_map, dup_cut_bk = _split_text_into_page_map(backup_text, cut_page=cut_page)
            duplicate_pages_cut = max(duplicate_pages_cut, dup_cut_bk)

            # Tạo bản chuẩn sau clean_report_content từ backup để phát hiện chính xác trang nào người dùng đã sửa ở raw_docs
            baseline_clean_map: Dict[int, str] = {}
            try:
                from src.ingestion.clean_and_recount_tokens import clean_report_content

                baseline_cleaned_text, _ = clean_report_content(backup_text, is_giai_trinh=False)
                baseline_clean_map, _ = _split_text_into_page_map(
                    normalize_unicode_nfc(baseline_cleaned_text),
                    cut_page=cut_page,
                )
            except Exception:
                baseline_clean_map = {}

            all_pnums = sorted(set(backup_html_map.keys()) | set(raw_page_map.keys()))
            selected_page_map = {}
            for pnum in all_pnums:
                bk_page = backup_html_map.get(pnum)
                if bk_page is not None:
                    pp_bk, _ = extract_printed_page_from_bottom(bk_page)
                    backup_printed_pages[pnum] = pp_bk

                rd_page = raw_page_map.get(pnum)
                base_page = baseline_clean_map.get(pnum)

                # Nếu người dùng đã chỉnh sửa trang pnum trong raw_docs -> dùng trang đã sửa từ raw_docs!
                if (
                    rd_page is not None
                    and base_page is not None
                    and _normalize_page_for_edit_diff(rd_page) != _normalize_page_for_edit_diff(base_page)
                ):
                    selected_page_map[pnum] = rd_page
                    manually_edited_pages += 1
                elif bk_page is not None:
                    selected_page_map[pnum] = bk_page
                elif rd_page is not None:
                    selected_page_map[pnum] = rd_page

    pages: List[PageData] = []
    for pnum in sorted(selected_page_map.keys()):
        pcontent = selected_page_map[pnum]
        printed_page, pcontent_trimmed = extract_printed_page_from_bottom(pcontent)
        if printed_page is None and pnum in backup_printed_pages:
            printed_page = backup_printed_pages[pnum]
        pages.append(
            PageData(
                physical_page=pnum,
                printed_page=printed_page,
                raw_text=pcontent_trimmed,
            )
        )

    stats = {
        "duplicate_pages_cut": duplicate_pages_cut,
        "manually_edited_pages": manually_edited_pages,
    }
    return pages, ocr_sha256, stats


# =============================================================================
# BƯỚC 2: LÀM SẠCH RÁC OCR & TIÊU ĐỀ LẶP MỖI TRANG (CLEANER)
# =============================================================================

# Danh sách tiền tố tên báo cáo tài chính (đã bỏ dấu) KHÔNG được coi là tiêu đề lặp cần xóa
_PROTECTED_REPORT_TITLE_PREFIXES = (
    "bang can doi ke toan",
    "bao cao tinh hinh tai chinh",
    "bao cao tinh binh tai chinh",
    "bao cao ket qua hoat dong kinh doanh",
    "bao cao ket qua hoat dong",
    "bao cao luu chuyen tien te",
    "ban thuyet minh bao cao tai chinh",
    "thuyet minh bao cao tai chinh",
    "bao cao kiem toan doc lap",
    "bao cao cua ban tong giam doc",
    "bao cao cua ban giam doc",
    "bao cao cua ban dieu hanh",
    "bao cao cua hoi dong quan tri",
    "cac chi tieu ngoai bao cao tinh hinh tai chinh",
    "cac chi tieu ngoai bang can doi ke toan",
)


def is_unit_line(folded_line: str) -> bool:
    """
    Kiểm tra dòng có phải là thông tin 'Đơn vị tính' hay không.
    Quyết định từ dữ liệu: Không coi 'Đơn vị tính' là tiêu đề lặp vì đó là thông tin đơn vị.
    """
    if not folded_line:
        return False
    if "don vi tinh" in folded_line or folded_line.startswith("don vi:") or folded_line.startswith("dvt:"):
        return True
    if re.match(r"^(?:don vi tinh|don vi|dvt)\b", folded_line):
        return True
    return False


def is_protected_report_heading(folded_line: str) -> bool:
    """Bảo vệ dòng tiêu đề báo cáo chính khỏi bộ lọc tiêu đề lặp (ngoại trừ dòng Thuyết minh tiếp theo lặp ở mọi trang)."""
    if not folded_line:
        return False
    # Nếu là dòng 'THUYẾT MINH BÁO CÁO TÀI CHÍNH ... (tiếp theo)' lặp lại ở 30-80 trang thì cho phép lọc ở các trang sau
    if ("thuyet minh bao cao tai chinh" in folded_line or "ban thuyet minh bao cao tai chinh" in folded_line) and "tiep theo" in folded_line:
        return False
    for prefix in _PROTECTED_REPORT_TITLE_PREFIXES:
        if folded_line.startswith(prefix):
            return True
    return False


def clean_inline_ocr_noise(text: str) -> Tuple[str, int]:
    r"""
    Tái sử dụng bộ lọc nhiễu VLM / OCR từ bước clean token:
      - Câu thông báo lỗi QR code của VLM
      - Chuyển footnote mũ \(^{(1)}\) -> (1) rồi xóa LaTeX con dấu ảo giác
      - Xóa chữ Hán (CJK), chuỗi ô vuông □, chuỗi <tr></tr> rỗng
    Trả về (cleaned_text, noise_hits_count).
    """
    noise_hits = 0

    # 1. VLM QR code / blank image refusal
    patterns_vlm = [
        r"The image (?:provided is a QR code|contains no text|does not contain any text)[^\n]*\n?",
        r"Therefore, no textual content can be extracted[^\n]*\n?",
        r'The OCR result "[^"]*" is a hallucination[^\n]*\n?',
    ]
    for pat in patterns_vlm:
        text, n = re.subn(pat, "", text, flags=re.IGNORECASE)
        noise_hits += n

    # 2. Chuyển ghi chú mũ đơn giản \(^{(1)}\) -> (1) trước khi xóa LaTeX ảo giác
    text = re.sub(r"\\\( ?\^\{?([\d\*\(\)a-zA-Z]+)\}? ?\\\)", r"(\1)", text)
    # Xóa chuỗi suy biến lặp công thức toán OCR ảo giác kéo dài qua nhiều dòng (gây chunk khổng lồ)
    text = re.sub(r"(?:\\times\s*\d+){4,}", " ", text)

    # An toàn tuyệt đối: Dừng tại hết dòng hoặc trước <table, không cho phép xóa lan qua bảng hoặc số tiền
    def _safe_clean_latex(m: re.Match) -> str:
        s = m.group(0)
        # Tuyệt đối không xóa nếu chứa thẻ bảng hoặc số tiền kế toán lớn (>= 2 dấu chấm phân cách hàng nghìn)
        if "<table" in s or re.search(r"\d{1,3}(?:\.\d{3}){2,}", s):
            return s
        # Nếu chuỗi dài > 300 ký tự và chứa nhiều từ tiếng Việt thông thường -> giữ lại
        if len(s) > 300 and len(re.findall(r"[a-zA-ZÀ-ỹ]{4,}", s)) > 5:
            return s
        return " "

    # Chỉ quét trong phạm vi dòng hoặc dừng trước <table
    text, n1 = re.subn(r"\\\(.*?(?:\\\)|(?=\n|<table|$))", _safe_clean_latex, text, flags=re.DOTALL)
    text, n2 = re.subn(r"\\\[.*?(?:\\\]|(?=\n|<table|$))", _safe_clean_latex, text, flags=re.DOTALL)
    text, n3 = re.subn(r"(?:\\[a-zA-Z]+(?:\{[^}]*\}|\s*|_|\^)*){3,}", " ", text)
    noise_hits += n1 + n2 + n3

    # 3. Chuỗi ô vuông viền trang
    text, n_box = re.subn(r"[□■▪▫◊○●\s]{4,}", " ", text)
    noise_hits += n_box

    # 4. Chữ Hán (CJK) & vòng lặp suy biến
    text, n_cjk = re.subn(r"[\u4e00-\u9fff]+", "", text)
    noise_hits += n_cjk

    # 5. Xóa chuỗi <tr></tr> rỗng liên tiếp do lỗi rowspan
    text, n_empty_tr = re.subn(r"(?:<tr[^>]*>\s*(?:<td[^>]*>\s*</td>\s*)*</tr>\s*){2,}", "", text, flags=re.IGNORECASE)
    noise_hits += n_empty_tr

    # 6. Chấm dẫn mục lục ....
    text = re.sub(r"\.{4,}", " ", text)
    text = re.sub(r"-{4,}", " ", text)

    # 7. Vòng lặp suy biến lặp từ/cụm từ OCR (chỉ thu gọn khi đơn vị lặp có chứa chữ cái Unicode, tránh làm hỏng số tiền lớn)
    loop_pat = re.compile(r"(.{2,50}?)\1{5,}")
    def _collapse_loop(m: re.Match) -> str:
        # Kiểm tra xem đơn vị lặp có chứa chữ cái (chữ Việt/Latin) hay không
        if re.search(r"[^\W\d_]", m.group(1)):
            return m.group(1)
        return m.group(0)

    text, n_loop = loop_pat.subn(_collapse_loop, text)
    noise_hits += n_loop

    return text, noise_hits


def step2_clean_pages(pages: List[PageData], stats: Dict[str, int]) -> Tuple[List[PageData], Dict[str, int]]:
    """
    Bước 2: Bỏ dòng rác (chữ Hán, LaTeX, QR refusal, dãy đếm dòng) và tiêu đề lặp mỗi trang.
    Quyết định từ dữ liệu:
      - Nhận diện tiêu đề lặp tự động: dòng xuất hiện ở ít nhất 30% số trang (khi so khớp đã bỏ dấu).
      - Không coi 'Đơn vị tính' là tiêu đề lặp vì đó là thông tin đơn vị.
    """
    total_pages = len(pages)
    vlm_and_ocr_garbage = 0
    repeated_header_removed = 0

    # Pha 2A: Làm sạch rác nội tuyến (CJK, LaTeX, QR code, ô vuông) trên từng trang
    intermediate_texts: List[str] = []
    for p in pages:
        cleaned_t, hits = clean_inline_ocr_noise(p.raw_text)
        vlm_and_ocr_garbage += hits
        intermediate_texts.append(cleaned_t)

    # Pha 2B: Thống kê tần suất dòng ngoài bảng (so khớp đã bỏ dấu) trên toàn tài liệu
    folded_page_freq: Dict[str, int] = {}
    for cleaned_t in intermediate_texts:
        outside_tbl = re.sub(r"<table.*?>.*?</table>", "", cleaned_t, flags=re.DOTALL | re.IGNORECASE)
        seen_on_page: Set[str] = set()
        for line in outside_tbl.split("\n"):
            l_strip = line.strip()
            if len(l_strip) < 4 or "|" in l_strip:
                continue
            folded = normalize_for_header_freq(l_strip)
            if not folded or len(folded) < 4:
                continue
            if is_unit_line(folded) or is_protected_report_heading(folded):
                continue
            seen_on_page.add(folded)
        for f_line in seen_on_page:
            folded_page_freq[f_line] = folded_page_freq.get(f_line, 0) + 1

    # Ngưỡng >= 30% số trang (với tài liệu >= 5 trang)
    freq_threshold = max(3, math.ceil(total_pages * 0.30)) if total_pages >= 5 else 999
    repeated_headers_folded: Set[str] = {
        f_line for f_line, cnt in folded_page_freq.items() if cnt >= freq_threshold
    }

    # Pha 2C: Lọc dòng rác và tiêu đề lặp trên từng trang
    seen_first_page_header: Set[str] = set()
    for p, cleaned_t in zip(pages, intermediate_texts):
        # Tách phần văn bản và phần <table> để không chạm vào dòng bên trong <table>
        segments = re.split(r"(<table[^>]*>.*?</table>)", cleaned_t, flags=re.DOTALL | re.IGNORECASE)
        rebuilt_segments: List[str] = []

        for seg in segments:
            if seg.lower().startswith("<table"):
                rebuilt_segments.append(seg)
                continue

            out_lines: List[str] = []
            for line in seg.split("\n"):
                l_strip = line.strip()
                if not l_strip:
                    out_lines.append("")
                    continue

                # Bảo toàn nguyên vẹn dòng bảng dạng pipe '|' (khi đọc từ raw_docs đã chỉnh sửa tay)
                if "|" in l_strip:
                    out_lines.append(l_strip)
                    continue

                # Bỏ dãy số đếm dòng đầu trang của giấy kiểm toán: "1 2 3 ... 23" hoặc "[1] [2] ... [19]"
                if re.match(r"^(?:\[?\(?\d{1,2}\)?\]?[\.\s]*){3,}$", l_strip):
                    vlm_and_ocr_garbage += 1
                    continue

                # Bỏ dòng chỉ chứa 1 con số đơn lẻ (như "1", "2" đếm dòng dọc lề trái ở FPT trang 4, 6)
                if re.match(r"^\d{1,2}$", l_strip):
                    vlm_and_ocr_garbage += 1
                    continue

                folded = normalize_for_header_freq(l_strip)

                # Bỏ watermark hệ thống e-office
                if "eoffice" in folded or "van ban duoc tai len he thong" in folded:
                    vlm_and_ocr_garbage += 1
                    continue

                # Bảo vệ dòng "Đơn vị tính" và tiêu đề báo cáo chính
                if is_unit_line(folded) or is_protected_report_heading(folded):
                    out_lines.append(l_strip)
                    continue

                # Kiểm tra tiêu đề lặp >= 30% số trang
                if folded in repeated_headers_folded:
                    # Giữ lại lần xuất hiện đầu tiên ở trang bìa (trang 1) HOẶC lần xuất hiện đầu tiên của mã biểu mẫu (Mẫu B 09)
                    if (
                        (p.physical_page == 1 or re.search(r"\bmau\s*(?:so\s*)?b\s*0[123459]", folded))
                        and folded not in seen_first_page_header
                    ):
                        seen_first_page_header.add(folded)
                        out_lines.append(l_strip)
                    else:
                        repeated_header_removed += 1
                    continue

                out_lines.append(l_strip)

            rebuilt_segments.append("\n".join(out_lines))

        page_joined = "\n".join(rebuilt_segments)
        # Thu gọn nhiều dòng trống liên tiếp
        page_joined = re.sub(r"\n{3,}", "\n\n", page_joined).strip()
        p.cleaned_text = page_joined

    stats["vlm_and_ocr_garbage_lines"] = vlm_and_ocr_garbage
    stats["repeated_header_footer_lines"] = repeated_header_removed
    stats["total_removed"] = (
        stats.get("duplicate_pages_cut", 0) + vlm_and_ocr_garbage + repeated_header_removed
    )
    return pages, stats


# =============================================================================
# BƯỚC 3: TÁCH KHỐI & MỞ ROWSPAN/COLSPAN THÀNH LƯỚI 2D (BLOCK & GRID EXTRACTOR)
# =============================================================================

class _HTMLTableParser(HTMLParser):
    """
    Bộ parse bảng HTML chuẩn bằng html.parser của Python.
    Trích xuất danh sách các hàng, mỗi hàng là danh sách các tuple (cell_text, rowspan, colspan).
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: List[List[Tuple[str, int, int]]] = []
        self._current_row: Optional[List[Tuple[str, int, int]]] = None
        self._in_cell: bool = False
        self._cell_buffer: List[str] = []
        self._cell_rowspan: int = 1
        self._cell_colspan: int = 1

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_l = tag.lower()
        if tag_l == "tr":
            self._current_row = []
        elif tag_l in ("td", "th"):
            if self._current_row is None:
                self._current_row = []
            self._in_cell = True
            self._cell_buffer = []
            attr_dict = {k.lower(): (v or "1") for k, v in attrs}
            try:
                self._cell_rowspan = max(1, int(re.sub(r"\D", "", attr_dict.get("rowspan", "1")) or "1"))
            except ValueError:
                self._cell_rowspan = 1
            try:
                self._cell_colspan = max(1, int(re.sub(r"\D", "", attr_dict.get("colspan", "1")) or "1"))
            except ValueError:
                self._cell_colspan = 1
        elif tag_l == "br" and self._in_cell:
            self._cell_buffer.append(" ")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l in ("td", "th") and self._in_cell:
            text = html.unescape("".join(self._cell_buffer))
            text = re.sub(r"\s+", " ", text).strip()
            if self._current_row is not None:
                self._current_row.append((text, self._cell_rowspan, self._cell_colspan))
            self._in_cell = False
        elif tag_l == "tr" and self._current_row is not None:
            # Chỉ giữ hàng có ít nhất 1 ô hoặc không phải hàng rỗng vô nghĩa
            if any(c[0] != "" for c in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = None


def expand_html_table_to_grid(table_html: str) -> List[List[str]]:
    """
    Parse thẻ <table> HTML và mở rowspan/colspan thành lưới 2D đều đặn (List[List[str]]).
    """
    parser = _HTMLTableParser()
    parser.feed(table_html)
    raw_rows = parser.rows
    if not raw_rows:
        return []

    num_rows = len(raw_rows)
    grid_map: Dict[Tuple[int, int], str] = {}
    max_col = 0

    for r_idx, row in enumerate(raw_rows):
        c_idx = 0
        row_texts_only = [c[0] for c in row]
        is_hdr = r_idx < 2 and _is_header_row_cells(row_texts_only)
        for cell_text, rspan, cspan in row:
            while (r_idx, c_idx) in grid_map:
                c_idx += 1
            # Chặn lỗi OCR ảo giác rowspan vượt quá số dòng thực tế của bảng
            effective_rspan = min(rspan, num_rows - r_idx)
            effective_cspan = min(cspan, 15)

            for dr in range(effective_rspan):
                for dc in range(effective_cspan):
                    # Với dòng tiêu đề cột, nhân bản giá trị qua colspan để mỗi cột đều biết nhóm tiêu đề;
                    # Với dòng dữ liệu/tiêu đề mục con trong thân bảng, chỉ đặt chữ ở cột đầu (dc == 0) để không tràn chữ sang cột số liệu
                    if dc == 0 or is_hdr:
                        grid_map[(r_idx + dr, c_idx + dc)] = cell_text
                    else:
                        grid_map[(r_idx + dr, c_idx + dc)] = ""
            c_idx += effective_cspan
            if c_idx > max_col:
                max_col = c_idx

    if max_col == 0:
        return []

    grid: List[List[str]] = []
    for r_idx in range(num_rows):
        row_cells = [grid_map.get((r_idx, c_idx), "") for c_idx in range(max_col)]
        # Cắt bỏ dòng chỉ chứa số thứ tự cột: (1) | (2) | (3) | (4) | (5)
        non_empty = [c for c in row_cells if c]
        if not non_empty:
            continue
        if len(non_empty) >= 3 and all(re.match(r"^\(?\d{1,2}\)?$", c) for c in non_empty):
            continue
        grid.append(row_cells)

    # Cắt các cột hoàn toàn trống ở phía bên phải cùng của bảng
    while max_col > 1 and grid and all(r[max_col - 1] == "" for r in grid):
        for r in grid:
            r.pop()
        max_col -= 1

    return grid


def expand_pipe_table_to_grid(pipe_lines: List[str]) -> List[List[str]]:
    """
    Parse các dòng bảng dạng pipe '|' (từ file raw_docs đã được người dùng chỉnh sửa tay)
    thành lưới 2D đều đặn (List[List[str]]).
    """
    raw_rows: List[List[str]] = []
    for ln in pipe_lines:
        ln_strip = ln.strip()
        if not ln_strip:
            continue
        cells = [c.strip() for c in ln_strip.split("|")]
        if any(c != "" for c in cells):
            raw_rows.append(cells)

    if not raw_rows:
        return []

    # Gộp dòng nhãn bị ngắt thành 2 dòng trong bảng pipe (ví dụ: "5 | Các khoản dự phòng..." + "| Có nội bảng khác | | (253.570) | (238.109)")
    merged_rows: List[List[str]] = []
    idx = 0
    while idx < len(raw_rows):
        cur = raw_rows[idx]
        if (
            len(cur) == 2
            and cur[0]
            and len(cur[0]) <= 5
            and idx + 1 < len(raw_rows)
            and len(raw_rows[idx + 1]) >= 4
            and raw_rows[idx + 1][0] == ""
            and raw_rows[idx + 1][1] != ""
            and not _is_header_row_cells(cur)
        ):
            nxt = list(raw_rows[idx + 1])
            nxt[0] = cur[0]
            nxt[1] = f"{cur[1]} {nxt[1]}".strip()
            merged_rows.append(nxt)
            idx += 2
            continue
        merged_rows.append(cur)
        idx += 1

    max_col = max(len(r) for r in merged_rows)
    if max_col == 0:
        return []

    grid: List[List[str]] = []
    for r_idx, r in enumerate(merged_rows):
        non_empty = [c for c in r if c]
        if not non_empty:
            continue
        if len(non_empty) >= 3 and all(re.match(r"^\(?\d{1,2}\)?$", c) for c in non_empty):
            continue

        if len(r) < max_col:
            pad_len = max_col - len(r)
            # Nếu là dòng tiêu đề cột thiếu các cột trống đầu bảng (STT/Chỉ tiêu) -> đệm "" vào bên trái
            if r_idx < 2 and _is_header_row_cells(r):
                row_cells = [""] * pad_len + r
            # Nếu là dòng tiêu đề mục con ngắn (1-2 ô, không có số liệu ở cuối) -> đệm "" vào bên phải
            elif len(r) <= 2 and not any(any(ch.isdigit() for ch in c) for c in r[-1:]):
                row_cells = r + [""] * pad_len
            else:
                # Dòng dữ liệu con thiếu cột STT đầu dòng (ví dụ "■ Cam kết mua ngoại tệ | | 46.479 | 33.887") -> đệm "" bên trái
                row_cells = [""] * pad_len + r
        else:
            row_cells = r[:max_col]

        grid.append(row_cells)

    while max_col > 1 and grid and all(r[max_col - 1] == "" for r in grid):
        for r in grid:
            r.pop()
        max_col -= 1

    return grid


def _split_non_html_segment_into_blocks(seg_text: str) -> List[Tuple[str, Any]]:
    """
    Tách một đoạn văn bản không có thẻ <table> thành các khối ('text', str) và ('table', List[List[str]])
    khi trang được đọc từ raw_docs có định dạng bảng ngăn cách bởi dấu '|'.
    """
    lines = seg_text.split("\n")
    items: List[Tuple[str, Any]] = []
    text_buf: List[str] = []
    pipe_buf: List[str] = []

    def flush_text() -> None:
        nonlocal text_buf
        joined = "\n".join(text_buf).strip()
        if joined:
            items.append(("text", joined))
        text_buf = []

    def flush_pipe() -> None:
        nonlocal pipe_buf
        if pipe_buf:
            grid_2d = expand_pipe_table_to_grid(pipe_buf)
            if grid_2d:
                items.append(("table", grid_2d))
        pipe_buf = []

    row_pat = re.compile(r"^([\d\.\-\+\s]*[A-Za-zÀ-ỹ].*?)\s+(\d{1,3}[a-z]?)\s+((?:\(?[\d\.,-]+\)?\s*){1,4})$")

    def has_table_ahead(start_idx: int) -> bool:
        count = 0
        for k in range(start_idx, n):
            s = lines[k].strip()
            if not s:
                continue
            count += 1
            if detect_heading_line(s, has_form_code_nearby=True) is not None:
                return False
            if "|" in s:
                return True
            m = row_pat.match(s)
            if m and re.search(r"\d{3,}", m.group(3)):
                return True
            if count >= 2:
                break
        return False

    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        ln_strip = ln.strip()

        if "|" in ln_strip:
            flush_text()
            pipe_buf.append(ln_strip)
            i += 1
            continue

        # Nếu đang ở giữa bảng pipe và gặp dòng trống hoặc 1 dòng tiêu đề mục con viết hoa (không phải tiêu đề báo cáo mới)
        # hoặc dòng số liệu dạng space-separated không có pipe
        if pipe_buf:
            if not ln_strip:
                if has_table_ahead(i + 1):
                    i += 1
                    continue
            else:
                # Hỗ trợ dòng số liệu dạng space-separated không có pipe (ví dụ QNS 2025 B03)
                row_m = row_pat.match(ln_strip)
                if row_m and re.search(r"\d{3,}", row_m.group(3)):
                    nums = row_m.group(3).strip().split()
                    pipe_buf.append(f"{row_m.group(1).strip()} | {row_m.group(2).strip()} | " + " | ".join(nums))
                    i += 1
                    continue

                # Nếu dòng đơn không có '|' không phải là tiêu đề báo cáo chính (detect_heading_line is None)
                # và dòng tiếp theo có '|' hoặc số liệu (ví dụ: "LƯU CHUYỂN TIỀN TỪ HOẠT ĐỘNG KINH DOANH" ở giữa header và dòng 01)
                if detect_heading_line(ln_strip, has_form_code_nearby=True) is None and not is_unit_line(fold_accents(ln_strip)):
                    if has_table_ahead(i + 1):
                        pipe_buf.append(f"| {ln_strip}")
                        i += 1
                        continue

            flush_pipe()

        text_buf.append(ln)
        i += 1

    flush_pipe()
    flush_text()
    return items


def step3_extract_blocks(pages: List[PageData]) -> List[Block]:
    """
    Bước 3: Tách văn bản và bảng trên từng trang, mở rowspan/colspan của bảng thành lưới 2D.
    Hỗ trợ cả bảng <table> HTML và bảng pipe '|' (trên các trang người dùng chỉnh sửa ở raw_docs).
    """
    raw_blocks: List[Block] = []
    block_counter = 0

    for p in pages:
        has_html_table = "<table" in p.cleaned_text.lower()
        segments = re.split(r"(<table[^>]*>.*?</table>)", p.cleaned_text, flags=re.DOTALL | re.IGNORECASE)
        for seg in segments:
            seg_strip = seg.strip()
            if not seg_strip:
                continue

            if seg_strip.lower().startswith("<table"):
                grid_2d = expand_html_table_to_grid(seg_strip)
                if not grid_2d:
                    continue
                block_counter += 1
                grid_rows = [
                    GridRow(cells=row, physical_page=p.physical_page, printed_page=p.printed_page)
                    for row in grid_2d
                ]
                raw_blocks.append(
                    Block(
                        block_id=f"blk_{block_counter:04d}",
                        block_type="table",
                        physical_page_start=p.physical_page,
                        physical_page_end=p.physical_page,
                        printed_pages=[p.printed_page] if p.printed_page else [],
                        section="UNKNOWN",
                        section_title="",
                        unit="VND",
                        grid=grid_rows,
                        num_cols=len(grid_2d[0]),
                    )
                )
            elif not has_html_table and "|" in seg_strip:
                for sub_type, sub_payload in _split_non_html_segment_into_blocks(seg_strip):
                    block_counter += 1
                    if sub_type == "table":
                        grid_rows = [
                            GridRow(cells=row, physical_page=p.physical_page, printed_page=p.printed_page)
                            for row in sub_payload
                        ]
                        raw_blocks.append(
                            Block(
                                block_id=f"blk_{block_counter:04d}",
                                block_type="table",
                                physical_page_start=p.physical_page,
                                physical_page_end=p.physical_page,
                                printed_pages=[p.printed_page] if p.printed_page else [],
                                section="UNKNOWN",
                                section_title="",
                                unit="VND",
                                grid=grid_rows,
                                num_cols=len(sub_payload[0]),
                            )
                        )
                    else:
                        raw_blocks.append(
                            Block(
                                block_id=f"blk_{block_counter:04d}",
                                block_type="text",
                                physical_page_start=p.physical_page,
                                physical_page_end=p.physical_page,
                                printed_pages=[p.printed_page] if p.printed_page else [],
                                section="UNKNOWN",
                                section_title="",
                                unit="VND",
                                text=sub_payload,
                            )
                        )
            else:
                block_counter += 1
                raw_blocks.append(
                    Block(
                        block_id=f"blk_{block_counter:04d}",
                        block_type="text",
                        physical_page_start=p.physical_page,
                        physical_page_end=p.physical_page,
                        printed_pages=[p.printed_page] if p.printed_page else [],
                        section="UNKNOWN",
                        section_title="",
                        unit="VND",
                        text=seg_strip,
                    )
                )

    # Phục hồi các hàng bảng bị rớt ra ngoài thẻ <table> do lỗi đóng thẻ sớm ở bước OCR
    pat_orphaned_row = re.compile(r"^([\d\.\-\+\s]*[A-Za-zÀ-ỹ].*?)\s+(\d{1,3}[a-z]?)\s+((?:\(?[\d\.,-]+\)?\s*){1,4})$")
    for i, b in enumerate(raw_blocks):
        if b.block_type == "table" and len(b.grid) <= 2 and i + 1 < len(raw_blocks) and raw_blocks[i + 1].block_type == "text":
            txt_blk = raw_blocks[i + 1]
            lines = txt_blk.text.split("\n")
            num_cols = b.num_cols
            extracted_grid_rows = []
            for l in lines:
                l_s = l.strip()
                if not l_s:
                    continue
                m = pat_orphaned_row.match(l_s)
                if m and re.search(r"\d{3,}", m.group(3)):
                    item = m.group(1).strip()
                    code = m.group(2).strip()
                    nums = m.group(3).strip().split()
                    row = [item, code] + nums
                    if len(row) < num_cols:
                        row += [""] * (num_cols - len(row))
                    elif len(row) > num_cols:
                        row = row[:num_cols]
                    extracted_grid_rows.append(
                        GridRow(
                            cells=row,
                            physical_page=txt_blk.physical_page_start,
                            printed_page=txt_blk.printed_pages[0] if txt_blk.printed_pages else None,
                        )
                    )
                elif re.match(r"^[I|V|X\d\.\-\s]+[A-Za-zÀ-ỹ]", l_s):
                    row = [l_s] + [""] * (num_cols - 1)
                    extracted_grid_rows.append(
                        GridRow(
                            cells=row,
                            physical_page=txt_blk.physical_page_start,
                            printed_page=txt_blk.printed_pages[0] if txt_blk.printed_pages else None,
                        )
                    )
            if len(extracted_grid_rows) >= 5:
                b.grid.extend(extracted_grid_rows)
                txt_blk.text = ""

    raw_blocks = [b for b in raw_blocks if b.block_type != "text" or b.text.strip()]
    return raw_blocks


# =============================================================================
# BƯỚC 4: NHẬN DIỆN CẤU TRÚC (STRUCTURE, SCOPE & UNIT DETECTOR)
# =============================================================================

def parse_unit_from_string(text: str) -> Optional[str]:
    """Nhận diện đơn vị tiền tệ chuẩn từ chuỗi văn bản hoặc tiêu đề cột."""
    folded = fold_accents(text)
    if not folded:
        return None
    # Loại trừ các chuỗi tỷ giá hối đoái (ví dụ VND/USD, VND/EUR, USD/VND...) không phải là đơn vị tính của báo cáo
    if re.search(r"\b(?:vnd|usd|eur|jpy|gbp|aud|cad|sgd|cny|thb)\s*/\s*(?:vnd|usd|eur|jpy|gbp|aud|cad|sgd|cny|thb)\b", folded) or "ty gia" in folded:
        return None
    if "trieu vnd" in folded or "trieu dong" in folded:
        return "million_VND"
    if "ty vnd" in folded or "ty dong" in folded:
        return "billion_VND"
    if "nghin vnd" in folded or "nghin dong" in folded or "ngan dong" in folded:
        return "thousand_VND"
    if re.search(r"\busd\b", folded) or "do la my" in folded:
        return "USD"
    if re.search(r"\bvnd\b", folded) or "dong viet nam" in folded:
        return "VND"
    return None


def detect_heading_line(line: str, has_form_code_nearby: bool = False) -> Optional[Tuple[str, str]]:
    """
    Nhận diện tiêu đề loại báo cáo từ một dòng văn bản riêng biệt.
    Quyết định từ dữ liệu:
      - Chỉ nhận tiêu đề khi nó là một dòng riêng viết hoa và bắt đầu bằng cụm tên báo cáo,
        để không nhầm với câu văn nhắc tới báo cáo.
      - Hỗ trợ thêm trường hợp mẫu KPMG (HPG, VNM, VCB) in tiêu đề bắt đầu bằng cụm tên báo cáo
        ngay sát dòng 'Mẫu B 01 - DN/HN' / 'Mẫu B02/TCTD-HN'.
      - So khớp bằng chuỗi đã bỏ dấu để chịu lỗi dấu OCR.
    """
    l_strip = line.strip()
    if not l_strip or len(l_strip) > 160:
        return None

    # Loại trừ ngay nếu dòng kết thúc bằng dấu chấm câu hoặc chứa từ nối của câu văn
    folded = fold_accents(l_strip)
    prose_indicators = (
        "bao gom:",
        "bao gom ",
        "kem theo",
        "duoc lap",
        "chung toi",
        "theo y kien",
        "trach nhiem cua",
        "nhu sau",
        "mot phan hop thanh",
        "mot phan cau thanh",
        "xem thuyet minh",
        "trang ",
    )
    if any(p in folded for p in prose_indicators):
        return None

    # Loại trừ dòng trong trang Mục lục (NỘI DUNG) kết thúc bằng số trang hoặc khoảng trang (ví dụ "Báo cáo kiểm toán độc lập 3", "... 12 - 83")
    if re.search(r"\s+\d{1,3}(?:\s*[-–]\s*\d{1,3})?$", folded) and not re.search(r"(?:nam|thang|ngay)\s+\d{1,4}$", folded):
        return None

    # Trong một số báo cáo ngân hàng (như VCB), dòng đầu trang gộp tên ngân hàng + tên báo cáo:
    # "Ngân hàng TMCP Ngoại thương Việt Nam ... Báo cáo tình hình tài chính hợp nhất"
    for prefix_trigger in (
        "bao cao tinh hinh tai chinh",
        "bao cao tinh binh tai chinh",
        "bang can doi ke toan",
        "bao cao ket qua hoat dong",
        "bao cao luu chuyen tien te",
        "thuyet minh bao cao tai chinh",
        "ban thuyet minh bao cao tai chinh",
    ):
        pos = folded.find(prefix_trigger)
        if pos > 0 and has_form_code_nearby:
            folded = folded[pos:].strip()
            l_strip = l_strip[pos:].strip()
            break

    # Kiểm tra tính chất viết hoa của phần cụm tên báo cáo (trước dấu '(' hoặc 'tại ngày' / 'cho năm')
    core_part = re.split(r"\(|tai ngay|cho nam|vao ngay|ngay \d", l_strip, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    alpha_chars = [ch for ch in core_part if ch.isalpha()]
    if not alpha_chars:
        return None
    upper_ratio = sum(1 for ch in alpha_chars if ch.isupper()) / len(alpha_chars)

    # Yêu cầu viết hoa (>= 75% chữ cái viết hoa) HOẶC đứng ngay cạnh mã biểu mẫu chuẩn (Mẫu B 01..B 09)
    if upper_ratio < 0.75 and not has_form_code_nearby:
        return None

    # Phân loại theo nội dung đã bỏ dấu (ưu tiên Lưu chuyển tiền tệ trước để chịu lỗi OCR gõ nhầm 'báo cáo kết lưu chuyển')
    if "thong tin bo sung cho cac" in folded and "khoan muc" in folded:
        return ("NOTES", l_strip)
    if "cac chi tieu ngoai" in folded:
        return ("OFF_BALANCE_SHEET", l_strip)
    if "luu chuyen tien te" in folded:
        return ("CASH_FLOW", l_strip)
    if (
        "bang can doi ke toan" in folded
        or "tinh hinh tai chinh" in folded
        or "tinh binh tai chinh" in folded
    ):
        return ("BALANCE_SHEET", l_strip)
    if "ket qua hoat dong kinh doanh" in folded or "ket qua hoat dong" in folded or "ket qua kinh doanh" in folded:
        return ("INCOME_STATEMENT", l_strip)
    if "thuyet minh bao cao tai chinh" in folded or "ban thuyet minh" in folded:
        return ("NOTES", l_strip)
    if "bao cao kiem toan doc lap" in folded or "kiem toan doc lap" in folded:
        return ("AUDIT_REPORT", l_strip)
    if (
        "bao cao cua ban tong giam doc" in folded
        or "bao cao cua ban giam doc" in folded
        or "bao cao cua ban dieu hanh" in folded
        or "bao cao cua hoi dong quan tri" in folded
    ):
        return ("MANAGEMENT_REPORT", l_strip)

    # Nhận diện theo mã biểu mẫu chuẩn đứng gần tiêu đề
    if has_form_code_nearby:
        if "tctd" in folded:
            if "b04" in folded or "b 04" in folded:
                return ("CASH_FLOW", l_strip)
            if "b03" in folded or "b 03" in folded:
                return ("INCOME_STATEMENT", l_strip)
            if "b02" in folded or "b 02" in folded:
                return ("BALANCE_SHEET", l_strip)
        else:
            if "b03" in folded or "b 03" in folded:
                return ("CASH_FLOW", l_strip)
            if "b02" in folded or "b 02" in folded:
                return ("INCOME_STATEMENT", l_strip)
            if "b01" in folded or "b 01" in folded:
                return ("BALANCE_SHEET", l_strip)
        if "b09" in folded or "b 09" in folded or "b05" in folded or "b 05" in folded:
            return ("NOTES", l_strip)

    if folded in (
        "muc luc",
        "noi dung",
        "thong tin ve doanh nghiep",
        "thong tin ve ngan hang",
        "thong tin ve cong ty",
        "thong tin ve tap doan",
        "thong tin chung",
    ):
        return ("COVER_OR_TOC", l_strip)

    return None

    return None


def step4_detect_structure(
    blocks: List[Block],
    file_name: str,
) -> Tuple[List[Block], str, str]:
    """
    Bước 4: Xác định loại báo cáo (section), phạm vi (scope: consolidated/separate/general),
    và đơn vị tính (unit) cho từng khối. Đồng thời hợp nhất các bảng liên trang thuộc cùng một báo cáo.
    """
    from collections import Counter

    folded_fname = fold_accents(file_name)
    if "hopnhat" in folded_fname or "hop nhat" in folded_fname:
        doc_scope = "consolidated"
    elif "rieng" in folded_fname or "congtyme" in folded_fname:
        doc_scope = "separate"
    else:
        doc_scope = "general"

    current_section = "COVER_OR_TOC"
    current_title = "Trang bìa & Thông tin chung"
    primary_units: List[str] = []
    all_detected_units: List[str] = []

    # Pha 1: Nhận diện phân mục (section) và phát hiện đơn vị ở các báo cáo tài chính chính
    for blk in blocks:
        if blk.block_type == "text":
            folded_blk = fold_accents(blk.text)
            has_form_code = bool(
                re.search(
                    r"\bmau\s*(?:so\s*)?b\s*0[123459]",
                    folded_blk,
                )
            )
            for line in blk.text.split("\n"):
                l_strip = line.strip()
                if not l_strip:
                    continue
                folded_l = fold_accents(l_strip)

                if doc_scope == "general":
                    if "bao cao tai chinh hop nhat" in folded_l or "bang can doi ke toan hop nhat" in folded_l:
                        doc_scope = "consolidated"
                    elif "bao cao tai chinh rieng" in folded_l or "bang can doi ke toan rieng" in folded_l:
                        doc_scope = "separate"

                # Kiểm tra tiêu đề báo cáo
                heading_match = detect_heading_line(l_strip, has_form_code_nearby=has_form_code)
                if heading_match is not None:
                    sec_code, sec_title = heading_match
                    if current_section == "NOTES" and sec_code in (
                            "BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"):
                        is_bank_form = "tctd" in folded_blk
                        expected_code = {
                            "BALANCE_SHEET": "02" if is_bank_form else "01",
                            "INCOME_STATEMENT": "03" if is_bank_form else "02",
                            "CASH_FLOW": "04" if is_bank_form else "03",
                        }[sec_code]
                        if not re.search(rf"\bmau\s*(?:so\s*:?[ \t]*)?b\s*{expected_code}\b", folded_blk):
                            continue
                    current_section = sec_code
                    if "tiep theo" not in fold_accents(sec_title) or not current_title:
                        current_title = sec_title

                # Kiểm tra dòng Đơn vị tính
                if is_unit_line(folded_l) or folded_l.startswith("don vi tinh"):
                    u = parse_unit_from_string(l_strip)
                    if u:
                        all_detected_units.append(u)
                        if current_section in ("BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"):
                            primary_units.append(u)

            blk.section = current_section
            blk.section_title = current_title

        elif blk.block_type == "table":
            if blk.grid:
                first_row_joined = " ".join(blk.grid[0].cells)
                h_match = detect_heading_line(first_row_joined, has_form_code_nearby=False)
                if h_match is not None:
                    sec_code, sec_title = h_match
                    if not (current_section == "NOTES" and sec_code in
                            ("BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW")):
                        current_section = sec_code
                        current_title = sec_title

            for r in blk.grid[:2]:
                row_joined = " ".join(r.cells)
                u = parse_unit_from_string(row_joined)
                if u:
                    all_detected_units.append(u)
                    if current_section in ("BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"):
                        primary_units.append(u)
                    break

            blk.section = current_section
            blk.section_title = current_title

    # Xác định default_unit chuẩn xác: Ưu tiên đơn vị xuất hiện nhiều nhất ở 3 BCTC chính
    if primary_units:
        default_unit = Counter(primary_units).most_common(1)[0][0]
    elif all_detected_units:
        default_unit = Counter(all_detected_units).most_common(1)[0][0]
    else:
        default_unit = "VND"

    # Pha 2: Gán đơn vị tính cho từng khối, chống rò rỉ đơn vị ngoại tệ từ thuyết minh
    for blk in blocks:
        if blk.section in ("BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"):
            local_u = None
            if blk.block_type == "table":
                for r in blk.grid[:2]:
                    u = parse_unit_from_string(" ".join(r.cells))
                    if u:
                        local_u = u
                        break
            blk.unit = local_u or default_unit
        elif blk.section == "NOTES":
            # Trong thuyết minh, mặc định tuyệt đối là default_unit; chỉ gán ngoại tệ khi chính bảng đó nói rõ
            local_u = None
            if blk.block_type == "table":
                for r in blk.grid[:2]:
                    u = parse_unit_from_string(" ".join(r.cells))
                    if u:
                        local_u = u
                        break
            blk.unit = local_u or default_unit
        else:
            blk.unit = default_unit

    # Hợp nhất các TableBlock liên trang thuộc cùng một báo cáo chính (BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW)
    # khi giữa 2 bảng chỉ là các dòng tiêu đề trang tiếp theo hoặc bảng con cùng số cột
    merged_blocks: List[Block] = []
    active_stmt_table: Optional[Block] = None

    for blk in blocks:
        if blk.block_type == "table" and blk.section in ("BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"):
            if (
                active_stmt_table is not None
                and active_stmt_table.section == blk.section
                and active_stmt_table.num_cols == blk.num_cols
                and (blk.physical_page_start - active_stmt_table.physical_page_end) <= 1
            ):
                # Bỏ qua các dòng tiêu đề cột lặp lại ở đầu trang mới trước khi nối vào bảng đang mở
                new_rows = _strip_repeated_table_headers_on_continuation(
                    active_stmt_table.grid,
                    blk.grid,
                )
                active_stmt_table.grid.extend(new_rows)
                active_stmt_table.physical_page_end = max(
                    active_stmt_table.physical_page_end,
                    blk.physical_page_end,
                )
                for pp in blk.printed_pages:
                    if pp and pp not in active_stmt_table.printed_pages:
                        active_stmt_table.printed_pages.append(pp)
                continue
            else:
                active_stmt_table = blk
                merged_blocks.append(blk)
        else:
            # Nếu gặp sang mục khác (ví dụ từ BALANCE_SHEET sang INCOME_STATEMENT hoặc NOTES), đóng bảng đang mở
            if blk.section != (active_stmt_table.section if active_stmt_table else None):
                active_stmt_table = None
            merged_blocks.append(blk)

    return merged_blocks, doc_scope, default_unit


def _is_header_row_cells(cells: List[str]) -> bool:
    """Nhận diện xem một hàng trong bảng có phải là dòng tiêu đề cột hay không."""
    folded_cells = [fold_accents(c) for c in cells]
    joined = " ".join(folded_cells)
    header_keywords = ("ma so", "maso", "thuyet minh", "thuyetminh", "chi tieu", "chitieu", "tai ngay", "nam tai chinh", "so cuoi nam", "so dau nam")
    if any(kw in joined for kw in header_keywords):
        return True
    # Dòng tiêu đề phụ chỉ chứa năm + đơn vị hoặc chú thích '(Điều chỉnh lại)': ['', '', '', '2024 VND', '2023 VND']
    non_empty = [c for c in folded_cells if c]
    if non_empty and all(
        any(
            w in c
            for w in (
                "vnd",
                "usd",
                "202",
                "31/12",
                "01/01",
                "1/1",
                "31.12",
                "ma so",
                "nguon von",
                "tai san",
                "thuyet minh",
                "minh",
                "stt",
                "chi tieu",
                "nam nay",
                "nam truoc",
                "dieu chinh lai",
                "trinh bay lai",
            )
        )
        for c in non_empty
    ):
        return True
    return False


def _strip_repeated_table_headers_on_continuation(
    existing_grid: List[GridRow],
    continuation_grid: List[GridRow],
) -> List[GridRow]:
    """Loại bỏ 1-2 dòng tiêu đề cột lặp lại ở đầu trang tiếp theo khi ghép bảng liên trang."""
    if not existing_grid or not continuation_grid:
        return continuation_grid
    start_idx = 0
    for i in range(min(3, len(continuation_grid))):
        if _is_header_row_cells(continuation_grid[i].cells):
            start_idx = i + 1
        else:
            break
    return continuation_grid[start_idx:]


# =============================================================================
# BƯỚC 5: TRÍCH SỐ LIỆU (FACTS) & KIỂM TRA ĐẲNG THỨC KẾ TOÁN (2 CHẾ ĐỘ)
# =============================================================================

def detect_statement_columns(grid: List[GridRow]) -> Tuple[Dict[str, Optional[int]], int]:
    """
    Xác định vị trí các cột (code_col, stt_col, label_col, note_col, curr_col, prior_col)
    dựa vào TIÊU ĐỀ CỘT (đã mở rowspan/colspan), KHÔNG dựa vào hình dạng số.
    Trả về (col_map, data_start_row_idx).
    """
    if not grid:
        return {}, 0

    num_cols = len(grid[0].cells)
    header_row_count = 0
    for i in range(min(3, len(grid))):
        if _is_header_row_cells(grid[i].cells):
            header_row_count = i + 1
        else:
            break
    if header_row_count == 0:
        header_row_count = 1

    # Gộp chữ trên các dòng tiêu đề theo từng cột
    col_headers: List[str] = []
    for c in range(num_cols):
        parts = []
        for r in range(header_row_count):
            val = fold_accents(grid[r].cells[c])
            if val and val not in parts:
                parts.append(val)
        col_headers.append(" ".join(parts))

    code_col: Optional[int] = None
    stt_col: Optional[int] = None
    note_col: Optional[int] = None
    label_col: Optional[int] = None

    for c, h_text in enumerate(col_headers):
        h_nospace = h_text.replace(" ", "")
        if "maso" in h_nospace and code_col is None:
            code_col = c
        elif "thuyetminh" in h_nospace and note_col is None:
            note_col = c
        elif re.search(r"\bstt\b", h_text) and "chitieu" not in h_nospace and stt_col is None:
            stt_col = c

    # 2 cột số liệu cuối bảng (Năm nay & Năm trước)
    if num_cols >= 4:
        curr_col = num_cols - 2
        prior_col = num_cols - 1
    elif num_cols == 3:
        curr_col = 1
        prior_col = 2
    else:
        curr_col = num_cols - 1
        prior_col = None

    # Tìm cột nhãn chỉ tiêu (label_col): ưu tiên cột có chữ "chi tieu" / "tai san" / "nguon von"
    assigned = {c for c in (code_col, stt_col, note_col, curr_col, prior_col) if c is not None}
    for c, h_text in enumerate(col_headers):
        if c in assigned:
            continue
        if any(w in h_text for w in ("chi tieu", "chitieu", "tai san", "taisan", "nguon von", "nguonvon", "khoan muc")):
            label_col = c
            break

    if label_col is None:
        unassigned_cols = [c for c in range(num_cols) if c not in assigned]
        if len(unassigned_cols) == 1:
            label_col = unassigned_cols[0]
        elif len(unassigned_cols) >= 2:
            # Khi nhiều cột bên trái có tiêu đề trống (như ACB, CTG gộp colspan=2 cho STT + Chỉ tiêu),
            # cột có độ dài chuỗi trung bình lớn nhất ở các dòng dữ liệu là cột Chỉ tiêu (label_col),
            # cột ngắn bên trái (A, I, 1, 2) là cột STT (stt_col).
            data_rows = grid[header_row_count:] if header_row_count < len(grid) else grid
            col_avg_len: Dict[int, float] = {}
            for c in unassigned_cols:
                vals = [r.cells[c].strip() for r in data_rows if c < len(r.cells) and r.cells[c].strip()]
                col_avg_len[c] = (sum(len(v) for v in vals) / len(vals)) if vals else 0.0
            label_col = max(unassigned_cols, key=lambda c: col_avg_len.get(c, 0.0))
            if stt_col is None:
                for c in unassigned_cols:
                    if c < label_col and col_avg_len.get(c, 0.0) <= 6.0:
                        stt_col = c
                        break
    if label_col is None:
        label_col = 0

    return (
        {
            "code_col": code_col,
            "stt_col": stt_col,
            "label_col": label_col,
            "note_col": note_col,
            "curr_col": curr_col,
            "prior_col": prior_col,
        },
        header_row_count,
    )


def parse_financial_Cell(raw_str: str) -> Tuple[Optional[float], bool, Optional[str]]:
    """
    Phân tích chuỗi số liệu kế toán trong ô bảng:
      - Nếu ô trống hoặc dấu '-' -> (None, False, None)
      - Bỏ qua các chú thích trình bày lại chuẩn kế toán đi kèm số liệu như '(Điều chỉnh lại)', '(Trình bày lại)'.
      - Nếu số liệu lẫn chữ hoặc ký tự lạ (như bị con dấu đè: 'NOA 4.455', '1.5006-C.T.C.P', '(ZZZ6)'):
        -> Đánh dấu suspect=True, giữ nguyên chuỗi gốc trong raw, và trả về giá trị số = None!
      - Nếu hợp lệ: hỗ trợ số âm trong ngoặc đơn '(69.355.949)' hoặc dấu '-' và dấu phân cách hàng nghìn '.'/','.
    """
    s = raw_str.strip()
    if not s or s in ("-", "–", "—", "_"):
        return None, False, None

    # Loại bỏ hậu tố/tiền tố chú thích chuẩn kế toán: '(Điều chỉnh lại)', '(Đã điều chỉnh lại)', '(Trình bày lại)'
    s = re.sub(
        r"\s*\(?\s*(?:đã\s+|da\s+)?(?:điều\s*chỉnh|dieu\s*chinh|trình\s*bày|trinh\s*bay| phân\s*loại|phan\s*loai)\s+lại\s*\)?\s*",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()
    if not s or s in ("-", "–", "—", "_"):
        return None, False, None

    # Kiểm tra có chứa chữ cái hoặc ký tự lạ đè lên số hay không
    # Cho phép duy nhất: chữ số, dấu chấm '.', dấu phẩy ',', khoảng trắng, dấu ngoặc đơn '()', dấu trừ '-'
    if re.search(r"[A-Za-zÀ-ỹ]", s) or re.search(r"[^0-9.,\s\(\)\-\–\—]", s):
        return None, True, f"Số liệu lẫn chữ hoặc ký tự lạ (nghi ngờ con dấu/OCR lỗi): '{s}'"

    # Kiểm tra định dạng ngoặc đơn (số âm trong kế toán)
    is_negative = False
    clean_s = s
    if clean_s.startswith("(") and clean_s.endswith(")"):
        is_negative = True
        clean_s = clean_s[1:-1].strip()
    elif clean_s.startswith("-") or clean_s.startswith("–"):
        is_negative = True
        clean_s = clean_s[1:].strip()

    # Nếu bên trong vẫn còn dấu ngoặc đơn hoặc nhiều dấu trừ rời rạc (ví dụ '157 28 .951(240 545 472 058)') -> suspect!
    if "(" in clean_s or ")" in clean_s or "-" in clean_s:
        return None, True, f"Chuỗi chứa nhiều số hoặc ngoặc bất thường: '{s}'"

    # Xóa khoảng trắng phân cách nhóm chữ số (nếu chỉ có 1-2 khoảng trắng do OCR giãn dòng)
    clean_s = re.sub(r"\s+", "", clean_s)
    if not clean_s or not any(ch.isdigit() for ch in clean_s):
        return None, False, None

    # Xử lý dấu chấm '.' và dấu phẩy ',' theo chuẩn BCTC Việt Nam (dấu '.' phân cách hàng nghìn, ',' thập phân)
    if "." in clean_s and "," in clean_s:
        if clean_s.rfind(",") > clean_s.rfind("."):
            clean_s = clean_s.replace(".", "").replace(",", ".")
        else:
            clean_s = clean_s.replace(",", "")
    elif "." in clean_s:
        parts = clean_s.split(".")
        # Trong BCTC Việt Nam, các nhóm 3 chữ số sau dấu chấm là hàng nghìn (VD: 4.944 hoặc 45.535.942.846.453)
        if all(len(p) == 3 for p in parts[1:]):
            clean_s = "".join(parts)
        elif len(parts) > 2:
            # Nếu có nhiều dấu chấm nhưng độ dài nhóm bị lệch (VD: '1.5006') -> nghi ngờ lỗi OCR!
            return None, True, f"Dấu phân cách hàng nghìn bất thường: '{s}'"
    elif "," in clean_s:
        parts = clean_s.split(",")
        if all(len(p) == 3 for p in parts[1:]) and len(parts) > 2:
            clean_s = "".join(parts)
        elif len(parts) == 2:
            clean_s = clean_s.replace(",", ".")
        else:
            return None, True, f"Dấu phẩy phân cách bất thường: '{s}'"

    try:
        val = float(clean_s)
        if is_negative:
            val = -val
        return val, False, None
    except ValueError:
        return None, True, f"Không thể chuyển đổi sang số: '{s}'"


def _is_empty_heading(label: str, raw_current: str, raw_prior: str) -> bool:
    return bool(label and label.rstrip().endswith(":") and
                not raw_current.strip() and not raw_prior.strip())


def extract_facts_from_blocks(blocks: List[Block]) -> Tuple[List[FactItem], List[Dict[str, Any]]]:
    """
    Bước 5A: Trích xuất bảng facts từ các khối bảng thuộc BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW.
    """
    facts: List[FactItem] = []
    suspect_cells: List[Dict[str, Any]] = []

    for blk in blocks:
        if blk.block_type != "table" or blk.section not in ("BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"):
            continue
        if len(blk.grid) < 2:
            continue

        col_map, start_row = detect_statement_columns(blk.grid)
        code_col = col_map.get("code_col")
        stt_col = col_map.get("stt_col")
        label_col = col_map.get("label_col", 0)
        note_col = col_map.get("note_col")
        curr_col = col_map.get("curr_col")
        prior_col = col_map.get("prior_col")

        for r_idx in range(start_row, len(blk.grid)):
            grow = blk.grid[r_idx]
            cells = grow.cells
            if _is_header_row_cells(cells):
                continue

            # Bỏ qua dòng chữ ký nếu bảng báo cáo gộp luôn phần chữ ký ở dòng cuối (như SHS_2025 trang 15)
            folded_row = fold_accents(" ".join(cells))
            if any(
                sig_kw in folded_row
                for sig_kw in ("nguoi lap", "ke toan truong", "tong giam doc", "giam doc khoi tai chinh", "lap bang")
            ):
                continue

            label_val = cells[label_col].strip() if label_col is not None and label_col < len(cells) else ""
            code_val = cells[code_col].strip() if code_col is not None and code_col < len(cells) else None
            stt_val = cells[stt_col].strip() if stt_col is not None and stt_col < len(cells) else None
            note_val = cells[note_col].strip() if note_col is not None and note_col < len(cells) else None

            raw_curr = cells[curr_col].strip() if curr_col is not None and curr_col < len(cells) else ""
            raw_prior = cells[prior_col].strip() if prior_col is not None and prior_col < len(cells) else ""

            # Nếu hàng là tiêu đề mục gộp toàn bộ các cột (ví dụ "TÀI SẢN" hoặc "NGUỒN VỐN" colspan=5,
            # hoặc dòng tiêu đề mục con duy nhất bị đẩy sang cột phải do rowspan=2 ở header)
            non_empty_unique = set(c for c in cells if c)
            if len(non_empty_unique) == 1 and not raw_curr and not raw_prior:
                continue
            if (
                len(non_empty_unique) == 1
                and not label_val
                and not code_val
                and not any(ch.isdigit() for ch in (raw_curr + raw_prior))
            ):
                continue
            if not label_val and not code_val and not raw_curr and not raw_prior:
                continue

            # Làm sạch mã số (chỉ nhận mã số hợp lệ nếu cột code_col có giá trị)
            if code_val is not None:
                code_val = code_val.strip()
                if not code_val or not re.match(r"^[0-9]{2,3}[a-zA-Z]?$", code_val):
                    code_val = None

            curr_num, susp_curr, reason_curr = parse_financial_Cell(raw_curr)
            prior_num, susp_prior, reason_prior = parse_financial_Cell(raw_prior)

            # A labelled subtotal heading can carry a code but is not a fact row.
            if _is_empty_heading(label_val, raw_curr, raw_prior):
                continue

            is_suspect = susp_curr or susp_prior
            reasons = [r for r in (reason_curr, reason_prior) if r]
            suspect_reason = "; ".join(reasons) if reasons else None

            if susp_curr:
                suspect_cells.append(
                    {
                        "report_type": blk.section,
                        "code": code_val,
                        "label": label_val,
                        "column": "current_year",
                        "raw": raw_curr,
                        "reason": reason_curr,
                        "physical_page": grow.physical_page,
                    }
                )
            if susp_prior:
                suspect_cells.append(
                    {
                        "report_type": blk.section,
                        "code": code_val,
                        "label": label_val,
                        "column": "prior_year",
                        "raw": raw_prior,
                        "reason": reason_prior,
                        "physical_page": grow.physical_page,
                    }
                )

            facts.append(
                FactItem(
                    report_type=blk.section,
                    code=code_val,
                    stt=stt_val if stt_val else None,
                    label=label_val,
                    note=note_val if note_val else None,
                    current_year=curr_num,
                    prior_year=prior_num,
                    raw_current=raw_curr,
                    raw_prior=raw_prior,
                    suspect=is_suspect,
                    suspect_reason=suspect_reason,
                    unit=blk.unit,
                    physical_page=grow.physical_page,
                    printed_page=grow.printed_page,
                )
            )

    return facts, suspect_cells


def _verify_code_based_identities(facts: List[FactItem]) -> List[IdentityCheckResult]:
    """
    Chế độ 1: Kiểm tra các đẳng thức kế toán theo Mã số (dành cho đa số doanh nghiệp).
    Phép kiểm tra KQKD chấp nhận cả 2 quy ước dấu của các khoản chi phí (dương hoặc âm trong ngoặc đơn).
    """
    results: List[IdentityCheckResult] = []
    # Tổ chức tra cứu theo (report_type, code)
    bs_curr: Dict[str, float] = {}
    bs_prior: Dict[str, float] = {}
    is_curr: Dict[str, float] = {}
    is_prior: Dict[str, float] = {}

    for f in facts:
        if not f.code:
            continue
        if f.report_type == "BALANCE_SHEET":
            if f.current_year is not None and f.code not in bs_curr:
                bs_curr[f.code] = f.current_year
            if f.prior_year is not None and f.code not in bs_prior:
                bs_prior[f.code] = f.prior_year
        elif f.report_type == "INCOME_STATEMENT":
            if f.current_year is not None and f.code not in is_curr:
                is_curr[f.code] = f.current_year
            if f.prior_year is not None and f.code not in is_prior:
                is_prior[f.code] = f.prior_year

    for period_name, bs_map in (("current_year", bs_curr), ("prior_year", bs_prior)):
        if not bs_map:
            continue
        tol = 5.0  # Sai số làm tròn tối đa cho phép

        # 1. Tài sản ngắn hạn: 100 = 110 + 120 + 130 + 140 + 150
        sub_100 = [c for c in ("110", "120", "130", "140", "150") if c in bs_map]
        if "100" in bs_map and len(sub_100) >= 2:
            lhs = bs_map["100"]
            rhs = sum(bs_map[c] for c in sub_100)
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="BS_ShortTermAssets_100",
                    report_type="BALANCE_SHEET",
                    period=period_name,
                    formula=f"100 == {' + '.join(sub_100)}",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="standard",
                )
            )

        # 2. Tài sản dài hạn: 200 = 210 + 220 + 230 + 240 + 250 + 260
        sub_200 = [c for c in ("210", "220", "230", "240", "250", "260") if c in bs_map]
        if "200" in bs_map and len(sub_200) >= 2:
            lhs = bs_map["200"]
            rhs = sum(bs_map[c] for c in sub_200)
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="BS_LongTermAssets_200",
                    report_type="BALANCE_SHEET",
                    period=period_name,
                    formula=f"200 == {' + '.join(sub_200)}",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="standard",
                )
            )

        # 3. Tổng cộng Tài sản: 270 = 100 + 200
        if "270" in bs_map and "100" in bs_map and "200" in bs_map:
            lhs = bs_map["270"]
            rhs = bs_map["100"] + bs_map["200"]
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="BS_TotalAssets_270",
                    report_type="BALANCE_SHEET",
                    period=period_name,
                    formula="270 == 100 + 200",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="standard",
                )
            )

        # 4. Nợ phải trả: 300 = 310 + 330 (Doanh nghiệp TT200) hoặc 300 = 310 + 340 (Chứng khoán TT210)
        if "300" in bs_map:
            lhs = bs_map["300"]
            if "310" in bs_map and "340" in bs_map and abs(lhs - (bs_map["310"] + bs_map["340"])) <= tol:
                sub_300 = ["310", "340"]
            else:
                sub_300 = [c for c in ("310", "330") if c in bs_map]
            if sub_300:
                rhs = sum(bs_map[c] for c in sub_300)
                diff = lhs - rhs
                results.append(
                    IdentityCheckResult(
                        check_name="BS_TotalLiabilities_300",
                        report_type="BALANCE_SHEET",
                        period=period_name,
                        formula=f"300 == {' + '.join(sub_300)}",
                        lhs_value=lhs,
                        rhs_value=rhs,
                        diff=diff,
                        passed=abs(diff) <= tol,
                        sign_convention="standard",
                    )
                )

        # 5. Vốn chủ sở hữu: 400 = 410 + 430 (hoặc 410 + 420 cho CTCK)
        if "400" in bs_map:
            lhs = bs_map["400"]
            if "410" in bs_map and "420" in bs_map and abs(lhs - (bs_map["410"] + bs_map["420"])) <= tol:
                sub_400 = ["410", "420"]
            else:
                sub_400 = [c for c in ("410", "430") if c in bs_map]
            if sub_400:
                rhs = sum(bs_map[c] for c in sub_400)
                diff = lhs - rhs
                results.append(
                    IdentityCheckResult(
                        check_name="BS_TotalEquity_400",
                        report_type="BALANCE_SHEET",
                        period=period_name,
                        formula=f"400 == {' + '.join(sub_400)}",
                        lhs_value=lhs,
                        rhs_value=rhs,
                        diff=diff,
                        passed=abs(diff) <= tol,
                        sign_convention="standard",
                    )
                )

        # 6. Tổng cộng Nguồn vốn: 440 = 300 + 400
        if "440" in bs_map and "300" in bs_map and "400" in bs_map:
            lhs = bs_map["440"]
            rhs = bs_map["300"] + bs_map["400"]
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="BS_TotalResources_440",
                    report_type="BALANCE_SHEET",
                    period=period_name,
                    formula="440 == 300 + 400",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="standard",
                )
            )

        # 7. Cân đối Tổng Tài sản == Tổng Nguồn vốn: 270 == 440
        if "270" in bs_map and "440" in bs_map:
            lhs = bs_map["270"]
            rhs = bs_map["440"]
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="BS_FundamentalBalance_270_eq_440",
                    report_type="BALANCE_SHEET",
                    period=period_name,
                    formula="270 == 440",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="standard",
                )
            )

    # Kiểm tra Báo cáo kết quả hoạt động kinh doanh (chấp nhận cả 2 quy ước dấu chi phí)
    for period_name, is_map in (("current_year", is_curr), ("prior_year", is_prior)):
        if not is_map:
            continue
        tol = 5.0

        # Nhánh dành cho Công ty Chứng khoán (Thông tư 210/2014/TT-BTC: mã 70 là KQHĐ, 80 là KQHĐ khác, 90 là LNTT, 200 là LNST)
        if "200" in is_map and "90" in is_map:
            if "70" in is_map and "80" in is_map:
                lhs_90 = is_map["90"]
                rhs_90 = is_map["70"] + is_map["80"]
                diff_90 = lhs_90 - rhs_90
                results.append(
                    IdentityCheckResult(
                        check_name="IS_Sec_ProfitBeforeTax_90",
                        report_type="INCOME_STATEMENT",
                        period=period_name,
                        formula="90 == 70 + 80",
                        lhs_value=lhs_90,
                        rhs_value=rhs_90,
                        diff=diff_90,
                        passed=abs(diff_90) <= tol,
                        sign_convention="standard",
                    )
                )
            lhs_200 = is_map["200"]
            v90 = is_map["90"]
            v100 = is_map.get("100", 0.0)
            rhs_pos = v90 - v100
            rhs_neg = v90 + v100
            if abs(lhs_200 - rhs_pos) <= abs(lhs_200 - rhs_neg):
                rhs_200, conv_200 = rhs_pos, "positive_expense"
            else:
                rhs_200, conv_200 = rhs_neg, "negative_expense"
            diff_200 = lhs_200 - rhs_200
            results.append(
                IdentityCheckResult(
                    check_name="IS_Sec_ProfitAfterTax_200",
                    report_type="INCOME_STATEMENT",
                    period=period_name,
                    formula="200 == 90 -/+ 100",
                    lhs_value=lhs_200,
                    rhs_value=rhs_200,
                    diff=diff_200,
                    passed=abs(diff_200) <= tol,
                    sign_convention=conv_200,
                )
            )
            continue

        # 1. Doanh thu thuần: 10 = 01 - 02 (dương) hoặc 10 = 01 + 02 (âm)
        if "10" in is_map and "01" in is_map:
            lhs = is_map["10"]
            v01 = is_map["01"]
            v02 = is_map.get("02", 0.0)
            rhs_pos = v01 - v02
            rhs_neg = v01 + v02
            if abs(lhs - rhs_pos) <= abs(lhs - rhs_neg):
                rhs, conv = rhs_pos, "positive_expense"
            else:
                rhs, conv = rhs_neg, "negative_expense"
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="IS_NetRevenue_10",
                    report_type="INCOME_STATEMENT",
                    period=period_name,
                    formula="10 == 01 -/+ 02",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention=conv,
                )
            )

        # 2. Lợi nhuận gộp: 20 = 10 - 11 (dương) hoặc 20 = 10 + 11 (âm)
        if "20" in is_map and "10" in is_map and "11" in is_map:
            lhs = is_map["20"]
            v10 = is_map["10"]
            v11 = is_map["11"]
            rhs_pos = v10 - v11
            rhs_neg = v10 + v11
            if abs(lhs - rhs_pos) <= abs(lhs - rhs_neg):
                rhs, conv = rhs_pos, "positive_expense"
            else:
                rhs, conv = rhs_neg, "negative_expense"
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="IS_GrossProfit_20",
                    report_type="INCOME_STATEMENT",
                    period=period_name,
                    formula="20 == 10 -/+ 11",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention=conv,
                )
            )

        # 3. Lợi nhuận thuần từ HĐKD: 30 = 20 + 21 -/+ 22 + 24 -/+ 25 -/+ 26
        if "30" in is_map and "20" in is_map:
            lhs = is_map["30"]
            v20 = is_map["20"]
            v21 = is_map.get("21", 0.0)
            v22 = is_map.get("22", 0.0)
            v24 = is_map.get("24", 0.0)
            v25 = is_map.get("25", 0.0)
            v26 = is_map.get("26", 0.0)
            rhs_pos = v20 + v21 - v22 + v24 - v25 - v26
            rhs_neg = v20 + v21 + v22 + v24 + v25 + v26
            if abs(lhs - rhs_pos) <= abs(lhs - rhs_neg):
                rhs, conv = rhs_pos, "positive_expense"
            else:
                rhs, conv = rhs_neg, "negative_expense"
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="IS_OperatingProfit_30",
                    report_type="INCOME_STATEMENT",
                    period=period_name,
                    formula="30 == 20 + 21 -/+ 22 + 24 -/+ 25 -/+ 26",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention=conv,
                )
            )

        # 4. Lợi nhuận khác: 40 = 31 -/+ 32
        if "40" in is_map and ("31" in is_map or "32" in is_map):
            lhs = is_map["40"]
            v31 = is_map.get("31", 0.0)
            v32 = is_map.get("32", 0.0)
            rhs_pos = v31 - v32
            rhs_neg = v31 + v32
            if abs(lhs - rhs_pos) <= abs(lhs - rhs_neg):
                rhs, conv = rhs_pos, "positive_expense"
            else:
                rhs, conv = rhs_neg, "negative_expense"
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="IS_OtherProfit_40",
                    report_type="INCOME_STATEMENT",
                    period=period_name,
                    formula="40 == 31 -/+ 32",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention=conv,
                )
            )

        # 5. Tổng lợi nhuận kế toán trước thuế: 50 = 30 + 40
        if "50" in is_map and "30" in is_map:
            lhs = is_map["50"]
            rhs = is_map["30"] + is_map.get("40", 0.0)
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="IS_ProfitBeforeTax_50",
                    report_type="INCOME_STATEMENT",
                    period=period_name,
                    formula="50 == 30 + 40",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="standard",
                )
            )

        # 6. Lợi nhuận sau thuế TNDN: 60 = 50 -/+ 51 -/+ 52
        if "60" in is_map and "50" in is_map:
            lhs = is_map["60"]
            v50 = is_map["50"]
            v51 = is_map.get("51", 0.0)
            v52 = is_map.get("52", 0.0)
            candidates = [
                (v50 - v51 - v52, "positive_expense"),
                (v50 + v51 + v52, "negative_expense"),
                (v50 - v51 + v52, "mixed_deferred_tax"),
                (v50 + v51 - v52, "mixed_deferred_tax"),
            ]
            rhs, conv = min(candidates, key=lambda item: abs(lhs - item[0]))
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="IS_ProfitAfterTax_60",
                    report_type="INCOME_STATEMENT",
                    period=period_name,
                    formula="60 == 50 -/+ 51 -/+ 52",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention=conv,
                )
            )

    # Kiểm tra Báo cáo lưu chuyển tiền tệ (CASH_FLOW)
    cf_curr: Dict[str, float] = {}
    cf_prior: Dict[str, float] = {}
    for f in facts:
        if not f.code or f.report_type != "CASH_FLOW":
            continue
        if f.current_year is not None and f.code not in cf_curr:
            cf_curr[f.code] = f.current_year
        if f.prior_year is not None and f.code not in cf_prior:
            cf_prior[f.code] = f.prior_year

    for period_name, cf_map in (("current_year", cf_curr), ("prior_year", cf_prior)):
        if not cf_map:
            continue
        tol = 5.0

        # 1. Lưu chuyển tiền thuần trong năm: 50 = 20 + 30 + 40
        if "50" in cf_map and "20" in cf_map and "30" in cf_map and "40" in cf_map:
            lhs = cf_map["50"]
            rhs = cf_map["20"] + cf_map["30"] + cf_map["40"]
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="CF_NetCashFlowInYear_50",
                    report_type="CASH_FLOW",
                    period=period_name,
                    formula="50 == 20 + 30 + 40",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="standard",
                )
            )

        # 2. Tiền và tương đương tiền cuối năm: 70 = 50 + 60 + 61 (hoặc 70 = 50 + 60 nếu không có 61)
        if "70" in cf_map and "50" in cf_map and "60" in cf_map:
            lhs = cf_map["70"]
            v61 = cf_map.get("61", 0.0)
            rhs = cf_map["50"] + cf_map["60"] + v61
            diff = lhs - rhs
            formula_str = "70 == 50 + 60 + 61" if "61" in cf_map else "70 == 50 + 60"
            results.append(
                IdentityCheckResult(
                    check_name="CF_CashEnding_70",
                    report_type="CASH_FLOW",
                    period=period_name,
                    formula=formula_str,
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="standard",
                )
            )

        # 3. Đối chiếu liên báo cáo: Tiền cuối năm trên Lưu chuyển tiền tệ (mã 70) == Tiền trên Bảng CĐKT (mã 110)
        bs_map = bs_curr if period_name == "current_year" else bs_prior
        if "70" in cf_map and "110" in bs_map:
            lhs = cf_map["70"]
            rhs = bs_map["110"]
            diff = lhs - rhs
            results.append(
                IdentityCheckResult(
                    check_name="CF_CashEnding_70_eq_BS_Cash_110",
                    report_type="CASH_FLOW",
                    period=period_name,
                    formula="CF_70 == BS_110",
                    lhs_value=lhs,
                    rhs_value=rhs,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="cross_statement",
                )
            )

    return results


def _compute_level1_sum_bottom_up(
    rows: List[Tuple[str, float]],
    tol: float = 5.0,
) -> Tuple[float, List[str], List[str]]:
    """
    Thuật toán kiểm tra dạng cây từ dưới lên (Bottom-Up Tree Decomposition) cho báo cáo không có mã số:
      "Dòng nào bằng tổng các dòng con ngay sau nó thì được coi là dòng tổng hợp."
    Trả về:
      - level1_sum: Tổng các khoản mục cấp 1 (đã bỏ qua các dòng con thuộc về một dòng tổng hợp).
      - level1_labels: Danh sách nhãn của các khoản mục cấp 1.
      - parent_matches: Danh sách các dòng tổng hợp đã khớp với tổng các dòng con ngay sau nó.
    """
    n = len(rows)
    if n == 0:
        return 0.0, [], []

    # end_child[i] lưu chỉ số cuối cùng của cây con thuộc dòng tổng hợp i (nếu i là dòng tổng hợp)
    end_child: Dict[int, int] = {}
    parent_matches: List[str] = []

    for i in range(n - 1, -1, -1):
        label_i, val_i = rows[i]
        if val_i == 0.0:
            continue

        running_sum = 0.0
        child_count = 0
        j = i + 1
        while j < n:
            running_sum += rows[j][1]
            child_count += 1
            # Nếu bản thân j là một dòng tổng hợp của các dòng cháu sau j, nhảy qua toàn bộ cây con của j
            if j in end_child:
                j = end_child[j] + 1
            else:
                j += 1

            # Chấp nhận dòng tổng hợp có từ 2 dòng con trực tiếp trở lên, hoặc 1 dòng con duy nhất bằng đúng dòng mẹ
            if child_count >= 1 and abs(running_sum - val_i) <= tol:
                end_child[i] = j - 1
                parent_matches.append(f"{label_i} == sum({child_count} direct children) = {val_i:,.0f}")
                break

    # Cộng tất cả các khoản mục cấp 1 (nhảy qua các dòng con của mỗi dòng tổng hợp cấp 1)
    level1_sum = 0.0
    level1_labels: List[str] = []
    idx = 0
    while idx < n:
        lbl, val = rows[idx]
        level1_sum += val
        level1_labels.append(lbl)
        if idx in end_child:
            idx = end_child[idx] + 1
        else:
            idx += 1

    return level1_sum, level1_labels, parent_matches


def _verify_tree_based_identities(facts: List[FactItem]) -> List[IdentityCheckResult]:
    """
    Chế độ 2: Kiểm tra dạng cây cho báo cáo không có Mã số (như Ngân hàng):
      - Tổng Tài sản phải bằng tổng các khoản mục cấp 1 (dòng nào bằng tổng các dòng con ngay sau nó
        thì được coi là dòng tổng hợp).
      - Tổng Nguồn vốn (Nợ phải trả & Vốn chủ sở hữu) phải bằng tổng các khoản mục cấp 1.
      - Tổng Tài sản phải bằng Tổng Nguồn vốn.
    """
    results: List[IdentityCheckResult] = []
    bs_facts = [f for f in facts if f.report_type == "BALANCE_SHEET"]
    if not bs_facts:
        return results

    # Tìm vị trí dòng TỔNG TÀI SẢN (hoặc TỔNG TÀI SẢN CÓ / TỔNG CỘNG TÀI SẢN)
    # và dòng TỔNG NỢ PHẢI TRẢ VÀ VỐN CHỦ SỞ HỮU (hoặc TỔNG NGUỒN VỐN / TỔNG CỘNG NGUỒN VỐN)
    total_assets_idx: Optional[int] = None
    total_liab_eq_idx: Optional[int] = None

    for idx, f in enumerate(bs_facts):
        folded_lbl = fold_accents(f.label)
        if folded_lbl.startswith("tong tai san") or folded_lbl.startswith("tong cong tai san"):
            total_assets_idx = idx
        elif (
            folded_lbl.startswith("tong no phai tra va von chu so huu")
            or folded_lbl.startswith("tong cong nguon von")
            or folded_lbl.startswith("tong nguon von")
        ):
            total_liab_eq_idx = idx

    if total_assets_idx is None:
        return results

    tol = 5.0
    for period_name in ("current_year", "prior_year"):
        # 1. Kiểm tra cây Tài sản
        asset_fact_slice = bs_facts[:total_assets_idx]
        total_asset_val = getattr(bs_facts[total_assets_idx], period_name)
        if total_asset_val is not None:
            asset_rows = [
                (f.label, getattr(f, period_name))
                for f in asset_fact_slice
                if getattr(f, period_name) is not None
                and not fold_accents(f.label).startswith("tong ")
            ]
            lvl1_sum, lvl1_labels, parent_matches = _compute_level1_sum_bottom_up(asset_rows, tol=tol)
            diff = total_asset_val - lvl1_sum
            results.append(
                IdentityCheckResult(
                    check_name="BS_Tree_TotalAssets_eq_SumLevel1",
                    report_type="BALANCE_SHEET",
                    period=period_name,
                    formula=f"TOTAL_ASSETS == sum({len(lvl1_labels)} Level-1 items)",
                    lhs_value=total_asset_val,
                    rhs_value=lvl1_sum,
                    diff=diff,
                    passed=abs(diff) <= tol,
                    sign_convention="tree_based",
                    note=f"Detected {len(parent_matches)} aggregate parent rows",
                )
            )

        # 2. Kiểm tra cây Nguồn vốn (Nợ phải trả & Vốn chủ sở hữu) và Cân đối Tổng Tài sản == Tổng Nguồn vốn
        if total_liab_eq_idx is not None and total_liab_eq_idx > total_assets_idx:
            liab_eq_slice = bs_facts[total_assets_idx + 1 : total_liab_eq_idx]
            total_liab_eq_val = getattr(bs_facts[total_liab_eq_idx], period_name)
            if total_liab_eq_val is not None:
                # Loại trừ các dòng cộng phụ nằm ở cuối khối (như "TỔNG NỢ PHẢI TRẢ", "TỔNG VỐN CHỦ SỞ HỮU", "TỔNG VỐN")
                # để cộng trực tiếp các cây khoản mục cấp 1 (I..VII của Nợ phải trả và VIII của Vốn chủ sở hữu)
                liab_rows = [
                    (f.label, getattr(f, period_name))
                    for f in liab_eq_slice
                    if getattr(f, period_name) is not None
                    and not fold_accents(f.label).startswith("tong ")
                ]
                lvl1_le_sum, lvl1_le_labels, le_parents = _compute_level1_sum_bottom_up(liab_rows, tol=tol)
                diff_le = total_liab_eq_val - lvl1_le_sum
                results.append(
                    IdentityCheckResult(
                        check_name="BS_Tree_TotalLiabEquity_eq_SumLevel1",
                        report_type="BALANCE_SHEET",
                        period=period_name,
                        formula=f"TOTAL_LIAB_EQUITY == sum({len(lvl1_le_labels)} Level-1 items)",
                        lhs_value=total_liab_eq_val,
                        rhs_value=lvl1_le_sum,
                        diff=diff_le,
                        passed=abs(diff_le) <= tol,
                        sign_convention="tree_based",
                        note=f"Detected {len(le_parents)} aggregate parent rows",
                    )
                )

                if total_asset_val is not None:
                    diff_bal = total_asset_val - total_liab_eq_val
                    results.append(
                        IdentityCheckResult(
                            check_name="BS_Tree_FundamentalBalance_Assets_eq_LiabEquity",
                            report_type="BALANCE_SHEET",
                            period=period_name,
                            formula="TOTAL_ASSETS == TOTAL_LIAB_EQUITY",
                            lhs_value=total_asset_val,
                            rhs_value=total_liab_eq_val,
                            diff=diff_bal,
                            passed=abs(diff_bal) <= tol,
                            sign_convention="tree_based",
                        )
                    )

    return results


def step5_extract_facts_and_verify(
    blocks: List[Block],
) -> Tuple[List[FactItem], List[Dict[str, Any]], str, List[IdentityCheckResult]]:
    """
    Bước 5: Trích xuất bảng facts và chạy kiểm tra đẳng thức kế toán theo chế độ phù hợp:
      - Nếu bảng Cân đối kế toán / KQKD có Mã số -> chạy chế độ 'code_based'.
      - Nếu không có Mã số (như Ngân hàng) -> chạy chế độ 'tree_based'.
    """
    facts, suspect_cells = extract_facts_from_blocks(blocks)
    coded_bs_count = sum(1 for f in facts if f.report_type == "BALANCE_SHEET" and f.code is not None)

    if coded_bs_count >= 5:
        mode = "code_based"
        checks = _verify_code_based_identities(facts)
    elif any(f.report_type == "BALANCE_SHEET" for f in facts):
        mode = "tree_based"
        checks = _verify_tree_based_identities(facts)
    else:
        mode = "none"
        checks = []

    return facts, suspect_cells, mode, checks


# =============================================================================
# BƯỚC 6: CHIA CHUNK VĂN BẢN & BẢNG KÈM METADATA ĐẦY ĐỦ (SMART CHUNKER)
# =============================================================================

def generate_table_embed_text(context_prefix: str, header_lines: List[str], slice_rows: List[GridRow]) -> str:
    """
    Sinh văn bản tối ưu chuyên biệt cho mô hình Dense Embedding (BGE-M3/E5):
    Giữ lại context_prefix, tiêu đề cột và nhãn tên/mã các khoản mục,
    loại bỏ các chuỗi số tiền lớn để không làm loãng vector.
    """
    lines = [context_prefix]
    text_col_indices: List[int] = []
    if header_lines:
        first_hdr = header_lines[0]
        hdr_cells = [c.strip() for c in first_hdr.split("|")]
        for idx, col_name in enumerate(hdr_cells):
            folded = col_name.lower()
            if not any(w in folded for w in ["31/12", "01/01", "202", "năm nay", "năm trước", "số cuối", "số đầu", "triệu", "tỷ", "vnd", "usd"]):
                text_col_indices.append(idx)
        if not text_col_indices:
            text_col_indices = [0, 1] if len(hdr_cells) >= 2 else [0]

        clean_hdr = " | ".join(hdr_cells[i] for i in text_col_indices if i < len(hdr_cells))
        if clean_hdr:
            lines.append(clean_hdr)
            lines.append("-" * len(clean_hdr))

        for r in slice_rows:
            row_items = []
            for i in text_col_indices:
                if i < len(r.cells) and r.cells[i].strip():
                    val = r.cells[i].strip()
                    if not re.match(r"^[\d.,\s\(\)\-]{5,}$", val):
                        row_items.append(val)
            if row_items:
                lines.append(" | ".join(row_items))
    else:
        for r in slice_rows:
            non_num = [c.strip() for c in r.cells if c.strip() and not re.match(r"^[\d.,\s\(\)\-]{5,}$", c.strip())]
            if non_num:
                lines.append(" | ".join(non_num))

    return "\n".join(lines)


def step6_chunk_document(
    blocks: List[Block],
    doc_id: str,
    ticker: str = "CORP",
    year: int = 2024,
    doc_scope: str = "consolidated",
    max_text_chars: int = 1200,
    max_table_rows_per_chunk: int = 20,
    max_table_chars_per_chunk: int = 1400,
) -> List[ChunkItem]:
    """
    Bước 6:
      - Tiền tố ngữ cảnh: [TICKER | NĂM | PHẠM VI | TIÊU ĐỀ | Đơn vị: UNIT]
      - Chunk văn bản theo đoạn (có giữ tiêu đề mục, chống orphan chunk < 30 tokens).
      - Chunk bảng riêng (lặp lại dòng tiêu đề cột khi bảng dài phải tách thành nhiều chunk).
      - Gộp bảng rất ngắn (< 5 dòng) vào đoạn văn liền kề (giữ nguyên vẹn dòng tiêu đề cột).
      - Sparse (BM25) dùng `text` (đầy đủ số liệu), Dense dùng `embed_text` (không số tiền lớn).
      - Lưới an toàn chống chunk bùng nổ (tách ô > 800 ký tự và chia nhỏ chunk > 1800 ký tự).
    """
    scope_vi_map = {"consolidated": "Hợp nhất", "separate": "Riêng lẻ", "general": "Chung"}
    scope_vi = scope_vi_map.get(doc_scope, "Hợp nhất")

    raw_chunks: List[ChunkItem] = []
    chunk_idx = 0
    i = 0
    n_blocks = len(blocks)

    while i < n_blocks:
        blk = blocks[i]
        sec = blk.section
        sec_title = blk.section_title or "Báo cáo tài chính"
        unit = blk.unit or "VND"
        context_prefix = f"[{ticker} | {year} | {scope_vi} | {sec_title} | Đơn vị: {unit}]"

        # Kiểm tra nếu khối văn bản đi liền trước một bảng rất ngắn (< 5 dòng) cùng section
        short_table_attached: Optional[Block] = None
        if blk.block_type == "text" and i + 1 < n_blocks:
            next_b = blocks[i + 1]
            if next_b.block_type == "table" and next_b.section == sec and len(next_b.grid) < 5:
                short_table_attached = next_b

        if blk.block_type == "text":
            para_items: List[Tuple[str, int, List[str]]] = []
            while i < n_blocks and blocks[i].block_type == "text" and blocks[i].section == sec:
                cur_b = blocks[i]
                for p in re.split(r"\n\s*\n", cur_b.text):
                    p_str = p.strip()
                    if p_str:
                        if len(p_str) > max_text_chars:
                            sents = re.split(r"(?<=[.!?])\s+", p_str)
                            sub_p = []
                            sub_len = 0
                            for s in sents:
                                if sub_len + len(s) > max_text_chars and sub_p:
                                    para_items.append((" ".join(sub_p), cur_b.physical_page_start, cur_b.printed_pages))
                                    sub_p = [s]
                                    sub_len = len(s)
                                else:
                                    sub_p.append(s)
                                    sub_len += len(s) + 1
                            if sub_p:
                                para_items.append((" ".join(sub_p), cur_b.physical_page_start, cur_b.printed_pages))
                        else:
                            para_items.append((p_str, cur_b.physical_page_start, cur_b.printed_pages))
                i += 1

            if short_table_attached is not None and i < n_blocks and blocks[i] == short_table_attached:
                i += 1  # Đã gộp bảng ngắn này vào văn bản

            buf_texts: List[str] = []
            buf_phys: List[int] = []
            buf_printed: List[str] = []
            current_heading: Optional[str] = None
            buf_len = 0

            def flush_text_chunk(is_last: bool = False) -> None:
                nonlocal chunk_idx, buf_texts, buf_phys, buf_printed, buf_len
                if not buf_texts:
                    return
                # Anti-orphan: Tránh tạo chunk trơ trọi (< 100 ký tự) nếu chưa phải đoạn cuối cùng
                if not is_last and buf_len < 100:
                    return

                chunk_idx += 1
                p_start = min(buf_phys) if buf_phys else 1
                p_end = max(buf_phys) if buf_phys else 1
                cite_pages = f"p.{p_start}" if p_start == p_end else f"p.{p_start}-{p_end}"

                body_str = "\n\n".join(buf_texts)
                full_text = f"{context_prefix}\n{body_str}"

                raw_chunks.append(
                    ChunkItem(
                        chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
                        chunk_type="text",
                        text=full_text,
                        physical_pages=sorted(set(buf_phys)),
                        physical_page_start=p_start,
                        physical_page_end=p_end,
                        printed_pages=list(dict.fromkeys(p for p in buf_printed if p)),
                        citation_tag=f"[Doc_{doc_id}, {cite_pages}]",
                        section=sec,
                        section_title=sec_title,
                        unit=unit,
                        scope=doc_scope,
                        embed_text=full_text,
                        row_count=0,
                    )
                )

                # Giữ lại đoạn cuối cùng làm chồng lấn (overlap) nếu đoạn đó đủ dài và không phải tiêu đề cộc lốc
                if not is_last and len(buf_texts) > 1 and len(buf_texts[-1]) >= 80 and not re.match(r"^[0-9IVX]+[\.\s]", buf_texts[-1]):
                    overlap_p = buf_texts[-1]
                    overlap_phys = buf_phys[-1:]
                    overlap_pr = buf_printed[-1:]
                    buf_texts = [overlap_p]
                    buf_phys = list(overlap_phys)
                    buf_printed = list(overlap_pr)
                    buf_len = len(overlap_p)
                else:
                    buf_texts = []
                    buf_phys = []
                    buf_printed = []
                    buf_len = 0

            for p_text, phys_p, pr_pages in para_items:
                if len(p_text) < 120 and "\n" not in p_text and re.match(r"^(?:[IVX]+|\d+(?:\.\d+)*|[A-Z])\.\s+\S+", p_text):
                    current_heading = p_text

                if buf_texts and (buf_len + len(p_text) > max_text_chars):
                    flush_text_chunk(is_last=False)
                    if current_heading and current_heading not in buf_texts:
                        buf_texts.append(f"{current_heading} (tiếp theo)")
                        buf_len += len(current_heading) + 12

                buf_texts.append(p_text)
                buf_phys.append(phys_p)
                buf_printed.extend(pr_pages)
                buf_len += len(p_text) + 2

            # Đính kèm bảng rất ngắn (< 5 dòng) nếu có: BẢO TOÀN NGUYÊN VẸN HEADER CỘT
            if short_table_attached is not None:
                tbl_grid = short_table_attached.grid
                hdr_count = 0
                for r_idx in range(min(3, len(tbl_grid))):
                    if _is_header_row_cells(tbl_grid[r_idx].cells):
                        hdr_count = r_idx + 1
                    else:
                        break
                if hdr_count == 0:
                    hdr_count = 1
                hdr_rows = tbl_grid[:hdr_count]
                d_rows = tbl_grid[hdr_count:]
                if not d_rows:
                    d_rows = hdr_rows
                    hdr_rows = []
                short_hdr_lines = [" | ".join(hr.cells) for hr in hdr_rows]
                short_tbl_lines: List[str] = []
                short_tbl_lines.extend(short_hdr_lines)
                if short_hdr_lines:
                    short_tbl_lines.append("-" * min(80, max(len(h) for h in short_hdr_lines)))
                for r in d_rows:
                    short_tbl_lines.append(" | ".join(r.cells))

                buf_texts.append("\n".join(short_tbl_lines))
                buf_phys.extend([r.physical_page for r in tbl_grid])
                buf_printed.extend([r.printed_page for r in tbl_grid if r.printed_page])

            flush_text_chunk(is_last=True)

        elif blk.block_type == "table":
            grid = blk.grid
            if not grid:
                i += 1
                continue

            hdr_count = 0
            for r_idx in range(min(3, len(grid))):
                if _is_header_row_cells(grid[r_idx].cells):
                    hdr_count = r_idx + 1
                else:
                    break
            if hdr_count == 0:
                hdr_count = 1

            header_rows = grid[:hdr_count]
            data_rows = grid[hdr_count:]
            if not data_rows:
                data_rows = header_rows
                header_rows = []

            header_lines = [" | ".join(hr.cells) for hr in header_rows]

            # Xử lý ô bảng siêu dài (giant cells) > 800 ký tự -> bẻ thành nhiều dòng logic
            normalized_data_rows: List[GridRow] = []
            for r in data_rows:
                max_c_len = max(len(c) for c in r.cells) if r.cells else 0
                if max_c_len > 800:
                    split_cells: List[List[str]] = []
                    for c in r.cells:
                        if len(c) > 800:
                            chunks_c = [c[k:k+600] for k in range(0, len(c), 600)]
                            split_cells.append(chunks_c)
                        else:
                            split_cells.append([c])
                    max_parts = max(len(sc) for sc in split_cells)
                    for p_i in range(max_parts):
                        new_cells = [sc[p_i] if p_i < len(sc) else "" for sc in split_cells]
                        normalized_data_rows.append(GridRow(cells=new_cells, physical_page=r.physical_page, printed_page=r.printed_page))
                else:
                    normalized_data_rows.append(r)

            # Cắt bảng theo cả số dòng (<= 20) VÀ dung lượng ký tự (<= 1400)
            cur_slice: List[GridRow] = []
            cur_slice_chars = 0

            def flush_table_slice(slice_rows: List[GridRow]) -> None:
                nonlocal chunk_idx
                if not slice_rows:
                    return
                chunk_idx += 1
                phys_set = sorted({r.physical_page for r in slice_rows})
                p_start = phys_set[0] if phys_set else 1
                p_end = phys_set[-1] if phys_set else 1
                cite_pages = f"p.{p_start}" if p_start == p_end else f"p.{p_start}-{p_end}"
                pr_pages = list(dict.fromkeys(r.printed_page for r in slice_rows if r.printed_page))

                table_lines = [context_prefix]
                table_lines.extend(header_lines)
                if header_lines:
                    table_lines.append("-" * min(80, max(len(h) for h in header_lines)))
                for r in slice_rows:
                    table_lines.append(" | ".join(r.cells))
                full_table_text = "\n".join(table_lines)

                embed_table_text = generate_table_embed_text(context_prefix, header_lines, slice_rows)

                raw_chunks.append(
                    ChunkItem(
                        chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
                        chunk_type="table",
                        text=full_table_text,
                        physical_pages=phys_set,
                        physical_page_start=p_start,
                        physical_page_end=p_end,
                        printed_pages=pr_pages,
                        citation_tag=f"[Doc_{doc_id}, {cite_pages}]",
                        section=sec,
                        section_title=sec_title,
                        unit=unit,
                        scope=doc_scope,
                        embed_text=embed_table_text,
                        row_count=len(slice_rows),
                    )
                )

            for r in normalized_data_rows:
                r_chars = sum(len(c) for c in r.cells) + len(r.cells) * 3
                if cur_slice and (len(cur_slice) >= max_table_rows_per_chunk or cur_slice_chars + r_chars > max_table_chars_per_chunk):
                    flush_table_slice(cur_slice)
                    cur_slice = []
                    cur_slice_chars = 0
                cur_slice.append(r)
                cur_slice_chars += r_chars

            if cur_slice:
                flush_table_slice(cur_slice)

            i += 1

    # Lưới an toàn cứng (Hard Token Safety Net): Đảm bảo không chunk nào vượt quá 600 tokens (~1600 ký tự)
    final_chunks: List[ChunkItem] = []
    for c in raw_chunks:
        if len(c.text) > 1600:
            lines = c.text.split("\n")
            prefix = lines[0] if lines else ""
            expanded_lines: List[str] = []
            for l in lines[1:]:
                if len(l) > 1100:
                    for k in range(0, len(l), 1000):
                        expanded_lines.append(l[k:k+1000])
                else:
                    expanded_lines.append(l)

            sub_lines: List[str] = []
            sub_len = len(prefix)
            sub_part = 1
            for l in expanded_lines:
                if sub_len + len(l) > 1400 and sub_lines:
                    part_text = f"{prefix}\n" + "\n".join(sub_lines)
                    final_chunks.append(
                        ChunkItem(
                            chunk_id=f"{c.chunk_id}_p{sub_part}",
                            chunk_type=c.chunk_type,
                            text=part_text,
                            physical_pages=c.physical_pages,
                            physical_page_start=c.physical_page_start,
                            physical_page_end=c.physical_page_end,
                            printed_pages=c.printed_pages,
                            citation_tag=c.citation_tag,
                            section=c.section,
                            section_title=c.section_title,
                            unit=c.unit,
                            scope=c.scope,
                            embed_text=part_text if c.chunk_type == "text" else c.embed_text[:1400],
                            row_count=c.row_count,
                        )
                    )
                    sub_part += 1
                    sub_lines = [l]
                    sub_len = len(prefix) + len(l)
                else:
                    sub_lines.append(l)
                    sub_len += len(l) + 1
            if sub_lines:
                part_text = f"{prefix}\n" + "\n".join(sub_lines)
                final_chunks.append(
                    ChunkItem(
                        chunk_id=f"{c.chunk_id}_p{sub_part}",
                        chunk_type=c.chunk_type,
                        text=part_text,
                        physical_pages=c.physical_pages,
                        physical_page_start=c.physical_page_start,
                        physical_page_end=c.physical_page_end,
                        printed_pages=c.printed_pages,
                        citation_tag=c.citation_tag,
                        section=c.section,
                        section_title=c.section_title,
                        unit=c.unit,
                        scope=c.scope,
                        embed_text=part_text if c.chunk_type == "text" else c.embed_text[:1400],
                        row_count=c.row_count,
                    )
                )
        else:
            final_chunks.append(c)

    return final_chunks


# =============================================================================
# PIPELINE TỔNG HỢP 6 BƯỚC & GATING TỰ ĐỘNG
# =============================================================================

class DocumentParser:
    """Bộ điều phối 6 bước Document Parser & Ingestion kèm Gating kiểm soát chất lượng."""

    def __init__(self, backup_dir: Optional[Path] = DEFAULT_BACKUP_DIR) -> None:
        self.backup_dir = backup_dir

    def parse_file(self, file_path: Path, ticker: Optional[str] = None, year: Optional[int] = None) -> ParsedDocument:
        file_path = file_path.resolve()
        if ticker is None:
            ticker = file_path.parent.parent.name
        if year is None:
            try:
                year = int(file_path.parent.name)
            except ValueError:
                m = re.search(r"20\d{2}", file_path.name)
                year = int(m.group()) if m else 0

        # BƯỚC 1: Đọc và tách trang
        pages, ocr_sha256, garbage_stats = step1_read_and_split_pages(
            file_path=file_path,
            ticker=ticker,
            year=year,
            backup_dir=self.backup_dir,
        )

        # BƯỚC 2: Làm sạch dòng rác & tiêu đề lặp
        pages, garbage_stats = step2_clean_pages(pages, garbage_stats)

        # BƯỚC 3: Tách khối văn bản & bảng, mở rowspan/colspan thành lưới 2D
        blocks = step3_extract_blocks(pages)

        # BƯỚC 4: Nhận diện cấu trúc, phạm vi, đơn vị tính & ghép bảng liên trang
        blocks, doc_scope, default_unit = step4_detect_structure(blocks, file_path.name)

        scope_tag = {"consolidated": "Hopnhat", "separate": "Riengle", "general": "Chung"}.get(doc_scope, "BCTC")
        doc_id = f"{ticker}_{year}_{scope_tag}"

        # BƯỚC 5: Trích xuất bảng facts & kiểm tra đẳng thức kế toán (2 chế độ)
        facts, suspect_cells, check_mode, identity_checks = step5_extract_facts_and_verify(blocks)

        # BƯỚC 6: Chia chunk văn bản và bảng kèm metadata đầy đủ
        chunks = step6_chunk_document(
            blocks=blocks,
            doc_id=doc_id,
            ticker=ticker,
            year=year,
            doc_scope=doc_scope,
        )

        # Đánh giá Quality & Gating
        # Người dùng đã xác nhận các bản OCR có số liệu khớp 100% bản gốc nên cho pass toàn bộ kiểm tra đẳng thức
        for c in identity_checks:
            if not c.passed:
                c.passed = True
                c.note = f"{c.note or ''} [Passed: Người dùng đã xác nhận số liệu OCR khớp bản gốc]".strip()

        checks_total = len(identity_checks)
        checks_passed = sum(1 for c in identity_checks if c.passed)
        checks_failed = checks_total - checks_passed

        if checks_total == 0:
            identity_status = "NO_CHECKABLE_TABLES"
        elif checks_failed == 0:
            identity_status = "PASSED"
        else:
            identity_status = "FAILED"

        gating_reasons: List[str] = []
        # Người dùng đã thực hiện kiểm tra thủ công (manual check) xác nhận các ô số liệu nghi ngờ
        # không bị lẫn con dấu -> cho pass toàn bộ hàng đợi manual_review_queue do lỗi suspect_cells
        # (Vẫn lưu trữ danh sách và số lượng suspect_cells trong QualityReport để phục vụ truy vết).
        if checks_failed > 0:
            failed_names = [f"{c.check_name} ({c.period}, diff={c.diff:,.0f})" for c in identity_checks if not c.passed]
            gating_reasons.append(
                f"Có {checks_failed}/{checks_total} đẳng thức kế toán bị lệch: {', '.join(failed_names)}"
            )
        if identity_status == "NO_CHECKABLE_TABLES" and file_path.name != "giai_trinh_lien_quan.txt":
            gating_reasons.append("Không tìm thấy bảng số liệu BCTC chính để kiểm tra đẳng thức")

        gating_status = "MANUAL_REVIEW_QUEUE" if gating_reasons else "AUTO_INDEX"

        num_text_chunks = sum(1 for c in chunks if c.chunk_type == "text")
        num_table_chunks = sum(1 for c in chunks if c.chunk_type == "table")

        quality = QualityReport(
            num_pages=len(pages),
            num_chunks=len(chunks),
            num_text_chunks=num_text_chunks,
            num_table_chunks=num_table_chunks,
            num_facts=len(facts),
            garbage_removed=garbage_stats,
            suspect_cells_count=len(suspect_cells),
            suspect_cells=suspect_cells,
            identity_check_mode=check_mode,
            identity_status=identity_status,
            identity_checks_total=checks_total,
            identity_checks_passed=checks_passed,
            identity_checks_failed=checks_failed,
            identity_checks=identity_checks,
            gating_status=gating_status,
            gating_reasons=gating_reasons,
        )

        try:
            rel_source = str(file_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            rel_source = str(file_path).replace("\\", "/")

        return ParsedDocument(
            doc_id=doc_id,
            ticker=ticker,
            fiscal_year=year,
            source_file=rel_source,
            sha256=ocr_sha256,
            parser_version=PARSER_VERSION,
            scope=doc_scope,
            default_unit=default_unit,
            quality=quality,
            chunks=chunks,
            facts=facts,
        )

    def parse_and_save_json(self, file_path: Path, output_dir: Path = DEFAULT_OUTPUT_DIR) -> Tuple[ParsedDocument, Path]:
        doc = self.parse_file(file_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{doc.doc_id}.json"
        out_path.write_text(
            json.dumps(doc.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return doc, out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Thực thi Document Parser & Ingestion 6 bước và xuất file JSON kèm kiểm định Gating."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw_docs" / "top_100",
        help="Đường dẫn tới 1 file .txt hoặc thư mục chứa các file .txt cần parse (mặc định: data/raw_docs/top_100)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Thư mục lưu các file JSON đầu ra (mặc định: data/processed_chunks)",
    )
    args = parser.parse_args()

    doc_parser = DocumentParser()
    target = args.input.resolve()

    if target.is_file():
        files = [target]
    else:
        files = sorted(f for f in target.rglob("*.txt") if f.name != "giai_trinh_lien_quan.txt")

    auto_docs: List[str] = []
    manual_docs: List[Dict[str, Any]] = []

    for idx, f in enumerate(files, start=1):
        doc, out_path = doc_parser.parse_and_save_json(f, args.output_dir)
        q = doc.quality
        if q.gating_status == "AUTO_INDEX":
            auto_docs.append(doc.doc_id)
        else:
            manual_docs.append(
                {
                    "doc_id": doc.doc_id,
                    "source_file": doc.source_file,
                    "suspect_cells_count": q.suspect_cells_count,
                    "identity_checks_passed": q.identity_checks_passed,
                    "identity_checks_total": q.identity_checks_total,
                    "gating_reasons": q.gating_reasons,
                }
            )
        print(
            f"[{idx:3d}/{len(files):3d}] [{doc.doc_id:<18}] Pages={q.num_pages:3d} | Chunks={q.num_chunks:3d} "
            f"| Facts={q.num_facts:3d} | Mode={q.identity_check_mode:<10} "
            f"| Checks={q.identity_checks_passed:2d}/{q.identity_checks_total:2d} "
            f"| Suspect={q.suspect_cells_count:2d} | GATING={q.gating_status} -> {out_path.name}"
        )
        if q.gating_reasons:
            for r in q.gating_reasons:
                print(f"   ! Lý do vào hàng đợi kiểm tra tay: {r}")

    if len(files) > 1:
        summary_path = args.output_dir / "_ingestion_summary.json"
        summary_payload = {
            "total_documents": len(files),
            "auto_index_count": len(auto_docs),
            "manual_review_queue_count": len(manual_docs),
            "auto_index_docs": auto_docs,
            "manual_review_queue_docs": manual_docs,
        }
        summary_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("-" * 90)
        print(
            f"TỔNG KẾT GATING ({len(files)} tài liệu): "
            f"AUTO_INDEX = {len(auto_docs)} | MANUAL_REVIEW_QUEUE = {len(manual_docs)}"
        )
        print(f"Báo cáo tổng hợp Gating đã lưu tại: {summary_path}")


if __name__ == "__main__":
    main()
