"""Evaluate source-bound qualitative Gemini Writer on v2.1 Dev fixtures."""
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
from src.agents.qualitative_llm_writer import build_qualitative_view
from src.agents.state import state_from_json
from src.agents.verification import render_section_citations, verify_section_deterministically
from src.agents.writer_model import GeminiWriterModel


FIXTURES = ROOT / "data/report_output/v2_1_fixtures"
OUTPUT = FIXTURES / "qualitative_llm_dev_20261109"


def load_state(ticker: str, section_id: str) -> dict:
    numeric = state_from_json((FIXTURES / f"{ticker}_research_state.json")
                              .read_text(encoding="utf-8"))
    notes = state_from_json((FIXTURES / f"{ticker}_w6_note_research_state.json")
                            .read_text(encoding="utf-8"))
    sections = [*numeric["outline"].sections, *notes["outline"].sections]
    section = next(item for item in sections if item.section_id == section_id)
    notes["outline"] = numeric["outline"].model_copy(update={"sections": [section]})
    return notes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", choices=["hut", "gmd", "fpt"],
                        default=["fpt", "hut", "gmd"])
    parser.add_argument("--sections", nargs="+", choices=["S1", "S2", "S6", "S7"],
                        default=["S1", "S2", "S6", "S7"])
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    model = GeminiWriterModel()
    for ticker in args.tickers:
        for section_id in args.sections:
            stem = f"{ticker}_{section_id.lower()}"
            if (OUTPUT / f"{stem}.json").exists():
                print(f"{ticker.upper()} {section_id}: existing result kept", flush=True)
                continue
            state = load_state(ticker, section_id)
            section = state["outline"].sections[0]
            result = build_llm_writer(model, record_raw_outputs=True)(state)
            draft = next(iter(result["section_drafts"].values()))
            log = next(iter(result["writer_run_logs"].values()))
            verification = verify_section_deterministically(
                draft, state["request"], state["evidence_by_id"],
                state["calculations_by_id"], state["research_results"],
                state["evidence_aliases"], section)
            rendered = render_section_citations(
                draft, state["evidence_by_id"], state["calculations_by_id"],
                state["research_results"], section)
            payload = {
                "snapshot": "v2.1", "ticker": ticker.upper(),
                "section_view": build_qualitative_view(section, state),
                "writer_run_log": log.model_dump(mode="json"),
                "draft": draft.model_dump(mode="json"),
                "verification": verification.model_dump(mode="json"),
            }
            (OUTPUT / f"{stem}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (OUTPUT / f"{stem}.md").write_text(rendered + "\n", encoding="utf-8")
            print(f"{ticker.upper()} {section_id}: attempts={log.attempts} "
                  f"fallback={log.used_fallback} verifier={verification.status} "
                  f"blocks={len(draft.blocks)}", flush=True)


if __name__ == "__main__":
    main()
