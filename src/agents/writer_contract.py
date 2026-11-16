"""Typed boundary between a narrative model and the deterministic Writer."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class WriterRequest(BaseModel):
    system: str
    section_view: str
    feedback: list[str] = Field(default_factory=list)
    response_schema: dict


class WriterResponse(BaseModel):
    text: str
    token_usage: dict[str, int] = Field(default_factory=dict)


class WriterModel(Protocol):
    def generate(self, request: WriterRequest) -> WriterResponse: ...


class NarrativeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    template: str = Field(min_length=1)


class PeriodLimitationDecl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    warning_code: str = Field(pattern=r"^period_inconsistency:\d{4}->\d{4}$")
    evidence_aliases: list[str] = Field(min_length=1)
    block_id: str


class NarrativeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[NarrativeBlock] = Field(min_length=1, max_length=5)
    period_limitations: list[PeriodLimitationDecl] = Field(default_factory=list)


class QualitativeBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str = Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    task_id: str = Field(min_length=1)
    evidence_alias: str = Field(pattern=r"^E[1-9]\d*$")
    quote: str = Field(min_length=30, max_length=650)
    observation: str = Field(min_length=1, max_length=400)


class QualitativeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[QualitativeBlock] = Field(default_factory=list, max_length=12)


class WriterRunLog(BaseModel):
    section_id: str
    revision: int
    attempts: int
    errors_by_attempt: list[list[str]]
    warnings_by_attempt: list[list[str]]
    block_counts_by_attempt: list[int | None] = Field(default_factory=list)
    raw_outputs_by_attempt: list[str | None] = Field(default_factory=list)
    attempt_elapsed_ms: list[int] = Field(default_factory=list)
    used_fallback: bool
    prompt_version: str
    token_usage: dict[str, int] = Field(default_factory=dict)
    elapsed_ms: int
