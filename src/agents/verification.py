"""Citation rendering, deterministic checks, and LLM semantic verification."""
from __future__ import annotations

import json
from pathlib import Path
import re
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from src.schemas.report_schema import (
    CalculationResult, CannotComputeLimitation, Claim, DataGapLimitation,
    DraftBlock, DraftLimitation, EvidenceRecord, NotesTask, ReportRequest, ResearchResult,
    SectionDraft, SectionPlan, VerificationIssue, VerificationResult, calculated_claim_matches,
    fact_citation_matches_source, note_citation_matches_source,
)
from src.agents.citation_recall import scan_template_candidates
from src.agents.planner_rules import METRIC_RULES, RATIO_LABELS
from src.agents.report_tables import UNIT_FACTORS, _vi
from src.agents.verifier_contract import (
    CitedFactView, CitedNoteView, SemanticVerificationOutput, VerifiedClaimView,
    VerifierBlockView, VerifierModel, VerifierRequest, VerifierResponse,
    VerifierRunLog, VerifierSectionView,
)
from src.tools.metric_resolver import METRICS, metric_name_resolver, normalize_name
from src.tools.schemas import FactEvidence, MetricResolverInput, NoteEvidence

VERIFIER_PROMPT_PATH = Path(__file__).parent / "prompts" / "verifier_system.md"
VERIFIER_PROMPT_VERSION = "sv1-v1"

_MANUAL_CITATION = re.compile(r"\[[^\[\]]+\]")
_NUMBER = re.compile(r"(?<![\w])[-+−]?\d[\d.,]*(?![\w])")
_PERIOD_WARNING = re.compile(r"^period_inconsistency:(\d{4})->(\d{4})$")
_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")
_HEADING_NUMBER = re.compile(r"\b(?:mục|phần|chương|thuyết minh|điều|quý|tháng|ngày)\s+\d+\b(?![.,]\d|%)", re.IGNORECASE)


