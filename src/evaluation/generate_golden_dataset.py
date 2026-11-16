"""
Script tự động sinh bộ câu hỏi đánh giá chuẩn (Golden Evaluation Set)
cho hệ thống Retrieval và Citation Báo cáo Tài chính Việt Nam.
Phiên bản: v2.0 (Chuẩn hóa toàn diện nhãn Ground Truth & Bằng chứng Đa tầng)

Cải tiến chuẩn hóa trong v2.0:
1. Loại A (Facts): Khớp chuẩn (code, report_type) để triệt tiêu lỗi nhầm Cash Flow vs Income Statement.
   Bao gồm cả chunk Bảng kế toán chính lẫn chunk Thuyết minh chi tiết (Detailed Note) và sub-chunks liền kề.
   Lưu trữ chính xác ground_truth_value (float), raw_value (chuỗi format), unit.
2. Loại B (Văn bản Thuyết minh): Nhận diện chuẩn xác theo Cấu trúc Báo cáo (AUDIT_REPORT, MANAGEMENT_REPORT, NOTES),
   thu thập TOÀN BỘ các chunks cấu thành văn bản/thuyết minh đó vào gold_chunk_ids.
   Loại bỏ hoàn toàn False Negatives do gán nhãn đơn lẻ hay nhầm lẫn từ khóa phụ.
3. Loại C (Chuỗi thời gian): Thu thập đầy đủ các chunk chứa chỉ tiêu qua các năm trong giai đoạn,
   lưu cấu trúc ground_truth_values theo năm, đặt fiscal_year = None để hỗ trợ tìm kiếm đa năm.
4. Loại Trap (Bẫy): Giữ nguyên 5 câu hỏi ngoại suy kiểm tra khả năng phát hiện không có dữ liệu.
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Đưa thư mục gốc vào sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.indexing.vietnamese_sparse_tokenizer import normalize_vietnamese_sparse

PROCESSED_DIR = Path("data/processed_chunks")
SPLIT_FILE = Path("configs/eval_dataset_split.json")
OUTPUT_FILE = Path("configs/golden_evaluation_dataset.json")

# Danh sách chỉ tiêu chuẩn hóa cho Loại A: (code, report_type, metric_name, question_template)
CORE_METRIC_TEMPLATES = [
    # Báo cáo kết quả hoạt động kinh doanh (INCOME_STATEMENT)
    ("10", "INCOME_STATEMENT", "Doanh thu thuần về bán hàng và cung cấp dịch vụ", "Doanh thu thuần của {ticker} năm {year} là bao nhiêu?"),
    ("20", "INCOME_STATEMENT", "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ", "Lợi nhuận gộp của {ticker} trong năm tài chính {year} đạt bao nhiêu?"),
    ("21", "INCOME_STATEMENT", "Doanh thu hoạt động tài chính", "Doanh thu hoạt động tài chính của {ticker} năm {year} đạt mức nào?"),
    ("22", "INCOME_STATEMENT", "Chi phí tài chính", "Chi phí tài chính của {ticker} trong năm {year} là bao nhiêu?"),
    ("23", "INCOME_STATEMENT", "Chi phí lãi vay", "Chi phí lãi vay phát sinh trong năm {year} của {ticker} là bao nhiêu?"),
    ("25", "INCOME_STATEMENT", "Chi phí bán hàng", "Chi phí bán hàng của {ticker} năm {year} ghi nhận con số nào?"),
    ("26", "INCOME_STATEMENT", "Chi phí quản lý doanh nghiệp", "Chi phí quản lý doanh nghiệp của {ticker} trong năm {year} là bao nhiêu?"),
    ("50", "INCOME_STATEMENT", "Tổng lợi nhuận kế toán trước thuế", "Lợi nhuận trước thuế của {ticker} năm {year} là bao nhiêu?"),
    ("60", "INCOME_STATEMENT", "Lợi nhuận sau thuế thu nhập doanh nghiệp", "Lợi nhuận sau thuế của {ticker} năm {year} đạt mức nào?"),

    # Bảng cân đối kế toán (BALANCE_SHEET)
    ("100", "BALANCE_SHEET", "Tài sản ngắn hạn", "Tổng tài sản ngắn hạn của {ticker} tại thời điểm cuối năm {year} là bao nhiêu?"),
    ("110", "BALANCE_SHEET", "Tiền và các khoản tương đương tiền", "Chỉ tiêu tiền và tương đương tiền của {ticker} năm {year} đạt bao nhiêu?"),
    ("120", "BALANCE_SHEET", "Đầu tư tài chính ngắn hạn", "Giá trị đầu tư tài chính ngắn hạn của {ticker} cuối năm {year} là bao nhiêu?"),
    ("130", "BALANCE_SHEET", "Các khoản phải thu ngắn hạn", "Tổng các khoản phải thu ngắn hạn của {ticker} năm {year} là bao nhiêu?"),
    ("140", "BALANCE_SHEET", "Hàng tồn kho", "Giá trị hàng tồn kho của {ticker} tại ngày 31/12/{year} là bao nhiêu?"),
    ("200", "BALANCE_SHEET", "Tài sản dài hạn", "Tài sản dài hạn của {ticker} năm {year} ghi nhận con số nào?"),
    ("220", "BALANCE_SHEET", "Tài sản cố định", "Giá trị tài sản cố định của {ticker} năm {year} là bao nhiêu?"),
    ("270", "BALANCE_SHEET", "Tổng cộng tài sản", "Tổng tài sản của {ticker} tại ngày kết thúc năm tài chính {year} là bao nhiêu?"),
    ("300", "BALANCE_SHEET", "Nợ phải trả", "Tổng nợ phải trả của {ticker} tính đến cuối năm {year} là bao nhiêu?"),
    ("310", "BALANCE_SHEET", "Nợ ngắn hạn", "Nợ ngắn hạn của {ticker} năm {year} chiếm bao nhiêu?"),
    ("320", "BALANCE_SHEET", "Vay và nợ thuê tài chính ngắn hạn", "Dư nợ vay ngắn hạn của {ticker} năm {year} là bao nhiêu?"),
    ("330", "BALANCE_SHEET", "Nợ dài hạn", "Dư nợ dài hạn của {ticker} tại năm {year} là bao nhiêu?"),
    ("400", "BALANCE_SHEET", "Vốn chủ sở hữu", "Quy mô vốn chủ sở hữu của {ticker} trong năm {year} là bao nhiêu?"),
    ("411", "BALANCE_SHEET", "Vốn góp của chủ sở hữu", "Vốn điều lệ / vốn góp chủ sở hữu của {ticker} năm {year} là bao nhiêu?"),
]

# Cấu hình chủ đề chuẩn hóa cho Loại B (Thuyết minh & Văn bản)
TOPIC_CONFIGS = [
    {
        "topic": "AUDIT_REPORT",
        "name": "Báo cáo Kiểm toán Độc lập",
        "template": "Ý kiến của kiểm toán viên độc lập đối với báo cáo tài chính của {ticker} năm {year} là gì?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec == "AUDIT_REPORT" or "kiem toan doc lap" in title_norm or "y kien cua kiem toan vien" in txt_norm[:400]
    },
    {
        "topic": "MANAGEMENT_REPORT",
        "name": "Báo cáo Ban Giám đốc",
        "template": "Trách nhiệm của Ban Giám đốc trong việc lập và trình bày BCTC {ticker} năm {year} gồm những gì?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec == "MANAGEMENT_REPORT" or "ban tong giam doc" in title_norm or "ban giam doc" in title_norm or "trach nhiem cua ban giam doc" in txt_norm[:400]
    },
    {
        "topic": "ACCOUNTING_POLICIES",
        "name": "Chính sách Kế toán Áp dụng",
        "template": "Chính sách kế toán áp dụng của {ticker} trong năm {year} được trình bày như thế nào?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec in ["NOTES", ""] and c.get("chunk_type") == "text" and any(k in txt_norm[:400] for k in ["chinh sach ke toan chu yeu", "chinh sach ke toan ap dung", "co so lap bao cao tai chinh"])
    },
    {
        "topic": "CASH_POLICY",
        "name": "Chính sách Tiền và Tương đương tiền",
        "template": "Nguyên tắc ghi nhận và phân loại tiền và các khoản tương đương tiền của {ticker} năm {year}?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec in ["NOTES", ""] and c.get("chunk_type") == "text" and "tien va cac khoan tuong duong tien" in txt_norm[:400]
    },
    {
        "topic": "INVENTORY_POLICY",
        "name": "Phương pháp Hàng tồn kho",
        "template": "Phương pháp xác định giá trị và trích lập dự phòng giảm giá hàng tồn kho của {ticker} năm {year}?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec in ["NOTES", ""] and c.get("chunk_type") == "text" and ("hang ton kho" in txt_norm[:400] and any(k in txt_norm[:500] for k in ["du phong", "nguyen tac", "gia tri thuan"]))
    },
    {
        "topic": "FIXED_ASSETS_POLICY",
        "name": "Khấu hao Tài sản Cố định",
        "template": "Chính sách trích khấu hao tài sản cố định hữu hình của {ticker} năm {year} quy định ra sao?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec in ["NOTES", ""] and c.get("chunk_type") == "text" and "tai san co dinh" in txt_norm[:400] and "khau hao" in txt_norm[:500]
    },
    {
        "topic": "RECEIVABLES_POLICY",
        "name": "Phải thu và Dự phòng Nợ khó đòi",
        "template": "Thuyết minh chi tiết về các khoản phải thu của khách hàng và trích lập nợ khó đòi tại {ticker} năm {year}?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec in ["NOTES", ""] and c.get("chunk_type") == "text" and any(k in txt_norm[:400] for k in ["phai thu cua khach hang", "phai thu ngan han", "kho doi"])
    },
    {
        "topic": "RELATED_PARTIES",
        "name": "Giao dịch Bên liên quan",
        "template": "Thông tin về giao dịch và số dư trọng yếu với các bên liên quan của {ticker} năm {year}?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec in ["NOTES", ""] and any(k in txt_norm[:400] for k in ["cac ben lien quan", "thuyet minh ve cac ben lien quan"])
    },
    {
        "topic": "FINANCIAL_RISK",
        "name": "Quản trị Rủi ro Tài chính",
        "template": "Các biện pháp quản trị rủi ro thanh khoản và rủi ro lãi suất của {ticker} trong năm {year}?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec in ["NOTES", ""] and any(k in txt_norm[:400] for k in ["quan ly rui ro tai chinh", "rui ro thanh khoan", "rui ro lai suat"])
    },
    {
        "topic": "TAX_POLICY",
        "name": "Thuế Thu nhập Doanh nghiệp",
        "template": "Chính sách thuế thu nhập doanh nghiệp hiện hành và hoãn lại của {ticker} năm {year}?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec in ["NOTES", ""] and ("thue thu nhap doanh nghiep" in txt_norm[:400] or "chi phi thue thu nhap" in txt_norm[:400])
    },
    {
        "topic": "BORROWINGS",
        "name": "Vay và Nợ thuê Tài chính",
        "template": "Thuyết minh chi tiết về các khoản vay và nợ thuê tài chính của {ticker} trong năm {year}?",
        "filter_fn": lambda c, sec, title_norm, txt_norm: sec in ["NOTES", ""] and ("vay va no thue tai chinh" in txt_norm[:400] or "vay ngan han va dai han" in txt_norm[:400])
    },
]

# Câu hỏi bẫy (Traps)
TRAP_QUESTIONS = [
    {
        "question": "Doanh thu thuần hợp nhất của FOX năm 2024 đạt bao nhiêu?",
        "ticker": "FOX",
        "fiscal_year": 2024,
        "scope": "consolidated",
        "reason": "Mã cổ phiếu FOX không nằm trong corpus dữ liệu Top 100",
    },
    {
        "question": "Lợi nhuận trước thuế của DPM năm 2023 ghi nhận con số nào?",
        "ticker": "DPM",
        "fiscal_year": 2023,
        "scope": "consolidated",
        "reason": "Mã cổ phiếu DPM không nằm trong corpus dữ liệu Top 100",
    },
    {
        "question": "Tổng tài sản của VCB năm 2024 đạt bao nhiêu?",
        "ticker": "VCB",
        "fiscal_year": 2024,
        "scope": "consolidated",
        "reason": "Mã cổ phiếu VCB không nằm trong corpus dữ liệu Top 100",
    },
    {
        "question": "Chi phí nghiên cứu phát triển thị trường xe điện tại châu Âu của QNS năm 2025 là bao nhiêu?",
        "ticker": "QNS",
        "fiscal_year": 2025,
        "scope": "consolidated",
        "reason": "QNS là công ty mía đường, không có sự kiện xe điện châu Âu",
    },
    {
        "question": "Báo cáo kiểm toán độc lập của FPT năm 2018 có ý kiến ngoại trừ nào không?",
        "ticker": "FPT",
        "fiscal_year": 2018,
        "scope": "consolidated",
        "reason": "Năm 2018 nằm ngoài phạm vi thời gian của corpus (2022-2025)",
    },
]


def load_split_config() -> Tuple[Set[str], Set[str]]:
    data = json.loads(SPLIT_FILE.read_text(encoding="utf-8"))
    return set(data["dev_tickers"]), set(data["test_tickers"])


def find_chunks_containing_fact(
    chunks: List[Dict[str, Any]], 
    report_type: str, 
    physical_page: Optional[int], 
    code: str, 
    label: str,
    note: Optional[str] = None
) -> Tuple[List[str], List[int]]:
    """
    Tìm tất cả các chunk chứa bằng chứng cho Fact:
    1. Bảng báo cáo chính (Primary Financial Table) thuộc report_type trên trang physical_page (+-1).
    2. Thuyết minh chi tiết (Detailed Note) nếu có số thuyết minh (note).
    3. Mở rộng cho các sub-chunk liên đới (_p1, _p2).
    """
    matched_ids = set()
    matched_pages = set()
    label_norm = normalize_vietnamese_sparse(label)
    label_core = re.sub(r"^[0-9\.\-\s\(\)=]+", "", label_norm).strip()

    # 1. Quét tìm chunk bảng chính
    for c in chunks:
        sec = (c.get("section") or "").upper()
        pages = c.get("physical_pages", [])
        text = c.get("text", "")
        text_norm = normalize_vietnamese_sparse(text)
        cid = c["chunk_id"]

        is_same_section = (sec == report_type) or (report_type in sec)
        is_near_page = physical_page and (physical_page in pages or physical_page - 1 in pages or physical_page + 1 in pages)

        if is_same_section and is_near_page:
            # Khớp mã số (ví dụ "| 10 |") hoặc nhãn chỉ tiêu
            if f"| {code} |" in text or f"|{code}|" in text or (label_core and len(label_core) >= 5 and label_core in text_norm):
                matched_ids.add(cid)
                matched_pages.update(pages)

    # 2. Nếu có thuyết minh liên kết (note), quét tìm chunk thuyết minh tương ứng
    if note and note.strip().isdigit():
        note_num = note.strip()
        for c in chunks:
            sec = (c.get("section") or "").upper()
            if sec in ["NOTES", ""] and c.get("chunk_type") in ["table", "text"]:
                text = c.get("text", "")
                text_norm = normalize_vietnamese_sparse(text)
                note_pattern = rf"(?:^|\n)\s*{note_num}\s+[A-ZÀ-Ỹa-zà-ỹ]"
                if re.search(note_pattern, text) or f"thuyet minh {note_num}" in text_norm:
                    if label_core and any(word in text_norm for word in label_core.split()[:3]):
                        matched_ids.add(c["chunk_id"])
                        matched_pages.update(c.get("physical_pages", []))

    # 3. Mở rộng cho sub-chunk lân cận (nếu chunk bị chia tách _p1, _p2)
    expanded_ids = set(matched_ids)
    for cid in matched_ids:
        base_id = re.sub(r"_p\d+$", "", cid)
        for c in chunks:
            if c["chunk_id"].startswith(base_id) and c["chunk_id"] not in expanded_ids:
                if any(p in matched_pages for p in c.get("physical_pages", [])):
                    expanded_ids.add(c["chunk_id"])

    return sorted(list(expanded_ids)), sorted(list(matched_pages))


def main():
    random.seed(42)
    dev_tickers, test_tickers = load_split_config()

    files = sorted([f for f in PROCESSED_DIR.glob("*.json") if not f.name.startswith("_")])
    print(f"Đọc dữ liệu từ {len(files)} file BCTC...")

    docs_by_id = {}
    docs_by_ticker = defaultdict(list)
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc_id = doc["doc_id"]
        docs_by_id[doc_id] = doc
        docs_by_ticker[doc["ticker"]].append(doc)

    golden_questions: List[Dict[str, Any]] = []
    q_counter = 0

    # =========================================================================
    # 1. SINH CÂU HỎI LOẠI A: SỐ LIỆU TỪ FACTS CHUẨN HÓA (~50-60 CÂU)
    # =========================================================================
    print("Đang sinh câu hỏi Loại A (Số liệu từ Facts chuẩn hóa)...")
    type_a_samples = []

    for ticker, t_docs in docs_by_ticker.items():
        split = "dev" if ticker in dev_tickers else "test"
        selected_docs = random.sample(t_docs, min(2, len(t_docs)))
        for doc in selected_docs:
            year = doc["fiscal_year"]
            chunks = doc.get("chunks", [])
            facts = doc.get("facts", [])

            # Nhóm facts theo cặp (code, report_type)
            fact_map = {}
            for f in facts:
                c_code = f.get("code")
                r_type = f.get("report_type")
                if c_code and r_type:
                    fact_map[(c_code, r_type)] = f

            for code, target_report_type, metric_name, q_template in CORE_METRIC_TEMPLATES:
                key = (code, target_report_type)
                if key in fact_map:
                    f_item = fact_map[key]
                    phys_page = f_item.get("physical_page")
                    gold_chunks, gold_pages = find_chunks_containing_fact(
                        chunks=chunks,
                        report_type=target_report_type,
                        physical_page=phys_page,
                        code=code,
                        label=f_item.get("label", ""),
                        note=f_item.get("note")
                    )
                    if gold_chunks:
                        q_text = q_template.format(ticker=ticker, year=year)
                        type_a_samples.append({
                            "question": q_text,
                            "ticker": ticker,
                            "fiscal_year": year,
                            "scope": doc.get("scope", "consolidated"),
                            "type": "A",
                            "split": split,
                            "gold_chunk_ids": gold_chunks,
                            "gold_pages": gold_pages,
                            "ground_truth_value": f_item.get("current_year"),
                            "raw_value": f_item.get("raw_current"),
                            "unit": f_item.get("unit") or doc.get("default_unit", "VND"),
                            "metric_name": metric_name,
                            "code": code,
                            "report_type": target_report_type,
                        })
                        break  # 1 fact mỗi doc để phân bổ đều

    random.shuffle(type_a_samples)
    selected_type_a = type_a_samples[:60]
    for item in selected_type_a:
        q_counter += 1
        item["question_id"] = f"Q_A_{q_counter:03d}"
        golden_questions.append(item)

    print(f"- Đã sinh {len(selected_type_a)} câu hỏi Loại A chuẩn hóa.")

    # =========================================================================
    # 2. SINH CÂU HỎI LOẠI B: VĂN BẢN THUYẾT MINH / KIỂM TOÁN / BAN GIÁM ĐỐC (~40 CÂU)
    # =========================================================================
    print("Đang sinh câu hỏi Loại B (Văn bản Thuyết minh & Báo cáo chuẩn cấu trúc)...")
    type_b_candidates = []

    for ticker, t_docs in docs_by_ticker.items():
        split = "dev" if ticker in dev_tickers else "test"
        for doc in t_docs:
            year = doc["fiscal_year"]
            chunks = doc.get("chunks", [])

            for top_cfg in TOPIC_CONFIGS:
                topic_id = top_cfg["topic"]
                filter_fn = top_cfg["filter_fn"]
                matched_cids = []
                matched_pages = set()

                for c in chunks:
                    sec = (c.get("section") or "").upper()
                    sec_title = (c.get("section_title") or "")
                    title_norm = normalize_vietnamese_sparse(sec_title)
                    txt = c.get("text", "")
                    txt_norm = normalize_vietnamese_sparse(txt)

                    if filter_fn(c, sec, title_norm, txt_norm):
                        matched_cids.append(c["chunk_id"])
                        matched_pages.update(c.get("physical_pages", []))

                # Chỉ nhận topic nếu tìm thấy từ 1 đến 6 chunk bằng chứng rõ ràng
                if 1 <= len(matched_cids) <= 8:
                    q_text = top_cfg["template"].format(ticker=ticker, year=year)
                    type_b_candidates.append({
                        "question": q_text,
                        "ticker": ticker,
                        "fiscal_year": year,
                        "scope": doc.get("scope", "consolidated"),
                        "type": "B",
                        "split": split,
                        "gold_chunk_ids": sorted(matched_cids),
                        "gold_pages": sorted(list(matched_pages)),
                        "ground_truth_value": None,
                        "topic": topic_id,
                        "topic_name": top_cfg["name"],
                    })

    random.shuffle(type_b_candidates)
    seen_b_keys = set()
    selected_type_b = []
    for item in type_b_candidates:
        key = (item["ticker"], item["topic"])
        if key not in seen_b_keys:
            seen_b_keys.add(key)
            selected_type_b.append(item)
            if len(selected_type_b) >= 45:
                break

    for item in selected_type_b:
        q_counter += 1
        item["question_id"] = f"Q_B_{q_counter:03d}"
        golden_questions.append(item)

    print(f"- Đã sinh {len(selected_type_b)} câu hỏi Loại B chuẩn hóa.")

    # =========================================================================
    # 3. SINH CÂU HỎI LOẠI C: CHUỖI THỜI GIAN NHIỀU NĂM (~12 CÂU)
    # =========================================================================
    print("Đang sinh câu hỏi Loại C (Chuỗi thời gian nhiều năm)...")
    multi_year_tickers = [t for t, t_docs in docs_by_ticker.items() if len(t_docs) >= 3]
    selected_c_tickers = random.sample(multi_year_tickers, min(15, len(multi_year_tickers)))

    for ticker in selected_c_tickers:
        split = "dev" if ticker in dev_tickers else "test"
        t_docs = sorted(docs_by_ticker[ticker], key=lambda d: d["fiscal_year"])
        years = [d["fiscal_year"] for d in t_docs]
        start_yr, end_yr = years[0], years[-1]

        target_code = "10"
        target_name = "Doanh thu thuần"
        target_report_type = "INCOME_STATEMENT"

        gold_chunks = []
        gold_pages = []
        yearly_values = {}

        for doc in t_docs:
            y = doc["fiscal_year"]
            chunks = doc.get("chunks", [])
            facts = doc.get("facts", [])
            f_match = next((f for f in facts if f.get("code") == target_code and f.get("report_type") == target_report_type), None)
            if f_match:
                p = f_match.get("physical_page")
                c_ids, p_list = find_chunks_containing_fact(
                    chunks=chunks,
                    report_type=target_report_type,
                    physical_page=p,
                    code=target_code,
                    label=f_match.get("label", ""),
                    note=f_match.get("note")
                )
                gold_chunks.extend(c_ids)
                gold_pages.extend(p_list)
                if f_match.get("current_year") is not None:
                    yearly_values[str(y)] = {
                        "value": f_match.get("current_year"),
                        "raw": f_match.get("raw_current"),
                        "unit": f_match.get("unit") or doc.get("default_unit", "VND")
                    }

        if gold_chunks:
            q_counter += 1
            golden_questions.append({
                "question_id": f"Q_C_{q_counter:03d}",
                "question": f"Tình hình biến động {target_name} của {ticker} trong giai đoạn {start_yr}-{end_yr} như thế nào?",
                "ticker": ticker,
                "fiscal_year": None,  # Mở cho truy vấn toàn dải thời gian
                "years_covered": years,
                "scope": "consolidated",
                "type": "C",
                "split": split,
                "gold_chunk_ids": sorted(list(set(gold_chunks))),
                "gold_pages": sorted(list(set(gold_pages))),
                "ground_truth_values": yearly_values,
                "metric_name": target_name,
            })

    print(f"- Đã sinh {len([q for q in golden_questions if q['type'] == 'C'])} câu hỏi Loại C.")

    # =========================================================================
    # 4. THÊM CÂU HỎI BẪY (TRAPS) (5 CÂU)
    # =========================================================================
    for idx, trap in enumerate(TRAP_QUESTIONS, start=1):
        q_counter += 1
        golden_questions.append({
            "question_id": f"Q_TRAP_{q_counter:03d}",
            "question": trap["question"],
            "ticker": trap["ticker"],
            "fiscal_year": trap["fiscal_year"],
            "scope": trap["scope"],
            "type": "TRAP",
            "split": "dev" if idx % 2 != 0 else "test",
            "gold_chunk_ids": [],
            "gold_pages": [],
            "ground_truth_value": None,
            "trap_reason": trap["reason"],
        })

    # =========================================================================
    # LƯU FILE KẾT QUẢ CHUẨN HÓA
    # =========================================================================
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "v2.0",
        "description": "Bộ câu hỏi kiểm chuẩn (Golden Evaluation Set v2.0) đã chuẩn hóa toàn diện nhãn Ground Truth & Bằng chứng Đa tầng.",
        "total_questions": len(golden_questions),
        "split_counts": {
            "dev": sum(1 for q in golden_questions if q["split"] == "dev"),
            "test": sum(1 for q in golden_questions if q["split"] == "test"),
        },
        "type_counts": {
            "A": sum(1 for q in golden_questions if q["type"] == "A"),
            "B": sum(1 for q in golden_questions if q["type"] == "B"),
            "C": sum(1 for q in golden_questions if q["type"] == "C"),
            "TRAP": sum(1 for q in golden_questions if q["type"] == "TRAP"),
        },
        "questions": golden_questions,
    }

    OUTPUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + "=" * 80)
    print(f"ĐÃ TẠO THÀNH CÔNG BỘ CÂU HỎI GOLDEN SET v2.0 TẠI: {OUTPUT_FILE}")
    print(f"- Tổng số câu hỏi: {len(golden_questions)}")
    print(f"- Tập DEV: {payload['split_counts']['dev']} câu | Tập TEST: {payload['split_counts']['test']} câu")
    print(f"- Phân loại: Loại A={payload['type_counts']['A']} | Loại B={payload['type_counts']['B']} | Loại C={payload['type_counts']['C']} | Bẫy={payload['type_counts']['TRAP']}")
    print("=" * 80)


if __name__ == "__main__":
    main()
