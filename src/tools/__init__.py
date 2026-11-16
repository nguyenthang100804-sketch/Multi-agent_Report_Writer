"""Standard financial agent interface, independent of an LLM framework."""
from .agent_tools import (
    AgentTools, get_function_calling_specs, get_output_schema,
    metric_name_resolver, query_fact_tool, query_time_series_tool, search_notes_tool,
)
from .schemas import (
    FactQueryInput, MetricResolverInput, NotesSearchInput, TimeSeriesQueryInput, ToolResult,
)

__all__ = ["AgentTools", "get_function_calling_specs", "get_output_schema",
           "query_fact_tool", "query_time_series_tool", "search_notes_tool",
           "metric_name_resolver", "FactQueryInput", "MetricResolverInput",
           "NotesSearchInput", "TimeSeriesQueryInput", "ToolResult"]
