"""Validated inputs and JSON-serializable outputs for financial agent tools."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Year = Annotated[int, Field(strict=True, ge=2022, le=2025)]
ReportType = Literal["BALANCE_SHEET", "INCOME_STATEMENT", "CASH_FLOW"]
Scope = Literal["consolidated", "separate", "general"]


class ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class MetricResolverInput(ToolModel):
    metric_name: str = Field(min_length=1, max_length=200)


class MetricSelection(ToolModel):
    metric_name: str | None = Field(default=None, min_length=1, max_length=200)
    item_code: str | None = Field(default=None, min_length=1, max_length=20,
                                  description="Accounting code as string; preserve leading zeros.")
    report_type: ReportType | None = None

    @model_validator(mode="after")
    def check_selection(self):
        if self.metric_name is None and (self.item_code is None or self.report_type is None):
            raise ValueError("Supply metric_name or both item_code and report_type")
        if self.item_code is not None and self.report_type is None:
            raise ValueError("Explicit item_code requires report_type")
        return self


class FactQueryInput(MetricSelection):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    fiscal_year: Year
    scope: Scope = "consolidated"

    @field_validator("ticker")
    @classmethod
    def upper_ticker(cls, value: str) -> str:
        return value.upper()


class TimeSeriesQueryInput(MetricSelection):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    start_year: Year = 2022
    end_year: Year = 2025
    scope: Scope = "consolidated"

    @field_validator("ticker")
    @classmethod
    def upper_ticker(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def check_range(self):
        if self.start_year > self.end_year:
            raise ValueError("start_year must not exceed end_year")
        return self


class NotesSearchInput(ToolModel):
    query: str = Field(min_length=1, max_length=2000)
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    fiscal_year: Year
    scope: Scope = "consolidated"
    sections: list[Literal["NOTES", "AUDIT_REPORT", "MANAGEMENT_REPORT"]] = Field(
        default_factory=lambda: ["NOTES"], min_length=1, max_length=3)

    @field_validator("ticker")
    @classmethod
    def upper_ticker(cls, value: str) -> str:
        return value.upper()


class MetricCandidate(ToolModel):
    metric_name: str
    code: str
    report_type: ReportType
    applicability: str = "Standard non-bank Vietnamese financial statements; verify source labels."


class FactEvidence(ToolModel):
    doc_id: str
    fact_index: int
    ticker: str
    fiscal_year: int
    scope: str
    report_type: str
    code: str | None
    label: str
    value: float | None
    raw_value: str | None
    unit: str | None
    prior_year: float | None
    raw_prior: str | None
    suspect: bool | None
    source_file: str
    physical_page: int
    printed_page: str | None
    citation_tag: str
    chunk_ids: list[str]


class NoteEvidence(ToolModel):
    chunk_id: str
    doc_id: str
    ticker: str
    fiscal_year: int
    scope: str
    section: str
    text: str
    source_file: str
    physical_pages: list[int]
    printed_pages: list[str]
    citation_tag: str
    rerank_score: float | None = None
    topic_roles: list[str] = Field(default_factory=list)


class ToolResult(ToolModel):
    status: Literal["ok", "partial", "not_found", "ambiguous", "invalid_input", "error"]
    message: str = ""
    facts: list[FactEvidence] = Field(default_factory=list)
    chunks: list[NoteEvidence] = Field(default_factory=list)
    candidates: list[MetricCandidate] = Field(default_factory=list)
    missing_years: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    safe_for_calculation: bool = False