def _parse_number(token: str) -> Decimal:
    token = token.strip(".,").replace("−", "-")
    unsigned = token.lstrip("+-")
    if "," in unsigned:
        whole, fraction = unsigned.split(",", 1)
        if not fraction.isdigit() or ("." in whole and not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", whole)):
            raise ValueError(token)
        return Decimal(token.replace(".", "").replace(",", "."))
    if "." in unsigned and not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", unsigned):
        if not re.fullmatch(r"\d+\.\d+", unsigned):
            raise ValueError(token)
        return Decimal(token)
    return Decimal(token.replace(".", ""))


def _extract_numbers(text: str) -> tuple[list[Decimal], list[str]]:
    values = []
    invalid = []
    clean = _HEADING_NUMBER.sub("", _DATE.sub("", _MANUAL_CITATION.sub("", text)))
    for match in _NUMBER.finditer(clean):
        prefix = clean[max(0, match.start() - 12):match.start()]
        if re.search(r"(?:^|\n)\s*$", prefix) and match.group().endswith("."):
            continue
        token = match.group().strip(".,")
        if token:
            try:
                values.append(_parse_number(token))
            except ValueError:
                invalid.append(token)
    return values, invalid


def _numbers(text: str) -> list[Decimal]:
    return _extract_numbers(text)[0]


def _display_matches(claim: Claim, source_value: Decimal) -> bool:
    if claim.display_value is None:
        return False
    value = abs(source_value) if claim.display_sign == "magnitude" else source_value
    value /= claim.display_scale
    decimals = (claim.display_rounding_decimals if claim.display_rounding_decimals is not None
                else claim.rounding_decimals if claim.claim_type == "calculated" else None)
    if decimals is not None:
        quantum = Decimal(1).scaleb(-decimals)
        value = value.quantize(quantum, rounding=ROUND_HALF_UP)
    return value == claim.display_value


def _display_unit_matches(claim: Claim) -> bool:
    source_unit = claim.unit if claim.claim_type == "direct_fact" else claim.asserted_unit
    display = (claim.display_unit or "").casefold().strip()
    if source_unit == "percent":
        return display in ("%", "phần trăm", "percent") and claim.display_scale == 1
    vnd_source_scale = {"VND": 1, "thousand_VND": 1000,
                        "million_VND": 1000000, "billion_VND": 1000000000}
    if source_unit in vnd_source_scale:
        if "usd" in display or "đô la" in display:
            return False
        suffix = "đồng" if display.endswith("đồng") else "vnd" if display.endswith("vnd") else None
        if suffix is None:
            return False
        prefix = display[:-len(suffix)].strip()
        display_scale = {"": 1, "nghìn": 1000, "triệu": 1000000,
                         "tỷ": 1000000000, "nghìn tỷ": 1000000000000}.get(prefix)
        return display_scale is not None and claim.display_scale == Decimal(
            display_scale) / vnd_source_scale[source_unit]
    if source_unit == "USD":
        suffix = "usd" if display.endswith("usd") else "đô la" if display.endswith("đô la") else None
        prefix = display[:-len(suffix)].strip() if suffix else None
        return suffix is not None and claim.display_scale == {
            "": 1, "nghìn": 1000, "triệu": 1000000, "tỷ": 1000000000}.get(prefix)
    return source_unit is not None and source_unit.casefold() == display and claim.display_scale == 1


_DIRECTION_WORDS = {
    "increasing": ("tăng",), "decreasing": ("giảm",),
    "flat": ("đi ngang", "ổn định", "không đổi"),
    "mixed": ("tăng giảm", "không đều"),
}

_CALCULATION_REASONS = {
    "An input value is null or suspect": "đầu vào thiếu giá trị hoặc bị đánh dấu nghi vấn",
    "Ratio input is null or suspect": "đầu vào thiếu giá trị hoặc bị đánh dấu nghi vấn",
    "A ratio input has a cross-report period inconsistency":
        "đầu vào có cảnh báo không nhất quán giữa các kỳ báo cáo",
    "Ratio denominator is zero": "mẫu số bằng không",
    "A year is missing or duplicated": "chuỗi năm thiếu hoặc có dòng trùng",
    "CAGR needs every year and a positive period": "chuỗi năm không đầy đủ",
    "query_time_series_tool marked the series unsafe":
        "chuỗi số liệu không đủ điều kiện để tính",
}


def _direction_matches(text: str, direction: str) -> bool:
    words = text.casefold()
    expected = _DIRECTION_WORDS[direction]
    # "tăng giảm" is one mixed-direction expression, not two opposite assertions.
    other_words = words.replace("tăng giảm", "") if direction == "mixed" else words
    return any(word in words for word in expected) and not any(
        word in other_words for other, terms in _DIRECTION_WORDS.items()
        if other != direction for word in terms)


def limitation_sentence(warning_code: str, label: str = "Chỉ tiêu",
                        earlier: FactEvidence | None = None,
                        later: FactEvidence | None = None) -> str:
    match = _PERIOD_WARNING.fullmatch(warning_code)
    if match is None:
        raise ValueError(f"Unknown limitation warning: {warning_code}")
    if (earlier is not None and later is not None and earlier.value is not None and
            later.prior_year is not None and earlier.unit == later.unit and
            earlier.unit in UNIT_FACTORS):
        factor = UNIT_FACTORS[earlier.unit] / Decimal(10) ** 9
        first = _vi(Decimal(str(earlier.value)) * factor)
        second = _vi(Decimal(str(later.prior_year)) * factor)
        return (f"Giới hạn dữ liệu. {label} năm {match[1]} là {first} tỷ đồng "
                f"theo báo cáo năm {match[1]}, nhưng cột năm trước của báo cáo "
                f"năm {match[2]} ghi {second} tỷ đồng; hai giá trị không khớp.")
    return (f"Giới hạn dữ liệu. {label} năm {match[1]} không khớp cột năm trước "
            f"trong báo cáo năm {match[2]}; có thể có trình bày lại hoặc khác biệt trích xuất.")


def attach_code_limitations(draft: SectionDraft, section: SectionPlan,
                            calculations: dict[str, CalculationResult],
                            research_results: dict[str, ResearchResult]) -> SectionDraft:
    """Add limitations that follow from failed section inputs, independent of Writer."""
    result = draft.model_copy(deep=True)
    result.limitations = [item for item in result.limitations
                          if item.kind == "period_inconsistency"]
    if not result.blocks:
        result.blocks.append(DraftBlock(block_id="data_limitations", template="", text=""))
    block_id = result.blocks[-1].block_id
    task_ids = {task.task_id for task in section.research_tasks}
    calculation_ids = {spec.calculation_id for spec in section.calculation_specs}
    calculation_ids.update(key for key in calculations
                           if any(key.startswith(task_id + ":") for task_id in task_ids))
    for key in sorted(calculation_ids):
        calculation = calculations.get(key)
        if calculation is not None and calculation.status == "cannot_compute" and not any(
            item.kind == "cannot_compute" and item.calculation_id == key
            for item in result.limitations):
            result.limitations.append(CannotComputeLimitation(
                calculation_id=key, block_id=block_id))
    for key in sorted(task_ids):
        research = research_results.get(key)
        if research is not None and research.status in ("no_evidence", "partial") and (
            not research.evidence_ids or research.missing) and not any(
            item.kind == "data_gap" and item.research_task_id == key
            for item in result.limitations):
            result.limitations.append(DataGapLimitation(
                research_task_id=key, block_id=block_id))
    return result


def limitation_code(limitation, calculations: dict[str, CalculationResult],
                    research_results: dict[str, ResearchResult]) -> str:
    if limitation.kind == "period_inconsistency":
        return limitation.warning_code
    if limitation.kind == "data_gap":
        return "data_gap:" + research_results[limitation.research_task_id].status
    reason = calculations[limitation.calculation_id].reason or "unknown"
    return "cannot_compute:" + re.sub(r"[^a-z0-9]+", "_", reason.casefold()).strip("_")


_TASK_LABELS = {key: name for _, key, name, _ in METRIC_RULES}


def _task_label(task_id: str, section: SectionPlan | None) -> str:
    if section is not None:
        task = next((item for item in section.research_tasks
                     if item.task_id == task_id), None)
        if task is not None and getattr(task, "metric_name", None):
            return task.metric_name
    return RATIO_LABELS.get(task_id, _TASK_LABELS.get(task_id, "chỉ tiêu"))


def _calculation_description(calculation: CalculationResult,
                             section: SectionPlan | None,
                             evidence: dict[str, EvidenceRecord]) -> str:
    spec = next((item for item in section.calculation_specs
                 if item.calculation_id == calculation.calculation_id), None) if section else None
    source = spec.source_task_id if spec else calculation.calculation_id.split(":", 1)[0]
    label = _task_label(source, section)
    p = calculation.parameters
    if calculation.operation == "ratio":
        year = p.get("year")
        if year is None and calculation.input_evidence_ids:
            record = evidence.get(calculation.input_evidence_ids[0])
            year = record.payload.fiscal_year if record else None
        return f"{label} năm {year}" if year else label
    if calculation.operation == "yoy":
        return f"mức thay đổi của {label} năm {p.get('current_year')} so với năm {p.get('prior_year')}"
    if calculation.operation == "cagr":
        return (f"tốc độ tăng trưởng kép hằng năm của {label} "
                f"giai đoạn {p.get('start_year')}–{p.get('end_year')}")
    if calculation.operation == "difference":
        return (f"chênh lệch của {label} "
                f"giai đoạn {p.get('start_year')}–{p.get('end_year')}")
    return f"xu hướng của {label} giai đoạn {p.get('start_year')}–{p.get('end_year')}"


def _render_limitations(limitations: list, evidence: dict[str, EvidenceRecord],
                        calculations: dict[str, CalculationResult],
                        research_results: dict[str, ResearchResult],
                        section: SectionPlan | None) -> list[str]:
    """Render root data issues once, then name affected calculations."""
    gap_items = [item for item in limitations if item.kind == "data_gap"]
    period_items = [item for item in limitations if item.kind == "period_inconsistency"]
    failed = {item.calculation_id: calculations[item.calculation_id]
              for item in limitations if item.kind == "cannot_compute" and
              item.calculation_id in calculations}
    handled = set()
    lines = []
    grouped_gaps: dict[tuple, list[tuple]] = {}
    for item in gap_items:
        result = research_results.get(item.research_task_id)
        if result is None:
            continue
        task = (next((task for task in section.research_tasks
                      if task.task_id == item.research_task_id), None)
                if section is not None else None)
        if isinstance(task, NotesTask):
            scope = ("toàn bộ mục kiểm toán đã trích xuất"
                     if task.sections == ["AUDIT_REPORT"] else
                     "các đoạn đã truy xuất")
            state = ("Không tìm thấy nội dung" if result.status == "no_evidence"
                     else "Chưa đủ nội dung")
            lines.append(f"Giới hạn truy xuất. {state} về {task.query.lower()} "
                         f"trong {scope} của báo cáo năm {task.fiscal_year}.")
            continue
        years = tuple(sorted({int(match.group()) for missing in result.missing
                              if (match := re.search(r"\d{4}", missing.description))}))
        affected = [key for key in result.evidence_ids if key in evidence and
                    evidence[key].payload.fiscal_year in years]
        facts = [evidence[key].payload for key in affected
                 if isinstance(evidence[key].payload, FactEvidence)]
        if result.missing and all(m.reason == "not_in_corpus" for m in result.missing):
            issue = "chưa tìm thấy số liệu"
            affected = []
        elif facts and all(f.value is None for f in facts):
            issue = "dữ liệu trích xuất không có giá trị"
        elif any(f.suspect for f in facts):
            issue = "có số liệu bị đánh dấu nghi vấn"
        else:
            issue = "chưa có giá trị sử dụng được"
        code = next((fact.code for fact in facts if fact.code), None)
        if code is None and section is not None:
            task = next((task for task in section.research_tasks
                         if task.task_id == item.research_task_id), None)
            code = getattr(task, "item_code", None)
        label = _task_label(item.research_task_id, section)
        grouped_gaps.setdefault((years, issue), []).append((
            item.research_task_id, label + (f" (mã {code})" if code else ""), affected))
    for (years, issue), group in grouped_gaps.items():
        labels = " và ".join(item[1] for item in group)
        period = " năm " + ", ".join(map(str, years)) if years else ""
        source_ids = list(dict.fromkeys(key for _, _, ids in group for key in ids))
        tags = list(dict.fromkeys(evidence[key].payload.citation_tag for key in source_ids))
        if issue == "dữ liệu trích xuất không có giá trị":
            names = " và ".join(label[0].lower() + label[1:]
                                  for _, label, _ in group)
            sentence = f"Giới hạn dữ liệu. Dữ liệu trích xuất không có giá trị cho {names}{period}."
        else:
            sentence = f"Giới hạn dữ liệu. {labels} {issue}{period}."
        lines.append(sentence + (" " + " ".join(tags) if tags else ""))
        related = []
        for key, calculation in failed.items():
            reason = (calculation.reason or "").casefold()
            if key in handled or not any(term in reason for term in (
                    "null", "suspect", "missing", "unsafe", "0 rows")):
                continue
            if any(key.startswith(task_id + ":") or
                   set(calculation.input_evidence_ids) &
                   set(research_results[task_id].evidence_ids)
                   for task_id, _, _ in group):
                handled.add(key)
                related.append(_calculation_description(calculation, section, evidence))
        if related:
            lines.append("Vì vậy không tính được " + "; ".join(related) + ".")
    by_warning: dict[str, list] = {}
    for item in period_items:
        by_warning.setdefault(item.warning_code, []).append(item)
    for warning, items in by_warning.items():
        match = _PERIOD_WARNING.fullmatch(warning)
        for item in items:
            records = [evidence[key].payload for key in item.evidence_ids
                       if key in evidence and isinstance(evidence[key].payload, FactEvidence)]
            earlier = next((fact for fact in records if fact.fiscal_year == int(match[1])), None)
            later = next((fact for fact in records if fact.fiscal_year == int(match[2]) and
                          earlier is not None and fact.code == earlier.code), None)
            task_id = next((key for key, result in research_results.items()
                            if warning in result.warnings and
                            set(item.evidence_ids).issubset(result.evidence_ids)), None)
            label = _task_label(task_id, section) if task_id else (
                earlier.label if earlier else "Chỉ tiêu")
            tags = list(dict.fromkeys(fact.citation_tag for fact in (earlier, later)
                                      if fact is not None))
            lines.append(limitation_sentence(warning, label, earlier, later) +
                         (" " + " ".join(tags) if tags else ""))
        related = []
        for key, calculation in failed.items():
            if key in handled or "period inconsistency" not in (calculation.reason or ""):
                continue
            handled.add(key)
            related.append(_calculation_description(calculation, section, evidence))
        if related:
            lines.append("Vì vậy không tính được " + "; ".join(related) + ".")
    for key, calculation in failed.items():
        if key in handled:
            continue
        reason = _CALCULATION_REASONS.get(calculation.reason,
                                          "đầu vào không đáp ứng điều kiện tính")
        tags = list(dict.fromkeys(evidence[item].payload.citation_tag
                                  for item in calculation.input_evidence_ids if item in evidence))
        lines.append("Giới hạn dữ liệu. Không thể tính " +
                     _calculation_description(calculation, section, evidence) +
                     " vì " + reason + "." +
                     (" " + " ".join(tags) if tags else ""))
    return lines


def render_section_citations(draft: SectionDraft,
                             evidence_by_id: dict[str, EvidenceRecord],
                             calculations_by_id: dict[str, CalculationResult] | None = None,
                             research_results: dict[str, ResearchResult] | None = None,
                             section_plan: SectionPlan | None = None) -> str:
    """Append deduplicated source tags to each block from evidence metadata only."""
    rendered = []
    for block in draft.blocks:
        if _MANUAL_CITATION.search(block.text):
            raise ValueError("Run verification and remove manual citations before rendering")
        tags = []
        for claim in block.claims:
            for evidence_id in claim.evidence_ids:
                record = evidence_by_id.get(evidence_id)
                if record is None:
                    raise ValueError(f"Unknown evidence ID: {evidence_id}")
                payload = record.payload
                valid = (fact_citation_matches_source(payload) if isinstance(payload, FactEvidence)
                         else note_citation_matches_source(payload))
                if not valid:
                    raise ValueError(f"Invalid source citation for {evidence_id}")
                if payload.citation_tag not in tags:
                    tags.append(payload.citation_tag)
        text = block.text + (" " + " ".join(tags) if tags else "")
        block_limitations = [item for item in draft.limitations
                             if item.block_id == block.block_id]
        if block_limitations:
            text += "\n" + "\n".join(_render_limitations(
                block_limitations, evidence_by_id, calculations_by_id or {},
                research_results or {}, section_plan))
        rendered.append(text)
    return "\n\n".join(rendered)


def _issue(claim_id: str, error_type: str, reason: str, action: str = "rewrite",
           severity: str = "error") -> VerificationIssue:
    return VerificationIssue(claim_id=claim_id, error_type=error_type,
                             reason=reason, action=action, severity=severity)


def verify_section_deterministically(
    draft: SectionDraft, request: ReportRequest,
    evidence_by_id: dict[str, EvidenceRecord],
    calculations_by_id: dict[str, CalculationResult],
    research_results: dict[str, ResearchResult],
    evidence_aliases: dict[str, str] | None = None,
    section_plan: SectionPlan | None = None,
) -> VerificationResult:
    """Check references, metadata, exact facts and arithmetic; semantic review follows."""
    issues = []
    research_by_evidence: dict[str, list[ResearchResult]] = {}
    for research in research_results.values():
        for evidence_id in research.evidence_ids:
            research_by_evidence.setdefault(evidence_id, []).append(research)
    block_ids = {block.block_id for block in draft.blocks}
    section_task_ids = ({task.task_id for task in section_plan.research_tasks}
                        if section_plan is not None else None)
    section_calculation_ids = ({spec.calculation_id for spec in section_plan.calculation_specs}
                               if section_plan is not None else None)
    if section_plan is not None:
        section_calculation_ids.update(key for key in calculations_by_id
            if any(key.startswith(task_id + ":") for task_id in section_task_ids))
    for limitation in draft.limitations:
        if limitation.kind == "period_inconsistency":
            valid = (all(key in evidence_by_id for key in limitation.evidence_ids) and
                any(limitation.warning_code in research.warnings and
                    set(limitation.evidence_ids).issubset(research.evidence_ids)
                    for research in research_results.values()))
        elif limitation.kind == "cannot_compute":
            calculation = calculations_by_id.get(limitation.calculation_id)
            valid = (calculation is not None and calculation.status == "cannot_compute" and
                     (section_calculation_ids is None or
                      limitation.calculation_id in section_calculation_ids))
        else:
            research = research_results.get(limitation.research_task_id)
            valid = (research is not None and research.status in ("no_evidence", "partial")
                     and (section_task_ids is None or
                          limitation.research_task_id in section_task_ids)
                     and (not research.evidence_ids or bool(research.missing)))
        if limitation.block_id not in block_ids or not valid:
            issues.append(_issue(limitation.block_id, "period_mismatch",
                                 "Invalid limitation declaration"))
    if section_plan is not None:
        calculation_ids = {spec.calculation_id for spec in section_plan.calculation_specs}
        task_ids = {task.task_id for task in section_plan.research_tasks}
        calculation_ids.update(key for key in calculations_by_id
                               if any(key.startswith(task_id + ":") for task_id in task_ids))
        for calculation_id in calculation_ids:
            calculation = calculations_by_id.get(calculation_id)
            if calculation is not None and calculation.status == "cannot_compute" and not any(
                item.kind == "cannot_compute" and item.calculation_id == calculation_id
                for item in draft.limitations):
                issues.append(_issue(calculation_id, "missing_limitation",
                                     "Failed calculation has no limitation"))
        for task_id in task_ids:
            research = research_results.get(task_id)
            if research is not None and research.status in ("no_evidence", "partial") and (
                not research.evidence_ids or research.missing) and not any(
                item.kind == "data_gap" and item.research_task_id == task_id
                for item in draft.limitations):
                issues.append(_issue(task_id, "missing_limitation",
                                     "Data gap has no limitation"))
    for block in draft.blocks:
        if block.template is not None:
            if section_plan is not None:
                from src.agents.writer_menu import build_placeholder_menu, validate_template_menu
                menu = build_placeholder_menu(section_plan, {
                    "evidence_by_id": evidence_by_id,
                    "calculations_by_id": calculations_by_id,
                    "research_results": research_results,
                    "evidence_aliases": evidence_aliases or {},
                })
                try:
                    validate_template_menu(block.template, menu)
                except ValueError as exc:
                    issues.append(_issue(block.block_id, "placeholder_out_of_menu", str(exc)))
            from src.agents.draft_rendering import render_template
            try:
                expected_text, expected_claims = render_template(
                    block.template, block.block_id, evidence_by_id,
                    calculations_by_id, evidence_aliases or {})
            except ValueError as exc:
                issues.append(_issue(block.block_id, "render_mismatch", str(exc)))
            else:
                if expected_text != block.text or ("{{" in block.template and
                                                    expected_claims != block.claims):
                    issues.append(_issue(block.block_id, "render_mismatch",
                                         "Text or claims differ from rendered template"))
        if _MANUAL_CITATION.search(block.text):
            issues.append(_issue(block.block_id, "invalid_citation",
                                 "Writer text contains a manual citation"))
        text_numbers, malformed = _extract_numbers(block.text)
        for token in malformed:
            issues.append(_issue(block.block_id, "number_format",
                                 f"Invalid number format in prose: {token}"))
        display_values = [claim.display_value for claim in block.claims
                          if claim.display_value is not None]
        note_values = {
            number for claim in block.claims if claim.claim_type == "qualitative"
            for evidence_id in claim.evidence_ids
            if evidence_id in evidence_by_id and
            isinstance(evidence_by_id[evidence_id].payload, NoteEvidence)
            for number in _numbers(evidence_by_id[evidence_id].payload.text)
        }
        for number in text_numbers:
            if (number not in display_values and number not in note_values and
                    number not in range(request.start_year, request.end_year + 1)):
                issues.append(_issue(block.block_id, "unsupported_claim",
                                     f"Unlinked number in prose: {number}"))
        for claim in block.claims:
            records = [evidence_by_id[key] for key in claim.evidence_ids
                       if key in evidence_by_id]
            if len(records) != len(claim.evidence_ids):
                issues.append(_issue(claim.claim_id, "missing_evidence", "Unknown evidence ID"))
                continue
            if claim.display_value is not None and claim.display_value not in text_numbers:
                issues.append(_issue(claim.claim_id, "value_mismatch",
                                     "Declared display value is absent from prose"))
            if claim.display_unit is not None and claim.display_unit.casefold() not in block.text.casefold():
                issues.append(_issue(claim.claim_id, "unit_mismatch",
                                     "Declared display unit is absent from prose"))
            if claim.display_unit is not None and not _display_unit_matches(claim):
                issues.append(_issue(claim.claim_id, "unit_mismatch",
                                     "Display currency or unit differs from source"))
            for record in records:
                payload = record.payload
                if payload.scope != request.scope or payload.ticker != request.ticker:
                    issues.append(_issue(claim.claim_id, "scope_mismatch", "Source scope or ticker differs"))
                if not request.start_year <= payload.fiscal_year <= request.end_year:
                    issues.append(_issue(claim.claim_id, "period_mismatch",
                                         "Source year is outside the request range"))
                valid = (fact_citation_matches_source(payload) if isinstance(payload, FactEvidence)
                         else note_citation_matches_source(payload))
                if not valid:
                    issues.append(_issue(claim.claim_id, "invalid_citation", "Source tag differs from metadata"))
                for research in research_by_evidence.get(record.evidence_id, []):
                    for warning in research.warnings:
                        match = _PERIOD_WARNING.fullmatch(warning)
                        if match is None or payload.fiscal_year not in (int(match[1]), int(match[2])):
                            continue
                        covered_years = {evidence_by_id[key].payload.fiscal_year
                                         for key in claim.evidence_ids if key in evidence_by_id}
                        spans_pair = {int(match[1]), int(match[2])}.issubset(covered_years)
                        acknowledged = any(
                            isinstance(limitation, DraftLimitation) and
                            limitation.warning_code == warning and
                            limitation.block_id == block.block_id and
                            set(claim.evidence_ids) == set(limitation.evidence_ids)
                            for limitation in draft.limitations
                        )
                        severity = ("error" if claim.claim_type == "calculated" and
                                    spans_pair and not acknowledged else "warning")
                        issues.append(_issue(
                            claim.claim_id, "period_mismatch",
                            "Cross-report prior-year value differs" +
                            ("; limitation declared" if acknowledged else "; explanation required"),
                            "rewrite" if severity == "error" else "declare_limitation", severity))
            if claim.claim_type == "direct_fact":
                if len(records) != 1 or not isinstance(records[0].payload, FactEvidence):
                    issues.append(_issue(claim.claim_id, "missing_evidence", "Direct fact needs one fact row"))
                    continue
                fact = records[0].payload
                if claim.fiscal_year != fact.fiscal_year:
                    issues.append(_issue(claim.claim_id, "period_mismatch", "Claim year differs from source"))
                if claim.unit != fact.unit:
                    issues.append(_issue(claim.claim_id, "unit_mismatch", "Claim unit differs from source"))
                if fact.value is None or claim.value != Decimal(str(fact.value)):
                    issues.append(_issue(claim.claim_id, "value_mismatch", "Claim value differs from source"))
                if not _display_matches(claim, claim.value):
                    issues.append(_issue(claim.claim_id, "value_mismatch",
                                         "Display value does not match source value and scale"))
                resolved = metric_name_resolver(MetricResolverInput(metric_name=claim.metric))
                if resolved.status == "ok" and (fact.code, fact.report_type) != (
                    resolved.candidates[0].code, resolved.candidates[0].report_type
                ):
                    issues.append(_issue(claim.claim_id, "unsupported_claim", "Metric code differs from source"))
                elif resolved.status != "ok" and normalize_name(claim.metric) != normalize_name(fact.label):
                    issues.append(_issue(claim.claim_id, "unsupported_claim", "Metric label differs from source"))
                same_rows = [other for other in evidence_by_id.values()
                             if isinstance(other.payload, FactEvidence) and
                             (other.payload.ticker, other.payload.scope, other.payload.report_type,
                              other.payload.code, other.payload.fiscal_year) ==
                             (fact.ticker, fact.scope, fact.report_type, fact.code, fact.fiscal_year)]
                if len(same_rows) > 1:
                    issues.append(_issue(claim.claim_id, "conflicting_evidence",
                                         "Multiple source rows match this metric and year",
                                         "declare_limitation"))
            elif claim.claim_type == "calculated":
                calculation = calculations_by_id.get(claim.calculation_id)
                if claim.asserted_direction is not None and not _direction_matches(
                    block.text, claim.asserted_direction
                ):
                    issues.append(_issue(claim.claim_id, "unsupported_claim",
                                         "Prose trend direction differs from typed assertion"))
                if calculation is not None and any(
                    key not in evidence_by_id for key in calculation.input_evidence_ids
                ):
                    issues.append(_issue(claim.claim_id, "missing_evidence",
                                         "Calculation input evidence is missing"))
                if calculation is None or not calculated_claim_matches(claim, calculation):
                    issues.append(_issue(claim.claim_id, "calculation_error",
                                         "Typed assertion or source IDs differ from calculation"))
                elif calculation.value is not None and not _display_matches(claim, calculation.value):
                    issues.append(_issue(claim.claim_id, "value_mismatch",
                                         "Display value does not match calculation and scale"))
            elif any(not isinstance(record.payload, NoteEvidence) for record in records):
                issues.append(_issue(claim.claim_id, "unsupported_claim",
                                     "Qualitative claim must cite note evidence"))
    errors = [issue for issue in issues if issue.severity == "error"]
    status = ("needs_revision" if any(issue.action == "rewrite" for issue in errors)
              else "insufficient_evidence" if errors else "passed")
    return VerificationResult(section_id=draft.section_id, revision=draft.revision,
                              level="deterministic", status=status, issues=issues)


def _is_pure_heading_or_empty(block: DraftBlock) -> bool:
    stripped = block.text.strip()
    if not stripped:
        return True
    return stripped.startswith("#") and "\n" not in stripped and not block.claims


def _calculation_period_label(calculation: CalculationResult,
                              evidence_by_id: dict[str, EvidenceRecord]) -> str | None:
    p = calculation.parameters
    if "current_year" in p and "prior_year" in p:
        return f"năm {p['current_year']} so với năm {p['prior_year']}"
    if "start_year" in p and "end_year" in p:
        return f"giai đoạn {p['start_year']}–{p['end_year']}"
    if "year" in p:
        return f"năm {p['year']}"
    if calculation.input_evidence_ids:
        record = evidence_by_id.get(calculation.input_evidence_ids[0])
        if record is not None:
            return f"năm {record.payload.fiscal_year}"
    return None


def _rendered_fragment_for_claim(claim: Claim, placeholder_token: str | None,
                                 calculation: CalculationResult | None) -> str | None:
    from src.agents.draft_rendering import _number
    if claim.claim_type == "calculated" and claim.asserted_direction is not None:
        if calculation is not None and "start_year" in calculation.parameters and "end_year" in calculation.parameters:
            years = int(calculation.parameters["end_year"]) - int(calculation.parameters["start_year"]) + 1
        else:
            years = 3
        return {"increasing": "tăng" if years == 2 else "tăng liên tục",
                "decreasing": "giảm" if years == 2 else "giảm liên tục",
                "flat": "đi ngang",
                "mixed": "diễn biến không đều"}.get(claim.asserted_direction)
    if claim.display_value is None or claim.display_unit is None:
        return None
    decimals = (claim.display_rounding_decimals if claim.display_rounding_decimals is not None
                else claim.rounding_decimals if claim.claim_type == "calculated" else 0)
    shown = _number(claim.display_value, decimals)
    fragment = shown + ("%" if claim.display_unit == "%" else f" {claim.display_unit}")
    if placeholder_token and placeholder_token.startswith("{{D:") and calculation is not None and calculation.value is not None:
        if calculation.value > 0:
            return f"tăng {fragment}"
        if calculation.value < 0:
            return f"giảm {fragment}"
        return f"không đổi ({fragment})"
    return fragment


def build_verifier_section_view(
    draft: SectionDraft,
    request: ReportRequest,
    evidence_by_id: dict[str, EvidenceRecord],
    calculations_by_id: dict[str, CalculationResult],
    research_results: dict[str, ResearchResult],
    evidence_aliases: dict[str, str] | None = None,
    section_plan: SectionPlan | None = None,
) -> VerifierSectionView:
    """Build an isolated, resolved section view for the LLM Semantic Verifier."""
    from src.agents.draft_rendering import TOKEN

    aliases_by_id = {eid: alias for alias, eid in (evidence_aliases or {}).items()}
    cited_facts: dict[str, CitedFactView] = {}
    cited_notes: dict[str, CitedNoteView] = {}
    block_views: list[VerifierBlockView] = []

    def register_evidence(evidence_id: str) -> None:
        record = evidence_by_id.get(evidence_id)
        if record is None:
            return
        payload = record.payload
        if isinstance(payload, FactEvidence):
            if evidence_id not in cited_facts:
                label = next((name for name, code, report_type, _ in METRICS
                              if (code, report_type) == (payload.code, payload.report_type)),
                             payload.label)
                cited_facts[evidence_id] = CitedFactView(
                    evidence_id=evidence_id,
                    alias=aliases_by_id.get(evidence_id),
                    metric_label=label,
                    code=payload.code,
                    report_type=payload.report_type,
                    fiscal_year=payload.fiscal_year,
                    value="null" if payload.value is None else str(payload.value),
                    unit=payload.unit,
                )
        elif isinstance(payload, NoteEvidence):
            if evidence_id not in cited_notes:
                cited_notes[evidence_id] = CitedNoteView(
                    evidence_id=evidence_id,
                    fiscal_year=payload.fiscal_year,
                    section=payload.section,
                    topic_roles=list(payload.topic_roles),
                    text=payload.text,
                )

    for block in draft.blocks:
        if _is_pure_heading_or_empty(block):
            continue
        value_tokens: list[str] = []
        if block.template is not None:
            value_tokens = [
                match.group(0) for match in TOKEN.finditer(block.template)
                if not match.group(1).startswith(("Y:", "P:C:"))
            ]
        claim_views: list[VerifiedClaimView] = []
        for idx, claim in enumerate(block.claims):
            token = value_tokens[idx] if idx < len(value_tokens) else None
            for eid in claim.evidence_ids:
                register_evidence(eid)
            if claim.claim_type == "direct_fact":
                record = evidence_by_id.get(claim.evidence_ids[0]) if claim.evidence_ids else None
                fact = record.payload if (record and isinstance(record.payload, FactEvidence)) else None
                label = claim.metric or (fact.label if fact else None)
                report_type = fact.report_type if fact else None
                period = f"năm {claim.fiscal_year}" if claim.fiscal_year else None
                fragment = _rendered_fragment_for_claim(claim, token, None)
                claim_views.append(VerifiedClaimView(
                    claim_id=claim.claim_id,
                    claim_type="direct_fact",
                    placeholder_token=token,
                    rendered_fragment=fragment,
                    metric_label=label,
                    report_type=report_type,
                    operation=None,
                    fiscal_year_or_period=period,
                    evidence_ids=list(claim.evidence_ids),
                ))
            elif claim.claim_type == "calculated":
                calculation = calculations_by_id.get(claim.calculation_id or "")
                if calculation is not None:
                    for eid in calculation.input_evidence_ids:
                        register_evidence(eid)
                spec = (next((item for item in section_plan.calculation_specs
                              if item.calculation_id == claim.calculation_id), None)
                        if section_plan and claim.calculation_id else None)
                source_id = (spec.source_task_id if spec else
                             (claim.calculation_id or "").split(":", 1)[0])
                label = _task_label(source_id, section_plan) if source_id else None
                first_rec = (evidence_by_id.get(calculation.input_evidence_ids[0])
                             if calculation and calculation.input_evidence_ids else None)
                report_type = (first_rec.payload.report_type
                               if first_rec and isinstance(first_rec.payload, FactEvidence) else None)
                period = (_calculation_period_label(calculation, evidence_by_id)
                          if calculation is not None else None)
                fragment = _rendered_fragment_for_claim(claim, token, calculation)
                claim_views.append(VerifiedClaimView(
                    claim_id=claim.claim_id,
                    claim_type="calculated",
                    placeholder_token=token,
                    rendered_fragment=fragment,
                    metric_label=label,
                    report_type=report_type,
                    operation=calculation.operation if calculation else None,
                    fiscal_year_or_period=period,
                    evidence_ids=list(claim.evidence_ids),
                ))
            else:
                years = sorted({
                    evidence_by_id[eid].payload.fiscal_year
                    for eid in claim.evidence_ids
                    if eid in evidence_by_id
                })
                period = ("năm " + ", ".join(map(str, years))) if years else None
                claim_views.append(VerifiedClaimView(
                    claim_id=claim.claim_id,
                    claim_type="qualitative",
                    placeholder_token=token,
                    rendered_fragment=None,
                    metric_label=None,
                    report_type="NOTES",
                    operation=None,
                    fiscal_year_or_period=period,
                    evidence_ids=list(claim.evidence_ids),
                ))
        _, soft_warnings = scan_template_candidates(
            block.template if block.template is not None else block.text
        )
        block_views.append(VerifierBlockView(
            block_id=block.block_id,
            template=block.template,
            text=block.text,
            claims=claim_views,
            regex_warnings=soft_warnings,
        ))

    declared_limitations = _render_limitations(
        draft.limitations, evidence_by_id, calculations_by_id,
        research_results, section_plan,
    )
    return VerifierSectionView(
        ticker=request.ticker,
        scope=request.scope,
        start_year=request.start_year,
        end_year=request.end_year,
        section_id=draft.section_id,
        title=section_plan.title if section_plan else draft.section_id,
        objective=section_plan.objective if section_plan else "",
        blocks=block_views,
        cited_facts=cited_facts,
        cited_notes=cited_notes,
        declared_limitations=declared_limitations,
    )


def _validate_semantic_output(output: SemanticVerificationOutput,
                              view: VerifierSectionView) -> list[VerificationIssue]:
    if output.section_id != view.section_id:
        raise ValueError(f"section_id mismatch: expected {view.section_id}, got {output.section_id}")
    expected_ids = [block.block_id for block in view.blocks]
    actual_ids = [item.block_id for item in output.block_verdicts]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("duplicate_block_verdict_id")
    if set(actual_ids) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(actual_ids))
        extra = sorted(set(actual_ids) - set(expected_ids))
        raise ValueError(f"block coverage mismatch: missing={missing}, extra={extra}")
    claims_by_block = {
        block.block_id: {claim.claim_id for claim in block.claims}
        for block in view.blocks
    }
    issues: list[VerificationIssue] = []
    for verdict in output.block_verdicts:
        valid_claims = claims_by_block[verdict.block_id]
        for finding in verdict.findings:
            if (finding.claim_id is not None and
                    finding.claim_id not in valid_claims and
                    finding.claim_id != verdict.block_id):
                raise ValueError(
                    f"unknown claim_id {finding.claim_id} in block {verdict.block_id}"
                )
            if finding.verdict == "supported":
                continue
            reason = f"[{finding.category}] {finding.reason}"
            if finding.offending_span:
                reason += f" (đoạn: '{finding.offending_span}')"
            issues.append(VerificationIssue(
                claim_id=finding.claim_id or finding.block_id,
                error_type=finding.error_type or "unsupported_claim",
                reason=reason,
                action=finding.action,
                severity=finding.severity,
            ))
    return issues


