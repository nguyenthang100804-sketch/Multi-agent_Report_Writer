"""Writer W0 contracts against typed data and the fixed dev fixtures."""
import unittest
import re
from pathlib import Path

from pydantic import ValidationError

from src.agents.draft_rendering import render_block, render_template
from src.agents.report_graph import build_report_graph
from src.agents.state import state_from_json
from src.agents.verification import (
    attach_code_limitations, limitation_code, verify_section_deterministically,
)
from src.schemas.report_schema import (
    CalculationResult, CannotComputeLimitation, DataGapLimitation, DraftBlock,
    DraftLimitation, SectionDraft,
)


ROOT = Path(__file__).resolve().parents[2]


def fixture(ticker):
    return state_from_json((ROOT / f"data/report_output/{ticker}_research_state.json")
                           .read_text(encoding="utf-8"))


class WriterW0Tests(unittest.TestCase):
    def test_three_limitation_types_require_exact_anchor_and_round_trip(self):
        cases = [
            (DraftLimitation, {"warning_code": "period_inconsistency:2024->2025",
                               "evidence_ids": ["e"]}, "evidence_ids"),
            (CannotComputeLimitation, {"calculation_id": "c"}, "calculation_id"),
            (DataGapLimitation, {"research_task_id": "t"}, "research_task_id"),
        ]
        for model, anchor, field in cases:
            with self.subTest(kind=model.__name__):
                item = model(block_id="b", **anchor)
                self.assertEqual(model.model_validate_json(item.model_dump_json()), item)
                with self.assertRaises(ValidationError):
                    model(block_id="b", **{k: v for k, v in anchor.items() if k != field})
                with self.assertRaises(ValidationError):
                    model(block_id="b", **anchor,
                          **({"evidence_ids": ["wrong"]} if model is not DraftLimitation
                             else {"calculation_id": "wrong"}))
        draft = SectionDraft(section_id="s", outline_version=1, revision=1,
                             blocks=[DraftBlock(block_id="b", template="", text="")],
                             limitations=[model(block_id="b", **anchor)
                                          for model, anchor, _ in cases])
        loaded = SectionDraft.model_validate_json(draft.model_dump_json())
        self.assertEqual([type(item) for item in loaded.limitations],
                         [model for model, _, _ in cases])

    def test_rendered_text_and_claims_detect_tampering(self):
        state = fixture("hut")
        evidence_id = next(key for key, record in state["evidence_by_id"].items()
                           if record.kind == "fact" and record.payload.code == "10"
                           and record.payload.report_type == "INCOME_STATEMENT"
                           and record.payload.fiscal_year == 2025)
        aliases = {"E1": evidence_id}
        block = render_block("b", "Doanh thu đạt {{E1}}.", state["evidence_by_id"],
                             {}, aliases)
        context = {"evidence_by_id": state["evidence_by_id"],
                   "calculations_by_id": {}, "evidence_aliases": aliases}
        self.assertEqual(DraftBlock.model_validate(block.model_dump(), context=context), block)
        draft = SectionDraft(section_id="S3", outline_version=1, revision=1,
                             blocks=[block])
        result = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"], {},
            state["research_results"], aliases)
        self.assertEqual(result.status, "passed", result.issues)
        draft.blocks[0].text = re.sub(r"\d", "9", draft.blocks[0].text, count=1)
        with self.assertRaises(ValidationError):
            DraftBlock.model_validate(draft.blocks[0].model_dump(), context=context)
        result = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"], {},
            state["research_results"], aliases)
        self.assertIn("render_mismatch", [issue.error_type for issue in result.issues])
        with self.assertRaisesRegex(ValueError, "literal digit"):
            render_template("Doanh thu năm 2025 là {{E1}}.", "b",
                            state["evidence_by_id"], {}, aliases)

    def test_synthetic_magnitudes_rounding_and_abs(self):
        state = fixture("hut")
        source = next(record for record in state["evidence_by_id"].values()
                      if record.kind == "fact" and record.payload.unit == "VND")
        evidence = {}
        aliases = {}
        for alias, value in (("E1", 1_200_000_000_000),
                             ("E2", 1_200_000_000),
                             ("E3", 40_000), ("E4", -1_200_000_000)):
            key = alias.lower()
            evidence[key] = source.model_copy(deep=True)
            evidence[key].evidence_id = key
            evidence[key].payload.value = value
            aliases[alias] = key
        text, claims = render_template(
            "{{E1}}. {{E2}}. {{E3}}. {{E4|abs}}.", "b", evidence, {}, aliases)
        self.assertIn("1,2 nghìn tỷ đồng", text)
        self.assertIn("1,2 tỷ đồng", text)
        self.assertIn("40.000,0 đồng", text)
        self.assertEqual(claims[-1].display_sign, "magnitude")
        self.assertEqual(claims[-1].value, -1_200_000_000)

    def test_fpt_failures_generate_code_limitations_and_validate_anchors(self):
        state = fixture("fpt")
        section = next(x for x in state["outline"].sections if x.section_id == "S5")
        draft = SectionDraft(section_id="S5", outline_version=1, revision=1,
                             blocks=[DraftBlock(block_id="b", template="", text="")])
        missing = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"],
            state["evidence_aliases"], section)
        self.assertIn("missing_limitation", [issue.error_type for issue in missing.issues])
        draft = attach_code_limitations(draft, section, state["calculations_by_id"],
                                        state["research_results"])
        self.assertEqual(sum(x.kind == "cannot_compute" for x in draft.limitations), 7)
        self.assertEqual(sum(x.kind == "data_gap" for x in draft.limitations), 2)
        self.assertTrue(all(limitation_code(item, state["calculations_by_id"],
                                            state["research_results"]).startswith(item.kind + ":")
                            for item in draft.limitations))
        result = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"],
            state["evidence_aliases"], section)
        self.assertNotIn("missing_limitation", [issue.error_type for issue in result.issues])
        draft.limitations[0].calculation_id = "gross_margin:2025"
        result = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"],
            state["evidence_aliases"], section)
        self.assertEqual(result.status, "needs_revision")

    def test_graph_adds_fpt_limitations_without_writer_declaring_them(self):
        state = fixture("fpt")
        self.assertTrue(any(warning.startswith("period_inconsistency:")
                            for research in state["research_results"].values()
                            for warning in research.warnings))
        graph = build_report_graph(
            lambda _request: state["outline"],
            lambda _state: {key: state[key] for key in (
                "research_results", "evidence_by_id", "evidence_aliases",
                "calculations_by_id")},
            lambda _state: {"section_drafts": {("S5", 1): SectionDraft(
                section_id="S5", outline_version=1, revision=1,
                blocks=[DraftBlock(block_id="b", template="", text="")])}})
        result = graph.invoke({"request": state["request"]})
        draft = result["section_drafts"][("S5", 1)]
        self.assertEqual(len(draft.limitations), 9)
        self.assertEqual(result["verification_results"][("S5", 1)].status, "passed")

    def test_trend_phrases_follow_series_length_and_record_zero_threshold(self):
        calculations = {}
        for years, direction, expected in [
            (2, "increasing", "tăng"), (3, "increasing", "tăng liên tục"),
            (2, "decreasing", "giảm"), (3, "mixed", "diễn biến không đều")]:
            calculation = CalculationResult(
                calculation_id=f"t{years}:{direction}", operation="trend",
                input_evidence_ids=["e"], parameters={"start_year": 2022,
                "end_year": 2021 + years, "flat_absolute_threshold": "0"},
                direction=direction, status="ok")
            calculations[calculation.calculation_id] = calculation
            text, _ = render_template("Xu hướng {{T:" + calculation.calculation_id + "}}.",
                                      "b", {}, calculations, {})
            self.assertEqual(text, "Xu hướng " + expected + ".")
        self.assertEqual(calculations["t2:increasing"].parameters[
            "flat_absolute_threshold"], "0")


if __name__ == "__main__":
    unittest.main()
