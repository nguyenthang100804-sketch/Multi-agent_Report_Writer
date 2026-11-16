"""Every section-menu token must survive rendering and deterministic verification."""
import unittest
from pathlib import Path
from decimal import Decimal

from src.agents.draft_rendering import render_block
from src.agents.state import state_from_json
from src.agents.template_writer import build_template_writer
from src.agents.verification import _extract_numbers, verify_section_deterministically
from src.agents.writer_menu import build_placeholder_menu


ROOT = Path(__file__).resolve().parents[2] / "data/report_output"


class WriterRenderContractTests(unittest.TestCase):
    def test_period_words_do_not_swallow_percent_values(self):
        values, invalid = _extract_numbers(
            "Trong tháng 12 và quý 4, mức tăng là 223,46% và 3,2 điểm phần trăm.")
        self.assertEqual(values, [Decimal("223.46"), Decimal("3.2")])
        self.assertEqual(invalid, [])
        values, _ = _extract_numbers("Tháng 223,46% là mức thay đổi được tính.")
        self.assertEqual(values, [Decimal("223.46")])

    def test_every_allowed_token_round_trips_through_verifier(self):
        for ticker in ("hut", "gmd", "fpt", "bsr", "bwe", "dcm", "gas", "gex", "qns"):
            suffix = "research_state.json" if ticker in ("hut", "gmd", "fpt") else \
                     "writer_eval_research_state.json"
            state = state_from_json((ROOT / f"{ticker}_{suffix}").read_text(encoding="utf-8"))
            baselines = {draft.section_id: draft for draft in
                         build_template_writer()(state)["section_drafts"].values()}
            for section in state["outline"].sections:
                if section.section_id not in ("S3", "S4", "S5"):
                    continue
                menu = build_placeholder_menu(section, state)
                for token in menu["allowed_tokens"]:
                    body = token[2:-2]
                    if body.startswith("E"):
                        alias = body.partition("|")[0]
                        template = f"Giá trị {{{{Y:{alias}}}}} là {token}."
                    elif body.startswith("Y:"):
                        template = f"Giá trị {token} là {{{{{body[2:]}}}}}."
                    elif body.startswith("P:C:"):
                        key = body[4:]
                        result = "T" if key in menu["trends"] else "C"
                        template = f"Giá trị {token} là {{{{{result}:{key}}}}}."
                    elif body.startswith("D:"):
                        key = body[2:]
                        template = f"Chỉ tiêu {{{{P:C:{key}}}}} {token}."
                    else:
                        key = body[2:]
                        template = f"Giá trị {{{{P:C:{key}}}}} là {token}."
                    with self.subTest(ticker=ticker, section=section.section_id, token=token):
                        block = render_block("probe", template, state["evidence_by_id"],
                                             state["calculations_by_id"], state["evidence_aliases"])
                        draft = baselines[section.section_id].model_copy(deep=True)
                        draft.blocks.append(block)
                        checked = verify_section_deterministically(
                            draft, state["request"], state["evidence_by_id"],
                            state["calculations_by_id"], state["research_results"],
                            state["evidence_aliases"], section)
                        self.assertEqual(checked.status, "passed", checked.issues)


if __name__ == "__main__":
    unittest.main()
