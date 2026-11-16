"""Run read-only Planner evaluation cases after an API key is configured."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.agents.planner_agent import build_planner_agent
from src.agents.planner_model import GeminiPlannerModel
from src.agents.planner import plan_report
from src.schemas.report_schema import ReportRequest
from src.tools.agent_tools import AgentTools


def evaluate(cases: list[dict], plan) -> dict:
    rows = []
    for case in cases:
        request = ReportRequest.model_validate(case["request"])
        output = plan(request)
        section_ids = [section.section_id for section in output.outline.sections] if output.outline else []
        reference = plan_report(request)
        template_ids = ({section.section_id for section in reference.outline.sections}
                        if reference.outline else set())
        represented = ({sid for section in output.outline.sections
                        for sid in [section.section_id, *section.template_section_ids]}
                       if output.outline else set())
        decisions = {sid for decision in output.decisions
                     if decision.action in {"omit", "merge"}
                     for sid in decision.template_section_ids}
        missing_explanations = sorted(template_ids - represented - decisions)
        known_observations = {item.observation_id for item in output.observations}
        data_decisions = [item for item in output.decisions if item.basis == "data"]
        supported_decisions = sum(bool(item.observation_ids) and
                                  set(item.observation_ids) <= known_observations
                                  for item in data_decisions)
        expected_status = case["expected_status"]
        required = set(case.get("required_sections", []))
        rows.append({
            "case_id": case["case_id"], "status": output.status,
            "status_correct": output.status == expected_status,
            "required_sections_present": required <= represented,
            "sections": section_ids, "decision_count": len(output.decisions),
            "observation_count": len(output.observations),
            "used_fallback": output.used_fallback,
            "validator_pass": (output.status == "ready" and
                               output.prompt_version is not None and
                               not output.used_fallback),
            "within_two_repairs": (output.status == "ready" and
                                   output.prompt_version is not None and
                                   not output.used_fallback and
                                   output.repair_count <= 2),
            "unexplained_template_sections": missing_explanations,
            "data_decisions_with_evidence": supported_decisions,
            "data_decision_count": len(data_decisions),
            "model_turns": output.model_turns,
            "repair_count": output.repair_count,
            "tool_call_count": output.tool_call_count,
            "token_usage": output.token_usage,
            "elapsed_ms": output.elapsed_ms,
            "note_codes": [note.code for note in output.notes],
        })
    ready = [row for row, case in zip(rows, cases)
             if case["expected_status"] == "ready"]
    return {"cases": rows,
            "status_accuracy": sum(row["status_correct"] for row in rows) / len(rows)
            if rows else 0,
            "validator_pass_rate": sum(row["validator_pass"] for row in ready) /
            len(ready) if ready else None,
            "within_two_repairs_rate": sum(row["within_two_repairs"] for row in ready) /
            len(ready) if ready else None,
            "fallback_count": sum(row["used_fallback"] for row in rows),
            "unexplained_section_count": sum(len(row["unexplained_template_sections"])
                                             for row in rows),
            "data_decision_evidence_rate": (
                sum(row["data_decisions_with_evidence"] for row in rows) /
                sum(row["data_decision_count"] for row in rows)
                if any(row["data_decision_count"] for row in rows) else None),
            "total_repairs": sum(row["repair_count"] for row in rows),
            "total_elapsed_ms": sum(row["elapsed_ms"] for row in rows),
            "total_tokens": (sum(row["token_usage"].get("total_tokens", 0)
                                 for row in rows)
                             if any(row["token_usage"] for row in rows) else None)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path,
                        default=Path("configs/planner_eval_dev.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    with AgentTools() as tools:
        result = evaluate(cases, build_planner_agent(GeminiPlannerModel(), tools))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
