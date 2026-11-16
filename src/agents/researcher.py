"""Deterministic Researcher over the existing financial tools."""
from __future__ import annotations

import re
from collections.abc import Callable

from src.indexing.vietnamese_sparse_tokenizer import normalize_vietnamese_sparse

from src.agents.calculations import calculate_cagr, calculate_difference, calculate_ratio, calculate_yoy
from src.agents.state import (
    ReportState, snapshot_version_for_db, snapshot_version_for_note_index,
)
from src.schemas.report_schema import (
    CalculationResult, FactTask, NotesTask, RatioTask, TimeSeriesTask,
    calculate_trend, record_tool_result,
)
from src.tools.agent_tools import AgentTools


NOTE_TOPIC_PHRASES = {
    "business": ("nganh nghe", "hoat dong kinh doanh", "cong ty con"),
    "accounting_basis": ("ky ke toan", "don vi tien te", "che do ke toan"),
    "opinion": ("y kien kiem toan", "y kien cua kiem toan vien"),
    "emphasis": ("van de can nhan manh", "van de nhan manh", "co so y kien ngoai tru"),
    "auditor": ("cong ty kiem toan", "don vi kiem toan", "kiem toan vien"),
    "borrowings": ("khoan vay", "no thue tai chinh", "lai suat vay"),
    "revenue_policy": ("ghi nhan doanh thu", "doanh thu duoc ghi nhan"),
    "depreciation": ("khau hao", "thoi gian su dung huu ich"),
    "provisions": ("trich lap du phong", "du phong phai thu", "du phong hang ton kho"),
    "borrowing_policy": ("khoan vay", "no thue tai chinh", "lai suat vay"),
    "related_parties": ("ben lien quan",),
    "financial_risks": ("rui ro thanh khoan", "rui ro tin dung", "rui ro ty gia", "rui ro lai suat"),
    "commitments": ("cam ket", "nghia vu tiem tang", "nghia vu hoan nguyen"),
    "subsequent_events": ("su kien sau ngay", "su kien phat sinh sau", "sau ngay ket thuc ky ke toan"),
}


def _normalize_note_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", normalize_vietnamese_sparse(value)))


