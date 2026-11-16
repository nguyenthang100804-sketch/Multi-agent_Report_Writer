"""Detect differences between a year's current value and next year's prior value."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import re

from src.storage.duckdb_manager import DEFAULT_DB_PATH, DuckDBManager
from src.tools.metric_resolver import normalize_name
from src.tools.schemas import FactEvidence


def _key(row: dict) -> tuple:
    identifier = row["code"] if row["code"] is not None else normalize_name(row["label"])
    return row["ticker"], row["scope"], row["report_type"], identifier


def find_period_inconsistencies(rows: list[dict]) -> tuple[int, list[dict]]:
    """Compare available value sets; keep ambiguous groups visible in the result."""
    groups: dict[tuple, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("suspect") or row.get("code") is None and not row.get("label"):
            continue
        groups[_key(row)][row["fiscal_year"]].append(row)
    compared = 0
    issues = []
    for key, years in groups.items():
        for year, current_rows in years.items():
            next_rows = years.get(year + 1, [])
            current = {Decimal(str(row["value"])) for row in current_rows
                       if row.get("value") is not None}
            prior = {Decimal(str(row["prior_year"])) for row in next_rows
                     if row.get("prior_year") is not None}
            units = {row.get("unit") for row in [*current_rows, *next_rows]}
            if not current or not prior or len(units) != 1 or None in units:
                continue
            compared += 1
            if current.isdisjoint(prior):
                issues.append({"ticker": key[0], "scope": key[1], "report_type": key[2],
                               "item_code_or_label": key[3], "year": year,
                               "current_values": [str(value) for value in sorted(current)],
                               "next_prior_values": [str(value) for value in sorted(prior)],
                               "unit": next(iter(units)),
                               "ambiguous_rows": len(current_rows) > 1 or len(next_rows) > 1,
                               "current_docs": sorted({row["doc_id"] for row in current_rows}),
                               "next_docs": sorted({row["doc_id"] for row in next_rows})})
    return compared, sorted(issues, key=lambda issue: (
        issue["ticker"], issue["report_type"], issue["item_code_or_label"], issue["year"]))


def scan_period_consistency(db_path: str | Path = DEFAULT_DB_PATH) -> tuple[int, list[dict]]:
    """Scan all non-suspect facts in the DuckDB corpus without mutating it."""
    with DuckDBManager(db_path) as manager:
        result = manager.connection.execute(
            "SELECT ticker, scope, report_type, code, label, fiscal_year, "
            "current_year AS value, prior_year, unit, doc_id, suspect "
            "FROM financial_facts WHERE fiscal_year BETWEEN 2022 AND 2025"
        )
        columns = [column[0] for column in result.description]
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
    return find_period_inconsistencies(rows)


def period_warnings_for_facts(facts: list[FactEvidence]) -> list[str]:
    rows = [dict(ticker=f.ticker, scope=f.scope, report_type=f.report_type,
                 code=f.code, label=f.label, fiscal_year=f.fiscal_year,
                 value=f.value, prior_year=f.prior_year, unit=f.unit,
                 doc_id=f.doc_id, suspect=f.suspect) for f in facts]
    _, issues = find_period_inconsistencies(rows)
    return [f"period_inconsistency:{issue['year']}->{issue['year'] + 1}"
            for issue in issues]


def warning_affects_years(warnings: list[str], years: set[int]) -> bool:
    for warning in warnings:
        match = re.fullmatch(r"period_inconsistency:(\d{4})->(\d{4})", warning)
        if match and {int(match[1]), int(match[2])}.issubset(years):
            return True
    return False
