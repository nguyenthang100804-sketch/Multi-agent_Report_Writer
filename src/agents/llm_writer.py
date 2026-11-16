"""Section-scoped model prose with deterministic validation and fallback."""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field

from src.agents.citation_recall import scan_template_candidates
from src.agents.draft_rendering import TOKEN, render_block, render_template
from src.agents.qualitative_llm_writer import write_qualitative_section
from src.agents.template_writer import build_template_writer
from src.agents.verification import (
    _render_limitations, attach_code_limitations, verify_section_deterministically,
)
from src.agents.writer_contract import (
    NarrativeOutput, WriterModel, WriterRequest, WriterResponse, WriterRunLog,
)
from src.agents.writer_menu import build_placeholder_menu, validate_template_menu
from src.schemas.report_schema import DraftLimitation, SectionDraft
from src.tools.schemas import FactEvidence


PROMPT_PATH = Path(__file__).parent / "prompts" / "writer_system.md"
PROMPT_VERSION = "w4-v5"
_HANDWRITTEN_UNIT = re.compile(
    r"^\s*\(?\s*(?:%|(?:nghìn\s+)?tỷ\b|triệu\b|đồng\b|điểm\s+phần\s+trăm\b)", re.I)
_INTERNAL_ID = re.compile(r"\b[a-z]+(?:_[a-z]+)+(?:[:][\w-]+)*\b", re.I)
_INVALID_C_ABS = re.compile(r"\{\{C:([A-Za-z0-9:_-]+)\|abs\}\}")
_DIRECTION_C = re.compile(r"\b(tăng|giảm)\s+\{\{C:([A-Za-z0-9:_-]+)\}\}", re.I)
_DIRECTION_D = re.compile(r"\b(?:tăng|giảm)\s+\{\{D:[A-Za-z0-9:_-]+\}\}", re.I)
_DIRECTION_WORD = re.compile(r"\b(tăng|giảm|lên|xuống|về(?=\s+(?:mức|ngưỡng)))\b", re.I)


class SectionView(BaseModel):
    section_id: str
    title: str
    objective: str
    facts: dict
    calculations: dict
    trends: dict
    allowed_tokens: list[str]
    known_limitations: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)


def build_section_view(section, state: dict, fallback_draft: SectionDraft) -> SectionView:
    """Show a model only values and limitations belonging to this section."""
    menu = build_placeholder_menu(section, state)
    evidence = state["evidence_by_id"]
    calculations = state["calculations_by_id"]
    aliases = state["evidence_aliases"]
    facts = {alias: {**item, "display": render_template(
        f"{{{{{alias}}}}}", "preview", evidence, calculations, aliases)[0]}
        for alias, item in menu["facts"].items()}
    numeric = {key: {**item, "display": render_template(
        f"{{{{C:{key}}}}}", "preview", evidence, calculations, aliases)[0]}
        for key, item in menu["calculations"].items()}
    for key, item in numeric.items():
        if item["operation"] in ("difference", "yoy"):
            item["direction_display"] = render_template(
                f"{{{{D:{key}}}}}", "preview", evidence, calculations, aliases)[0]
    trends = {key: {**item, "display": render_template(
        f"{{{{T:{key}}}}}", "preview", evidence, calculations, aliases)[0]}
        for key, item in menu["trends"].items()}
    previous = [result for result in state.get("verification_results", {}).values()
                if result.section_id == section.section_id and
                result.outline_version == state.get("outline_version", 1)]
    latest = max(previous, key=lambda item: item.revision) if previous else None
    instructions = [issue.reason for issue in latest.issues] if latest else []
    limitations = _render_limitations(fallback_draft.limitations, evidence,
                                     calculations, state["research_results"], section)
    return SectionView(section_id=section.section_id, title=section.title,
                       objective=section.objective, facts=facts, calculations=numeric,
                       trends=trends, allowed_tokens=menu["allowed_tokens"],
                       known_limitations=limitations,
                       revision_instructions=instructions)


def _parse_output(raw: str) -> NarrativeOutput:
    data = json.loads(raw)
    if isinstance(data, dict) and any(isinstance(block, dict) and
                                       "template" not in block
                                       for block in data.get("blocks", [])):
        raise ValueError("missing_template")
    return NarrativeOutput.model_validate(data)


