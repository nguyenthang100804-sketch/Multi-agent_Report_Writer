"""Read-only, request-scoped tools and provenance for the Planner LLM."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from src.agents.state import snapshot_version_for_db, snapshot_version_for_note_index
from src.schemas.report_schema import PlannerObservation, PlannerToolCall, ReportRequest
from src.tools.agent_tools import AgentTools
from src.tools.metric_resolver import METRICS, metric_name_resolver
from src.tools.schemas import (
    FactQueryInput, MetricResolverInput, NotesSearchInput, TimeSeriesQueryInput,
    ToolResult,
)


class PlannerToolbox:
    """The LLM may choose reads, but cannot change ticker, scope or source type."""

    def __init__(self, request: ReportRequest, tools: AgentTools,
                 note_snapshot_version: str | None = None):
        self.request = request
        self.tools = tools
        self.fact_snapshot = snapshot_version_for_db(tools.db_path)
        self.note_snapshot = note_snapshot_version
        if self.note_snapshot is None:
            try:
                self.note_snapshot = snapshot_version_for_note_index()
            except FileNotFoundError:
                pass
        self.resolver_snapshot = hashlib.sha256(
            json.dumps(METRICS, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.observations: dict[str, PlannerObservation] = {}

    def observe(self, call: PlannerToolCall) -> PlannerObservation:
        name = call.tool_name
        supplied = dict(call.arguments)
        if name == "metric_name_resolver":
            args = MetricResolverInput.model_validate(supplied).model_dump()
            result = metric_name_resolver(MetricResolverInput(**args))
            snapshot = self.resolver_snapshot
        else:
            if supplied.get("ticker", self.request.ticker).upper() != self.request.ticker:
                raise ValueError("Planner tool ticker differs from request")
            if supplied.get("scope", self.request.scope) != self.request.scope:
                raise ValueError("Planner tool scope differs from request")
            supplied["ticker"], supplied["scope"] = self.request.ticker, self.request.scope
            if name in {"query_fact_tool", "query_time_series_tool"}:
                if "item_code" in supplied or "report_type" in supplied:
                    raise ValueError("Planner must resolve a metric name; explicit codes are not accepted")
                model = FactQueryInput if name == "query_fact_tool" else TimeSeriesQueryInput
                supplied = model.model_validate(supplied).model_dump()
                self._check_years(supplied)
                metric_name = supplied["metric_name"]
                resolved = metric_name_resolver(MetricResolverInput(metric_name=metric_name))
                if resolved.status != "ok" or len(resolved.candidates) != 1:
                    args = supplied
                    result = resolved
                else:
                    metric = resolved.candidates[0]
                    supplied.update(item_code=metric.code, report_type=metric.report_type)
                    args = model.model_validate(supplied).model_dump()
                    self._check_years(args)
                    result = self.tools.execute(name, args)
                snapshot = self.fact_snapshot
            else:
                args = NotesSearchInput.model_validate(supplied).model_dump()
                self._check_years(args)
                snapshot = self.note_snapshot or "note-snapshot-unavailable"
                result = (self.tools.execute(name, args) if self.note_snapshot else
                          ToolResult(status="error", message="Note snapshot version is unavailable"))
        payload = json.dumps([name, args, snapshot], ensure_ascii=False, sort_keys=True)
        observation_id = "obs:" + hashlib.sha256(payload.encode()).hexdigest()[:20]
        observation = PlannerObservation(observation_id=observation_id, tool_name=name,
                                         arguments=args, snapshot_version=snapshot,
                                         result=result)
        prior = self.observations.get(observation_id)
        if prior is not None and prior != observation:
            raise ValueError("The same tool arguments returned conflicting data")
        self.observations[observation_id] = observation
        return observation

    def _check_years(self, args: dict[str, Any]) -> None:
        first = args.get("fiscal_year", args.get("start_year"))
        last = args.get("fiscal_year", args.get("end_year"))
        if first < self.request.start_year or last > self.request.end_year:
            raise ValueError("Planner tool year is outside the requested range")

    @staticmethod
    def preview(observation: PlannerObservation) -> dict[str, Any]:
        """Send compact evidence data to the LLM; retain the full result in state."""
        result = observation.result
        return {
            "observation_id": observation.observation_id,
            "tool_name": observation.tool_name,
            "arguments": observation.arguments,
            "status": result.status,
            "message": result.message,
            "missing_years": result.missing_years,
            "safe_for_calculation": result.safe_for_calculation,
            "warnings": result.warnings,
            "candidates": [x.model_dump(mode="json") for x in result.candidates],
            "facts": [{"year": x.fiscal_year, "code": x.code,
                       "report_type": x.report_type, "value": x.value,
                       "unit": x.unit, "suspect": x.suspect}
                      for x in result.facts],
            "chunks": [{"chunk_id": x.chunk_id, "year": x.fiscal_year,
                        "section": x.section, "text_excerpt": x.text[:300]}
                       for x in result.chunks[:5]],
        }
