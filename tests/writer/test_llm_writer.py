"""Fake-model contract, repair loop, and section-only fallback for W4."""
import json
import unittest
from decimal import Decimal
from pathlib import Path

from src.agents.citation_recall import scan_template_candidates, scan_unclaimed_blocks
from src.agents.draft_rendering import render_template
from src.agents.llm_writer import _validate_templates, build_llm_writer, build_section_view
from src.agents.report_graph import build_report_graph
from src.agents.state import state_from_json, state_to_json
from src.agents.template_writer import build_template_writer
from src.agents.writer_contract import NarrativeOutput, WriterResponse
from src.agents.writer_menu import build_placeholder_menu
from src.agents.writer_model import GeminiWriterModel
from src.schemas.report_schema import VerificationIssue, VerificationResult


ROOT = Path(__file__).resolve().parents[2]


def fixture(ticker="hut"):
    return state_from_json((ROOT / f"data/report_output/{ticker}_research_state.json")
                           .read_text(encoding="utf-8"))


class FakeWriterModel:
    def __init__(self, state, scripts=None):
        self.baseline = {draft.section_id: draft for draft in
                         build_template_writer()(state)["section_drafts"].values()}
        self.scripts = {key: list(value) for key, value in (scripts or {}).items()}
        self.requests = []

    def valid(self, section_id):
        draft = self.baseline[section_id]
        return json.dumps({"blocks": [
            {"block_id": f"b{index}", "template": block.template}
            for index, block in enumerate(draft.blocks[1:], 1)]})

    def generate(self, request):
        self.requests.append(request)
        section_id = json.loads(request.section_view)["section_id"]
        scenario = self.scripts.get(section_id, [])
        response = scenario.pop(0) if scenario else self.valid(section_id)
        if isinstance(response, Exception):
            raise response
        return WriterResponse(text=response, token_usage={"input_tokens": 10,
                                                          "output_tokens": 5})


def run_graph(state, model):
    graph = build_report_graph(
        lambda _request: state["outline"],
        lambda _state: {key: state[key] for key in (
            "research_results", "evidence_by_id", "evidence_aliases",
            "calculations_by_id")}, build_llm_writer(model))
    return graph.invoke({"request": state["request"]})