def verify_section_semantically(
    draft: SectionDraft,
    request: ReportRequest,
    evidence_by_id: dict[str, EvidenceRecord],
    calculations_by_id: dict[str, CalculationResult],
    research_results: dict[str, ResearchResult],
    verifier_model: VerifierModel,
    evidence_aliases: dict[str, str] | None = None,
    section_plan: SectionPlan | None = None,
    *,
    deterministic_result: VerificationResult | None = None,
    max_repairs: int = 1,
    record_raw_outputs: bool = False,
) -> tuple[VerificationResult, VerifierRunLog]:
    """Run LLM semantic verification after deterministic verification passes; fail closed on errors."""
    if max_repairs < 0:
        raise ValueError("max_repairs must be nonnegative")
    det = deterministic_result or verify_section_deterministically(
        draft, request, evidence_by_id, calculations_by_id,
        research_results, evidence_aliases, section_plan,
    )
    det = det.model_copy(update={"outline_version": draft.outline_version})
    if det.status != "passed":
        return det, VerifierRunLog(
            section_id=draft.section_id,
            outline_version=draft.outline_version,
            revision=draft.revision,
            deterministic_status=det.status,
            semantic_called=False,
            semantic_status=None,
            final_level="deterministic",
            issue_count=len(det.issues),
            prompt_version=VERIFIER_PROMPT_VERSION,
        )

    view = build_verifier_section_view(
        draft, request, evidence_by_id, calculations_by_id,
        research_results, evidence_aliases, section_plan,
    )
    if not view.blocks:
        full_empty = det.model_copy(update={"level": "full"})
        return full_empty, VerifierRunLog(
            section_id=draft.section_id,
            outline_version=draft.outline_version,
            revision=draft.revision,
            deterministic_status=det.status,
            semantic_called=False,
            semantic_status="passed",
            final_level="full",
            issue_count=len(full_empty.issues),
            prompt_version=VERIFIER_PROMPT_VERSION,
        )

    system = VERIFIER_PROMPT_PATH.read_text(encoding="utf-8")
    started = time.perf_counter()
    errors_by_attempt: list[list[str]] = []
    raw_outputs: list[str | None] = []
    attempt_times: list[int] = []
    token_usage: dict[str, int] = {}
    feedback: list[str] = []
    last_error: str | None = None

    for _ in range(max_repairs + 1):
        attempt_started = time.perf_counter()
        req = VerifierRequest(
            system=system,
            section_view=view.model_dump_json(),
            feedback=feedback,
            response_schema=SemanticVerificationOutput.model_json_schema(),
        )
        try:
            response = VerifierResponse.model_validate(verifier_model.verify(req))
        except Exception as exc:
            last_error = f"model_error: {exc}"
            errors_by_attempt.append([last_error])
            raw_outputs.append(None)
            attempt_times.append(round((time.perf_counter() - attempt_started) * 1000))
            break
        raw_outputs.append(response.text if record_raw_outputs else None)
        for name, count in response.token_usage.items():
            token_usage[name] = token_usage.get(name, 0) + count
        try:
            parsed = SemanticVerificationOutput.model_validate(json.loads(response.text))
            semantic_issues = _validate_semantic_output(parsed, view)
        except Exception as exc:
            last_error = str(exc)
            errors_by_attempt.append([last_error])
            attempt_times.append(round((time.perf_counter() - attempt_started) * 1000))
            feedback = [last_error]
            continue

        errors_by_attempt.append([])
        attempt_times.append(round((time.perf_counter() - attempt_started) * 1000))
        preserved_warnings = [issue for issue in det.issues if issue.severity == "warning"]
        combined_issues = preserved_warnings + semantic_issues
        errors = [issue for issue in combined_issues if issue.severity == "error"]
        status = ("needs_revision" if any(issue.action == "rewrite" for issue in errors)
                  else "insufficient_evidence" if errors else "passed")
        result = VerificationResult(
            section_id=draft.section_id,
            revision=draft.revision,
            outline_version=draft.outline_version,
            level="full",
            status=status,
            issues=combined_issues,
        )
        log = VerifierRunLog(
            section_id=draft.section_id,
            outline_version=draft.outline_version,
            revision=draft.revision,
            deterministic_status=det.status,
            semantic_called=True,
            semantic_status=status,
            final_level="full",
            attempts=len(errors_by_attempt),
            errors_by_attempt=errors_by_attempt,
            issue_count=len(combined_issues),
            raw_outputs_by_attempt=raw_outputs,
            attempt_elapsed_ms=attempt_times,
            prompt_version=VERIFIER_PROMPT_VERSION,
            token_usage=token_usage,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )
        return result, log

    # Fail-closed: never upgrade to level="full" when the semantic verifier fails technically.
    return det, VerifierRunLog(
        section_id=draft.section_id,
        outline_version=draft.outline_version,
        revision=draft.revision,
        deterministic_status=det.status,
        semantic_called=True,
        semantic_status="model_error",
        final_level="deterministic",
        attempts=len(errors_by_attempt),
        errors_by_attempt=errors_by_attempt,
        issue_count=len(det.issues),
        raw_outputs_by_attempt=raw_outputs,
        attempt_elapsed_ms=attempt_times,
        prompt_version=VERIFIER_PROMPT_VERSION,
        token_usage=token_usage,
        elapsed_ms=round((time.perf_counter() - started) * 1000),
        error_message=last_error,
    )


