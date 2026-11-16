"""Package v2.1 Writer drafts and isolated SectionViews for semantic review."""
from __future__ import annotations

import json
from pathlib import Path

from src.agents.report_tables import render_section_tables
from src.agents.state import state_from_json, state_to_json
from src.agents.template_writer import build_template_writer
from src.agents.verification import (
    build_verifier_section_view, render_section_citations,
    verify_section_deterministically,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "data/report_output/v2_1_fixtures"
OUTPUT = FIXTURES / "writer_verifier_samples"


def build_sample(ticker: str) -> tuple[dict[str, str], dict]:
    numeric = state_from_json((FIXTURES / f"{ticker}_research_state.json")
                              .read_text(encoding="utf-8"))
    state = state_from_json((FIXTURES / f"{ticker}_w6_note_research_state.json")
                            .read_text(encoding="utf-8"))
    outline = numeric["outline"].model_copy(update={
        "sections": [*numeric["outline"].sections, *state["outline"].sections],
    })
    state["outline"] = outline
    state["outlines_by_revision"] = {state.get("outline_version", 1): outline}
    state["run_status"] = "incomplete"
    drafts = build_template_writer()(state)["section_drafts"]
    by_section = {draft.section_id: draft for draft in drafts.values()}
    if set(by_section) != {f"S{index}" for index in range(1, 8)}:
        raise ValueError(f"{ticker}: expected S1–S7 drafts")

    reports = []
    views = {}
    results = {}
    sections = []
    for section in outline.sections:
        draft = by_section[section.section_id]
        result = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"],
            state["evidence_aliases"], section)
        result = result.model_copy(update={"outline_version": state["outline_version"]})
        if result.status != "passed":
            raise ValueError(f"{ticker}/{section.section_id}: {result.issues}")
        results[(section.section_id, draft.revision)] = result
        view = build_verifier_section_view(
            draft, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"],
            state["evidence_aliases"], section)
        views[section.section_id] = json.dumps(
            view.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        prose = render_section_citations(
            draft, state["evidence_by_id"], state["calculations_by_id"],
            state["research_results"], section)
        tables = render_section_tables(section, state)
        if tables and prose.startswith("## "):
            heading, separator, remainder = prose.partition("\n\n")
            prose = heading + "\n\n" + tables + (separator + remainder if remainder else "")
        reports.append(prose)
        sections.append({"section_id": section.section_id, "revision": draft.revision,
                         "blocks": len(draft.blocks),
                         "claims": sum(len(block.claims) for block in draft.blocks),
                         "limitations": len(draft.limitations),
                         "verification": "passed/deterministic"})

    state["section_drafts"] = drafts
    state["verification_results"] = results
    state["final_report"] = "\n\n".join(reports)
    files = {
        f"{ticker.upper()}_draft.md": state["final_report"] + "\n",
        f"{ticker.upper()}_state.json": state_to_json(state) + "\n",
        **{f"{ticker.upper()}_{section_id}_verifier_view.json": source
           for section_id, source in views.items()},
    }
    return files, {"ticker": ticker.upper(), "sections": sections}


def main() -> None:
    files = {}
    manifest = {"snapshot": "v2.1", "verification_level": "deterministic",
                "samples": []}
    for ticker in ("hut", "gmd", "fpt"):
        sample_files, summary = build_sample(ticker)
        files.update(sample_files)
        manifest["samples"].append(summary)
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if OUTPUT.exists():
        previous = OUTPUT / "manifest.json"
        if not previous.exists() or json.loads(previous.read_text(encoding="utf-8"))[
                "snapshot"] != "v2.1":
            raise ValueError(f"Refusing to overwrite an unrelated sample directory: {OUTPUT}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        (OUTPUT / filename).write_text(content, encoding="utf-8")
    print(f"Wrote {len(files)} files to {OUTPUT}")


if __name__ == "__main__":
    main()
