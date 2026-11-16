"""Conservative, deterministic aliases for standard Vietnamese item codes."""
import re
import unicodedata

from .schemas import MetricCandidate, MetricResolverInput, ToolResult


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold()).replace("đ", "d")
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


# Exact normalized aliases only: no fuzzy guessing of distinct accounting items.
METRICS = [
    ("Doanh thu thuần", "10", "INCOME_STATEMENT", ["doanh thu thuần", "doanh thu thuần về bán hàng và cung cấp dịch vụ", "net revenue"]),
    ("Lợi nhuận gộp", "20", "INCOME_STATEMENT", ["lợi nhuận gộp", "gross profit"]),
    ("Lợi nhuận trước thuế", "50", "INCOME_STATEMENT", ["lợi nhuận trước thuế", "lntt", "profit before tax"]),
    ("Lợi nhuận sau thuế", "60", "INCOME_STATEMENT", ["lợi nhuận sau thuế", "lợi nhuận sau thuế tndn", "lnst", "profit after tax"]),
    ("Lợi nhuận sau thuế của cổ đông công ty mẹ", "61", "INCOME_STATEMENT", ["lợi nhuận sau thuế của cổ đông công ty mẹ", "lợi nhuận sau thuế công ty mẹ", "lnst công ty mẹ"]),
    ("Tổng tài sản", "270", "BALANCE_SHEET", ["tổng tài sản", "total assets"]),
    ("Nợ phải trả", "300", "BALANCE_SHEET", ["nợ phải trả", "tổng nợ phải trả", "total liabilities"]),
    ("Vốn chủ sở hữu", "400", "BALANCE_SHEET", ["vốn chủ sở hữu", "equity"]),
    ("Tiền và các khoản tương đương tiền", "110", "BALANCE_SHEET", ["tiền và các khoản tương đương tiền", "tiền và tương đương tiền", "cash and cash equivalents"]),
    ("Lưu chuyển tiền thuần từ hoạt động kinh doanh", "20", "CASH_FLOW", ["lưu chuyển tiền thuần từ hoạt động kinh doanh", "dòng tiền từ hoạt động kinh doanh", "operating cash flow"]),
    ("Lưu chuyển tiền thuần từ hoạt động đầu tư", "30", "CASH_FLOW", ["lưu chuyển tiền thuần từ hoạt động đầu tư", "investing cash flow"]),
    ("Lưu chuyển tiền thuần từ hoạt động tài chính", "40", "CASH_FLOW", ["lưu chuyển tiền thuần từ hoạt động tài chính", "financing cash flow"]),
]


def metric_name_resolver(args: MetricResolverInput) -> ToolResult:
    """Resolve exact aliases; broad names return candidates requiring clarification."""
    query = normalize_name(args.metric_name)
    exact = []
    possible = []
    for name, code, report_type, aliases in METRICS:
        candidate = MetricCandidate(metric_name=name, code=code, report_type=report_type)
        normalized = [normalize_name(a) for a in aliases]
        if query in normalized:
            exact.append(candidate)
        elif query and any(query in alias for alias in normalized):
            possible.append(candidate)
    matches = exact or possible
    if len(exact) == 1:
        return ToolResult(status="ok", candidates=exact,
                          warnings=["Standard non-bank codes; uncoded bank statements require label-based retrieval."])
    return ToolResult(status="ambiguous" if matches else "not_found", candidates=matches,
                      message="Use a specific supported metric name or an explicit code/report_type.")
