"""Eight small mutations proving that the Phase A grader detects known errors."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from src.agents.state import state_from_json
from src.evaluation.report_quality_benchmark import ROOT, grade


MUTATIONS = (
    ("digit", "hut", "missing_output_value", "36.317,44 [Doc_HUT_2025_Hopnhat, p.11]",
     "36.317,45 [Doc_HUT_2025_Hopnhat, p.11]"),
    ("year", "hut", "table_period", "| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |",
     "| Chỉ tiêu | 2022 | 2023 | 2024 | 2026 |"),
    ("unit", "hut", "table_unit", "### Số liệu theo năm (tỷ đồng)",
     "### Số liệu theo năm (triệu đồng)"),
    ("citation_page", "hut", "output_citation_mismatch", "36.317,44 [Doc_HUT_2025_Hopnhat, p.11]",
     "36.317,44 [Doc_HUT_2025_Hopnhat, p.12]"),
    ("missing_limitation_text", "fpt", "missing_limitation_text",
     "Giới hạn dữ liệu. Lợi nhuận sau thuế của cổ đông công ty mẹ (mã 61) chưa tìm thấy số liệu năm 2024, 2025.",
     ""),
    ("invented_cause", "hut", "causal_claim_without_note_support", "## Kết quả kinh doanh",
     "## Kết quả kinh doanh\n\nDoanh thu tăng do thương vụ sáp nhập."),
    ("absolute_absence", "hut", "absolute_absence_claim", "## Kết quả kinh doanh",
     "## Kết quả kinh doanh\n\nBáo cáo kiểm toán không có vấn đề nhấn mạnh."),
    ("missing_limitation_contract", "fpt", "missing_limitation", None, None),
)


def run_probe() -> dict:
    cases, states, fixtures = {}, {}, {}
    for ticker, case_id in (("hut", "hut_full"), ("fpt", "fpt_partial")):
        case_path = ROOT / "configs/report_quality_dev" / f"{case_id}.json"
        fixture = ROOT / "data/report_output/v2_1_fixtures" / f"{ticker}_research_state.json"
        cases[ticker] = json.loads(case_path.read_text(encoding="utf-8"))
        cases[ticker]["required_sections"] = ["S3", "S4", "S5"]  # Saved fixture only has these drafts.
        states[ticker] = state_from_json(fixture.read_text(encoding="utf-8"))
        fixtures[ticker] = fixture
    clean = {ticker: grade(cases[ticker], states[ticker])["automatic_checks_pass"]
             for ticker in cases}
    rows = []
    for name, ticker, expected, before, after in MUTATIONS:
        state = copy.deepcopy(states[ticker])
        if name == "missing_limitation_contract":
            for draft in state["section_drafts"].values():
                draft.limitations = [item for item in draft.limitations
                                     if getattr(item, "research_task_id", None) != "parent_profit"]
        else:
            if before not in state["final_report"]:
                raise ValueError(f"Mutation anchor changed: {name}")
            state["final_report"] = state["final_report"].replace(before, after, 1)
        findings = grade(cases[ticker], state)["findings"]
        actual = [item["code"] for item in findings]
        rows.append({"mutation": name, "case_id": cases[ticker]["case_id"],
                     "expected_finding": expected, "actual_findings": actual,
                     "detected": expected in actual})
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    return {"phase": "A", "purpose": "grader sensitivity, not report quality",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "corpus_version": "v2.1", "runtime": {"writer": "saved TemplateWriter fixture",
                                                   "model": None, "prompt_version": None},
            "fixture_sha256": {path.name: sha(path) for path in fixtures.values()},
            "clean_controls": clean, "mutations": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=ROOT / "evaluation/benchmarks/report_quality_phase_a_demo_mutations.json")
    args = parser.parse_args()
    result = run_probe()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Clean controls: {result['clean_controls']}")
    for row in result["mutations"]:
        print(f"{row['mutation']}: {'detected' if row['detected'] else 'MISSED'} ({row['case_id']})")
    if not all(result["clean_controls"].values()) or not all(row["detected"] for row in result["mutations"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