def _supported_correspondence(template: str, state: dict) -> bool:
    for relation in re.finditer(r"\btương ứng\b", template, re.I):
        before = list(TOKEN.finditer(template[:relation.start()]))
        after = next(TOKEN.finditer(template[relation.end():]), None)
        if not before or after is None or not before[-1][1].startswith("E") or not after[1].startswith("C:"):
            return False
        evidence_id = state["evidence_aliases"].get(before[-1][1].partition("|")[0])
        calculation = state["calculations_by_id"].get(after[1][2:])
        if (calculation is None or calculation.operation != "ratio" or
                not calculation.input_evidence_ids or
                calculation.input_evidence_ids[0] != evidence_id):
            return False
    return True


def _validate_templates(output: NarrativeOutput, menu: dict,
                        state: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    ids = [block.block_id for block in output.blocks]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_block_id")
    if len(menu["calculations"]) + len(menu["trends"]) >= 3 and len(ids) < 3:
        errors.append(f"need_3_to_5_observations: received {len(ids)} blocks; "
                      "need 3–5 blocks, one sentence per block")
    for block in output.blocks:
        template = block.template
        if len(re.findall(r"[.!?](?=\s|$)", template)) != 1:
            errors.append(f"{block.block_id}: one_sentence_per_block")
        invalid_abs = _INVALID_C_ABS.findall(template)
        if invalid_abs:
            errors.append(f"{block.block_id}: C: does not accept |abs; use "
                          "D:<calculation_id> for a signed change")
        checked_template = _INVALID_C_ABS.sub("", template)
        try:
            validate_template_menu(checked_template, menu)
        except ValueError as exc:
            errors.append(f"{block.block_id}: {exc}")
        stripped = TOKEN.sub("", checked_template)
        if match := re.search(r"\d", stripped):
            start, end = max(0, match.start() - 16), min(len(stripped), match.end() + 16)
            errors.append(f"{block.block_id}: literal_digit: {stripped[start:end].strip()}")
        hard, soft = scan_template_candidates(checked_template)
        errors.extend(f"{block.block_id}: {issue}" for issue in hard)
        warnings.extend(f"{block.block_id}: {issue}" for issue in soft
                        if not (issue.startswith("ambiguous_relation:") and
                                _supported_correspondence(template, state)))
        if match := _INTERNAL_ID.search(stripped):
            errors.append(f"{block.block_id}: internal_identifier: {match.group()}")
        if _DIRECTION_D.search(template):
            errors.append(f"{block.block_id}: duplicated_change_direction: D: "
                          "already renders the direction")
        directions = [match[1].lower() for match in _DIRECTION_WORD.finditer(stripped)]
        if any(match[1].startswith("D:") for match in TOKEN.finditer(template)):
            if directions and not _DIRECTION_D.search(template):
                errors.append(f"{block.block_id}: extra_change_direction: D: "
                              "already renders the direction; remove " + ", ".join(directions))
        elif directions:
            signed_changes = [state["calculations_by_id"].get(match[1][2:])
                              for match in TOKEN.finditer(template)
                              if match[1].startswith("C:")]
            signed_changes = [item for item in signed_changes if item is not None and
                              item.status == "ok" and item.operation in ("difference", "yoy")]
            if len(signed_changes) == 1:
                value = signed_changes[0].value
                if any(word == "về" or (word in ("tăng", "lên") and value <= 0) or
                       (word in ("giảm", "xuống") and value >= 0) for word in directions):
                    errors.append(f"{block.block_id}: change_direction_mismatch: "
                                  "use D: for the direction and magnitude")
        for match in _DIRECTION_C.finditer(template):
            calculation = state["calculations_by_id"].get(match[2])
            if calculation is not None and calculation.status == "ok":
                if match[1].lower() == "giảm" or calculation.value <= 0:
                    errors.append(f"{block.block_id}: directional_C_sign: use "
                                  f"{{{{D:{match[2]}}}}} instead of {match[1]} C:")
        matches = list(TOKEN.finditer(template))
        facts = [match for match in matches if re.fullmatch(r"E[1-9]\d*(?:\|abs)?", match[1])]
        for first, second in zip(facts, facts[1:]):
            between = template[first.end():second.start()]
            directions_between = [match[1].lower() for match in
                                  _DIRECTION_WORD.finditer(TOKEN.sub("", between))]
            if not directions_between:
                continue
            left = state["evidence_by_id"].get(
                state["evidence_aliases"].get(first[1].partition("|")[0], ""))
            right = state["evidence_by_id"].get(
                state["evidence_aliases"].get(second[1].partition("|")[0], ""))
            a = left.payload if left is not None else None
            b = right.payload if right is not None else None
            if (not isinstance(a, FactEvidence) or not isinstance(b, FactEvidence) or
                    (a.code, a.report_type, a.unit, a.scope) !=
                    (b.code, b.report_type, b.unit, b.scope)):
                errors.append(f"{block.block_id}: fact_direction_incomparable")
                continue
            change = Decimal(str(b.value)) - Decimal(str(a.value))
            if any(word == "về" or (word in ("tăng", "lên") and change <= 0) or
                   (word in ("giảm", "xuống") and change >= 0)
                   for word in directions_between):
                errors.append(f"{block.block_id}: fact_direction_mismatch")
        for match in matches:
            if unit := _HANDWRITTEN_UNIT.search(template[match.end():]):
                errors.append(f"{block.block_id}: handwritten_unit: {unit.group().strip()}")
            if match[1].startswith(("P:C:", "Y:")) and re.search(
                    r"\b(?:năm|giai đoạn)\s*$", template[:match.start()], re.I):
                errors.append(f"{block.block_id}: duplicated_period_prefix")
        if any(match[1].startswith(("E", "C:", "D:", "T:")) for match in matches) and not any(
            match[1].startswith(("Y:", "P:C:")) for match in matches):
            errors.append(f"{block.block_id}: missing_period_placeholder")
    return errors, warnings


def _compose(output: NarrativeOutput, section, state: dict,
             fallback_draft: SectionDraft) -> SectionDraft:
    evidence = state["evidence_by_id"]
    calculations = state["calculations_by_id"]
    aliases = state["evidence_aliases"]
    blocks = [fallback_draft.blocks[0].model_copy(deep=True)]
    for item in output.blocks:
        blocks.append(render_block(f"{section.section_id}:n:{item.block_id}",
                                   item.template, evidence, calculations, aliases))
    permitted = {(item.warning_code, tuple(sorted(item.evidence_ids))): item
                 for item in fallback_draft.limitations
                 if item.kind == "period_inconsistency"}
    declared = {}
    for item in output.period_limitations:
        ids = [aliases.get(alias) for alias in item.evidence_aliases]
        key = (item.warning_code, tuple(sorted(key for key in ids if key)))
        if None in ids or key not in permitted or item.block_id not in {
                block.block_id for block in output.blocks} or key in declared:
            raise ValueError("invalid_period_limitation")
        declared[key] = f"{section.section_id}:n:{item.block_id}"
    limitations = [DraftLimitation(
        warning_code=item.warning_code, evidence_ids=item.evidence_ids,
        block_id=declared.get(key, blocks[-1].block_id))
        for key, item in permitted.items()]
    draft = SectionDraft(section_id=section.section_id,
                         outline_version=fallback_draft.outline_version,
                         revision=fallback_draft.revision, blocks=blocks,
                         limitations=limitations)
    return attach_code_limitations(draft, section, calculations,
                                   state["research_results"])


def build_llm_writer(model: WriterModel, fallback=None, *, max_repairs: int = 2,
                     record_raw_outputs: bool = False,
                     progress: Callable[[str, str], None] | None = None):
    """Return a Writer node; failed sections alone fall back to TemplateWriter."""
    if max_repairs < 0:
        raise ValueError("max_repairs must be nonnegative")
    fallback = fallback or build_template_writer()
    system = PROMPT_PATH.read_text(encoding="utf-8")

    def write(state: dict) -> dict:
        def emit(stage: str, message: str) -> None:
            if progress is not None:
                progress(stage, message)

        emit("writer_prepare", "Đang chuẩn bị bảng số liệu và cấu trúc từng phần")
        baseline = fallback(state)["section_drafts"]
        emit("writer_prepare_done", f"Đã chuẩn bị {len(baseline)} phần bản nháp tham chiếu")
        sections = {section.section_id: section for section in state["outline"].sections}
        drafts, logs = {}, {}
        for key, reference in baseline.items():
            section = sections[reference.section_id]
            emit("writer_section", f"Đang viết {section.section_id} · {section.title}")
            if section.section_id in {"S1", "S2", "S6", "S7"}:
                drafts[key], log = write_qualitative_section(
                    model, section, state, reference,
                    max_repairs=max_repairs,
                    record_raw_outputs=record_raw_outputs)
                log_key = f"{reference.outline_version}:{section.section_id}:{reference.revision}"
                logs[log_key] = log
                emit("writer_section_done", f"Đã tạo bản nháp {section.section_id} · {section.title}")
                continue
            if section.section_id not in {"S3", "S4", "S5"}:
                drafts[key] = reference
                emit("writer_section_done", f"Đã tạo bản nháp {section.section_id} · {section.title}")
                continue
            menu = build_placeholder_menu(section, state)
            view = build_section_view(section, state, reference)
            started = time.perf_counter()
            errors_by_attempt, warnings_by_attempt, feedback = [], [], []
            raw_outputs, block_counts, attempt_times = [], [], []
            token_usage: dict[str, int] = {}
            accepted = None
            for attempt in range(1, max_repairs + 2):
                emit("writer_attempt", f"{section.section_id}: Gemini đang viết lượt {attempt}")
                attempt_started = time.perf_counter()
                request = WriterRequest(system=system,
                    section_view=view.model_dump_json(), feedback=feedback,
                    response_schema=NarrativeOutput.model_json_schema())
                try:
                    response = WriterResponse.model_validate(model.generate(request))
                    emit("writer_attempt_done", f"{section.section_id}: Gemini đã trả kết quả lượt {attempt}")
                except Exception as exc:
                    errors_by_attempt.append([f"model_error: {exc}"])
                    warnings_by_attempt.append([])
                    raw_outputs.append(None)
                    block_counts.append(None)
                    attempt_times.append(round((time.perf_counter() - attempt_started) * 1000))
                    break
                raw_outputs.append(response.text if record_raw_outputs else None)
                for name, count in response.token_usage.items():
                    token_usage[name] = token_usage.get(name, 0) + count
                try:
                    output = _parse_output(response.text)
                    block_counts.append(len(output.blocks))
                    errors, warnings = _validate_templates(output, menu, state)
                    if not errors:
                        candidate = _compose(output, section, state, reference)
                        errors.extend(f"{block.block_id}: missing_claim"
                                      for block in candidate.blocks[1:] if not block.claims)
                        errors.extend(f"{block.block_id}: mixed_monetary_scale"
                                      for block in candidate.blocks[1:]
                                      if "nghìn tỷ đồng" in block.text and
                                      re.search(r"(?<!nghìn )tỷ đồng", block.text))
                    if not errors:
                        checked = verify_section_deterministically(
                            candidate, state["request"], state["evidence_by_id"],
                            state["calculations_by_id"], state["research_results"],
                            state["evidence_aliases"], section)
                        errors.extend(f"{issue.error_type}: {issue.reason}"
                                      for issue in checked.issues if issue.severity == "error")
                        warnings.extend(f"{issue.error_type}: {issue.reason}"
                                        for issue in checked.issues if issue.severity == "warning")
                        if checked.status == "passed" and not errors:
                            accepted = candidate
                except Exception as exc:
                    if len(block_counts) < len(raw_outputs):
                        block_counts.append(None)
                    errors, warnings = [str(exc)], []
                errors_by_attempt.append(errors)
                warnings_by_attempt.append(warnings)
                attempt_times.append(round((time.perf_counter() - attempt_started) * 1000))
                if accepted is not None:
                    break
                feedback = errors
            drafts[key] = accepted or reference
            log_key = f"{reference.outline_version}:{section.section_id}:{reference.revision}"
            logs[log_key] = WriterRunLog(
                section_id=section.section_id, revision=reference.revision,
                attempts=len(errors_by_attempt), errors_by_attempt=errors_by_attempt,
                warnings_by_attempt=warnings_by_attempt,
                block_counts_by_attempt=block_counts,
                raw_outputs_by_attempt=raw_outputs,
                attempt_elapsed_ms=attempt_times,
                used_fallback=accepted is None, prompt_version=PROMPT_VERSION,
                token_usage=token_usage,
                elapsed_ms=round((time.perf_counter() - started) * 1000))
            emit("writer_section_done", f"Đã tạo bản nháp {section.section_id} · {section.title}"
                 + (" · dùng mẫu tham chiếu" if accepted is None else " · đã qua kiểm tra quy tắc"))
        return {"section_drafts": drafts, "writer_run_logs": logs}

    return write
