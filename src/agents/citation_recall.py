"""Cheap candidate scan for claims that typed placeholders cannot substantiate."""
from __future__ import annotations

import re

from src.agents.draft_rendering import TOKEN


HARD_PATTERNS = {
    "causal_language": re.compile(r"\b(?:do|nhờ|bởi vì|vì|dẫn đến|góp phần)\b", re.I),
    "word_comparison": re.compile(r"\b(?:gấp đôi|gấp ba|gần gấp)\b", re.I),
    "forecast_language": re.compile(r"\b(?:sẽ|kỳ vọng|dự kiến)\b", re.I),
    "ambiguous_cagr": re.compile(r"\bbình quân\b", re.I),
    "unsupported_extremum": re.compile(
        r"\b(?:đỉnh|đáy|cao nhất|thấp nhất|kỷ lục|lớn nhất|nhỏ nhất)\b", re.I),
    "unsupported_trend": re.compile(
        r"\b(?:tăng liên tục|giảm liên tục|tăng đều|giảm dần|đi ngang|diễn biến không đều)\b",
        re.I),
    "unsupported_sequence": re.compile(r"\b(?:tiếp tục|chuyển sang|đảo chiều|quay lại)\b", re.I),
}
WARNING_PATTERNS = {
    "word_comparison": re.compile(r"\b(?:cao hơn|thấp hơn)\b", re.I),
    "ambiguous_relation": re.compile(r"\btương ứng\b", re.I),
}


def scan_template_candidates(template: str) -> tuple[list[str], list[str]]:
    """Return hard errors and measured warnings outside placeholder tokens."""
    prose = TOKEN.sub("", template)
    errors = [f"{kind}: {match.group()}" for kind, pattern in HARD_PATTERNS.items()
              for match in pattern.finditer(prose)]
    warnings = [f"{kind}: {match.group()}" for kind, pattern in WARNING_PATTERNS.items()
                for match in pattern.finditer(prose)]
    return errors, warnings


def scan_unclaimed_blocks(blocks) -> list[str]:
    """Locate candidate assertions in blocks without any typed claim."""
    return [f"{block.block_id}: {issue}" for block in blocks if not block.claims
            for issue in scan_template_candidates(block.text)[0] +
            scan_template_candidates(block.text)[1]]
