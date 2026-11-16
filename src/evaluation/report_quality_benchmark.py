"""Phase A report benchmark: live deterministic graph and independently checked gold."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from src.agents.planner import plan_report
from src.agents.report_graph import build_report_graph
from src.agents.researcher import build_researcher
from src.agents.state import snapshot_version_for_db, snapshot_version_for_note_index
from src.agents.template_writer import build_template_writer
from src.schemas.report_schema import ReportRequest
from src.tools.agent_tools import AgentTools


ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = ROOT / "configs" / "report_quality_dev"


class AmbiguousRevenueTools(AgentTools):
    """Inject one conflicting row into a Dev run; never use its values as gold."""

    def execute(self, name, arguments):
        result = super().execute(name, arguments)
        if (name == "query_time_series_tool" and arguments.get("ticker") == "HUT"
                and arguments.get("item_code") == "10"
                and arguments.get("report_type") == "INCOME_STATEMENT"):
            row = next(fact for fact in result.facts if fact.fiscal_year == 2025)
            conflicting = row.model_copy(update={
                "fact_index": row.fact_index + 100000,
                "value": row.value + 1000000000,
                "raw_value": "SYNTHETIC CONFLICT - BENCHMARK ONLY",
            })
            return result.model_copy(update={
                "status": "ambiguous", "safe_for_calculation": False,
                "facts": [*result.facts, conflicting],
            })
        return result


def issue(code: str, severity: str, owner: str, detail: str) -> dict:
    return {"code": code, "severity": severity, "component_owner": owner,
            "detected_by": "automatic", "detail": detail}


def check_source(value: dict) -> bool:
    """Recheck a locked OCR line, independently of DuckDB and graph output."""
    if not value.get("verified_against_source"):
        return False
    path = ROOT / value["source_file"]
    lines = path.read_text(encoding="utf-8").splitlines()
    line = lines[value["source_line"] - 1]
    pages = [int(match[1]) for text in lines[:value["source_line"]]
             if (match := re.fullmatch(r"\[P\.(\d+)\]", text.strip()))]
    current_cell = line.split("|")[-2].strip()
    return (bool(pages) and pages[-1] == value["physical_page"]
            and "".join(char for char in current_cell if char.isdigit()) == value["value"]
            and value["source_label"] in line)


def _table_value(value: str) -> str:
    amount = (Decimal(value) / Decimal(10) ** 9).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _display_percent(value: str) -> str:
    return f"{Decimal(value):,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def _fact_point(point: dict, state: dict) -> list[dict]:
    findings = []
    section = next((section for section in state["outline"].sections
                    if section.section_id == point["section_hint"]), None)
    task = next((task for task in section.research_tasks
                 if getattr(task, "item_code", None) == point["item_code"]
                 and getattr(task, "report_type", None) == point["report_type"]), None) if section else None
    if task is None:
        return [issue("missing_task", "major", "Planner", point["id"])]
    research = state.get("research_results", {}).get(task.task_id)
    if research is None or research.status != point["expected_research_status"]:
        findings.append(issue("research_status", "major", "Researcher", point["id"]))
    if research is None:
        return findings
    records = state.get("evidence_by_id", {})
    facts = [records[key].payload for key in research.evidence_ids if key in records
             and records[key].kind == "fact"]
    for year_text, expected in point.get("expected_values", {}).items():
        year = int(year_text)
        if not check_source(expected):
            findings.append(issue("gold_source_unverified", "major", "Gold", f"{point['id']}/{year}"))
            continue
        matches = [fact for fact in facts if fact.fiscal_year == year]
        if len(matches) != 1 or Decimal(str(matches[0].value)) != Decimal(expected["value"]):
            findings.append(issue("fact_mismatch", "critical", "Researcher", f"{point['id']}/{year}"))
            continue
        fact = matches[0]
        if (fact.doc_id != expected["doc_id"] or fact.physical_page != expected["physical_page"]
                or fact.unit != expected["unit"]):
            findings.append(issue("fact_provenance", "critical", "Researcher", f"{point['id']}/{year}"))
        row = next((line for line in (state.get("final_report") or "").splitlines()
                    if line.startswith("| " + point["metric"] + " |")), "")
        cells = [cell.strip() for cell in row.split("|")]
        offset = year - state["request"].start_year + 2
        if len(cells) <= offset or not cells[offset].startswith(_table_value(expected["value"]) + " "):
            findings.append(issue("missing_output_value", "major", "Writer", f"{point['id']}/{year}"))
        elif cells[offset] != f"{_table_value(expected['value'])} {fact.citation_tag}":
            findings.append(issue("output_citation_mismatch", "critical", "Writer", f"{point['id']}/{year}"))
    for year in point.get("expected_missing_years", []):
        if any(fact.fiscal_year == year and fact.value is not None for fact in facts):
            findings.append(issue("unexpected_value", "critical", "Researcher", f"{point['id']}/{year}"))
    return findings


def grade(case: dict, state: dict) -> dict:
    findings = []
    status = state.get("run_status")
    planner_status = ("ready" if state.get("outline") is not None else status)
    if planner_status != case["expected_planner_status"]:
        findings.append(issue("planner_status", "critical", "Planner", str(planner_status)))
    if status != case["expected_run_status_phase_a"]:
        findings.append(issue("run_status", "critical", "Planner", str(status)))
    notes = {note.code for note in state.get("planner_notes", [])}
    if case.get("expected_stop_reason") not in (None, *notes):
        findings.append(issue("stop_reason", "major", "Planner", str(sorted(notes))))
    if case.get("must_not_create_report") and (state.get("final_report") or state.get("section_drafts")
                                                or state.get("research_results")):
        findings.append(issue("report_after_stop", "critical", "Writer", case["case_id"]))
    if status == "incomplete":
        sections = {section.section_id for section in state["outline"].sections}
        report_lines = (state.get("final_report") or "").splitlines()
        years = range(state["request"].start_year, state["request"].end_year + 1)
        year_header = "| Chỉ tiêu | " + " | ".join(map(str, years)) + " |"
        change_header = "| Chỉ tiêu | " + " | ".join(
            f"{year - 1}–{year}" for year in list(years)[1:]) + " |"
        numeric_sections = sum(any(task.task_type in ("fact", "time_series")
                                   for task in section.research_tasks)
                               for section in state["outline"].sections)
        if report_lines.count("### Số liệu theo năm (tỷ đồng)") != numeric_sections:
            findings.append(issue("table_unit", "critical", "Writer", "yearly monetary tables"))
        if any(line not in (year_header, change_header) for line in report_lines
               if line.startswith("| Chỉ tiêu |")) or report_lines.count(year_header) < numeric_sections:
            findings.append(issue("table_period", "critical", "Writer", "yearly table headers"))
        valid_tags = {record.payload.citation_tag
                      for record in state.get("evidence_by_id", {}).values()}
        note_tags = {record.payload.citation_tag
                     for record in state.get("evidence_by_id", {}).values()
                     if record.kind == "note"}
        for tag in set(re.findall(r"\[Doc_[A-Za-z0-9_]+, p\.\d+(?:-\d+)?\]",
                                  state.get("final_report") or "")) - valid_tags:
            findings.append(issue("unbacked_citation", "critical", "Writer", tag))
        if any(item["id"] == "CAUSE" for item in case.get("forbidden_claims", [])):
            for line in report_lines:
                plain = line.casefold()
                if (not line.startswith(("|", "Trích từ tài liệu", "Giới hạn")) and
                        re.search(r"\b(doanh thu|lợi nhuận|tổng tài sản|dòng tiền)\b.*\b(tăng|giảm)\b.*\b(do|nhờ|vì|bởi)\b", plain)):
                    cited = re.findall(r"\[Doc_[A-Za-z0-9_]+, p\.\d+(?:-\d+)?\]", line)
                    if not any(tag in note_tags for tag in cited):
                        findings.append(issue("causal_claim_without_note_support", "critical", "Writer", line))
        if any(item["id"] == "ABSENCE" for item in case.get("forbidden_claims", [])):
            for line in report_lines:
                if re.search(r"\bkhông có\b.{0,80}\b(vấn đề nhấn mạnh|rủi ro|cam kết)\b", line.casefold()):
                    findings.append(issue("absolute_absence_claim", "critical", "Writer", line))
        for section in state["outline"].sections:
            for task in section.research_tasks:
                if task.task_type == "ratio":
                    continue
                research = state.get("research_results", {}).get(task.task_id)
                if research is None:
                    findings.append(issue("unresearched_task", "major", "Researcher", task.task_id))
                elif (task.task_type in ("fact", "time_series") and research.evidence_ids
                      and not any(line.startswith("| " + (task.metric_name or task.task_id) + " |")
                                  for line in report_lines)):
                    findings.append(issue("missing_numeric_row", "major", "Writer", task.task_id))
        for section_id in case.get("required_sections", []):
            if section_id not in sections:
                findings.append(issue("missing_section", "major", "Planner", section_id))
            elif not any(result.section_id == section_id and result.status == "passed"
                         and result.level == "deterministic"
                         for result in state.get("verification_results", {}).values()):
                findings.append(issue("section_not_verified", "major", "Verifier", section_id))
        for point in case.get("required_points", []):
            if point["kind"] == "fact_series":
                findings.extend(_fact_point(point, state))
            elif point["kind"] == "research_status":
                result = state.get("research_results", {}).get(point["task_id"])
                if result is None or result.status != point["expected_status"]:
                    findings.append(issue("research_status", "major", "Researcher", point["id"]))
                if result and point.get("safe_for_calculation") is not None and result.safe_for_calculation != point["safe_for_calculation"]:
                    findings.append(issue("unsafe_calculation", "critical", "Researcher", point["id"]))
                if result and point.get("expected_missing_reason") and (
                        result.evidence_ids or not any(
                            item.reason == point["expected_missing_reason"] for item in result.missing)):
                    findings.append(issue("note_gap_not_declared", "major", "Researcher", point["id"]))
            elif point["kind"] == "calculation":
                result = state.get("calculations_by_id", {}).get(point["calculation_id"])
                if point.get("operation") == "yoy" and point.get("of"):
                    source = next(item for item in case["required_points"]
                                  if item["id"] == point["of"])
                    values = source["expected_values"]
                    earlier = values[str(point["start_year"])]
                    later = values[str(point["end_year"])]
                    if check_source(earlier) and check_source(later):
                        raw = (Decimal(later["value"]) - Decimal(earlier["value"])) / Decimal(earlier["value"]) * 100
                        quantum = Decimal(1).scaleb(-point["rounding_decimals"])
                        if raw.quantize(quantum, rounding=ROUND_HALF_UP) != Decimal(point["expected_value"]):
                            findings.append(issue("gold_calculation_invalid", "critical", "Gold", point["id"]))
                if result is None or result.status != point["expected_status"]:
                    findings.append(issue("calculation_status", "critical", "Researcher", point["id"]))
                elif result.status == "ok" and "expected_value" in point and (
                        result.value is None or abs(result.value - Decimal(point["expected_value"]))
                        > Decimal(point["tolerance"])):
                    findings.append(issue("calculation_value", "critical", "Researcher", point["id"]))
                if result is not None and result.status == "ok" and point.get("operation") == "yoy":
                    source = next(item for item in case["required_points"]
                                  if item["id"] == point["of"])
                    phrase = (f"Mức thay đổi của {source['metric']} năm {point['end_year']} "
                              f"so với năm {point['start_year']} là "
                              f"{_display_percent(point['expected_value'])}%.")
                    if phrase not in (state.get("final_report") or ""):
                        findings.append(issue("calculation_output", "major", "Writer", point["id"]))
        limitations = [lim for draft in state.get("section_drafts", {}).values()
                       for lim in draft.limitations]
        for expected in case.get("required_limitations", []):
            if not any(lim.kind == expected["kind"] and
                       getattr(lim, expected["anchor_field"], None) == expected["anchor"]
                       for lim in limitations):
                findings.append(issue("missing_limitation", "major", "Writer", expected["anchor"]))
            if expected.get("output_text") and expected["output_text"] not in (state.get("final_report") or ""):
                findings.append(issue("missing_limitation_text", "major", "Writer", expected["anchor"]))
    return {"case_id": case["case_id"], "case_kind": case["case_kind"],
            "planner_status": planner_status, "run_status": status,
            "automatic_checks_pass": not findings,
            "findings": findings, "manual_review_pending": bool(case.get("forbidden_claims")),
            "forbidden_claims": case.get("forbidden_claims", []),
            "final_report": state.get("final_report"),
            "verification": {result.section_id: {"status": result.status, "level": result.level}
                             for result in state.get("verification_results", {}).values()}}


def run_case(case: dict) -> dict:
    active = json.loads((ROOT / "configs/active_corpus.json").read_text(encoding="utf-8"))
    marker = case["corpus_version"].replace(".", "_")
    if not all(marker in active[key] for key in ("processed_dir", "facts_db", "collection_name")):
        raise ValueError(f"Gold corpus version {case['corpus_version']} differs from active corpus")
    request = ReportRequest.model_validate(case["request"])
    tools_type = AmbiguousRevenueTools if case["case_kind"] == "controlled_ambiguity" else AgentTools
    with tools_type() as tools:
        graph = build_report_graph(lambda req: plan_report(req, tools.db_path),
                                   build_researcher(tools), build_template_writer())
        state = graph.invoke({"request": request})
    return grade(case, state)


def pdf_audit_reference(cases: list[dict]) -> dict:
    path = ROOT / "evaluation/benchmarks/report_quality_pdf_spot_check.json"
    audit = json.loads(path.read_text(encoding="utf-8"))
    if audit["corpus_version"] != cases[0]["corpus_version"]:
        raise ValueError("PDF audit corpus version differs from gold")
    for source in audit["source_pdfs"].values():
        if hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError(f"PDF changed since visual audit: {source['path']}")
    checked = {(case["case_id"], point["id"], int(year)): value
               for case in cases for point in case.get("required_points", [])
               for year, value in point.get("expected_values", {}).items()
               if value.get("verified_against_pdf")}
    audited = {(item["case_id"], item["point_id"], item["fiscal_year"]): item
               for item in audit["checks"] if item["case_id"] in {case["case_id"] for case in cases}}
    if checked.keys() != audited.keys() or any(
            not audited[key]["matches"] or value["value"] != audited[key]["ocr_gold_value"]
            or value["physical_page"] != audited[key]["pdf_page"]
            for key, value in checked.items()):
        raise ValueError("PDF audit does not match gold flags and values")
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "checked_values": len(checked)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-dir", type=Path, default=CASES_DIR)
    parser.add_argument("--case", action="append", help="Run only these case IDs")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = sorted(args.cases_dir.glob("*.json"))
    cases = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if args.case:
        paths = [path for path, case in zip(paths, cases) if case["case_id"] in args.case]
        cases = [case for case in cases if case["case_id"] in args.case]
    if not cases:
        parser.error("No cases selected")
    rows = [run_case(case) for case in cases]
    pdf_audit = pdf_audit_reference(cases)
    active = json.loads((ROOT / "configs/active_corpus.json").read_text(encoding="utf-8"))
    code_paths = ("src/agents/planner.py", "src/agents/researcher.py",
                  "src/agents/template_writer.py", "src/agents/verification.py",
                  "src/evaluation/report_quality_benchmark.py")
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    result = {"phase": "A", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "corpus": {"version": cases[0]["corpus_version"], **active,
                         "facts_snapshot_id": snapshot_version_for_db(ROOT / active["facts_db"]),
                         "notes_snapshot_id": snapshot_version_for_note_index(ROOT / active["manifest"])},
              "source_audit": {"medium": "ocr_extracted_text",
                               "ocr_checked_values": sum(value.get("verified_against_source", False)
                                                         for case in cases for point in case.get("required_points", [])
                                                         for value in point.get("expected_values", {}).values()),
                               "pdf_checked_values": pdf_audit["checked_values"],
                               "pdf_audit": pdf_audit},
              "runtime": {"planner": {"implementation": "plan_report", "model": None, "prompt_version": None},
                          "researcher": {"implementation": "build_researcher", "notes_embedding_model": "bge-m3"},
                          "writer": {"implementation": "TemplateWriter", "model": None, "prompt_version": None},
                          "verifier": {"implementation": "deterministic", "model": None, "prompt_version": None},
                          "code_sha256": {path: sha(ROOT / path) for path in code_paths},
                          "gold_sha256": {path.name: sha(path) for path in paths}},
              "cases": rows, "automatic_checks_pass_count": sum(row["automatic_checks_pass"] for row in rows),
              "manual_review_pending_count": sum(row["manual_review_pending"] for row in rows)}
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