def verify_section_full(
    draft: SectionDraft,
    request: ReportRequest,
    evidence_by_id: dict[str, EvidenceRecord],
    calculations_by_id: dict[str, CalculationResult],
    research_results: dict[str, ResearchResult],
    verifier_model: VerifierModel | None = None,
    evidence_aliases: dict[str, str] | None = None,
    section_plan: SectionPlan | None = None,
    *,
    mode: Literal["blocking", "shadow"] = "blocking",
    max_repairs: int = 1,
    record_raw_outputs: bool = False,
) -> tuple[VerificationResult, VerifierRunLog]:
    """Two-stage verifier entry point: deterministic check first, then optional LLM semantic check.

    When mode='shadow', the semantic verifier runs and logs all findings and raw outputs,
    but does not override the deterministic status or elevate the verification level to 'full'.
    """
    det = verify_section_deterministically(
        draft, request, evidence_by_id, calculations_by_id,
        research_results, evidence_aliases, section_plan,
    ).model_copy(update={"outline_version": draft.outline_version})
    if det.status != "passed" or verifier_model is None:
        return det, VerifierRunLog(
            section_id=draft.section_id,
            outline_version=draft.outline_version,
            revision=draft.revision,
            mode=mode,
            deterministic_status=det.status,
            semantic_called=False,
            semantic_status=None,
            final_level="deterministic",
            issue_count=len(det.issues),
            prompt_version=VERIFIER_PROMPT_VERSION,
        )
    sem_result, sem_log = verify_section_semantically(
        draft, request, evidence_by_id, calculations_by_id,
        research_results, verifier_model, evidence_aliases, section_plan,
        deterministic_result=det, max_repairs=max_repairs,
        record_raw_outputs=(record_raw_outputs or mode == "shadow"),
    )
    if mode == "shadow":
        shadow_issues = [
            issue.model_copy(update={"severity": "warning"}) if issue.severity == "error" else issue
            for issue in sem_result.issues
        ]
        shadow_result = det.model_copy(update={"issues": shadow_issues})
        shadow_log = sem_log.model_copy(update={"mode": "shadow", "final_level": "deterministic"})
        return shadow_result, shadow_log
    return sem_result, sem_log
