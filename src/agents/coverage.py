"""Read-only corpus coverage gate before report planning."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field

from src.schemas.report_schema import ReportRequest
from src.storage.duckdb_manager import DEFAULT_DB_PATH, DuckDBManager
from src.tools.schemas import ToolModel


class CoverageResult(ToolModel):
    ticker: str
    scope: str
    available_years: list[int] = Field(default_factory=list)
    missing_years: list[int] = Field(default_factory=list)
    available_scopes: dict[str, list[int]] = Field(default_factory=dict)
    has_standard_codes: bool = False


class CoverageError(ValueError):
    def __init__(self, result: CoverageResult):
        self.result = result
        super().__init__(f"No corpus coverage for {result.ticker}/{result.scope} "
                         f"in years {result.missing_years}; available scopes: "
                         f"{result.available_scopes}")


def available_scopes(ticker: str, db_path: str | Path = DEFAULT_DB_PATH
                     ) -> dict[str, list[int]]:
    """Return observed non-suspect fiscal years for each scope of a ticker."""
    with DuckDBManager(db_path) as manager:
        rows = manager.connection.execute(
            "SELECT scope, fiscal_year FROM financial_facts "
            "WHERE ticker = ? AND suspect IS NOT TRUE "
            "GROUP BY scope, fiscal_year ORDER BY scope, fiscal_year",
            [ticker.upper()],
        ).fetchall()
    scopes: dict[str, list[int]] = {}
    for scope, year in rows:
        scopes.setdefault(scope, []).append(year)
    return scopes


def check_coverage(request: ReportRequest, db_path: str | Path = DEFAULT_DB_PATH) -> CoverageResult:
    """Require at least one non-suspect fact for each ticker/year/scope."""
    with DuckDBManager(db_path) as manager:
        rows = manager.connection.execute(
            "SELECT DISTINCT fiscal_year FROM financial_facts "
            "WHERE ticker = ? AND scope = ? AND suspect IS NOT TRUE "
            "AND fiscal_year BETWEEN ? AND ? "
            "ORDER BY fiscal_year",
            [request.ticker, request.scope, request.start_year, request.end_year],
        ).fetchall()
        standard = manager.connection.execute(
            "SELECT count(*) FROM financial_facts WHERE ticker = ? AND scope = ? "
            "AND report_type = 'BALANCE_SHEET' AND code = '270' "
            "AND current_year IS NOT NULL AND suspect IS NOT TRUE",
            [request.ticker, request.scope],
        ).fetchone()[0] > 0
    years = [year for (year,) in rows]
    result = CoverageResult(ticker=request.ticker, scope=request.scope,
                            available_years=years,
                            available_scopes=available_scopes(request.ticker, db_path),
                            has_standard_codes=standard,
                            missing_years=sorted(set(range(request.start_year, request.end_year + 1))
                                                 - set(years)))
    if result.missing_years:
        raise CoverageError(result)
    return result