def _one_edit(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    short, long = sorted((left, right), key=len)
    for index in range(len(long)):
        if short == long[:index] + long[index + 1:]:
            return True
    return False


def _has_phrase(text: str, phrase: str) -> bool:
    words, target = text.split(), phrase.split()
    for offset in range(len(words) - len(target) + 1):
        pairs = list(zip(words[offset:offset + len(target)], target))
        differences = [(actual, expected) for actual, expected in pairs if actual != expected]
        if not differences or (len(differences) == 1 and
                               min(map(len, differences[0])) >= 4 and
                               _one_edit(*differences[0])):
            return True
    return False


def _note_matches_topic(task: NotesTask, text: str) -> bool:
    topic = next((part for part in task.task_id.split(":") if part in NOTE_TOPIC_PHRASES), None)
    query = _normalize_note_text(task.query)
    if topic is None:
        topic = next((name for name, phrases in NOTE_TOPIC_PHRASES.items()
                      if any(phrase in query for phrase in phrases)), None)
    normalized = _normalize_note_text(text)
    if topic == "opinion":
        return (_has_phrase(normalized, "theo y kien cua chung toi") and
                _has_phrase(normalized, "phan anh trung thuc"))
    if topic == "emphasis":
        return any(_has_phrase(normalized, phrase) for phrase in
                   ("van de can nhan manh", "van de nhan manh", "co so y kien ngoai tru"))
    if topic == "accounting_basis":
        return any(_has_phrase(normalized, phrase) for phrase in
                   ("ky ke toan nam", "don vi tien te su dung trong ke toan",
                    "cong ty ap dung che do ke toan",
                    "tuan thu yeu cau cua cac chuan muc ke toan"))
    if topic == "borrowings":
        return any("vay" in (part := _normalize_note_text(paragraph)).split() and
                   any(_has_phrase(part, phrase) for phrase in
                       ("du no", "lai suat", "ngay dao han", "ky han")) and
                   re.search(r"\d{1,3}(?:[.,]\d{3})+|\d+[.,]\d+\s*%", paragraph)
                   for paragraph in text.split("\n\n"))
    if (topic == "financial_risks" and
            _has_phrase(normalized, "cac chinh sach ke toan chu yeu") and
            not _has_phrase(normalized, "quan ly rui ro tai chinh") and
            not _has_phrase(normalized, "phong ngua rui ro ty gia")):
        return False
    phrases = NOTE_TOPIC_PHRASES[topic] if topic else (query,)
    return any(_has_phrase(normalized, phrase) for phrase in phrases)


def _prefetched_result(state: ReportState, name: str, args: dict, version: str):
    """Reuse an exact Planner read only when its source snapshot still matches."""
    fields = (["ticker", "scope", "query", "fiscal_year", "sections"]
              if name == "search_notes_tool" else
              ["ticker", "scope", "item_code", "report_type",
               *( ["fiscal_year"] if name == "query_fact_tool" else ["start_year", "end_year"] )])
    for observation in state.get("planner_observations", {}).values():
        if (observation.tool_name == name and observation.snapshot_version == version and
                all(observation.arguments.get(key) == args.get(key) for key in fields)):
            return observation.result
    return None


def evidence_aliases(evidence_by_id: dict, existing: dict[str, str] | None = None
                     ) -> dict[str, str]:
    """Append aliases in metric/year order without renumbering existing IDs."""
    aliases = dict(existing or {})
    known = set(aliases.values())
    next_number = max((int(alias[1:]) for alias in aliases), default=0) + 1
    new_ids = sorted((key for key in evidence_by_id if key not in known),
                     key=lambda key: (getattr(evidence_by_id[key].payload, "label", ""),
                                      evidence_by_id[key].payload.fiscal_year, key))
    for key in new_ids:
        aliases[f"E{next_number}"] = key
        next_number += 1
    return aliases


def resolve_evidence_aliases(aliases: list[str], mapping: dict[str, str]) -> list[str]:
    return [mapping[alias] for alias in aliases]


def build_researcher(tools: AgentTools, note_snapshot_version: str | None = None, *,
                     progress: Callable[[str, str], None] | None = None):
    """Return a graph node that executes every planned task once."""
    if note_snapshot_version is None:
        try:
            note_snapshot_version = snapshot_version_for_note_index()
        except FileNotFoundError:
            pass
    def research(state: ReportState) -> dict:
        def emit(stage: str, message: str) -> None:
            if progress is not None:
                progress(stage, message)

        request = state["request"]
        fact_version = snapshot_version_for_db(tools.db_path)
        results = {}
        evidence = {}
        calculations = {}
        for section in state["outline"].sections:
            for task in section.research_tasks:
                if isinstance(task, RatioTask):
                    continue
                emit("research_task", f"Đang tra cứu {task.task_id} · {section.title}")
                if isinstance(task, NotesTask):
                    if note_snapshot_version is None:
                        raise ValueError("Notes task requires an index snapshot version")
                    name = "search_notes_tool"
                    args = {"ticker": request.ticker, "scope": request.scope,
                            "query": task.query, "fiscal_year": task.fiscal_year,
                            "sections": task.sections}
                    version = note_snapshot_version
                else:
                    name = "query_fact_tool" if isinstance(task, FactTask) else "query_time_series_tool"
                    args = {"ticker": request.ticker, "scope": request.scope,
                            "metric_name": task.metric_name, "item_code": task.item_code,
                            "report_type": task.report_type}
                    if isinstance(task, FactTask):
                        args["fiscal_year"] = task.fiscal_year
                    else:
                        args.update(start_year=task.start_year, end_year=task.end_year)
                    version = fact_version
                audit_section = isinstance(task, NotesTask) and task.sections == ["AUDIT_REPORT"]
                tool_result = (None if audit_section else
                               _prefetched_result(state, name, args, version))
                if tool_result is None:
                    tool_result = (tools.read_audit_section(request.ticker, task.fiscal_year,
                                                            request.scope) if audit_section else
                                   tools.execute(name, args))
                if (audit_section and ":emphasis:" in task.task_id and
                        tool_result.status == "ok" and not any(
                            "emphasis" in chunk.topic_roles for chunk in tool_result.chunks)):
                    tool_result = tool_result.model_copy(update={
                        "status": "not_found", "chunks": [],
                        "message": "full_audit_section_surveyed_no_emphasis"})
                if (isinstance(task, NotesTask) and
                        not audit_section and tool_result.status in ("ok", "partial") and
                        tool_result.chunks):
                    chunks = [chunk for chunk in tool_result.chunks
                              if _note_matches_topic(task, chunk.text)]
                    tool_result = tool_result.model_copy(update={
                        "chunks": chunks,
                        "status": tool_result.status if chunks else "not_found",
                    })
                result, records = record_tool_result(task, tool_result, version)
                results[task.task_id] = result
                status = {"sufficient": "đủ dữ liệu", "partial": "dữ liệu một phần",
                          "no_evidence": "chưa tìm thấy bằng chứng", "ambiguous": "cần làm rõ",
                          "error": "tra cứu lỗi"}[result.status]
                emit("research_task_done", f"Đã tra cứu {task.task_id} · {len(result.evidence_ids)} bằng chứng · {status}")
                for key, record in records.items():
                    if key in evidence and evidence[key] != record:
                        raise ValueError(f"Conflicting evidence {key}")
                    evidence[key] = record
                if (not isinstance(task, TimeSeriesTask) or not result.evidence_ids or
                        state["outline"].calculation_policy == "explicit"):
                    continue
                prefix = task.task_id
                calculations[f"{prefix}:trend"] = calculate_trend(
                    f"{prefix}:trend", result, records, task.start_year, task.end_year)
                calculations[f"{prefix}:cagr"] = calculate_cagr(
                    f"{prefix}:cagr", result, records, task.start_year, task.end_year)
                for year in range(task.start_year + 1, task.end_year + 1):
                    pair_ids = [key for key in result.evidence_ids
                                if records[key].payload.fiscal_year in (year - 1, year)]
                    pair_facts = [records[key].payload for key in pair_ids]
                    pair_safe = (len(pair_facts) == 2 and
                        {fact.fiscal_year for fact in pair_facts} == {year - 1, year} and
                        len({fact.unit for fact in pair_facts}) == 1 and
                        all(fact.value is not None and not fact.suspect for fact in pair_facts))
                    pair = result.model_copy(update={"evidence_ids": pair_ids,
                                                     "safe_for_calculation": pair_safe})
                    if pair_ids:
                        calculations[f"{prefix}:yoy:{year}"] = calculate_yoy(
                            f"{prefix}:yoy:{year}", pair, records, year - 1, year)
                endpoints = [key for key in result.evidence_ids
                             if records[key].payload.fiscal_year in
                             (task.start_year, task.end_year)]
                pair = result.model_copy(update={"evidence_ids": endpoints})
                if endpoints:
                    calculations[f"{prefix}:difference"] = calculate_difference(
                        f"{prefix}:difference", pair, records, task.start_year, task.end_year)
        if state["outline"].calculation_policy == "explicit":
            for section in state["outline"].sections:
                for spec in section.calculation_specs:
                    source = results[spec.source_task_id]
                    selected_ids = [key for key in source.evidence_ids
                                    if spec.start_year <= evidence[key].payload.fiscal_year <= spec.end_year]
                    selected = source.model_copy(update={"evidence_ids": selected_ids})
                    if spec.operation in ("yoy", "difference"):
                        selected_ids = [key for key in selected_ids
                                        if evidence[key].payload.fiscal_year in
                                        (spec.start_year, spec.end_year)]
                        selected = source.model_copy(update={
                            "evidence_ids": selected_ids,
                            "safe_for_calculation": (
                                len(selected_ids) == 2 and
                                {evidence[key].payload.fiscal_year for key in selected_ids} ==
                                {spec.start_year, spec.end_year} and
                                len({evidence[key].payload.unit for key in selected_ids}) == 1)})
                    if spec.operation == "yoy":
                        value = calculate_yoy(spec.calculation_id, selected, evidence,
                                              spec.start_year, spec.end_year)
                    elif spec.operation == "cagr":
                        value = calculate_cagr(spec.calculation_id, selected, evidence,
                                               spec.start_year, spec.end_year)
                    elif spec.operation == "difference":
                        value = calculate_difference(spec.calculation_id, selected, evidence,
                                                     spec.start_year, spec.end_year)
                    else:
                        value = calculate_trend(spec.calculation_id, selected, evidence,
                                                spec.start_year, spec.end_year)
                    calculations[spec.calculation_id] = value
        for section in state["outline"].sections:
            for task in section.research_tasks:
                if not isinstance(task, RatioTask):
                    continue
                for year in task.years:
                    source_ids = []
                    selected = []
                    problems = []
                    warnings = []
                    for source_task_id in (task.numerator_task_id, task.denominator_task_id):
                        source = results[source_task_id]
                        matches = [key for key in source.evidence_ids
                                   if evidence[key].payload.fiscal_year == year]
                        source_ids.extend(matches)
                        warnings.extend(source.warnings)
                        if len(matches) != 1:
                            problems.append(f"{source_task_id} has {len(matches)} rows for {year}")
                        else:
                            selected.append(matches[0])
                    calculation_id = f"{task.task_id}:{year}"
                    if problems:
                        calculations[calculation_id] = CalculationResult(
                            calculation_id=calculation_id, operation="ratio",
                            input_evidence_ids=list(dict.fromkeys(source_ids)),
                            parameters={"year": year}, status="cannot_compute",
                            reason="; ".join(problems))
                    elif task.positive_denominator and (
                            evidence[selected[1]].payload.value is not None and
                            evidence[selected[1]].payload.value <= 0):
                        calculations[calculation_id] = CalculationResult(
                            calculation_id=calculation_id, operation="ratio",
                            input_evidence_ids=selected, parameters={"year": year},
                            status="cannot_compute", reason="Ratio denominator must be positive")
                    else:
                        calculations[calculation_id] = calculate_ratio(
                            calculation_id, selected[0], selected[1], evidence,
                            warnings=warnings)
        return {"research_results": results, "evidence_by_id": evidence,
                "calculations_by_id": calculations,
                "evidence_aliases": evidence_aliases(
                    {**state.get("evidence_by_id", {}), **evidence},
                    state.get("evidence_aliases"))}

    return research
