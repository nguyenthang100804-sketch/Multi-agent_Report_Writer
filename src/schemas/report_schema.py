"""Contracts for a sourced financial report; tool evidence remains canonical."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Any, Literal

from pydantic import Field, ValidationInfo, model_validator

from src.tools.metric_resolver import metric_name_resolver, normalize_name
from src.tools.schemas import (
    FactEvidence, MetricCandidate, MetricResolverInput, MetricSelection, NoteEvidence,
    Scope, ToolModel, ToolResult, Year,
)

TrendDirection = Literal["increasing", "decreasing", "flat", "mixed"]
FACT_CITATION_PATTERN = re.compile(r"\[Doc_[A-Za-z0-9_]+, p\.[1-9][0-9]*\]")
NOTE_CITATION_PATTERN = re.compile(r"\[Doc_[A-Za-z0-9_]+, p\.[1-9][0-9]*(?:-[1-9][0-9]*)?\]")


class ReportRequest(ToolModel):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    start_year: Year
    end_year: Year
    scope: Scope = "consolidated"
    report_type: Literal["multi_year_financial_analysis"] = "multi_year_financial_analysis"
    audience: str = Field(min_length=1)
    language: str = "vi"
    instructions: str | None = None

    @model_validator(mode="after")
    def check_range(self):
        if self.start_year > self.end_year:
            raise ValueError("start_year must not exceed end_year")
        self.ticker = self.ticker.upper()
        return self


class _MetricTask(MetricSelection):
    task_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_resolved_metric(self):
        if self.metric_name is not None and self.item_code is not None:
            result = metric_name_resolver(MetricResolverInput(metric_name=self.metric_name))
            if result.status != "ok" or len(result.candidates) != 1:
                raise ValueError("metric_name cannot be resolved uniquely with explicit code")
            metric = result.candidates[0]
            if (self.item_code, self.report_type) != (metric.code, metric.report_type):
                raise ValueError("metric_name conflicts with item_code/report_type")
        return self


class FactTask(_MetricTask):
    task_type: Literal["fact"] = "fact"
    fiscal_year: Year


class TimeSeriesTask(_MetricTask):
    task_type: Literal["time_series"] = "time_series"
    start_year: Year
    end_year: Year

    @model_validator(mode="after")
    def check_range(self):
        if self.start_year > self.end_year:
            raise ValueError("start_year must not exceed end_year")
        return self


class NotesTask(ToolModel):
    task_type: Literal["notes"] = "notes"
    task_id: str = Field(min_length=1)
    query: str = Field(min_length=1, max_length=2000)
    fiscal_year: Year
    sections: list[Literal["NOTES", "AUDIT_REPORT", "MANAGEMENT_REPORT"]] = Field(
        default_factory=lambda: ["NOTES"], min_length=1, max_length=3)


class RatioTask(ToolModel):
    task_type: Literal["ratio"] = "ratio"
    task_id: str = Field(min_length=1)
    numerator_task_id: str = Field(min_length=1)
    denominator_task_id: str = Field(min_length=1)
    years: list[Year] = Field(min_length=1)
    positive_denominator: bool = False


class CalculationSpec(ToolModel):
    calculation_id: str = Field(min_length=1)
    operation: Literal["yoy", "cagr", "difference", "trend"]
    source_task_id: str = Field(min_length=1)
    start_year: Year
    end_year: Year

    @model_validator(mode="after")
    def check_years(self):
        if self.start_year >= self.end_year:
            raise ValueError("calculation needs two ordered years")
        if self.operation == "yoy" and self.end_year != self.start_year + 1:
            raise ValueError("YoY needs consecutive years")
        return self


class PlannerNote(ToolModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    section_id: str | None = None


class PlannerObservation(ToolModel):
    observation_id: str = Field(min_length=1)
    tool_name: Literal["metric_name_resolver", "query_fact_tool", "query_time_series_tool",
                       "search_notes_tool"]
    arguments: dict[str, Any]
    snapshot_version: str = Field(min_length=1)
    result: ToolResult


class OutlineDecision(ToolModel):
    action: Literal["keep", "omit", "merge", "split", "add"]
    basis: Literal["data", "audience", "instruction"] = "data"
    template_section_ids: list[str] = Field(default_factory=list)
    resulting_section_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    observation_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_basis(self):
        if self.basis == "data" and not self.observation_ids:
            raise ValueError("data-based decision needs observation IDs")
        return self


class SubsectionPlan(ToolModel):
    subsection_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    task_ids: list[str] = Field(default_factory=list)
    calculation_ids: list[str] = Field(default_factory=list)


ResearchTask = Annotated[FactTask | TimeSeriesTask | NotesTask | RatioTask,
                         Field(discriminator="task_type")]


class SectionPlan(ToolModel):
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    template_section_ids: list[str] = Field(default_factory=list)
    subsections: list[SubsectionPlan] = Field(default_factory=list)
    research_tasks: list[ResearchTask] = Field(default_factory=list)
    calculation_specs: list[CalculationSpec] = Field(default_factory=list)
    calculations_allowed: list[str] = Field(default_factory=list)
    status: Literal["pending", "researching", "drafting", "verifying", "approved", "incomplete"] = "pending"


class ReportOutline(ToolModel):
    outline_id: str | None = None
    sections: list[SectionPlan] = Field(min_length=1)
    calculation_policy: Literal["legacy", "explicit"] = "legacy"

    @model_validator(mode="after")
    def unique_ids(self):
        sections = [section.section_id for section in self.sections]
        all_tasks = [task for section in self.sections for task in section.research_tasks]
        tasks = [task.task_id for task in all_tasks]
        if len(sections) != len(set(sections)) or len(tasks) != len(set(tasks)):
            raise ValueError("section_id and task_id must be unique")
        sources = {task.task_id: task for task in all_tasks
                   if isinstance(task, (FactTask, TimeSeriesTask))}
        specs = [spec for section in self.sections for spec in section.calculation_specs]
        if len({spec.calculation_id for spec in specs}) != len(specs):
            raise ValueError("calculation_id must be unique")
        for spec in specs:
            source = sources.get(spec.source_task_id)
            if not isinstance(source, TimeSeriesTask):
                raise ValueError("calculation source must be a time series task")
            if not source.start_year <= spec.start_year < spec.end_year <= source.end_year:
                raise ValueError("calculation years must be covered by source task")
        subsection_ids = [item.subsection_id for section in self.sections
                          for item in section.subsections]
        if len(subsection_ids) != len(set(subsection_ids)):
            raise ValueError("subsection_id must be unique")
        for section in self.sections:
            declared = {spec.calculation_id for spec in section.calculation_specs}
            declared.update(f"{task.task_id}:{year}" for task in section.research_tasks
                            if isinstance(task, RatioTask) for year in task.years)
            if len(section.calculations_allowed) != len(set(section.calculations_allowed)):
                raise ValueError("calculations_allowed must not contain duplicates")
            if not set(section.calculations_allowed) <= declared:
                raise ValueError("calculations_allowed references undeclared calculation")
            for item in section.subsections:
                if not set(item.task_ids) <= set(tasks):
                    raise ValueError("subsection references unknown task")
                if not set(item.calculation_ids) <= {spec.calculation_id for spec in specs}:
                    raise ValueError("subsection references unknown calculation")
        for task in all_tasks:
            if isinstance(task, RatioTask):
                if task.numerator_task_id not in sources or task.denominator_task_id not in sources:
                    raise ValueError("ratio source task IDs must reference fact or time series tasks")
                if task.numerator_task_id == task.denominator_task_id:
                    raise ValueError("ratio needs two distinct source tasks")
                for year in task.years:
                    for source_id in (task.numerator_task_id, task.denominator_task_id):
                        source = sources[source_id]
                        if (isinstance(source, FactTask) and source.fiscal_year != year or
                            isinstance(source, TimeSeriesTask) and not
                            source.start_year <= year <= source.end_year):
                            raise ValueError("ratio year must be covered by both source tasks")
        return self


class PlannerOutput(ToolModel):
    status: Literal["ready", "needs_clarification", "rejected"]
    outline: ReportOutline | None = None
    notes: list[PlannerNote] = Field(default_factory=list)
    available_scopes: dict[str, list[int]] = Field(default_factory=dict)
    observations: list[PlannerObservation] = Field(default_factory=list)
    decisions: list[OutlineDecision] = Field(default_factory=list)
    prompt_version: str | None = None
    used_fallback: bool = False
    model_turns: int = 0
    repair_count: int = 0
    tool_call_count: int = 0
    elapsed_ms: int = 0
    token_usage: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_outline(self):
        if (self.status == "ready") != (self.outline is not None):
            raise ValueError("Only ready output may contain an outline")
        ids = [item.observation_id for item in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError("observation_id must be unique")
        for decision in self.decisions:
            if not set(decision.observation_ids) <= set(ids):
                raise ValueError("decision references unknown observation")
        return self


class PlannerProposal(ToolModel):
    outline: ReportOutline
    decisions: list[OutlineDecision]
    notes: list[PlannerNote] = Field(default_factory=list)


class PlannerToolCall(ToolModel):
    tool_name: Literal["metric_name_resolver", "query_fact_tool", "query_time_series_tool",
                       "search_notes_tool"]
    arguments: dict[str, Any]


class PlannerTurn(ToolModel):
    action: Literal["observe", "propose"]
    tool_calls: list[PlannerToolCall] = Field(default_factory=list)
    proposal: PlannerProposal | None = None

    @model_validator(mode="after")
    def check_action(self):
        if self.action == "observe" and (not self.tool_calls or self.proposal is not None):
            raise ValueError("observe requires tool calls only")
        if self.action == "propose" and (self.proposal is None or self.tool_calls):
            raise ValueError("propose requires a proposal only")
        return self


class EvidenceRecord(ToolModel):
    evidence_id: str
    kind: Literal["fact", "note"]
    snapshot_version: str = Field(min_length=1)
    payload: FactEvidence | NoteEvidence

    @model_validator(mode="after")
    def check_payload(self):
        if (self.kind == "fact") != isinstance(self.payload, FactEvidence):
            raise ValueError("kind and payload disagree")
        base_id = evidence_id_for(self.payload)
        if self.evidence_id != base_id and not self.evidence_id.startswith(base_id + ":"):
            raise ValueError("evidence_id does not match source metadata")
        return self


def evidence_id_for(payload: FactEvidence | NoteEvidence) -> str:
    if isinstance(payload, NoteEvidence):
        return payload.chunk_id
    key = [payload.doc_id, payload.report_type,
           payload.code if payload.code is not None else normalize_name(payload.label),
           payload.physical_page, "current"]
    return "fact:" + hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()


class MissingItem(ToolModel):
    description: str
    reason: Literal["not_in_corpus", "not_found_yet", "null_or_suspect"]


def action_for_missing(item: MissingItem) -> Literal["retrieve_more", "declare_limitation"]:
    return "retrieve_more" if item.reason == "not_found_yet" else "declare_limitation"


class ResearchResult(ToolModel):
    research_task_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["sufficient", "partial", "no_evidence", "ambiguous", "error"]
    missing: list[MissingItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    candidates: list[MetricCandidate] = Field(default_factory=list)
    safe_for_calculation: bool = False
    next_action: Literal["continue", "retry", "declare_limitation", "needs_clarification", "error"] = "continue"


def record_tool_result(task: ResearchTask, result: ToolResult, snapshot_version: str
                       ) -> tuple[ResearchResult, dict[str, EvidenceRecord]]:
    """Preserve every tool row; never turn backend failure into missing evidence."""
    records: dict[str, EvidenceRecord] = {}
    payloads = [*result.facts, *result.chunks]
    base_counts = {evidence_id_for(payload): sum(
        evidence_id_for(other) == evidence_id_for(payload) for other in payloads
    ) for payload in payloads}
    identical_counts: dict[str, int] = {}
    for payload in payloads:
        base_id = evidence_id_for(payload)
        if base_counts[base_id] == 1:
            evidence_id = base_id
        else:
            content = payload.model_dump(exclude={"fact_index"}, mode="json")
            digest = hashlib.sha256(json.dumps(content, sort_keys=True,
                                               ensure_ascii=False).encode()).hexdigest()[:16]
            prefix = f"{base_id}:{digest}"
            identical_counts[prefix] = identical_counts.get(prefix, 0) + 1
            evidence_id = f"{prefix}:{identical_counts[prefix]}"
        record = EvidenceRecord(evidence_id=evidence_id,
                                kind="fact" if isinstance(payload, FactEvidence) else "note",
                                snapshot_version=snapshot_version, payload=payload)
        records[evidence_id] = record
    duplicate = len(result.facts) > 1 and (
        isinstance(task, FactTask) or
        len({fact.fiscal_year for fact in result.facts}) < len(result.facts)
    )
    warnings = [*result.warnings]
    if duplicate:
        warnings.append("multiple_matching_rows")
    if result.facts:
        from src.agents.period_consistency import period_warnings_for_facts
        warnings.extend(period_warnings_for_facts(result.facts))
    missing = []
    if result.status == "not_found":
        surveyed = result.message == "full_audit_section_surveyed_no_emphasis"
        reason = ("not_in_corpus" if surveyed or not isinstance(task, NotesTask)
                  else "not_found_yet")
        description = ("không tìm thấy trong toàn bộ mục kiểm toán đã trích xuất"
                       if surveyed else "chưa tìm thấy trong các đoạn được truy xuất"
                       if isinstance(task, NotesTask) else "No matching source")
        missing.append(MissingItem(description=description, reason=reason))
    elif result.missing_years:
        for year in result.missing_years:
            invalid_row = any(fact.fiscal_year == year and
                              (fact.value is None or fact.suspect)
                              for fact in result.facts)
            missing.append(MissingItem(description=f"Fiscal year {year}",
                                       reason="null_or_suspect" if invalid_row else "not_in_corpus"))
    status = ("error" if result.status in ("error", "invalid_input") else
              "ambiguous" if result.status == "ambiguous" or duplicate else
              "no_evidence" if not records else
              "partial" if result.status == "partial" else "sufficient")
    next_action = ("error" if status == "error" else
                   "declare_limitation" if duplicate or any(
                       item.reason in ("not_in_corpus", "null_or_suspect") for item in missing) else
                   "needs_clarification" if status == "ambiguous" else
                   "retry" if any(item.reason == "not_found_yet" for item in missing) else
                   "continue")
    return ResearchResult(research_task_id=task.task_id, evidence_ids=list(records),
                          status=status, missing=missing, warnings=warnings,
                          issues=[result.message] if result.status in ("error", "invalid_input") else [],
                          candidates=result.candidates,
                          safe_for_calculation=result.safe_for_calculation,
                          next_action=next_action), records


def research_limitation_text(result: ResearchResult,
                             evidence_by_id: dict[str, EvidenceRecord]) -> str:
    """Name every conflicting source row instead of asking a user to choose one."""
    if result.next_action != "declare_limitation":
        raise ValueError("Research result does not require a limitation")
    lines = (["Không thể chọn một số liệu duy nhất từ các dòng nguồn sau:"]
             if result.evidence_ids else ["Không tìm thấy nguồn cho chỉ tiêu yêu cầu:"])
    facts = [(evidence_id, evidence_by_id[evidence_id].payload)
             for evidence_id in result.evidence_ids
             if isinstance(evidence_by_id[evidence_id].payload, FactEvidence)]
    counts: dict[tuple, int] = {}
    for _, fact in facts:
        key = (fact.fiscal_year, fact.report_type, fact.code)
        counts[key] = counts.get(key, 0) + 1
    if any(count > 1 for count in counts.values()):
        facts = [(evidence_id, fact) for evidence_id, fact in facts
                 if counts[(fact.fiscal_year, fact.report_type, fact.code)] > 1]
    for evidence_id, payload in facts:
        value = "null" if payload.value is None else format(Decimal(str(payload.value)), "f")
        if value.endswith(".0"):
            value = value[:-2]
        lines.append(f"- {payload.fiscal_year}: {payload.label} = {value} "
                     f"{payload.unit}; {payload.citation_tag}; evidence_id={evidence_id}")
    if not result.evidence_ids:
        lines.extend(f"- {item.description}: {item.reason}" for item in result.missing)
    return "\n".join(lines)


class Claim(ToolModel):
    claim_id: str
    claim_type: Literal["direct_fact", "calculated", "qualitative"]
    evidence_ids: list[str] = Field(min_length=1)
    calculation_id: str | None = None
    metric: str | None = None
    fiscal_year: Year | None = None
    value: Decimal | None = None
    unit: str | None = None
    display_value: Decimal | None = None
    display_unit: str | None = None
    display_scale: Decimal = Field(default=Decimal(1), gt=0)
    display_sign: Literal["signed", "magnitude"] = "signed"
    display_rounding_decimals: int | None = Field(default=None, ge=0)
    asserted_direction: TrendDirection | None = None
    asserted_value: Decimal | None = None
    asserted_unit: str | None = None
    rounding_decimals: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_claim(self):
        if self.claim_type == "direct_fact" and any(
            value is None for value in (self.metric, self.fiscal_year, self.value,
                                        self.unit, self.display_value, self.display_unit)
        ):
            raise ValueError("direct_fact needs source and display values, years and units")
        if self.claim_type == "calculated" and self.calculation_id is None:
            raise ValueError("calculated claim needs calculation_id")
        if self.claim_type == "calculated" and ((self.asserted_direction is None) ==
                                                (self.asserted_value is None)):
            raise ValueError("calculated claim needs exactly one asserted result")
        if self.asserted_value is not None and self.asserted_unit is None:
            raise ValueError("numeric assertion needs asserted_unit")
        if self.asserted_value is not None and (self.display_value is None or
                                                self.display_unit is None):
            raise ValueError("numeric assertion needs a display value and unit")
        if self.asserted_direction is not None and (self.asserted_unit is not None or
                                                     self.rounding_decimals is not None):
            raise ValueError("direction assertion has no unit or rounding")
        if self.claim_type != "calculated" and self.calculation_id is not None:
            raise ValueError("only calculated claims may reference a calculation")
        if self.claim_type != "calculated" and any(value is not None for value in (
            self.asserted_direction, self.asserted_value, self.asserted_unit, self.rounding_decimals
        )):
            raise ValueError("only calculated claims may assert a calculation result")
        return self


class DraftBlock(ToolModel):
    block_id: str
    template: str | None = None
    text: str
    claims: list[Claim] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_rendered_fields(self, info: ValidationInfo):
        if self.template is None or not info.context:
            return self
        from src.agents.draft_rendering import render_template
        expected_text, expected_claims = render_template(
            self.template, self.block_id, info.context["evidence_by_id"],
            info.context["calculations_by_id"], info.context["evidence_aliases"])
        if self.text != expected_text or self.claims != expected_claims:
            raise ValueError("Text or claims differ from rendered template")
        return self


class DraftLimitation(ToolModel):
    kind: Literal["period_inconsistency"] = "period_inconsistency"
    warning_code: str = Field(pattern=r"^period_inconsistency:\d{4}->\d{4}$")
    evidence_ids: list[str] = Field(min_length=1)
    block_id: str = Field(min_length=1)


class CannotComputeLimitation(ToolModel):
    kind: Literal["cannot_compute"] = "cannot_compute"
    calculation_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)


class DataGapLimitation(ToolModel):
    kind: Literal["data_gap"] = "data_gap"
    research_task_id: str = Field(min_length=1)
    block_id: str = Field(min_length=1)


Limitation = DraftLimitation | CannotComputeLimitation | DataGapLimitation


class SectionDraft(ToolModel):
    section_id: str
    outline_version: int = Field(ge=1)
    revision: int = Field(ge=1)
    blocks: list[DraftBlock]
    limitations: list[Limitation] = Field(default_factory=list)


class CalculationResult(ToolModel):
    calculation_id: str
    operation: Literal["yoy", "cagr", "difference", "trend", "ratio"]
    input_evidence_ids: list[str] = Field(default_factory=list)
    parameters: dict[str, int | str] = Field(default_factory=dict)
    value: Decimal | None = None
    unit: str | None = None
    direction: TrendDirection | None = None
    status: Literal["ok", "cannot_compute"]
    reason: str | None = None

    @model_validator(mode="after")
    def check_result(self):
        if self.status == "ok" and not self.input_evidence_ids:
            raise ValueError("successful calculation needs input evidence")
        if self.status == "ok" and self.operation == "trend" and (
            self.direction is None or self.value is not None or self.unit is not None
        ):
            raise ValueError("successful trend needs direction only")
        if self.status == "ok" and self.operation != "trend" and (
            self.value is None or self.unit is None or self.direction is not None
        ):
            raise ValueError("successful numeric calculation needs value and unit")
        if self.status == "cannot_compute" and not self.reason:
            raise ValueError("failed calculation needs a reason")
        return self


def calculate_trend(calculation_id: str, research: ResearchResult,
                    evidence_by_id: dict[str, EvidenceRecord],
                    start_year: Year, end_year: Year) -> CalculationResult:
    """Use the tool's safety decision and require a contiguous current-year series."""
    ids = research.evidence_ids
    parameters = {"start_year": start_year, "end_year": end_year,
                  "flat_absolute_threshold": "0"}
    reason = None
    if not research.safe_for_calculation:
        reason = "query_time_series_tool marked the series unsafe"
    from src.agents.period_consistency import warning_affects_years
    if reason is None and warning_affects_years(research.warnings,
                                                set(range(start_year, end_year + 1))):
        reason = "A current value differs from the next report's prior-year value"
    if reason is None and end_year <= start_year:
        reason = "A trend needs at least two years"
    facts = [evidence_by_id[key].payload for key in ids] if reason is None else []
    if reason is None and (any(not isinstance(fact, FactEvidence) for fact in facts) or
                           len(facts) != end_year - start_year + 1 or
                           {fact.fiscal_year for fact in facts} != set(range(start_year, end_year + 1))):
        reason = "A year is missing or duplicated"
    if reason is None and (any(fact.value is None for fact in facts) or
                           len({fact.unit for fact in facts}) != 1):
        reason = "Values or units are missing or inconsistent"
    if reason is not None:
        return CalculationResult(calculation_id=calculation_id, operation="trend",
                                 input_evidence_ids=ids, parameters=parameters,
                                 status="cannot_compute", reason=reason)
    values = [Decimal(str(fact.value)) for fact in sorted(facts, key=lambda fact: fact.fiscal_year)]
    changes = [b - a for a, b in zip(values, values[1:])]
    return CalculationResult(calculation_id=calculation_id, operation="trend",
                             input_evidence_ids=ids, parameters=parameters,
                             direction=("increasing" if changes and all(change > 0 for change in changes)
                                        else "decreasing" if changes and all(change < 0 for change in changes)
                                        else "flat" if changes and all(change == 0 for change in changes)
                                        else "mixed"), status="ok")


