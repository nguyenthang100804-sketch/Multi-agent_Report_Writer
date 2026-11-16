"""LLM selects and writes source-bound qualitative observations."""
import json
import unittest
from pathlib import Path

from src.agents.llm_writer import build_llm_writer
from src.agents.state import state_from_json
from src.agents.verification import verify_section_deterministically
from src.agents.writer_contract import WriterResponse
from src.agents.writer_menu import build_placeholder_menu, validate_template_menu


ROOT = Path(__file__).resolve().parents[2] / "data/report_output/v2_1_fixtures"


def fpt_s7_state():
    state = state_from_json((ROOT / "fpt_w6_note_research_state.json")
                            .read_text(encoding="utf-8"))
    section = next(item for item in state["outline"].sections
                   if item.section_id == "S7")
    state["outline"] = state["outline"].model_copy(update={"sections": [section]})
    return state, section


class SelectingModel:
    def __init__(self, *, invalid_quote=False, evidence_alias_override=None,
                 observation=None):
        self.calls = []
        self.invalid_quote = invalid_quote
        self.evidence_alias_override = evidence_alias_override
        self.observation = observation

    def generate(self, request):
        self.calls.append(request)
        view = json.loads(request.section_view)
        task = next(item for item in view["tasks"]
                    if ":financial_risks:" in item["task_id"])
        alias = next(alias for alias in task["evidence_aliases"]
                     if "phòng ngừa rủi ro tỷ giá" in view["chunks"][alias]["text"])
        text = view["chunks"][alias]["text"]
        start = text.index("Đối với các khoản vay bằng ngoại tệ")
        quote = text[start:text.index(".", start) + 1]
        if self.invalid_quote:
            quote = "Câu này không xuất hiện trong tài liệu được truy xuất."
        output = {"blocks": [{"block_id": "b1", "task_id": task["task_id"],
                              "evidence_alias": self.evidence_alias_override or alias,
                              "quote": quote,
                              "observation": self.observation or
                              "Tập đoàn dùng giao dịch ngoại tệ để phòng ngừa rủi ro tỷ giá."}]}
        return WriterResponse(text=json.dumps(output, ensure_ascii=False),
                              token_usage={"total_tokens": 100})


class QualitativeLLMWriterTests(unittest.TestCase):
    def test_verifier_menu_accepts_an_exact_model_selected_note_span(self):
        state, section = fpt_s7_state()
        menu = build_placeholder_menu(section, state)
        alias = next(alias for alias, item in menu["note_sources"].items()
                     if "Do đó, Tập đoàn không ghi nhận khoản dự phòng chi phí hoàn nguyên"
                     in item)
        source = menu["note_sources"][alias]
        start = source.index("Do đó, Tập đoàn không ghi nhận khoản dự phòng")
        end = source.index(".", start) + 1
        token = f"{{{{N:{alias}:{start}:{end}}}}}"
        self.assertNotIn(token, menu["allowed_tokens"])
        validate_template_menu(f"Trích từ tài liệu {{{{Y:{alias}}}}}: {token}", menu)
        with self.assertRaisesRegex(ValueError, "outside section menu"):
            validate_template_menu(f"{{{{N:{alias}:0:20}}}}", menu)

    def test_valid_selection_creates_claim_and_passes_verifier(self):
        state, section = fpt_s7_state()
        model = SelectingModel()
        output = build_llm_writer(model, max_repairs=0,
                                  record_raw_outputs=True)(state)
        draft = next(iter(output["section_drafts"].values()))
        log = next(iter(output["writer_run_logs"].values()))
        self.assertEqual(len(model.calls), 1)
        self.assertFalse(log.used_fallback)
        self.assertEqual(log.prompt_version, "w6-v1")
        self.assertEqual(log.block_counts_by_attempt, [1])
        self.assertIsNotNone(log.raw_outputs_by_attempt[0])
        self.assertIn("Tập đoàn dùng giao dịch ngoại tệ", draft.blocks[1].text)
        self.assertIn("năm 2025", draft.blocks[1].text)
        self.assertEqual(draft.blocks[1].claims[0].claim_type, "qualitative")
        result = verify_section_deterministically(
            draft, state["request"], state["evidence_by_id"],
            state["calculations_by_id"], state["research_results"],
            state["evidence_aliases"], section)
        self.assertEqual(result.status, "passed", result.issues)

    def test_quote_not_in_source_falls_back_for_section(self):
        state, _ = fpt_s7_state()
        model = SelectingModel(invalid_quote=True)
        output = build_llm_writer(model, max_repairs=0)(state)
        draft = next(iter(output["section_drafts"].values()))
        log = next(iter(output["writer_run_logs"].values()))
        self.assertTrue(log.used_fallback)
        self.assertEqual(log.attempts, 1)
        self.assertIn("quote_not_substantive_or_not_verbatim",
                      " ".join(log.errors_by_attempt[0]))
        self.assertNotIn("Tập đoàn dùng giao dịch ngoại tệ", draft.blocks[1].text)

    def test_other_task_evidence_and_literal_year_are_rejected(self):
        state, _ = fpt_s7_state()
        other_id = state["research_results"]["S6:revenue_policy:2025"].evidence_ids[0]
        other_alias = next(alias for alias, evidence_id in
                           state["evidence_aliases"].items() if evidence_id == other_id)
        for model, error in (
                (SelectingModel(evidence_alias_override=other_alias), "evidence_outside_task"),
                (SelectingModel(observation="Năm 2025 Tập đoàn phòng ngừa rủi ro."),
                 "invalid_observation")):
            with self.subTest(error=error):
                output = build_llm_writer(model, max_repairs=0)(state)
                log = next(iter(output["writer_run_logs"].values()))
                self.assertTrue(log.used_fallback)
                self.assertIn(error, " ".join(log.errors_by_attempt[0]))

    def test_model_error_falls_back_without_repeating_the_call(self):
        state, _ = fpt_s7_state()

        class UnavailableModel:
            calls = 0

            def generate(self, _request):
                self.calls += 1
                raise OSError("network unavailable")

        model = UnavailableModel()
        output = build_llm_writer(model)(state)
        log = next(iter(output["writer_run_logs"].values()))
        self.assertEqual(model.calls, 1)
        self.assertEqual(log.attempts, 1)
        self.assertTrue(log.used_fallback)
        self.assertIn("model_error", log.errors_by_attempt[0][0])


if __name__ == "__main__":
    unittest.main()
