"""
Schemas cho Module Document Parser & Ingestion (6 bước).
Định nghĩa cấu trúc dữ liệu chuẩn cho từng bước xử lý và cấu trúc JSON đầu ra của mỗi tài liệu BCTC.
Mỗi thuộc tính đều được gắn kèm định nghĩa chi tiết trong `field(metadata={"description": ...})`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PageData:
    """Dữ liệu đầu ra của Bước 1 (Đọc và tách trang) & Bước 2 (Làm sạch)."""

    physical_page: int = field(
        metadata={
            "description": "Số thứ tự trang vật lý trùng khớp với trang file PDF gốc (bắt đầu từ 1), dùng để tạo nhãn trích dẫn chuẩn [Doc_X, p.Y]."
        }
    )
    printed_page: Optional[str] = field(
        metadata={
            "description": "Số trang in trên giấy tìm thấy ở vùng chân trang (ví dụ '1', '15', 'II'); có thể là None ở trang bìa hoặc trang không in số trang."
        }
    )
    raw_text: str = field(
        metadata={
            "description": "Nội dung văn bản nguyên gốc của trang sau khi đã chuẩn hóa bảng mã Unicode về dạng dựng sẵn NFC."
        }
    )
    cleaned_text: str = field(
        default="",
        metadata={
            "description": "Nội dung trang sau Bước 2 (đã loại bỏ dòng rác chữ Hán/CJK, công thức LaTeX ảo giác, câu từ chối QR và tiêu đề lặp >= 30% số trang)."
        },
    )


@dataclass
class GridRow:
    """Một dòng trong lưới bảng 2D sau khi mở rowspan/colspan ở Bước 3."""

    cells: List[str] = field(
        metadata={
            "description": "Danh sách giá trị chuỗi của từng ô trên dòng sau khi đã trải phẳng thuộc tính rowspan và colspan."
        }
    )
    physical_page: int = field(
        metadata={
            "description": "Số trang vật lý (PDF) nơi dòng bảng này xuất hiện."
        }
    )
    printed_page: Optional[str] = field(
        metadata={
            "description": "Số trang in trên giấy của trang chứa dòng bảng này (nếu có)."
        }
    )


@dataclass
class Block:
    """Khối nội dung sau Bước 3 (Tách khối) và Bước 4 (Nhận diện cấu trúc)."""

    block_id: str = field(
        metadata={
            "description": "Mã định danh duy nhất của khối trong tài liệu (ví dụ: 'blk_0001', 'blk_0002')."
        }
    )
    block_type: str = field(
        metadata={
            "description": "Loại khối nội dung: 'text' (khối văn bản thuyết minh/báo cáo) hoặc 'table' (khối bảng biểu HTML đã mở lưới 2D)."
        }
    )
    physical_page_start: int = field(
        metadata={
            "description": "Số trang vật lý (PDF) bắt đầu của khối nội dung."
        }
    )
    physical_page_end: int = field(
        metadata={
            "description": "Số trang vật lý (PDF) kết thúc của khối nội dung (lớn hơn physical_page_start nếu bảng trải dài qua nhiều trang)."
        }
    )
    printed_pages: List[str] = field(
        metadata={
            "description": "Danh sách các số trang in trên giấy tương ứng với phạm vi trang của khối."
        }
    )
    section: str = field(
        metadata={
            "description": "Mã phân mục báo cáo chuẩn: 'COVER_OR_TOC' | 'MANAGEMENT_REPORT' | 'AUDIT_REPORT' | 'BALANCE_SHEET' | 'OFF_BALANCE_SHEET' | 'INCOME_STATEMENT' | 'CASH_FLOW' | 'NOTES'."
        }
    )
    section_title: str = field(
        metadata={
            "description": "Tiêu đề nguyên văn của báo cáo hoặc phần mục hiện tại (ví dụ: 'BẢNG CÂN ĐỐI KẾ TOÁN HỢP NHẤT')."
        }
    )
    unit: str = field(
        metadata={
            "description": "Đơn vị tiền tệ áp dụng cho khối: 'VND' | 'thousand_VND' | 'million_VND' | 'billion_VND' | 'USD'."
        }
    )
    text: str = field(
        default="",
        metadata={
            "description": "Nội dung văn bản của khối (chỉ dùng khi block_type == 'text')."
        },
    )
    grid: List[GridRow] = field(
        default_factory=list,
        metadata={
            "description": "Danh sách các dòng lưới 2D đã mở rowspan/colspan (chỉ dùng khi block_type == 'table')."
        },
    )
    num_cols: int = field(
        default=0,
        metadata={
            "description": "Số lượng cột chuẩn của lưới bảng 2D (bằng 0 đối với khối văn bản)."
        },
    )


@dataclass
class FactItem:
    """Một dòng số liệu kế toán chuẩn hóa trích xuất từ các báo cáo tài chính chính ở Bước 5."""

    report_type: str = field(
        metadata={
            "description": "Loại báo cáo tài chính chứa chỉ tiêu này: 'BALANCE_SHEET' | 'INCOME_STATEMENT' | 'CASH_FLOW'."
        }
    )
    code: Optional[str] = field(
        metadata={
            "description": "Mã số chỉ tiêu kế toán xác định theo tiêu đề cột 'Mã số' (ví dụ: '100', '270', '01', '60'; bằng None đối với báo cáo Ngân hàng không dùng mã số)."
        }
    )
    stt: Optional[str] = field(
        metadata={
            "description": "Ký hiệu số thứ tự/cấp mục của dòng chỉ tiêu (ví dụ: 'A', 'I', '1', 'a')."
        }
    )
    label: str = field(
        metadata={
            "description": "Tên/nhãn của khoản mục kế toán trên báo cáo (ví dụ: 'I. Tiền và các khoản tương đương tiền')."
        }
    )
    note: Optional[str] = field(
        metadata={
            "description": "Mã tham chiếu đến mục Thuyết minh báo cáo tài chính xác định theo tiêu đề cột 'Thuyết minh' (ví dụ: '4', 'V.01', '36')."
        }
    )
    current_year: Optional[float] = field(
        metadata={
            "description": "Giá trị số học của kỳ báo cáo năm nay/cuối năm (bằng None nếu ô trống '-' hoặc nếu suspect == True)."
        }
    )
    prior_year: Optional[float] = field(
        metadata={
            "description": "Giá trị số học của kỳ so sánh năm trước/đầu năm (bằng None nếu ô trống '-' hoặc nếu suspect == True)."
        }
    )
    raw_current: str = field(
        metadata={
            "description": "Chuỗi ký tự gốc trong ô số liệu năm nay trước khi chuyển thành số (được bảo toàn nguyên vẹn để đối chiếu khi suspect == True)."
        }
    )
    raw_prior: str = field(
        metadata={
            "description": "Chuỗi ký tự gốc trong ô số liệu năm trước trước khi chuyển thành số (được bảo toàn nguyên vẹn để đối chiếu khi suspect == True)."
        }
    )
    suspect: bool = field(
        metadata={
            "description": "Cờ đánh dấu nghi ngờ lỗi dữ liệu: bằng True nếu ô số liệu lẫn chữ cái, ký tự lạ (như bị con dấu đè) hoặc sai định dạng phân cách hàng nghìn."
        }
    )
    suspect_reason: Optional[str] = field(
        metadata={
            "description": "Mô tả chi tiết nguyên nhân ô số liệu bị đánh dấu suspect=True (bằng None nếu số liệu hợp lệ)."
        }
    )
    unit: str = field(
        metadata={
            "description": "Đơn vị tiền tệ của dòng số liệu ('VND', 'million_VND', 'billion_VND', 'USD')."
        }
    )
    physical_page: int = field(
        metadata={
            "description": "Số trang vật lý (PDF) nơi dòng chỉ tiêu này xuất hiện."
        }
    )
    printed_page: Optional[str] = field(
        metadata={
            "description": "Số trang in trên giấy của trang chứa dòng chỉ tiêu này."
        }
    )


@dataclass
class IdentityCheckResult:
    """Kết quả kiểm tra một đẳng thức kế toán ở Bước 5 (Chế độ Mã số hoặc Chế độ Cây)."""

    check_name: str = field(
        metadata={
            "description": "Tên định danh của phép kiểm tra đẳng thức (ví dụ: 'BS_TotalAssets_270', 'IS_GrossProfit_20', 'BS_Tree_TotalAssets_eq_SumLevel1')."
        }
    )
    report_type: str = field(
        metadata={
            "description": "Loại báo cáo được kiểm tra: 'BALANCE_SHEET' hoặc 'INCOME_STATEMENT'."
        }
    )
    period: str = field(
        metadata={
            "description": "Kỳ kế toán được kiểm tra: 'current_year' (năm nay/cuối năm) hoặc 'prior_year' (năm trước/đầu năm)."
        }
    )
    formula: str = field(
        metadata={
            "description": "Biểu thức công thức kế toán dùng để kiểm tra (ví dụ: '270 == 100 + 200', '20 == 10 -/+ 11')."
        }
    )
    lhs_value: Optional[float] = field(
        metadata={
            "description": "Giá trị vế trái (chỉ tiêu tổng hợp in trên báo cáo)."
        }
    )
    rhs_value: Optional[float] = field(
        metadata={
            "description": "Giá trị vế phải (tổng/hiệu tính toán từ các chỉ tiêu thành phần)."
        }
    )
    diff: Optional[float] = field(
        metadata={
            "description": "Độ lệch tuyệt đối giữa vế trái và vế phải (lhs_value - rhs_value)."
        }
    )
    passed: bool = field(
        metadata={
            "description": "Kết quả kiểm tra: True nếu độ lệch |diff| nằm trong ngưỡng dung sai làm tròn cho phép (<= 5 đơn vị)."
        }
    )
    sign_convention: Optional[str] = field(
        default=None,
        metadata={
            "description": "Quy ước dấu được phát hiện ở phép kiểm tra: 'positive_expense' (chi phí ghi dương), 'negative_expense' (chi phí ghi âm trong ngoặc), 'tree_based', hoặc 'standard'."
        },
    )
    note: Optional[str] = field(
        default=None,
        metadata={
            "description": "Ghi chú bổ sung về kết quả kiểm tra (ví dụ: số lượng dòng tổng hợp cấp cha phát hiện được trong kiểm tra cây)."
        },
    )


@dataclass
class ChunkItem:
    """Một đơn vị chunk văn bản hoặc bảng hoàn chỉnh ở Bước 6 dùng để đưa vào Embedding & Vector/BM25 Index."""

    chunk_id: str = field(
        metadata={
            "description": "Mã định danh duy nhất của chunk (ví dụ: 'FPT_2024_Hopnhat_chunk_0007')."
        }
    )
    chunk_type: str = field(
        metadata={
            "description": "Loại chunk: 'text' (đoạn văn bản thuyết minh kèm tiêu đề mục) hoặc 'table' (bảng số liệu giữ nguyên dòng tiêu đề cột)."
        }
    )
    text: str = field(
        metadata={
            "description": "Nội dung toàn văn hoàn chỉnh của chunk (bao gồm tiền tố ngữ cảnh, bảng đầy đủ số liệu và đoạn văn) dùng làm Payload cho Writer Agent và lập chỉ mục từ khóa Sparse (BM25)."
        }
    )
    physical_pages: List[int] = field(
        metadata={
            "description": "Danh sách tất cả các số trang vật lý (PDF) mà chunk này đi qua."
        }
    )
    physical_page_start: int = field(
        metadata={
            "description": "Số trang vật lý (PDF) bắt đầu của chunk."
        }
    )
    physical_page_end: int = field(
        metadata={
            "description": "Số trang vật lý (PDF) kết thúc của chunk."
        }
    )
    printed_pages: List[str] = field(
        metadata={
            "description": "Danh sách các số trang in trên giấy tương ứng với chunk."
        }
    )
    citation_tag: str = field(
        metadata={
            "description": "Nhãn trích dẫn chuẩn sẵn sàng cho Agent sử dụng (ví dụ: '[Doc_FPT_2024_Hopnhat, p.9]' hoặc '[Doc_FPT_2024_Hopnhat, p.6-8]')."
        }
    )
    section: str = field(
        metadata={
            "description": "Mã phân mục báo cáo chứa chunk ('BALANCE_SHEET', 'INCOME_STATEMENT', 'CASH_FLOW', 'NOTES', 'AUDIT_REPORT'...). "
        }
    )
    section_title: str = field(
        metadata={
            "description": "Tiêu đề đầy đủ của báo cáo hoặc mục chứa chunk."
        }
    )
    unit: str = field(
        metadata={
            "description": "Đơn vị tiền tệ áp dụng cho các con số trong chunk ('VND', 'million_VND', 'billion_VND', 'USD')."
        }
    )
    scope: str = field(
        metadata={
            "description": "Phạm vi báo cáo tài chính của tài liệu chứa chunk: 'consolidated' (hợp nhất), 'separate' (riêng), hoặc 'general' (chung)."
        }
    )
    embed_text: str = field(
        default="",
        metadata={
            "description": "Văn bản tối ưu chuyên biệt cho mô hình Dense Embedding (BGE-M3/E5): giữ nguyên tiền tố ngữ cảnh và nhãn tên/mã chỉ tiêu, loại bỏ các chuỗi số tiền lớn để tránh làm loãng vector."
        },
    )
    row_count: int = field(
        default=0,
        metadata={
            "description": "Số lượng dòng dữ liệu trong chunk bảng (bằng 0 nếu chunk_type == 'text')."
        },
    )


@dataclass
class QualityReport:
    """Báo cáo thống kê chất lượng xử lý tài liệu và quyết định phân luồng Gating."""

    num_pages: int = field(
        metadata={
            "description": "Tổng số trang hợp lệ của tài liệu sau khi đã cắt bỏ các trang trùng lặp song ngữ."
        }
    )
    num_chunks: int = field(
        metadata={
            "description": "Tổng số chunks (văn bản + bảng) được tạo ra ở Bước 6."
        }
    )
    num_text_chunks: int = field(
        metadata={
            "description": "Số lượng chunks thuộc loại văn bản (chunk_type == 'text')."
        }
    )
    num_table_chunks: int = field(
        metadata={
            "description": "Số lượng chunks thuộc loại bảng biểu (chunk_type == 'table')."
        }
    )
    num_facts: int = field(
        metadata={
            "description": "Tổng số dòng chỉ tiêu kế toán (FactItem) trích xuất được từ các báo cáo tài chính chính."
        }
    )
    garbage_removed: Dict[str, int] = field(
        metadata={
            "description": "Thống kê số lượng rác đã loại bỏ, gồm: 'duplicate_pages_cut', 'vlm_and_ocr_garbage_lines', 'repeated_header_footer_lines', 'total_removed'."
        }
    )
    suspect_cells_count: int = field(
        metadata={
            "description": "Tổng số ô số liệu bị đánh dấu nghi ngờ (suspect=True) do lẫn chữ hoặc con dấu đè."
        }
    )
    suspect_cells: List[Dict[str, Any]] = field(
        metadata={
            "description": "Danh sách chi tiết từng ô số liệu bị đánh dấu suspect=True (kèm report_type, code, label, column, raw, reason, physical_page)."
        }
    )
    identity_check_mode: str = field(
        metadata={
            "description": "Chế độ kiểm tra đẳng thức kế toán đã sử dụng: 'code_based' (theo mã số), 'tree_based' (dạng cây cho Ngân hàng), hoặc 'none'."
        }
    )
    identity_status: str = field(
        metadata={
            "description": "Trạng thái tổng hợp của kiểm tra đẳng thức: 'PASSED' (đạt 100%), 'FAILED' (có đẳng thức lệch), hoặc 'NO_CHECKABLE_TABLES'."
        }
    )
    identity_checks_total: int = field(
        metadata={
            "description": "Tổng số phép kiểm tra đẳng thức kế toán đã thực hiện trên tài liệu."
        }
    )
    identity_checks_passed: int = field(
        metadata={
            "description": "Số lượng phép kiểm tra đẳng thức kế toán đạt yêu cầu (passed == True)."
        }
    )
    identity_checks_failed: int = field(
        metadata={
            "description": "Số lượng phép kiểm tra đẳng thức kế toán bị lệch (passed == False)."
        }
    )
    identity_checks: List[IdentityCheckResult] = field(
        metadata={
            "description": "Danh sách kết quả chi tiết của từng phép kiểm tra đẳng thức kế toán."
        }
    )
    gating_status: str = field(
        metadata={
            "description": "Quyết định Gating tự động: 'AUTO_INDEX' (tự động đi tiếp sang embedding & index) hoặc 'MANUAL_REVIEW_QUEUE' (vào hàng đợi kiểm tra tay)."
        }
    )
    gating_reasons: List[str] = field(
        metadata={
            "description": "Danh sách lý do khiến tài liệu bị đưa vào hàng đợi kiểm tra tay MANUAL_REVIEW_QUEUE (rỗng nếu gating_status == 'AUTO_INDEX')."
        }
    )


@dataclass
class ParsedDocument:
    """Cấu trúc JSON hoàn chỉnh đầu ra cho mỗi tài liệu báo cáo tài chính."""

    doc_id: str = field(
        metadata={
            "description": "Mã định danh duy nhất của tài liệu (ví dụ: 'FPT_2024_Hopnhat')."
        }
    )
    ticker: str = field(
        metadata={
            "description": "Mã chứng khoán của doanh nghiệp/ngân hàng (ví dụ: 'FPT', 'VCB', 'HPG')."
        }
    )
    fiscal_year: int = field(
        metadata={
            "description": "Năm tài chính của báo cáo (ví dụ: 2022, 2023, 2024, 2025)."
        }
    )
    source_file: str = field(
        metadata={
            "description": "Đường dẫn tương đối tới file văn bản OCR đầu vào."
        }
    )
    sha256: str = field(
        metadata={
            "description": "Mã băm SHA-256 của file OCR gốc để kiểm soát tính toàn vẹn và chống xử lý trùng lặp."
        }
    )
    parser_version: str = field(
        metadata={
            "description": "Phiên bản của bộ Document Parser đã tạo ra file JSON này (ví dụ: 'v2.1')."
        }
    )
    scope: str = field(
        metadata={
            "description": "Phạm vi của báo cáo tài chính: 'consolidated' (hợp nhất), 'separate' (riêng/công ty mẹ), hoặc 'general' (chung)."
        }
    )
    default_unit: str = field(
        metadata={
            "description": "Đơn vị tiền tệ chính của báo cáo tài chính: 'VND' | 'thousand_VND' | 'million_VND' | 'billion_VND' | 'USD'."
        }
    )
    quality: QualityReport = field(
        metadata={
            "description": "Đối tượng chứa toàn bộ chỉ số chất lượng (số trang, số chunk, rác bị loại, ô nghi ngờ, kết quả kiểm tra đẳng thức và trạng thái Gating)."
        }
    )
    chunks: List[ChunkItem] = field(
        metadata={
            "description": "Danh sách toàn bộ các chunks văn bản và bảng biểu phục vụ truy xuất RAG."
        }
    )
    facts: List[FactItem] = field(
        metadata={
            "description": "Danh sách toàn bộ các dòng số liệu kế toán có cấu trúc (bảng facts) trích xuất từ BCTC."
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        """Chuyển đổi toàn bộ cấu trúc ParsedDocument sang dictionary tuần tự hóa JSON."""
        return asdict(self)
