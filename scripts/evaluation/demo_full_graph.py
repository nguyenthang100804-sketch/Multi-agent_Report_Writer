"""Interactive, one-process demo of the real Planner → Researcher → Writer → Verifier graph."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents.llm_writer import build_llm_writer
from src.agents.planner_model import GeminiPlannerModel
from src.agents.report_graph import build_agent_report_graph
from src.agents.state import report_checkpoint_serde
from src.agents.verifier_model import GeminiVerifierModel
from src.agents.writer_model import GeminiWriterModel
from src.schemas.report_schema import ReportRequest
from src.tools.agent_tools import AgentTools


ROOT = Path(__file__).resolve().parents[2]


def show_progress(graph, value, config):
    for update in graph.stream(value, config, stream_mode="updates"):
        for node, payload in update.items():
            if node == "__interrupt__":
                continue
            detail = f" — {payload['run_status']}" if isinstance(payload, dict) and payload.get("run_status") else ""
            print(f"{node}: xong{detail}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy demo graph thật và tự duyệt outline.")
    parser.add_argument("--ticker", default="HUT")
    parser.add_argument("--start-year", type=int, default=2022)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--scope", choices=("consolidated", "general", "separate"), default="consolidated")
    parser.add_argument("--audience", default="Nhà đầu tư")
    parser.add_argument("--mode", choices=("blocking", "shadow"), default="blocking")
    args = parser.parse_args()
    request = ReportRequest(ticker=args.ticker, start_year=args.start_year,
                            end_year=args.end_year, scope=args.scope, audience=args.audience)
    run_dir = ROOT / "data/report_output/demo_runs" / f"{request.ticker}_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir.mkdir(parents=True)
    config = {"configurable": {"thread_id": run_dir.name}}
    print(f"Đầu ra: {run_dir}", flush=True)

    with AgentTools() as tools:
        graph = build_agent_report_graph(
            GeminiPlannerModel(), tools, build_llm_writer(GeminiWriterModel()),
            verifier_model=GeminiVerifierModel(), verifier_mode=args.mode,
            checkpointer=InMemorySaver(serde=report_checkpoint_serde()),
        )
        show_progress(graph, {"request": request}, config)
        state = graph.get_state(config).values
        if state.get("run_status") == "awaiting_approval":
            outline = state["outline"]
            (run_dir / "outline.json").write_text(outline.model_dump_json(indent=2), encoding="utf-8")
            print("\nOutline cần duyệt:")
            for section in outline.sections:
                print(f"  {section.section_id}. {section.title} — {len(section.research_tasks)} tác vụ tìm dữ liệu")
            print(f"Chi tiết: {run_dir / 'outline.json'}")
            if state.get("planner_used_fallback"):
                print("Lưu ý: Planner đã dùng outline dự phòng.")
            answer = input("Nhập 'approve' để chạy tiếp, hoặc 'reject' để dừng: ").strip().lower()
            action = "approve" if answer == "approve" else "reject"
            show_progress(graph, Command(resume={"action": action,
                                                 "outline_version": state["outline_version"]}), config)
            state = graph.get_state(config).values

    report = state.get("final_report")
    if report:
        (run_dir / "report.md").write_text(report + "\n", encoding="utf-8")
    summary = {
        "request": request.model_dump(mode="json"),
        "verifier_mode": args.mode,
        "run_status": state.get("run_status"),
        "planner_used_fallback": state.get("planner_used_fallback", False),
        "planner_notes": [note.model_dump(mode="json") for note in state.get("planner_notes", [])],
        "writer": {key: {"used_fallback": log.used_fallback, "attempts": log.attempts,
                         "errors_by_attempt": log.errors_by_attempt}
                   for key, log in state.get("writer_run_logs", {}).items()},
        "verification": {result.section_id: {"status": result.status, "level": result.level,
                                              "issues": [{"type": issue.error_type, "reason": issue.reason}
                                                         for issue in result.issues]}
                         for result in state.get("verification_results", {}).values()},
        "semantic_status": {key: log.semantic_status
                            for key, log in state.get("verifier_run_logs", {}).items()},
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    print(f"\nTrạng thái cuối: {summary['run_status']}")
    print(f"Tóm tắt: {run_dir / 'summary.json'}")
    if report:
        print(f"Báo cáo: {run_dir / 'report.md'}")


if __name__ == "__main__":
    main()
