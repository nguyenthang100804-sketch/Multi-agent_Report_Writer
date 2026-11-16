"""One-off HUT smoke run through the real report graph."""
import json
import sys
import traceback
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


MODE = sys.argv[1] if len(sys.argv) > 1 else "shadow"
if MODE not in {"shadow", "blocking"}:
    raise ValueError("mode must be shadow or blocking")
OUT = Path(f"evaluation/smoke/full_graph_smoke_{MODE}_result.json")
result = {"ticker": "HUT", "corpus_version": "v2.1", "verifier_mode": MODE, "events": []}


def save():
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run_stream(graph, input_value, config):
    for update in graph.stream(input_value, config, stream_mode="updates"):
        for node, payload in update.items():
            event = {"node": node}
            if isinstance(payload, dict):
                event["run_status"] = payload.get("run_status")
                if node == "planner":
                    event["used_fallback"] = payload.get("planner_used_fallback")
                    event["section_count"] = len(payload.get("outline").sections) if payload.get("outline") else 0
                    event["notes"] = [item.code for item in payload.get("planner_notes", [])]
                    event["note_details"] = [item.model_dump(mode="json") for item in payload.get("planner_notes", [])]
                elif node == "researcher":
                    event["research_results"] = len(payload.get("research_results", {}))
                    event["evidence"] = len(payload.get("evidence_by_id", {}))
                elif node == "writer":
                    event["drafts"] = len(payload.get("section_drafts", {}))
                    event["fallback_sections"] = [key for key, log in payload.get("writer_run_logs", {}).items()
                                                   if getattr(log, "used_fallback", False)]
                    event["errors"] = {key: log.errors_by_attempt
                                       for key, log in payload.get("writer_run_logs", {}).items()}
                elif node == "verifier":
                    event["verification"] = {str(key): {"status": value.status, "level": value.level,
                                                        "issues": [issue.code for issue in value.issues]}
                                             for key, value in payload.get("verification_results", {}).items()}
                    event["semantic_status"] = {key: log.semantic_status
                                                for key, log in payload.get("verifier_run_logs", {}).items()}
                    event["verifier_errors"] = {key: log.errors_by_attempt
                                                for key, log in payload.get("verifier_run_logs", {}).items()}
                    event["verifier_usage"] = {key: {"elapsed_ms": log.elapsed_ms,
                                                      "token_usage": log.token_usage}
                                               for key, log in payload.get("verifier_run_logs", {}).items()}
            result["events"].append(event)
            save()
            print(json.dumps(event, ensure_ascii=False), flush=True)


request = ReportRequest(ticker="HUT", start_year=2022, end_year=2025,
                        scope="consolidated", audience="Nhà đầu tư")
config = {"configurable": {"thread_id": "full-graph-smoke-hut"}}
try:
    with AgentTools() as tools:
        graph = build_agent_report_graph(
            GeminiPlannerModel(), tools, build_llm_writer(GeminiWriterModel()),
            verifier_model=GeminiVerifierModel(), verifier_mode=MODE,
            checkpointer=InMemorySaver(serde=report_checkpoint_serde()),
        )
        run_stream(graph, {"request": request}, config)
        snapshot = graph.get_state(config)
        result["after_first_invoke"] = snapshot.values.get("run_status")
        save()
        if snapshot.values.get("run_status") == "awaiting_approval":
            print("Resuming test with outline approval", flush=True)
            run_stream(graph, Command(resume={"action": "approve",
                                             "outline_version": snapshot.values["outline_version"]}), config)
        snapshot = graph.get_state(config)
        result["final_status"] = snapshot.values.get("run_status")
        result["final_report_chars"] = len(snapshot.values.get("final_report") or "")
        save()
        print("FINAL_STATUS", result["final_status"], flush=True)
except Exception as exc:
    result["error_type"] = type(exc).__name__
    result["error"] = str(exc)
    result["traceback"] = traceback.format_exc()
    save()
    print("ERROR", type(exc).__name__, str(exc), flush=True)
    raise
