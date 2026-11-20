"""Financial agent tool registry, function schemas, validation and dispatch."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.storage.duckdb_manager import DEFAULT_DB_PATH, DuckDBManager
from .metric_resolver import metric_name_resolver as resolve_metric
from .schemas import (
    FactEvidence, FactQueryInput, MetricResolverInput, NotesSearchInput,
    TimeSeriesQueryInput, ToolResult,
)

LOGGER = logging.getLogger(__name__)
TOOL_INPUTS = {
    "query_fact_tool": FactQueryInput,
    "query_time_series_tool": TimeSeriesQueryInput,
    "search_notes_tool": NotesSearchInput,
    "metric_name_resolver": MetricResolverInput,
}
DESCRIPTIONS = {
    "query_fact_tool": "Look up one accounting metric for one year with source PDF/printed pages and citation. Prefer metric_name, or supply item_code and report_type. Missing evidence is not zero.",
    "query_time_series_tool": "Look up current-period values for one metric across 2022–2025. Preserve units and citations; inspect missing_years and safe_for_calculation before YoY/CAGR or charts.",
    "search_notes_tool": "Find up to five qualitative evidence chunks via filtered Qdrant dense + Vietnamese BM25 + RRF. Default section NOTES; optional audit/management sections. Rank is not evidence confidence.",
    "metric_name_resolver": "Resolve a Vietnamese/English metric alias to standard non-bank accounting code and report_type. Ambiguous or unsupported names require clarification; never guess bank-specific codes.",
}


def get_function_calling_specs() -> list[dict[str, Any]]:
    """Chat-style function calling definitions; arguments validated with Pydantic.

    These are ordinary JSON Schema definitions, not provider-specific strict-mode
    schemas. For clients requiring flat function definitions, flatten each entry's
    `function` object and add `type=function`.
    """
    return [{"type": "function", "function": {
        "name": name, "description": DESCRIPTIONS[name],
        "parameters": schema.model_json_schema(),
    }} for name, schema in TOOL_INPUTS.items()]


def get_output_schema() -> dict[str, Any]:
    """Shared structured output schema for all tools."""
    return ToolResult.model_json_schema()


class AgentTools:
    """Injectable runtime; no model or Qdrant connection until notes are searched."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH,
                 notes_retriever: Any = None) -> None:
        self.db_path = Path(db_path)
        self.notes_retriever = notes_retriever

    def __enter__(self) -> AgentTools:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        if self.notes_retriever is not None:
            self.notes_retriever.close()

    def read_audit_section(self, ticker: str, fiscal_year: int, scope: str) -> ToolResult:
        """Read the full audit section; callers still decide which excerpts answer a task."""
        try:
            if self.notes_retriever is None:
                from .notes_retriever import HybridNotesRetriever
                self.notes_retriever = HybridNotesRetriever()
            chunks = self.notes_retriever.read_audit_section(ticker, fiscal_year, scope)
            return ToolResult(status="ok" if chunks else "not_found", chunks=chunks,
                              message="Complete audit section; classify excerpts by topic.")
        except Exception:
            LOGGER.exception("Reading audit section failed")
            return ToolResult(status="error", message="Audit-section read failed; no evidence was fabricated.")

    def search_notes_candidates(self, arguments: dict[str, Any]) -> ToolResult:
        """Researcher-only wider read; Planner's public tool still returns five chunks."""
        try:
            args = NotesSearchInput.model_validate(arguments)
            if self.notes_retriever is None:
                from .notes_retriever import HybridNotesRetriever
                self.notes_retriever = HybridNotesRetriever()
            chunks = self.notes_retriever.search(
                args, limit=min(30, self.notes_retriever.candidate_pool_size))
            return ToolResult(status="ok" if chunks else "not_found", chunks=chunks)
        except ValidationError as exc:
            return ToolResult(status="invalid_input", message=str(exc))
        except Exception:
            LOGGER.exception("Expanded notes search failed")
            return ToolResult(status="error", message="Expanded notes search failed; no evidence was fabricated.")

    def _facts(self, args: FactQueryInput | TimeSeriesQueryInput) -> ToolResult:
        code, report_type = args.item_code, args.report_type
        if args.metric_name is not None:
            resolved = resolve_metric(MetricResolverInput(metric_name=args.metric_name))
            if resolved.status != "ok":
                return resolved
            metric = resolved.candidates[0]
            if (code is not None and code != metric.code) or (
                    report_type is not None and report_type != metric.report_type):
                return ToolResult(status="invalid_input", message="metric_name conflicts with explicit code/report_type")
            code, report_type = metric.code, metric.report_type
        start = args.fiscal_year if isinstance(args, FactQueryInput) else args.start_year
        end = args.fiscal_year if isinstance(args, FactQueryInput) else args.end_year
        with DuckDBManager(self.db_path) as manager:
            rows = manager.get_time_series(args.ticker, code, start, end,
                                           report_type=report_type, scope=args.scope)
        facts = [FactEvidence.model_validate({key: row[key] for key in FactEvidence.model_fields})
                 for row in rows]
        years = list(range(start, end + 1))
        missing = [year for year in years if not any(
            f.fiscal_year == year and f.value is not None for f in facts)]
        duplicates = any(sum(f.fiscal_year == year for f in facts) > 1 for year in years)
        units = {f.unit for f in facts}
        safe = bool(facts) and not missing and not duplicates and len(units) == 1 and None not in units
        warnings = []
        if duplicates:
            warnings.append("Multiple source rows for the same year; resolve conflicts before selecting a value.")
        if len(units) > 1 or (facts and None in units):
            warnings.append("Units differ or are missing; normalize compatible units before arithmetic.")
        if missing:
            warnings.append("Missing or null evidence is not zero; do not infer values from prior_year.")
        status = ("not_found" if not facts else "ambiguous" if duplicates else
                  "partial" if missing or not safe else "ok")
        return ToolResult(status=status, facts=facts, missing_years=missing,
                          safe_for_calculation=safe, warnings=warnings,
                          message="Current-period source values; formula-specific CAGR/YoY constraints still apply.")

    def execute(self, name: str, arguments: dict[str, Any] | str) -> ToolResult:
        """Validate and dispatch a tool call; failures are explicit structured results."""
        if name not in TOOL_INPUTS:
            return ToolResult(status="invalid_input", message=f"Unknown tool: {name}")
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            args = TOOL_INPUTS[name].model_validate(arguments)
        except (ValidationError, ValueError, TypeError) as exc:
            if isinstance(exc, ValidationError):
                message = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            else:
                message = "Arguments must be a valid JSON object."
            return ToolResult(status="invalid_input", message=message)
        try:
            if name == "metric_name_resolver":
                return resolve_metric(args)
            if name in {"query_fact_tool", "query_time_series_tool"}:
                return self._facts(args)
            if self.notes_retriever is None:
                from .notes_retriever import HybridNotesRetriever
                self.notes_retriever = HybridNotesRetriever()
            chunks = self.notes_retriever.search(args)
            return ToolResult(status="ok" if chunks else "not_found", chunks=chunks,
                              warnings=["Retrieved candidates require evidence checking; RRF rank is not evidence confidence."])
        except Exception:
            LOGGER.exception("Financial tool failed: %s", name)
            return ToolResult(status="error", message="Tool backend failed; inspect application logs. No evidence was fabricated.")


_DEFAULT_TOOLS = AgentTools()


def query_fact_tool(args: FactQueryInput | dict[str, Any]) -> ToolResult:
    """Single-year public tool accepting a validated model or argument dictionary."""
    return _DEFAULT_TOOLS.execute("query_fact_tool", args.model_dump() if isinstance(args, FactQueryInput) else args)


def query_time_series_tool(args: TimeSeriesQueryInput | dict[str, Any]) -> ToolResult:
    """Multi-year public tool accepting a validated model or argument dictionary."""
    return _DEFAULT_TOOLS.execute("query_time_series_tool", args.model_dump() if isinstance(args, TimeSeriesQueryInput) else args)


def search_notes_tool(args: NotesSearchInput | dict[str, Any]) -> ToolResult:
    """Qualitative public tool; reuse AgentTools context manager for explicit cleanup."""
    return _DEFAULT_TOOLS.execute("search_notes_tool", args.model_dump() if isinstance(args, NotesSearchInput) else args)


def metric_name_resolver(args: MetricResolverInput | dict[str, Any]) -> ToolResult:
    """Resolve a supported metric name conservatively."""
    return _DEFAULT_TOOLS.execute("metric_name_resolver", args.model_dump() if isinstance(args, MetricResolverInput) else args)
