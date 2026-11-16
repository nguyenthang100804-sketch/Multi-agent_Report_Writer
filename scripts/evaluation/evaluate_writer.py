"""Compare the optional Gemini Writer with the fixed TemplateWriter on Dev fixtures."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import truststore

truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.agents.llm_writer import build_llm_writer
from src.agents.report_graph import build_report_graph
from src.agents.state import state_from_json
from src.agents.template_writer import build_template_writer
from src.agents.writer_model import GeminiWriterModel


def run_graph(state, writer):
    graph = build_report_graph(
        lambda _request: state["outline"],
        lambda _state: {key: state[key] for key in (
            "research_results", "evidence_by_id", "evidence_aliases",
            "calculations_by_id")}, writer)
    return graph.invoke({"request": state["request"]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*", default=["hut", "gmd"],
                        choices=["hut", "gmd", "fpt", "bsr", "bwe", "dcm",
                                 "gas", "gex", "qns"])
    parser.add_argument("--sections", nargs="+", choices=["S3", "S4", "S5"],
                        default=["S3", "S4", "S5"])
    parser.add_argument("--run-label")
    args = parser.parse_args()
    model = GeminiWriterModel()
    summary = {"model": "gemini-3.8-flash", "sections": args.sections,
               "run_label": args.run_label, "tickers": {}}
    output_dir = ROOT / "data" / "report_output"
    for ticker in args.tickers:
        fixture_name = (f"{ticker}_research_state.json" if ticker in
                        ("hut", "gmd", "fpt") else
                        f"{ticker}_writer_eval_research_state.json")
        state = state_from_json((output_dir / fixture_name).read_text(encoding="utf-8"))
        state["outline"] = state["outline"].model_copy(update={
            "sections": [section for section in state["outline"].sections
                         if section.section_id in args.sections]})
        baseline = run_graph(state, build_template_writer())
        result = run_graph(state, build_llm_writer(model, record_raw_outputs=True))
        logs = list(result["writer_run_logs"].values())
        summary["tickers"][ticker] = {
            "baseline_sections_passed": sum(item.status == "passed" for item in
                                            baseline["verification_results"].values()),
            "llm_sections_passed": sum(item.status == "passed" for item in
                                       result["verification_results"].values()),
            "llm_authored_passed": sum(
                not log.used_fallback and any(
                    item.section_id == log.section_id and item.status == "passed"
                    for item in result["verification_results"].values())
                for log in logs),
            "sections_first_pass": sum(log.attempts == 1 and not log.used_fallback
                                       for log in logs),
            "mean_repairs": sum(max(0, log.attempts - 1) for log in logs) / len(logs),
            "fallback_count": sum(log.used_fallback for log in logs),
            "literal_digit_errors": sum("literal_digit" in error for log in logs
                                        for attempt in log.errors_by_attempt
                                        for error in attempt),
            "candidate_assertions": sum(any(kind in issue for kind in (
                "causal_language", "word_comparison", "forecast_language",
                "unsupported_extremum"))
                for log in logs for attempt in
                (log.errors_by_attempt + log.warnings_by_attempt) for issue in attempt),
            "token_usage": {key: sum(log.token_usage.get(key, 0) for log in logs)
                            for key in ("input_tokens", "output_tokens",
                                        "thinking_tokens", "total_tokens")},
            "elapsed_ms": sum(log.elapsed_ms for log in logs),
            "logs": [log.model_dump(mode="json") for log in logs],
        }
        if result.get("final_report"):
            report_name = (f"{ticker}_{args.run_label}_llm_writer_report.md"
                           if args.run_label else f"{ticker}_llm_writer_report.md")
            (output_dir / report_name).write_text(
                result["final_report"] + "\n", encoding="utf-8")
        print(ticker, summary["tickers"][ticker]["sections_first_pass"],
              summary["tickers"][ticker]["fallback_count"], flush=True)
    path = (output_dir / f"writer_{args.run_label}_eval.json" if args.run_label
            else output_dir / "writer_w4_eval_dev.json")
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
