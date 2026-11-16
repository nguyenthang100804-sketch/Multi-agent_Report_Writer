"""Deterministic arithmetic over current-period, tool-approved facts."""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

from src.agents.period_consistency import warning_affects_years
from src.schemas.report_schema import CalculationResult, EvidenceRecord, ResearchResult
from src.tools.schemas import FactEvidence


def _facts(research: ResearchResult, evidence_by_id: dict[str, EvidenceRecord]
           ) -> tuple[dict[int, FactEvidence], str | None]:
    if not research.safe_for_calculation:
        return {}, "query_time_series_tool marked the series unsafe"
    facts = []
    for evidence_id in research.evidence_ids:
        record = evidence_by_id.get(evidence_id)
        if record is None or not isinstance(record.payload, FactEvidence):
            return {}, "An input fact is missing"
        facts.append(record.payload)
    if not facts or any(f.value is None or f.suspect for f in facts):
        return {}, "An input value is null or suspect"
    if len({(f.ticker, f.scope, f.report_type, f.code, f.unit) for f in facts}) != 1:
        return {}, "Input metric, scope or unit differs"
    by_year = {f.fiscal_year: f for f in facts}
    if len(by_year) != len(facts):
        return {}, "Multiple rows match the same year"
    return by_year, None


def _result(calculation_id: str, operation: str, research: ResearchResult,
            parameters: dict, value: Decimal | None = None, unit: str | None = None,
            reason: str | None = None) -> CalculationResult:
    return CalculationResult(calculation_id=calculation_id, operation=operation,
                             input_evidence_ids=research.evidence_ids,
                             parameters=parameters, value=value, unit=unit,
                             status="cannot_compute" if reason else "ok", reason=reason)


def calculate_yoy(calculation_id: str, research: ResearchResult,
                  evidence_by_id: dict[str, EvidenceRecord], prior_year: int,
                  current_year: int, rounding_decimals: int = 2) -> CalculationResult:
    parameters = {"prior_year": prior_year, "current_year": current_year,
                  "rounding_decimals": rounding_decimals}
    facts, reason = _facts(research, evidence_by_id)
    if not reason and warning_affects_years(research.warnings, {prior_year, current_year}):
        reason = "A current value differs from the next report's prior-year value"
    if rounding_decimals < 0:
        reason = "rounding_decimals must be nonnegative"
    if not reason and (current_year != prior_year + 1 or
                       set(facts) != {prior_year, current_year}):
        reason = "YoY needs exactly two consecutive years"
    if not reason:
        start = Decimal(str(facts[prior_year].value))
        end = Decimal(str(facts[current_year].value))
        if start <= 0:
            reason = "YoY needs a positive base value; use difference instead"
    if reason:
        return _result(calculation_id, "yoy", research, parameters, reason=reason)
    quantum = Decimal(1).scaleb(-rounding_decimals)
    value = ((end - start) / start * 100).quantize(quantum, rounding=ROUND_HALF_UP)
    return _result(calculation_id, "yoy", research, parameters, value, "percent")


def calculate_cagr(calculation_id: str, research: ResearchResult,
                   evidence_by_id: dict[str, EvidenceRecord], start_year: int,
                   end_year: int, rounding_decimals: int = 2) -> CalculationResult:
    parameters = {"start_year": start_year, "end_year": end_year,
                  "rounding_decimals": rounding_decimals}
    facts, reason = _facts(research, evidence_by_id)
    if not reason and warning_affects_years(research.warnings,
                                            set(range(start_year, end_year + 1))):
        reason = "A current value differs from the next report's prior-year value"
    if rounding_decimals < 0:
        reason = "rounding_decimals must be nonnegative"
    if not reason and (end_year <= start_year or
                       set(facts) != set(range(start_year, end_year + 1))):
        reason = "CAGR needs every year and a positive period"
    if not reason:
        start = Decimal(str(facts[start_year].value))
        end = Decimal(str(facts[end_year].value))
        if start <= 0 or end <= 0:
            reason = "CAGR needs positive start and end values"
    if reason:
        return _result(calculation_id, "cagr", research, parameters, reason=reason)
    quantum = Decimal(1).scaleb(-rounding_decimals)
    value = ((end / start) ** (Decimal(1) / Decimal(end_year - start_year))
             - 1) * 100
    return _result(calculation_id, "cagr", research, parameters,
                   value.quantize(quantum, rounding=ROUND_HALF_UP), "percent")


def calculate_difference(calculation_id: str, research: ResearchResult,
                         evidence_by_id: dict[str, EvidenceRecord], start_year: int,
                         end_year: int) -> CalculationResult:
    parameters = {"start_year": start_year, "end_year": end_year}
    facts, reason = _facts(research, evidence_by_id)
    if not reason and warning_affects_years(research.warnings, {start_year, end_year}):
        reason = "A current value differs from the next report's prior-year value"
    if not reason and (end_year <= start_year or
                       set(facts) != {start_year, end_year}):
        reason = "Difference needs exactly two ordered years"
    if reason:
        return _result(calculation_id, "difference", research, parameters, reason=reason)
    value = Decimal(str(facts[end_year].value)) - Decimal(str(facts[start_year].value))
    return _result(calculation_id, "difference", research, parameters,
                   value, facts[start_year].unit)


def calculate_ratio(calculation_id: str, numerator_id: str, denominator_id: str,
                    evidence_by_id: dict[str, EvidenceRecord],
                    rounding_decimals: int = 2,
                    warnings: list[str] | None = None) -> CalculationResult:
    """Calculate a same-year percentage from two compatible fact rows."""
    ids = [numerator_id, denominator_id]
    parameters = {"rounding_decimals": rounding_decimals,
                  "numerator_id": numerator_id, "denominator_id": denominator_id}
    facts = [evidence_by_id[key].payload for key in ids if key in evidence_by_id]
    reason = None
    if len(facts) != 2 or any(not isinstance(fact, FactEvidence) for fact in facts):
        reason = "Ratio needs two fact rows"
    elif any(fact.value is None or fact.suspect for fact in facts):
        reason = "Ratio input is null or suspect"
    elif len({(fact.ticker, fact.scope, fact.fiscal_year, fact.unit) for fact in facts}) != 1:
        reason = "Ratio inputs need the same ticker, scope, year and unit"
    elif any(facts[0].fiscal_year in (int(match[1]), int(match[2]))
             for warning in warnings or []
             if (match := re.fullmatch(r"period_inconsistency:(\d{4})->(\d{4})", warning))):
        reason = "A ratio input has a cross-report period inconsistency"
    elif Decimal(str(facts[1].value)) == 0:
        reason = "Ratio denominator is zero"
    elif rounding_decimals < 0:
        reason = "rounding_decimals must be nonnegative"
    if reason:
        return CalculationResult(calculation_id=calculation_id, operation="ratio",
            input_evidence_ids=ids, parameters=parameters, status="cannot_compute", reason=reason)
    quantum = Decimal(1).scaleb(-rounding_decimals)
    value = (Decimal(str(facts[0].value)) / Decimal(str(facts[1].value)) * 100
             ).quantize(quantum, rounding=ROUND_HALF_UP)
    return CalculationResult(calculation_id=calculation_id, operation="ratio",
        input_evidence_ids=ids, parameters=parameters, value=value, unit="percent", status="ok")
