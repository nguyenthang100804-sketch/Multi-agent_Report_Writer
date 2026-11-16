"""Fixed one-ticker template; metric names are resolved before task creation."""
from __future__ import annotations

from src.tools.schemas import ReportType

SECTION_TITLES = {
    "S1": "Thông tin doanh nghiệp và phạm vi dữ liệu",
    "S2": "Ý kiến kiểm toán",
    "S3": "Kết quả kinh doanh",
    "S4": "Tình hình tài chính",
    "S5": "Lưu chuyển tiền tệ",
    "S6": "Chính sách kế toán và thuyết minh chọn lọc",
    "S7": "Bên liên quan, rủi ro, sự kiện sau niên độ",
}

RATIO_LABELS = {
    "gross_margin": "Biên lợi nhuận gộp",
    "net_margin": "Biên lợi nhuận ròng",
    "debt_to_assets": "Tỷ trọng nợ trên tổng tài sản",
    "equity_to_assets": "Tỷ trọng vốn chủ trên tổng tài sản",
    "cfo_to_net_income": "Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế",
}

# One metric per row. No accounting code is invented or read from this table.
METRIC_RULES: tuple[tuple[str, str, str, ReportType], ...] = (
    ("S3", "revenue", "Doanh thu thuần", "INCOME_STATEMENT"),
    ("S3", "gross_profit", "Lợi nhuận gộp", "INCOME_STATEMENT"),
    ("S3", "profit_before_tax", "Lợi nhuận trước thuế", "INCOME_STATEMENT"),
    ("S3", "net_income", "Lợi nhuận sau thuế", "INCOME_STATEMENT"),
    ("S3", "parent_profit", "Lợi nhuận sau thuế của cổ đông công ty mẹ", "INCOME_STATEMENT"),
    ("S4", "assets", "Tổng tài sản", "BALANCE_SHEET"),
    ("S4", "liabilities", "Nợ phải trả", "BALANCE_SHEET"),
    ("S4", "equity", "Vốn chủ sở hữu", "BALANCE_SHEET"),
    ("S4", "cash", "Tiền và các khoản tương đương tiền", "BALANCE_SHEET"),
    ("S5", "operating_cash_flow", "Lưu chuyển tiền thuần từ hoạt động kinh doanh", "CASH_FLOW"),
    ("S5", "investing_cash_flow", "Lưu chuyển tiền thuần từ hoạt động đầu tư", "CASH_FLOW"),
    ("S5", "financing_cash_flow", "Lưu chuyển tiền thuần từ hoạt động tài chính", "CASH_FLOW"),
)

OPTIONAL_NOTE_TOPICS = {
    "S6": (
        ("revenue_policy", "Nguyên tắc và thời điểm ghi nhận doanh thu"),
        ("depreciation", "Phương pháp khấu hao và thời gian sử dụng tài sản"),
        ("provisions", "Cách trích lập dự phòng phải thu và hàng tồn kho"),
        ("borrowing_policy", "Điều khoản và kỳ hạn các khoản vay"),
    ),
    "S7": (
        ("related_parties", "Các giao dịch và số dư với bên liên quan"),
        ("financial_risks", "Rủi ro thanh khoản tín dụng tỷ giá lãi suất"),
        ("commitments", "Cam kết và nghĩa vụ tiềm tàng"),
        ("subsequent_events", "Sự kiện phát sinh sau ngày kết thúc niên độ"),
    ),
}

BANK_TICKERS = frozenset({"ABB", "ACB", "BAB", "MSB", "NAB", "NVB"})
UNREVIEWED_FINANCIAL_TICKERS = frozenset({"PVI"})