class LLMWriterTests(unittest.TestCase):
    def test_signed_change_placeholder_and_direction_validation(self):
        root = ROOT / "data/report_output"
        for ticker in ("bwe", "dcm"):
            state = state_from_json((root / f"{ticker}_writer_eval_research_state.json")
                                    .read_text(encoding="utf-8"))
            section = next(s for s in state["outline"].sections if s.section_id == "S5")
            menu = build_placeholder_menu(section, state)
            key = "operating_cash_flow:difference:2025"
            self.assertIn(f"{{{{D:{key}}}}}", menu["allowed_tokens"])
            text, claims = render_template(
                f"Lưu chuyển tiền {{{{P:C:{key}}}}} {{{{D:{key}}}}}.", "b1",
                state["evidence_by_id"], state["calculations_by_id"],
                state["evidence_aliases"])
            self.assertIn("giảm ", text)
            self.assertNotIn("giảm -", text)
            self.assertEqual(claims[0].display_sign, "magnitude")
            self.assertLess(claims[0].asserted_value, 0)
            bad = NarrativeOutput.model_validate({"blocks": [{"block_id": "b1",
                "template": f"Lưu chuyển tiền {{{{P:C:{key}}}}} giảm {{{{C:{key}}}}}."}]})
            errors, _ = _validate_templates(bad, menu, state)
            self.assertTrue(any("directional_C_sign" in error for error in errors))
            bad.blocks[0].template = f"Lưu chuyển tiền {{{{P:C:{key}}}}} giảm {{{{C:{key}|abs}}}}."
            errors, _ = _validate_templates(bad, menu, state)
            self.assertEqual([error for error in errors if "C: does not accept |abs" in error],
                             [f"b1: C: does not accept |abs; use D:<calculation_id> for a signed change"])
            self.assertFalse(any("literal_digit" in error or "internal_identifier" in error
                                 or "Unknown placeholder" in error for error in errors))
            bad.blocks[0].template = f"Lưu chuyển tiền {{{{P:C:{key}}}}} giảm {{{{D:{key}}}}}."
            errors, _ = _validate_templates(bad, menu, state)
            self.assertTrue(any("duplicated_change_direction" in error for error in errors))
            if ticker == "bwe":
                model = FakeWriterModel(state)
                revised = json.loads(model.valid("S5"))
                revised["blocks"][0]["template"] = (
                    f"Lưu chuyển tiền thuần từ hoạt động kinh doanh "
                    f"{{{{P:C:{key}}}}} {{{{D:{key}}}}}.")
                model.scripts["S5"] = [json.dumps(revised)]
                result = run_graph(state, model)
                s5 = next(log for log in result["writer_run_logs"].values()
                          if log.section_id == "S5")
                self.assertFalse(s5.used_fallback)
                self.assertEqual(s5.errors_by_attempt, [[]])
                self.assertNotIn("giảm -", result["final_report"])

    def test_extremum_and_correspondence_scan(self):
        self.assertEqual(scan_template_candidates("Sau khi đạt đỉnh năm trước.")[0],
                         ["unsupported_extremum: đỉnh"])
        state = fixture("hut")
        section = next(s for s in state["outline"].sections if s.section_id == "S4")
        menu = build_placeholder_menu(section, state)
        ratio_key = next(key for key, item in menu["calculations"].items()
                         if item["operation"] == "ratio")
        numerator = state["calculations_by_id"][ratio_key].input_evidence_ids[0]
        alias = next(alias for alias, evidence_id in state["evidence_aliases"].items()
                     if evidence_id == numerator)
        related = NarrativeOutput.model_validate({"blocks": [{"block_id": "b1",
            "template": f"Giá trị {{{{{alias}}}}} tương ứng tỷ lệ {{{{C:{ratio_key}}}}} "
                        f"trong {{{{P:C:{ratio_key}}}}}."}]})
        _, warnings = _validate_templates(related, menu, state)
        self.assertFalse(any("ambiguous_relation" in warning for warning in warnings))
        other_alias = next(key for key in menu["facts"]
                           if state["evidence_aliases"][key] != numerator)
        unrelated = NarrativeOutput.model_validate({"blocks": [{"block_id": "b1",
            "template": f"Giá trị {{{{{other_alias}}}}} tương ứng mức {{{{C:{ratio_key}}}}} "
                        f"trong {{{{P:C:{ratio_key}}}}}."}]})
        _, warnings = _validate_templates(unrelated, menu, state)
        self.assertTrue(any("ambiguous_relation" in warning for warning in warnings))

    def test_yoy_direction_must_match_value(self):
        state = fixture("hut")
        section = next(s for s in state["outline"].sections if s.section_id == "S3")
        menu = build_placeholder_menu(section, state)
        key = "revenue:yoy:2025"
        template = (f"Doanh thu {{{{P:C:{key}}}}} ghi nhận mức tăng "
                    f"{{{{C:{key}}}}}.")
        output = NarrativeOutput.model_validate({"blocks": [{"block_id": "b1",
            "template": template}]})
        errors, _ = _validate_templates(output, menu, state)
        self.assertFalse(any("directional_C_sign" in error for error in errors))
        negative = dict(state)
        negative["calculations_by_id"] = dict(state["calculations_by_id"])
        negative["calculations_by_id"][key] = state["calculations_by_id"][key].model_copy(
            update={"value": Decimal("-1.00")})
        errors, _ = _validate_templates(output, menu, negative)
        self.assertTrue(any("directional_C_sign" in error for error in errors))

    def test_saved_direction_and_extremum_outputs_are_rejected(self):
        root = ROOT / "data/report_output"
        recent = json.loads((root / "writer_w4_v4_eight_dev_s5_eval.json")
                            .read_text(encoding="utf-8"))
        for ticker in ("dcm", "bwe", "gmd", "hut"):
            fixture_name = (f"{ticker}_research_state.json" if ticker in ("hut", "gmd")
                            else f"{ticker}_writer_eval_research_state.json")
            state = state_from_json((root / fixture_name).read_text(encoding="utf-8"))
            section = next(s for s in state["outline"].sections if s.section_id == "S5")
            raw = recent["tickers"][ticker]["logs"][0]["raw_outputs_by_attempt"][0]
            output = NarrativeOutput.model_validate_json(raw)
            errors, _ = _validate_templates(output, build_placeholder_menu(section, state), state)
            expected = "unsupported_sequence" if ticker == "hut" else "extra_change_direction"
            self.assertTrue(any(expected in error for error in errors), (ticker, errors))
        old = json.loads((root / "writer_w4_v3_six_dev_s345_eval.json")
                         .read_text(encoding="utf-8"))
        state = state_from_json((root / "qns_writer_eval_research_state.json")
                                .read_text(encoding="utf-8"))
        section = next(s for s in state["outline"].sections if s.section_id == "S4")
        raw = next(log for log in old["tickers"]["qns"]["logs"]
                   if log["section_id"] == "S4")["raw_outputs_by_attempt"][0]
        output = NarrativeOutput.model_validate_json(raw)
        errors, _ = _validate_templates(output, build_placeholder_menu(section, state), state)
        self.assertTrue(any("unsupported_extremum: đỉnh" in error for error in errors))

    def test_hut_cagr_phrase_does_not_hide_display_number(self):
        state = fixture("hut")
        saved = json.loads((ROOT / "data/report_output/writer_w4_v5_eight_dev_s34_eval.json")
                           .read_text(encoding="utf-8"))
        raw = next(log for log in saved["tickers"]["hut"]["logs"]
                   if log["section_id"] == "S3")["raw_outputs_by_attempt"][0]
        model = FakeWriterModel(state, {"S3": [raw]})
        result = build_llm_writer(model)(state)
        log = next(item for item in result["writer_run_logs"].values()
                   if item.section_id == "S3")
        self.assertEqual(log.attempts, 1)
        self.assertFalse(log.used_fallback)
        self.assertEqual(log.errors_by_attempt, [[]])

    def test_direction_between_two_facts_matches_values(self):
        state = fixture("hut")
        section = next(s for s in state["outline"].sections if s.section_id == "S3")
        menu = build_placeholder_menu(section, state)
        for first, second, expected_error in (("E56", "E59", False),
                                              ("E59", "E56", True)):
            output = NarrativeOutput.model_validate({"blocks": [{"block_id": "b1",
                "template": f"Doanh thu từ {{{{{first}}}}} vào {{{{Y:{first}}}}} "
                            f"lên {{{{{second}}}}} vào {{{{Y:{second}}}}}."}]})
            errors, _ = _validate_templates(output, menu, state)
            self.assertEqual(any("fact_direction_mismatch" in error for error in errors),
                             expected_error)

    def test_first_attempt_and_section_view_are_scoped(self):
        state = fixture()
        model = FakeWriterModel(state)
        result = run_graph(state, model)
        self.assertEqual({x.status for x in result["verification_results"].values()},
                         {"passed"})
        quantitative_logs = [x for x in result["writer_run_logs"].values()
                             if x.section_id in {"S3", "S4", "S5"}]
        self.assertEqual(len(quantitative_logs), 3)
        self.assertTrue(all(x.attempts == 1 and not x.used_fallback
                            for x in quantitative_logs))
        s3_request = next(req for req in model.requests
                          if json.loads(req.section_view)["section_id"] == "S3")
        view = json.loads(s3_request.section_view)
        s4 = next(s for s in state["outline"].sections if s.section_id == "S4")
        s4_aliases = set(build_section_view(s4, state, model.baseline["S4"]).facts)
        self.assertFalse(set(view["facts"]) & s4_aliases)
        self.assertTrue(view["facts"] and view["calculations"])
        self.assertTrue(all("display" in item for item in view["facts"].values()))
        self.assertIn("response_schema", type(s3_request).model_fields)
        self.assertEqual(result["final_report"].count("### Biến động theo kỳ"), 3)
        self.assertEqual(scan_unclaimed_blocks(model.baseline["S3"].blocks), [])
        restored = state_from_json(state_to_json(result))
        self.assertEqual(restored["writer_run_logs"], result["writer_run_logs"])

    def test_literal_digit_repairs_with_feedback_and_token_log(self):
        state = fixture()
        model = FakeWriterModel(state)
        bad = json.loads(model.valid("S3"))
        bad["blocks"][0]["template"] += " Năm 2025."
        model.scripts["S3"] = [json.dumps(bad), model.valid("S3")]
        result = run_graph(state, model)
        log = next(x for x in result["writer_run_logs"].values() if x.section_id == "S3")
        self.assertEqual(log.attempts, 2)
        self.assertIn("literal_digit", str(log.errors_by_attempt[0]))
        self.assertEqual(log.errors_by_attempt[1], [])
        self.assertFalse(log.used_fallback)
        self.assertEqual(log.token_usage["input_tokens"], 20)
        self.assertTrue(any("literal_digit" in str(req.feedback) for req in model.requests))

    def test_dev_log_keeps_raw_output_and_block_count(self):
        state = fixture()
        model = FakeWriterModel(state)
        short = {"blocks": [{"block_id": "b1", "template":
                 json.loads(model.valid("S3"))["blocks"][0]["template"]}]}
        model.scripts["S3"] = [json.dumps(short), model.valid("S3")]
        result = build_llm_writer(model, record_raw_outputs=True)(state)
        log = next(x for x in result["writer_run_logs"].values() if x.section_id == "S3")
        self.assertEqual(log.block_counts_by_attempt, [1, 4])
        self.assertEqual(json.loads(log.raw_outputs_by_attempt[0]), short)
        self.assertIn("received 1 blocks; need 3–5 blocks",
                      str(log.errors_by_attempt[0]))
        self.assertEqual(len(log.attempt_elapsed_ms), 2)

    def test_foreign_alias_and_unavailable_calculation_repair(self):
        state = fixture("fpt")
        model = FakeWriterModel(state)
        foreign = next(iter(build_section_view(
            next(s for s in state["outline"].sections if s.section_id == "S4"),
            state, model.baseline["S4"]).facts))
        bad_s3 = json.loads(model.valid("S3"))
        bad_s3["blocks"][0]["template"] = f"Chỉ tiêu năm {{{{Y:{foreign}}}}} là {{{{{foreign}}}}}."
        bad_s5 = json.loads(model.valid("S5"))
        bad_s5["blocks"][0]["template"] = (
            "Tỷ lệ {{P:C:cfo_to_net_income:2025}} là {{C:cfo_to_net_income:2025}}.")
        model.scripts = {"S3": [json.dumps(bad_s3), model.valid("S3")],
                         "S5": [json.dumps(bad_s5), model.valid("S5")]}
        result = run_graph(state, model)
        for section_id in ("S3", "S5"):
            log = next(x for x in result["writer_run_logs"].values()
                       if x.section_id == section_id)
            self.assertIn("outside section menu", str(log.errors_by_attempt[0]))
            self.assertFalse(log.used_fallback)
        self.assertIn("Dữ liệu trích xuất không có giá trị", result["final_report"])

    def test_semantic_candidates_units_missing_template_and_fallback(self):
        state = fixture()
        model = FakeWriterModel(state)
        bad = json.loads(model.valid("S3"))
        bad["blocks"][0]["template"] += " Do chi phí giảm, doanh thu sẽ gấp đôi."
        bad["blocks"][1]["template"] = bad["blocks"][1]["template"].replace(
            "{{C:gross_margin:2025}}.", "{{C:gross_margin:2025}} tỷ đồng.")
        model.scripts["S3"] = [json.dumps(bad), '{"blocks":[{"block_id":"b1"}]}',
                                "not JSON"]
        result = run_graph(state, model)
        log = next(x for x in result["writer_run_logs"].values() if x.section_id == "S3")
        self.assertEqual(log.attempts, 3)
        self.assertTrue(log.used_fallback)
        self.assertIn("causal_language", str(log.errors_by_attempt[0]))
        self.assertIn("word_comparison", str(log.errors_by_attempt[0]))
        self.assertIn("forecast_language", str(log.errors_by_attempt[0]))
        self.assertIn("handwritten_unit", str(log.errors_by_attempt[0]))
        self.assertIn("missing_template", str(log.errors_by_attempt[1]))
        self.assertEqual({x.status for x in result["verification_results"].values()},
                         {"passed"})
        self.assertFalse(any(x.used_fallback for x in result["writer_run_logs"].values()
                             if x.section_id in {"S4", "S5"}))
        self.assertEqual(scan_template_candidates("Cao hơn năm trước.")[1],
                         ["word_comparison: Cao hơn"])

    def test_model_exception_falls_back_only_one_section(self):
        state = fixture()
        model = FakeWriterModel(state, {"S4": [ConnectionError("network down")]})
        result = run_graph(state, model)
        logs = {x.section_id: x for x in result["writer_run_logs"].values()}
        self.assertTrue(logs["S4"].used_fallback)
        self.assertEqual(logs["S4"].attempts, 1)
        self.assertIn("model_error", str(logs["S4"].errors_by_attempt))
        self.assertFalse(logs["S3"].used_fallback)
        self.assertFalse(logs["S5"].used_fallback)

    def test_duplicate_period_prefix_and_extra_renderer_fields_are_rejected(self):
        state = fixture()
        model = FakeWriterModel(state)
        bad = json.loads(model.valid("S3"))
        bad["blocks"][0]["template"] = bad["blocks"][0]["template"].replace(
            "{{P:C:revenue:yoy:2025}}", "năm {{P:C:revenue:yoy:2025}}")
        bad_extra = json.loads(model.valid("S4"))
        bad_extra["blocks"][0]["text"] = "handwritten"
        model.scripts = {"S3": [json.dumps(bad), model.valid("S3")],
                         "S4": [json.dumps(bad_extra), model.valid("S4")]}
        result = run_graph(state, model)
        logs = {x.section_id: x for x in result["writer_run_logs"].values()}
        self.assertIn("duplicated_period_prefix", str(logs["S3"].errors_by_attempt[0]))
        self.assertIn("extra_forbidden", str(logs["S4"].errors_by_attempt[0]))
        self.assertEqual(result["final_report"].count("### Biến động theo kỳ"), 3)

    def test_valid_period_declaration_and_revision_feedback(self):
        state = fixture("fpt")
        model = FakeWriterModel(state)
        period = next(item for item in model.baseline["S5"].limitations
                      if item.kind == "period_inconsistency")
        alias_by_id = {evidence_id: alias for alias, evidence_id in
                       state["evidence_aliases"].items()}
        valid = json.loads(model.valid("S5"))
        valid["period_limitations"] = [{
            "warning_code": period.warning_code,
            "evidence_aliases": [alias_by_id[key] for key in period.evidence_ids],
            "block_id": "b1"}]
        model.scripts["S5"] = [json.dumps(valid)]
        previous = model.baseline["S5"].model_copy(deep=True)
        state["section_drafts"] = {("S5", 1): previous}
        state["verification_results"] = {("S5", 1): VerificationResult(
            section_id="S5", revision=1, outline_version=1,
            level="deterministic", status="needs_revision", issues=[
                VerificationIssue(claim_id="b", error_type="unsupported_claim",
                                  reason="Rewrite a claim", action="rewrite")])}
        result = build_llm_writer(model)(state)
        draft = next(d for d in result["section_drafts"].values()
                     if d.section_id == "S5")
        self.assertEqual(draft.revision, 2)
        self.assertTrue(any(l.kind == "period_inconsistency" and
                            l.block_id == "S5:n:b1" for l in draft.limitations))
        request = next(req for req in model.requests
                       if json.loads(req.section_view)["section_id"] == "S5")
        self.assertIn("Rewrite a claim", json.loads(request.section_view)[
            "revision_instructions"])

    def test_unclaimed_narrative_is_repaired(self):
        state = fixture()
        model = FakeWriterModel(state)
        generic = {"blocks": [{"block_id": key, "template": "Tình hình được trình bày."}
                              for key in ("b1", "b2", "b3")]}
        model.scripts["S3"] = [json.dumps(generic), model.valid("S3")]
        result = run_graph(state, model)
        log = next(x for x in result["writer_run_logs"].values() if x.section_id == "S3")
        self.assertIn("missing_claim", str(log.errors_by_attempt[0]))
        self.assertFalse(log.used_fallback)

    def test_reader_prose_cannot_expose_internal_identifier(self):
        state = fixture()
        model = FakeWriterModel(state)
        bad = json.loads(model.valid("S3"))
        bad["blocks"][0]["template"] += " REVENUE_YOY."
        model.scripts["S3"] = [json.dumps(bad), model.valid("S3")]
        result = run_graph(state, model)
        log = next(x for x in result["writer_run_logs"].values() if x.section_id == "S3")
        self.assertIn("internal_identifier", str(log.errors_by_attempt[0]))
        self.assertFalse(log.used_fallback)

    def test_year_prefix_rejected_and_renderer_shares_monetary_scale(self):
        state = fixture()
        model = FakeWriterModel(state)
        section = next(s for s in state["outline"].sections if s.section_id == "S3")
        from src.agents.writer_menu import build_placeholder_menu
        facts = build_placeholder_menu(section, state)["facts"]
        revenue = next(alias for alias, item in facts.items()
                       if item["label"] == "Doanh thu thuần" and item["fiscal_year"] == 2025)
        profit = next(alias for alias, item in facts.items()
                      if item["label"] == "Lợi nhuận sau thuế" and item["fiscal_year"] == 2025)
        bad = json.loads(model.valid("S3"))
        bad["blocks"][0]["template"] = (
            f"Doanh thu năm {{{{Y:{revenue}}}}} là {{{{{revenue}}}}}, "
            f"lợi nhuận {{{{Y:{profit}}}}} là {{{{{profit}}}}}.")
        model.scripts["S3"] = [json.dumps(bad), model.valid("S3")]
        result = run_graph(state, model)
        log = next(x for x in result["writer_run_logs"].values() if x.section_id == "S3")
        self.assertIn("duplicated_period_prefix", str(log.errors_by_attempt[0]))
        self.assertFalse(log.used_fallback)
        bad["blocks"][0]["template"] = bad["blocks"][0]["template"].replace(
            f"Doanh thu năm {{{{Y:{revenue}}}}}", f"Doanh thu {{{{Y:{revenue}}}}}")
        model = FakeWriterModel(state, {"S3": [json.dumps(bad), FakeWriterModel(state).valid("S3")]})
        result = run_graph(state, model)
        log = next(x for x in result["writer_run_logs"].values() if x.section_id == "S3")
        self.assertEqual(log.errors_by_attempt[0], [])
        block = next(block for draft in result["section_drafts"].values()
                     if draft.section_id == "S3" for block in draft.blocks
                     if block.block_id == "S3:n:b1")
        self.assertEqual({claim.display_unit for claim in block.claims}, {"tỷ đồng"})
        self.assertNotIn("nghìn tỷ đồng", block.text)
        self.assertEqual(scan_template_candidates("Hai số tương ứng nhau.")[1],
                         ["ambiguous_relation: tương ứng"])

    def test_saved_gmd_first_attempt_now_passes_with_shared_scale(self):
        state = fixture("gmd")
        diagnostic = json.loads((ROOT / "data/report_output/gmd_s3_w4_v2.json")
                                .read_text(encoding="utf-8"))
        first_output = diagnostic["raw_outputs_by_attempt"][0]
        model = FakeWriterModel(state, {"S3": [first_output]})
        result = build_llm_writer(model)(state)
        log = next(x for x in result["writer_run_logs"].values() if x.section_id == "S3")
        self.assertEqual(log.attempts, 1)
        self.assertEqual(log.errors_by_attempt, [[]])
        self.assertFalse(log.used_fallback)


class FakeGeminiResponse:
    text = '{"blocks":[]}'
    usage_metadata = type("Usage", (), {"prompt_token_count": 12,
                                          "candidates_token_count": 8,
                                          "thoughts_token_count": 2,
                                          "total_token_count": 22})()


class FakeGeminiClient:
    def __init__(self):
        self.models = self
        self.kwargs = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        return FakeGeminiResponse()


class GeminiWriterAdapterTests(unittest.TestCase):
    def test_temperature_schema_and_usage(self):
        client = FakeGeminiClient()
        from src.agents.writer_contract import WriterRequest, NarrativeOutput
        response = GeminiWriterModel(client=client).generate(WriterRequest(
            system="writer", section_view=json.dumps({"section_id": "S3"}),
            response_schema=NarrativeOutput.model_json_schema()))
        self.assertEqual(response.token_usage["total_tokens"], 22)
        self.assertEqual(client.kwargs["config"].temperature, 0)
        self.assertEqual(client.kwargs["config"].thinking_config.thinking_level, "LOW")
        self.assertEqual(client.kwargs["config"].response_mime_type, "application/json")
        self.assertTrue(client.kwargs["config"].response_json_schema)


if __name__ == "__main__":
    unittest.main()
