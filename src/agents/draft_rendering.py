"""Resolve the small Writer placeholder vocabulary from typed source data."""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

from src.schemas.report_schema import CalculationResult, Claim, DraftBlock, EvidenceRecord
from src.tools.metric_resolver import METRICS
from src.tools.schemas import FactEvidence, NoteEvidence


TOKEN = re.compile(r"\{\{(E[1-9]\d*(?:\|abs)?|Y:E[1-9]\d*|N:E[1-9]\d*:\d+:\d+|[CDT]:[A-Za-z0-9:_-]+|P:C:[A-Za-z0-9:_-]+)\}\}")
SOURCE_SCALE = {"VND": Decimal(1), "thousand_VND": Decimal(1000),
                "million_VND": Decimal(1000000), "billion_VND": Decimal(1000000000)}


def _number(value: Decimal, decimals: int) -> str:
    rounded = value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    whole, _, fraction = format(rounded, f".{decimals}f").partition(".")
    sign = "-" if whole.startswith("-") else ""
    whole = whole.lstrip("-")
    return sign + f"{int(whole):,}".replace(",", ".") + ("," + fraction if decimals else "")


def _display(value: Decimal, unit: str, decimals: int,
             forced_scale: tuple[Decimal, str] | None = None) -> tuple[str, Decimal, str, Decimal]:
    if unit == "percent":
        rounded = value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
        return _number(value, decimals) + "%", rounded, "%", Decimal(1)
    factor = SOURCE_SCALE.get(unit)
    if factor is None:
        return _number(value, decimals) + " " + unit, value, unit, Decimal(1)
    if forced_scale is not None:
        full_scale, label = forced_scale
        scale = full_scale / factor
        shown = value / scale
        return (_number(shown, decimals) + " " + label,
                shown.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP),
                label, scale)
    absolute = abs(value * factor)
    for full_scale, label in ((Decimal(10) ** 12, "nghìn tỷ đồng"),
                              (Decimal(10) ** 9, "tỷ đồng"),
                              (Decimal(10) ** 6, "triệu đồng"),
                              (Decimal(1), "đồng")):
        scale = full_scale / factor
        shown = value / scale
        if absolute >= full_scale and shown.quantize(
                Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP) != 0:
            return _number(shown, decimals) + " " + label, shown.quantize(
                Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP), label, scale
    shown = value * factor
    rounded = shown.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    return _number(shown, decimals) + " đồng", rounded, "đồng", Decimal(1) / factor


