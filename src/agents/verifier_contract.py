"""Typed boundary between the deterministic Verifier and the LLM Semantic Judge."""
from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


SemanticCategory = Literal[
    "metric_label_mismatch",
    "period_binding_mismatch",
    "calculation_semantics_mismatch",
    "polarity_or_value_judgment",
    "note_unsupported_or_extrapolated",
    "note_contradiction",
    "unclaimed_causal_assertion",
    "unclaimed_comparison_or_forecast",
    "unclaimed_factual_assertion",
]

AllowedErrorType = Literal[
    "unsupported_claim",
    "period_mismatch",
    "value_mismatch",
    "calculation_error",
    "missing_evidence",
    "conflicting_evidence",
]


class VerifiedClaimView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_id: str
    claim_type: Literal["direct_fact", "calculated", "qualitative"]
    placeholder_token: str | None = None
    rendered_fragment: str | None = None
    metric_label: str | None = None
    report_type: str | None = None
    operation: str | None = None
    fiscal_year_or_period: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class CitedFactView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    alias: str | None = None
    metric_label: str
    code: str | None = None
    report_type: str
    fiscal_year: int
    value: str
    unit: str


class CitedNoteView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    fiscal_year: int
    section: str
    topic_roles: list[str] = Field(default_factory=list)
    text: str


class VerifierBlockView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str
    template: str | None = None
    text: str
    claims: list[VerifiedClaimView] = Field(default_factory=list)
    regex_warnings: list[str] = Field(default_factory=list)


class VerifierSectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    scope: str
    start_year: int
    end_year: int
    section_id: str
    title: str
    objective: str
    blocks: list[VerifierBlockView]
    cited_facts: dict[str, CitedFactView] = Field(default_factory=dict)
    cited_notes: dict[str, CitedNoteView] = Field(default_factory=dict)
    declared_limitations: list[str] = Field(default_factory=list)


class SemanticBlockFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str = Field(min_length=1)
    claim_id: str | None = None
    verdict: Literal["supported", "unsupported", "contradicted", "extrapolated"]
    category: SemanticCategory | None = None
    error_type: AllowedErrorType | None = None
    action: Literal["rewrite", "retrieve_more", "declare_limitation"] = "rewrite"
    severity: Literal["error", "warning"] = "error"
    offending_span: str = ""
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_finding_fields(self):
        if self.verdict != "supported" and (self.category is None or self.error_type is None):
            raise ValueError("Non-supported finding requires category and error_type")
        return self


class SemanticBlockVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str = Field(min_length=1)
    status: Literal["passed", "failed"]
    findings: list[SemanticBlockFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_verdict_consistency(self):
        for finding in self.findings:
            if finding.block_id != self.block_id:
                raise ValueError(f"Finding block_id {finding.block_id} does not match {self.block_id}")
        has_error = any(
            finding.verdict != "supported" and finding.severity == "error"
            for finding in self.findings
        )
        if self.status == "passed" and has_error:
            raise ValueError("passed block verdict cannot contain error findings")
        if self.status == "failed" and not has_error:
            raise ValueError("failed block verdict requires at least one error finding")
        return self


class SemanticVerificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_id: str = Field(min_length=1)
    block_verdicts: list[SemanticBlockVerdict]


class VerifierRequest(BaseModel):
    system: str
    section_view: str
    feedback: list[str] = Field(default_factory=list)
    response_schema: dict


class VerifierResponse(BaseModel):
    text: str
    token_usage: dict[str, int] = Field(default_factory=dict)


class VerifierModel(Protocol):
    def verify(self, request: VerifierRequest) -> VerifierResponse: ...


class VerifierRunLog(BaseModel):
    section_id: str
    outline_version: int = 1
    revision: int
    mode: Literal["blocking", "shadow"] = "blocking"
    deterministic_status: str
    semantic_called: bool
    semantic_status: str | None = None
    final_level: Literal["deterministic", "full"]
    attempts: int = 0
    errors_by_attempt: list[list[str]] = Field(default_factory=list)
    issue_count: int = 0
    raw_outputs_by_attempt: list[str | None] = Field(default_factory=list)
    attempt_elapsed_ms: list[int] = Field(default_factory=list)
    prompt_version: str
    token_usage: dict[str, int] = Field(default_factory=dict)
    elapsed_ms: int = 0
    error_message: str | None = None