def calculated_claim_matches(claim: Claim, calculation: CalculationResult) -> bool:
    """Compare a typed assertion with its successful calculation, without parsing prose."""
    if (claim.claim_type != "calculated" or claim.calculation_id != calculation.calculation_id
            or calculation.status != "ok" or
            len(claim.evidence_ids) != len(calculation.input_evidence_ids) or
            set(claim.evidence_ids) != set(calculation.input_evidence_ids)):
        return False
    if calculation.operation == "trend":
        return claim.asserted_direction == calculation.direction
    if claim.asserted_value is None or claim.asserted_unit != calculation.unit:
        return False
    decimals = claim.rounding_decimals
    if decimals is None:
        return claim.asserted_value == calculation.value
    quantum = Decimal(1).scaleb(-decimals)
    return claim.asserted_value == calculation.value.quantize(quantum, rounding=ROUND_HALF_UP)


def fact_citation_matches_source(fact: FactEvidence) -> bool:
    """Check the exact citation format emitted by DuckDB ingestion for a fact."""
    expected = f"[Doc_{fact.doc_id}, p.{fact.physical_page}]"
    return bool(FACT_CITATION_PATTERN.fullmatch(fact.citation_tag)) and fact.citation_tag == expected


def note_citation_matches_source(note: NoteEvidence) -> bool:
    """Match the parser's single page or min-max page range exactly."""
    if not note.physical_pages or any(page < 1 for page in note.physical_pages):
        return False
    start, end = min(note.physical_pages), max(note.physical_pages)
    pages = str(start) if start == end else f"{start}-{end}"
    expected = f"[Doc_{note.doc_id}, p.{pages}]"
    return bool(NOTE_CITATION_PATTERN.fullmatch(note.citation_tag)) and note.citation_tag == expected


class VerificationIssue(ToolModel):
    claim_id: str
    error_type: Literal["missing_evidence", "invalid_citation", "value_mismatch",
                        "period_mismatch", "unit_mismatch", "scope_mismatch",
                        "conflicting_evidence", "calculation_error", "unsupported_claim",
                        "number_format", "render_mismatch", "missing_limitation",
                        "placeholder_out_of_menu"]
    reason: str
    action: Literal["rewrite", "retrieve_more", "declare_limitation"]
    severity: Literal["error", "warning"] = "error"


class VerificationResult(ToolModel):
    section_id: str
    revision: int = Field(ge=1)
    outline_version: int | None = Field(default=None, ge=1)
    level: Literal["deterministic", "full"]
    status: Literal["passed", "needs_revision", "insufficient_evidence"]
    issues: list[VerificationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_status(self):
        if self.status == "passed" and any(issue.severity == "error" for issue in self.issues):
            raise ValueError("passed verification cannot contain errors")
        return self