def render_template(template: str, block_id: str,
                    evidence_by_id: dict[str, EvidenceRecord],
                    calculations_by_id: dict[str, CalculationResult],
                    evidence_aliases: dict[str, str]) -> tuple[str, list[Claim]]:
    """Return rendered prose and claims; reject unsupported or unavailable tokens."""
    if re.search(r"\d", TOKEN.sub("", template)):
        raise ValueError("Writer template contains a literal digit")
    claims: list[Claim] = []
    sentence_ends = [match.start() for match in re.finditer(r"[.!?](?=\s|$)", template)]

    def sentence_index(position: int) -> int:
        return sum(end < position for end in sentence_ends)

    money_by_sentence: dict[int, list[tuple[Decimal, int]]] = {}
    for match in TOKEN.finditer(template):
        token = match[1]
        if token.startswith("E"):
            alias = token.partition("|")[0]
            record = evidence_by_id.get(evidence_aliases.get(alias, ""))
            fact = record.payload if record is not None else None
            if isinstance(fact, FactEvidence) and fact.value is not None and fact.unit in SOURCE_SCALE:
                money_by_sentence.setdefault(sentence_index(match.start()), []).append(
                    (Decimal(str(fact.value)) * SOURCE_SCALE[fact.unit], 1))
        elif token.startswith(("C:", "D:")):
            calculation = calculations_by_id.get(token[2:])
            if calculation is not None and calculation.status == "ok" and calculation.unit in SOURCE_SCALE:
                money_by_sentence.setdefault(sentence_index(match.start()), []).append(
                    (calculation.value * SOURCE_SCALE[calculation.unit],
                     int(calculation.parameters.get("rounding_decimals", 1))))
    scales = ((Decimal(10) ** 12, "nghìn tỷ đồng"),
              (Decimal(10) ** 9, "tỷ đồng"),
              (Decimal(10) ** 6, "triệu đồng"), (Decimal(1), "đồng"))
    shared_scale = {
        index: next(scale for scale in scales if all(
            amount == 0 or abs(amount) >= scale[0]
            for amount, _ in values))
        for index, values in money_by_sentence.items() if len(values) > 1}

    def replace(match: re.Match) -> str:
        token = match[1]
        claim_id = f"{block_id}:p{len(claims) + 1}"
        if token.startswith("Y:"):
            alias = token[2:]
            evidence_id = evidence_aliases.get(alias)
            if evidence_id not in evidence_by_id:
                raise ValueError(f"Unknown evidence year alias: {alias}")
            return f"năm {evidence_by_id[evidence_id].payload.fiscal_year}"
        if token.startswith("P:C:"):
            calculation_id = token[4:]
            calculation = calculations_by_id.get(calculation_id)
            if calculation is None or calculation.status != "ok":
                raise ValueError(f"Unavailable calculation period: {calculation_id}")
            p = calculation.parameters
            if "current_year" in p and "prior_year" in p:
                return f"năm {p['current_year']} so với năm {p['prior_year']}"
            if "start_year" in p and "end_year" in p:
                return f"giai đoạn {p['start_year']}–{p['end_year']}"
            if "year" in p:
                return f"năm {p['year']}"
            if calculation.operation == "ratio" and calculation.input_evidence_ids:
                first = evidence_by_id[calculation.input_evidence_ids[0]].payload
                return f"năm {first.fiscal_year}"
            raise ValueError(f"Calculation lacks a period: {calculation_id}")
        if token.startswith("N:"):
            _, alias, start_text, end_text = token.split(":")
            evidence_id = evidence_aliases.get(alias)
            record = evidence_by_id.get(evidence_id)
            if record is None or not isinstance(record.payload, NoteEvidence):
                raise ValueError(f"Unknown note alias: {alias}")
            start, end = int(start_text), int(end_text)
            if start >= end or end > len(record.payload.text):
                raise ValueError(f"Invalid note excerpt span: {token}")
            excerpt = record.payload.text[start:end]
            claims.append(Claim(claim_id=claim_id, claim_type="qualitative",
                                evidence_ids=[evidence_id]))
            return excerpt
        if token.startswith("E"):
            alias, _, modifier = token.partition("|")
            evidence_id = evidence_aliases.get(alias)
            if evidence_id not in evidence_by_id:
                raise ValueError(f"Unknown evidence alias: {alias}")
            fact = evidence_by_id[evidence_id].payload
            if not isinstance(fact, FactEvidence) or fact.value is None:
                raise ValueError(f"Alias {alias} does not reference a numeric fact")
            value = Decimal(str(fact.value))
            metric = next((name for name, code, report_type, _ in METRICS
                           if (code, report_type) == (fact.code, fact.report_type)),
                          fact.label)
            if not metric:
                raise ValueError(f"Fact {alias} has no usable metric label")
            shown = abs(value) if modifier == "abs" else value
            text, display_value, display_unit, scale = _display(
                shown, fact.unit, 1, shared_scale.get(sentence_index(match.start())))
            claims.append(Claim(claim_id=claim_id, claim_type="direct_fact",
                evidence_ids=[evidence_id], metric=metric, fiscal_year=fact.fiscal_year,
                value=value, unit=fact.unit, display_value=display_value,
                display_unit=display_unit, display_scale=scale,
                display_sign="magnitude" if modifier else "signed",
                display_rounding_decimals=1))
            return text
        kind, calculation_id = token.split(":", 1)
        calculation = calculations_by_id.get(calculation_id)
        if calculation is None or calculation.status != "ok":
            raise ValueError(f"Unavailable calculation: {calculation_id}")
        if kind == "T":
            if calculation.operation != "trend":
                raise ValueError(f"Not a trend calculation: {calculation_id}")
            years = int(calculation.parameters["end_year"]) - int(calculation.parameters["start_year"]) + 1
            phrase = {"increasing": "tăng" if years == 2 else "tăng liên tục",
                      "decreasing": "giảm" if years == 2 else "giảm liên tục",
                      "flat": "đi ngang", "mixed": "diễn biến không đều"}[calculation.direction]
            claims.append(Claim(claim_id=claim_id, claim_type="calculated",
                evidence_ids=calculation.input_evidence_ids,
                calculation_id=calculation_id, asserted_direction=calculation.direction))
            return phrase
        if calculation.operation == "trend":
            raise ValueError(f"Trend needs T placeholder: {calculation_id}")
        if kind == "D" and calculation.operation not in ("difference", "yoy"):
            raise ValueError(f"D needs a difference or YoY calculation: {calculation_id}")
        decimals = int(calculation.parameters.get("rounding_decimals", 1))
        text, display_value, display_unit, scale = _display(
            abs(calculation.value) if kind == "D" else calculation.value,
            calculation.unit, decimals,
            shared_scale.get(sentence_index(match.start())))
        claims.append(Claim(claim_id=claim_id, claim_type="calculated",
            evidence_ids=calculation.input_evidence_ids, calculation_id=calculation_id,
            asserted_value=calculation.value, asserted_unit=calculation.unit,
            display_value=display_value, display_unit=display_unit, display_scale=scale,
            display_sign="magnitude" if kind == "D" else "signed",
            display_rounding_decimals=decimals))
        if kind == "D":
            return ("tăng " if calculation.value > 0 else
                    "giảm " if calculation.value < 0 else "không đổi (") + text + (
                        ")" if calculation.value == 0 else "")
        return text

    rendered = TOKEN.sub(replace, template)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("Unknown placeholder")
    return rendered, claims


def render_block(block_id: str, template: str,
                 evidence_by_id: dict[str, EvidenceRecord],
                 calculations_by_id: dict[str, CalculationResult],
                 evidence_aliases: dict[str, str]) -> DraftBlock:
    text, claims = render_template(template, block_id, evidence_by_id,
                                   calculations_by_id, evidence_aliases)
    return DraftBlock(block_id=block_id, template=template, text=text, claims=claims)
