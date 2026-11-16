"""Package Gemini qualitative drafts with existing v2.1 numeric drafts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.agents.report_tables import render_section_tables
from src.agents.state import state_from_json, state_to_json
from src.agents.verification import (
    build_verifier_section_view, render_section_citations,
    verify_section_deterministically,
)
from src.schemas.report_schema import SectionDraft


FIXTURES = ROOT / "data/report_output/v2_1_fixtures"
INPUT = FIXTURES / "qualitative_llm_dev_20261109"
OUTPUT = INPUT / "full_samples"


def main() -> None:
    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise FileExistsError(f"Existing sample files kept: {OUTPUT}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {"snapshot": "v2.1", "qualitative": "Gemini Writer w6-v1",
                "quantitative": "existing TemplateWriter baseline",
                "verification_level": "deterministic", "samples": []}
    for ticker in ("fpt", "hut", "gmd"):
        state = state_from_json((FIXTURES / "writer_verifier_samples" /
                                 f"{ticker.upper()}_state.json").read_text(encoding="utf-8"))
        for section_id in ("S1", "S2", "S6", "S7"):
            source = json.loads((INPUT / f"{ticker}_{section_id.lower()}.json")
                                .read_text(encoding="utf-8"))
            draft = SectionDraft.model_validate(source["draft"])
            state["section_drafts"][(section_id, draft.revision)] = draft
        prose = []
        summary = []
        for section in state["outline"].sections:
            draft = next(item for item in state["section_drafts"].values()
                         if item.section_id == section.section_id)
            result = verify_section_deterministically(
                draft, state["request"], state["evidence_by_id"],
                state["calculations_by_id"], state["research_results"],
                state["evidence_aliases"], section)
            if result.status != "passed":
                raise ValueError(f"{ticker}/{section.section_id}: {result.issues}")
            state["verification_results"][(section.section_id, draft.revision)] = result
            view = build_verifier_section_view(
                draft, state["request"], state["evidence_by_id"],
                state["calculations_by_id"], state["research_results"],
                state["evidence_aliases"], section)
            (OUTPUT / f"{ticker.upper()}_{section.section_id}_verifier_view.json").write_text(
                view.model_dump_json(indent=2) + "\n", encoding="utf-8")
            text = render_section_citations(
                draft, state["evidence_by_id"], state["calculations_by_id"],
                state["research_results"], section)
            tables = render_section_tables(section, state)
            if tables and text.startswith("## "):
                heading, separator, remainder = text.partition("\n\n")
                text = heading + "\n\n" + tables + (separator + remainder if remainder else "")
            prose.append(text)
            summary.append({"section_id": section.section_id,
                            "source": "Gemini" if section.section_id in
                            {"S1", "S2", "S6", "S7"} else "TemplateWriter",
                            "verification": "passed/deterministic"})
        state["final_report"] = "\n\n".join(prose)
        (OUTPUT / f"{ticker.upper()}_draft.md").write_text(
            state["final_report"] + "\n", encoding="utf-8")
        (OUTPUT / f"{ticker.upper()}_state.json").write_text(
            state_to_json(state) + "\n", encoding="utf-8")
        manifest["samples"].append({"ticker": ticker.upper(), "sections": summary})
        print(f"{ticker.upper()}: 7/7 sections passed", flush=True)
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
