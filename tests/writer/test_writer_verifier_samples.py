"""Packaged Writer examples remain usable by the semantic Verifier."""
import json
import unittest
from pathlib import Path

from src.agents.state import state_from_json
from src.agents.verification import (
    build_verifier_section_view, verify_section_deterministically,
)


ROOT = (Path(__file__).resolve().parents[2] / "data/report_output/v2_1_fixtures"
        / "writer_verifier_samples")


class WriterVerifierSampleTests(unittest.TestCase):
    def test_three_full_drafts_round_trip_and_match_section_views(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([item["ticker"] for item in manifest["samples"]],
                         ["HUT", "GMD", "FPT"])
        for ticker in ("HUT", "GMD", "FPT"):
            with self.subTest(ticker=ticker):
                state = state_from_json((ROOT / f"{ticker}_state.json")
                                        .read_text(encoding="utf-8"))
                self.assertEqual(state["run_status"], "incomplete")
                self.assertEqual({section.section_id for section in
                                  state["outline"].sections},
                                 {f"S{index}" for index in range(1, 8)})
                self.assertEqual(state["final_report"] + "\n",
                                 (ROOT / f"{ticker}_draft.md")
                                 .read_text(encoding="utf-8"))
                for section in state["outline"].sections:
                    draft = next(item for item in state["section_drafts"].values()
                                 if item.section_id == section.section_id)
                    result = verify_section_deterministically(
                        draft, state["request"], state["evidence_by_id"],
                        state["calculations_by_id"], state["research_results"],
                        state["evidence_aliases"], section)
                    self.assertEqual(result.status, "passed", result.issues)
                    saved = json.loads((ROOT / f"{ticker}_{section.section_id}_verifier_view.json")
                                       .read_text(encoding="utf-8"))
                    expected = build_verifier_section_view(
                        draft, state["request"], state["evidence_by_id"],
                        state["calculations_by_id"], state["research_results"],
                        state["evidence_aliases"], section).model_dump(mode="json")
                    if section.section_id == "S2":
                        saved.pop("declared_limitations")
                        limitations = expected.pop("declared_limitations")
                        self.assertEqual(len(limitations), 1)
                        self.assertIn("toàn bộ mục kiểm toán đã trích xuất",
                                      limitations[0])
                    self.assertEqual(saved, expected)


if __name__ == "__main__":
    unittest.main()
