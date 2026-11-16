"""Code-rendered yearly values and period changes for numeric sections."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from src.agents.planner_rules import RATIO_LABELS
from src.schemas.report_schema import FactTask, RatioTask, TimeSeriesTask
from src.tools.schemas import FactEvidence


UNIT_FACTORS = {"VND": Decimal(1), "thousand_VND": Decimal(1000),
                "million_VND": Decimal(1000000), "billion_VND": Decimal(1000000000)}


def _vi(value: Decimal, decimals: int = 2) -> str:
    rounded = value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    return f"{rounded:,.{decimals}f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _citation_ids(ids: list[str], evidence: dict) -> str:
    tags = list(dict.fromkeys(evidence[key].payload.citation_tag
                              for key in ids if key in evidence))
    return " " + " ".join(tags) if tags else ""


def render_section_tables(section, state: dict) -> str:
    """Keep one monetary scale per table; missing or ambiguous cells stay blank."""
    years = range(state["request"].start_year, state["request"].end_year + 1)
    evidence = state["evidence_by_id"]
    research = state["research_results"]
    calculations = state["calculations_by_id"]
    rows = []
    for task in section.research_tasks:
        if not isinstance(task, (FactTask, TimeSeriesTask)) or task.task_id not in research:
            continue
        by_year = defaultdict(list)
        for key in research[task.task_id].evidence_ids:
            if key in evidence and isinstance(evidence[key].payload, FactEvidence):
                by_year[evidence[key].payload.fiscal_year].append((key, evidence[key].payload))
        if not by_year:
            continue
        cells = []
        for year in years:
            matches = by_year.get(year, [])
            if len(matches) != 1 or matches[0][1].value is None or matches[0][1].suspect:
                cells.append("—")
                continue
            key, fact = matches[0]
            factor = UNIT_FACTORS.get(fact.unit)
            if factor is None:
                raise ValueError(f"Unsupported table unit: {fact.unit}")
            value = Decimal(str(fact.value)) * factor / Decimal(10) ** 9
            cells.append(_vi(value) + _citation_ids([key], evidence))
        rows.append((task.metric_name or task.task_id, cells))
    if not rows:
        return ""
    header = "| Chỉ tiêu | " + " | ".join(map(str, years)) + " |"
    divider = "|---|" + "---:|" * len(list(years))
    lines = ["### Số liệu theo năm (tỷ đồng)", "", header, divider]
    lines.extend("| " + label + " | " + " | ".join(cells) + " |"
                 for label, cells in rows)

    ratio_rows = []
    for task in section.research_tasks:
        if not isinstance(task, RatioTask):
            continue
        cells = []
        for year in years:
            calculation = calculations.get(f"{task.task_id}:{year}")
            if calculation is None or calculation.status != "ok":
                cells.append("—")
            else:
                cells.append(_vi(calculation.value) + "%" +
                             _citation_ids(calculation.input_evidence_ids, evidence))
        ratio_rows.append((RATIO_LABELS.get(task.task_id, "Tỷ lệ"), cells))
    if ratio_rows:
        lines.extend(["", "### Tỷ lệ theo năm", "", header, divider])
        lines.extend("| " + label + " | " + " | ".join(cells) + " |"
                     for label, cells in ratio_rows)
    changes = defaultdict(dict)
    labels = {}
    for spec in section.calculation_specs:
        if spec.calculation_id not in section.calculations_allowed or spec.operation not in ("yoy", "difference"):
            continue
        source = next((task for task in section.research_tasks
                       if task.task_id == spec.source_task_id), None)
        if source is None:
            continue
        row = (spec.source_task_id, spec.operation)
        labels[row] = ((source.metric_name or spec.source_task_id) +
                       (" — YoY (%)" if spec.operation == "yoy" else
                        " — chênh lệch (tỷ đồng)"))
        changes[row][spec.end_year] = calculations.get(spec.calculation_id)
    if changes:
        change_years = list(years)[1:]
        change_header = "| Chỉ tiêu | " + " | ".join(
            f"{year - 1}–{year}" for year in change_years) + " |"
        change_divider = "|---|" + "---:|" * len(change_years)
        lines.extend(["", "### Biến động theo kỳ", "", change_header, change_divider])
        for row, by_year in changes.items():
            cells = []
            for year in change_years:
                result = by_year.get(year)
                if result is None or result.status != "ok":
                    cells.append("—")
                else:
                    value = result.value if row[1] == "yoy" else (
                        result.value * UNIT_FACTORS[result.unit] / Decimal(10) ** 9)
                    cells.append(_vi(value) + ("%" if row[1] == "yoy" else "") +
                                 _citation_ids(result.input_evidence_ids, evidence))
            lines.append("| " + labels[row] + " | " + " | ".join(cells) + " |")
    return "\n".join(lines)
