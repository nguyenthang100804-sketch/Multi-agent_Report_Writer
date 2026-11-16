"""Unit tests for the two-stage Semantic Verifier, fail-closed rules, and graph completion."""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import unittest

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents.draft_rendering import render_block
from src.agents.report_graph import build_report_graph
from src.agents.state import (
    can_complete, complete_run, is_run_complete, report_checkpoint_serde,
    state_from_json, state_to_json,
)
from src.agents.verification import (
    build_verifier_section_view, verify_section_deterministically,
    verify_section_full, verify_section_semantically,
)
from src.agents.verifier_contract import (
    SemanticBlockFinding, SemanticBlockVerdict, SemanticVerificationOutput,
    VerifierRequest, VerifierResponse,
)
from src.schemas.report_schema import (
    Claim, DraftBlock, DraftLimitation, EvidenceRecord, FactTask,
    ReportOutline, ReportRequest, SectionDraft, SectionPlan, TimeSeriesTask,
    record_tool_result,
)
from src.tools.schemas import FactEvidence, NoteEvidence, ToolResult


class FakeVerifierModel:
    def __init__(self, responses: list[str | Exception]):
        self.responses = list(responses)
        self.requests: list[VerifierRequest] = []

    def verify(self, request: VerifierRequest) -> VerifierResponse:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return VerifierResponse(
            text=item,
            token_usage={"input_tokens": 120, "output_tokens": 45, "total_tokens": 165},
        )


def _sample_state() -> dict:
    root = Path(__file__).resolve().parents[2]
    sample = state_from_json(
        (root / "docs" / "examples" / "synthetic-report-state.json").read_text(encoding="utf-8")
    )
    final_id = next(
        key for key, record in sample["evidence_by_id"].items()
        if record.payload.fiscal_year == 2024
    )
    sample["evidence_aliases"] = {"E1": final_id}
    return sample


class SemanticVerifierTests(unittest.TestCase):
    def test_deterministic_failure_skips_semantic_model_call(self):
        sample = _sample_state()
        section = sample["outline"].sections[0]
        # Unlinked number in prose causes deterministic failure
        bad_block = DraftBlock(
            block_id="b1",
            text="Doanh thu thuần năm 2024 đạt 999 VND.",
            claims=sample["section_drafts"][("revenue", 1)].blocks[0].claims,
        )
        draft = SectionDraft(
            section_id="revenue", outline_version=1, revision=1, blocks=[bad_block]
        )
        fake = FakeVerifierModel([
            SemanticVerificationOutput(
                section_id="revenue",
                block_verdicts=[SemanticBlockVerdict(block_id="b1", status="passed")],
            ).model_dump_json()
        ])
        result, log = verify_section_full(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            fake, sample["evidence_aliases"], section,
        )
        self.assertEqual(len(fake.requests), 0)
        self.assertEqual(result.level, "deterministic")
        self.assertEqual(result.status, "needs_revision")
        self.assertFalse(log.semantic_called)
        self.assertEqual(log.final_level, "deterministic")

    def test_clean_draft_earns_full_level_and_completes_run(self):
        sample = _sample_state()
        section = sample["outline"].sections[0]
        heading = render_block(
            "revenue:h", "## Doanh thu",
            sample["evidence_by_id"], sample["calculations_by_id"], sample["evidence_aliases"],
        )
        body = render_block(
            "revenue:b1", "Doanh thu thuần {{Y:E1}} đạt {{E1}}.",
            sample["evidence_by_id"], sample["calculations_by_id"], sample["evidence_aliases"],
        )
        draft = SectionDraft(
            section_id="revenue", outline_version=1, revision=2, blocks=[heading, body]
        )
        view = build_verifier_section_view(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            sample["evidence_aliases"], section,
        )
        # Pure heading block is omitted from view.blocks
        self.assertEqual([b.block_id for b in view.blocks], ["revenue:b1"])
        self.assertEqual(view.blocks[0].claims[0].placeholder_token, "{{E1}}")
        self.assertEqual(view.blocks[0].claims[0].rendered_fragment, "150,0 đồng")
        self.assertIn("Doanh thu thuần", view.blocks[0].claims[0].metric_label)

        fake = FakeVerifierModel([
            SemanticVerificationOutput(
                section_id="revenue",
                block_verdicts=[SemanticBlockVerdict(block_id="revenue:b1", status="passed")],
            ).model_dump_json()
        ])
        result, log = verify_section_full(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            fake, sample["evidence_aliases"], section,
        )
        self.assertEqual(len(fake.requests), 1)
        self.assertEqual(result.level, "full")
        self.assertEqual(result.status, "passed")
        self.assertTrue(log.semantic_called)
        self.assertEqual(log.final_level, "full")
        self.assertEqual(log.token_usage["total_tokens"], 165)

        sample["section_drafts"][("revenue", 2)] = draft
        sample["verification_results"][("revenue", 2)] = result
        sample["verifier_run_logs"] = {"1:revenue:2": log}
        self.assertTrue(can_complete(sample))
        self.assertEqual(complete_run(sample), {"run_status": "completed"})
        restored = state_from_json(state_to_json(sample))
        self.assertEqual(restored["verifier_run_logs"]["1:revenue:2"], log)

    def test_axis1_catches_swapped_metric_label_around_valid_placeholder(self):
        sample = _sample_state()
        section = sample["outline"].sections[0]
        # Template uses valid {{E1}} (Revenue), but prose claims it is Net Income
        swapped = render_block(
            "revenue:b1", "Lợi nhuận sau thuế {{Y:E1}} đạt {{E1}}.",
            sample["evidence_by_id"], sample["calculations_by_id"], sample["evidence_aliases"],
        )
        draft = SectionDraft(
            section_id="revenue", outline_version=1, revision=1, blocks=[swapped]
        )
        # Deterministic verifier passes because Claim.metric comes from E1
        det = verify_section_deterministically(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            sample["evidence_aliases"], section,
        )
        self.assertEqual(det.status, "passed")

        # Semantic Verifier catches the swapped metric label
        fake = FakeVerifierModel([
            SemanticVerificationOutput(
                section_id="revenue",
                block_verdicts=[
                    SemanticBlockVerdict(
                        block_id="revenue:b1",
                        status="failed",
                        findings=[
                            SemanticBlockFinding(
                                block_id="revenue:b1",
                                claim_id="revenue:b1:p1",
                                verdict="contradicted",
                                category="metric_label_mismatch",
                                error_type="unsupported_claim",
                                action="rewrite",
                                severity="error",
                                offending_span="Lợi nhuận sau thuế",
                                reason="E1 là Doanh thu thuần nhưng câu văn ghi là Lợi nhuận sau thuế",
                            )
                        ],
                    )
                ],
            ).model_dump_json()
        ])
        result, log = verify_section_full(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            fake, sample["evidence_aliases"], section,
        )
        self.assertEqual(result.level, "full")
        self.assertEqual(result.status, "needs_revision")
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].claim_id, "revenue:b1:p1")
        self.assertEqual(result.issues[0].error_type, "unsupported_claim")
        self.assertEqual(result.issues[0].action, "rewrite")
        self.assertIn("[metric_label_mismatch]", result.issues[0].reason)
        self.assertIn("Lợi nhuận sau thuế", result.issues[0].reason)
        self.assertEqual(log.semantic_status, "needs_revision")

    def test_axis2_and_axis3_qualitative_and_unclaimed_causal_findings(self):
        sample = _sample_state()
        note = NoteEvidence(
            chunk_id="ABC_2024_chunk_0010",
            doc_id="ABC_2024",
            ticker="ABC",
            fiscal_year=2024,
            scope="consolidated",
            section="NOTES",
            text="Chi phí đi vay được ghi nhận vào chi phí tài chính trong kỳ.",
            source_file="source.pdf",
            physical_pages=[25],
            printed_pages=["21"],
            citation_tag="[Doc_ABC_2024, p.25]",
            rerank_score=0.8,
            topic_roles=["borrowing_policy"],
        )
        sample["evidence_by_id"][note.chunk_id] = EvidenceRecord(
            evidence_id=note.chunk_id,
            kind="note",
            snapshot_version="index-v1",
            payload=note,
        )
        block = DraftBlock(
            block_id="s4:b1",
            template="Công ty có khoản vay ngắn hạn đáo hạn vào cuối kỳ, phản ánh áp lực thanh khoản.",
            text="Công ty có khoản vay ngắn hạn đáo hạn vào cuối kỳ, phản ánh áp lực thanh khoản.",
            claims=[
                Claim(
                    claim_id="s4:b1:c1",
                    claim_type="qualitative",
                    evidence_ids=[note.chunk_id],
                )
            ],
        )
        draft = SectionDraft(section_id="revenue", outline_version=1, revision=1, blocks=[block])
        view = build_verifier_section_view(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            sample["evidence_aliases"], sample["outline"].sections[0],
        )
        self.assertIn(note.chunk_id, view.cited_notes)
        self.assertEqual(view.cited_notes[note.chunk_id].topic_roles, ["borrowing_policy"])

        # Finding with declare_limitation only -> status becomes insufficient_evidence
        fake = FakeVerifierModel([
            SemanticVerificationOutput(
                section_id="revenue",
                block_verdicts=[
                    SemanticBlockVerdict(
                        block_id="s4:b1",
                        status="failed",
                        findings=[
                            SemanticBlockFinding(
                                block_id="s4:b1",
                                claim_id="s4:b1:c1",
                                verdict="extrapolated",
                                category="note_unsupported_or_extrapolated",
                                error_type="missing_evidence",
                                action="declare_limitation",
                                severity="error",
                                offending_span="khoản vay ngắn hạn đáo hạn vào cuối kỳ",
                                reason="Đoạn thuyết minh chỉ nêu chính sách chung, không có kỳ hạn vay",
                            )
                        ],
                    )
                ],
            ).model_dump_json()
        ])
        result, _ = verify_section_semantically(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            fake, sample["evidence_aliases"], sample["outline"].sections[0],
        )
        self.assertEqual(result.level, "full")
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(result.issues[0].action, "declare_limitation")

    def test_fail_closed_on_model_exception_or_invalid_coverage(self):
        sample = _sample_state()
        section = sample["outline"].sections[0]
        body = render_block(
            "revenue:b1", "Doanh thu thuần {{Y:E1}} đạt {{E1}}.",
            sample["evidence_by_id"], sample["calculations_by_id"], sample["evidence_aliases"],
        )
        draft = SectionDraft(section_id="revenue", outline_version=1, revision=1, blocks=[body])

        # Case 1: Model raises RuntimeError -> fail-closed to deterministic
        fake_error = FakeVerifierModel([RuntimeError("API timeout")])
        result1, log1 = verify_section_full(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            fake_error, sample["evidence_aliases"], section,
        )
        self.assertEqual(result1.level, "deterministic")
        self.assertEqual(result1.status, "passed")
        self.assertEqual(log1.final_level, "deterministic")
        self.assertEqual(log1.semantic_status, "model_error")
        self.assertIn("API timeout", log1.error_message)

        # Case 2: Model omits block on attempt 1, then fixes on repair attempt 2
        bad_coverage = SemanticVerificationOutput(
            section_id="revenue", block_verdicts=[]
        ).model_dump_json()
        good_coverage = SemanticVerificationOutput(
            section_id="revenue",
            block_verdicts=[SemanticBlockVerdict(block_id="revenue:b1", status="passed")],
        ).model_dump_json()
        fake_repair = FakeVerifierModel([bad_coverage, good_coverage])
        result2, log2 = verify_section_full(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            fake_repair, sample["evidence_aliases"], section, max_repairs=1,
        )
        self.assertEqual(result2.level, "full")
        self.assertEqual(result2.status, "passed")
        self.assertEqual(log2.attempts, 2)
        self.assertIn("block coverage mismatch", log2.errors_by_attempt[0][0])

        # Case 3: Model returns unknown claim_id on all attempts -> fail-closed
        bad_claim_json = SemanticVerificationOutput(
            section_id="revenue",
            block_verdicts=[
                SemanticBlockVerdict(
                    block_id="revenue:b1",
                    status="failed",
                    findings=[
                        SemanticBlockFinding(
                            block_id="revenue:b1",
                            claim_id="nonexistent_claim_99",
                            verdict="unsupported",
                            category="unclaimed_causal_assertion",
                            error_type="unsupported_claim",
                            reason="Claim ID bịa",
                        )
                    ],
                )
            ],
        ).model_dump_json()
        fake_bad_claim = FakeVerifierModel([bad_claim_json, bad_claim_json])
        result3, log3 = verify_section_full(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            fake_bad_claim, sample["evidence_aliases"], section, max_repairs=1,
        )
        self.assertEqual(result3.level, "deterministic")
        self.assertEqual(log3.final_level, "deterministic")
        self.assertEqual(log3.semantic_status, "model_error")

    def test_graph_completes_when_approved_and_semantic_verifier_passes(self):
        sample = _sample_state()

        def plan(_request):
            return sample["outline"]

        def research(_state):
            return {
                "research_results": sample["research_results"],
                "evidence_by_id": sample["evidence_by_id"],
                "calculations_by_id": sample["calculations_by_id"],
                "evidence_aliases": sample["evidence_aliases"],
            }

        def write(state):
            block = render_block(
                "revenue_block", "Doanh thu thuần {{Y:E1}} đạt {{E1}}.",
                state["evidence_by_id"], state["calculations_by_id"],
                state["evidence_aliases"],
            )
            draft = SectionDraft(
                section_id="revenue", outline_version=state["outline_version"],
                revision=1, blocks=[block],
            )
            return {"section_drafts": {("revenue", 1): draft}}

        fake_verifier = FakeVerifierModel([
            SemanticVerificationOutput(
                section_id="revenue",
                block_verdicts=[SemanticBlockVerdict(block_id="revenue_block", status="passed")],
            ).model_dump_json()
        ])
        graph = build_report_graph(
            plan, research, write,
            verifier_model=fake_verifier,
            require_outline_approval=True,
            checkpointer=InMemorySaver(serde=report_checkpoint_serde()),
        )
        config = {"configurable": {"thread_id": "semantic-verifier-graph-test"}}
        initial = graph.invoke({"request": sample["request"]}, config)
        self.assertEqual(initial["run_status"], "awaiting_approval")
        completed = graph.invoke(
            Command(resume={"action": "approve", "outline_version": 1}), config
        )
        self.assertEqual(completed["run_status"], "completed")
        self.assertTrue(is_run_complete(completed))
        self.assertEqual(
            completed["verification_results"][(1, "revenue", 1)].level, "full"
        )
        self.assertIn("1:revenue:1", completed["verifier_run_logs"])

    def test_shadow_mode_logs_findings_without_blocking_deterministic_pass(self):
        sample = _sample_state()
        section = sample["outline"].sections[0]
        body = render_block(
            "revenue:b1", "Lợi nhuận sau thuế {{Y:E1}} đạt {{E1}}.",
            sample["evidence_by_id"], sample["calculations_by_id"], sample["evidence_aliases"],
        )
        draft = SectionDraft(section_id="revenue", outline_version=1, revision=1, blocks=[body])
        fake = FakeVerifierModel([
            SemanticVerificationOutput(
                section_id="revenue",
                block_verdicts=[
                    SemanticBlockVerdict(
                        block_id="revenue:b1",
                        status="failed",
                        findings=[
                            SemanticBlockFinding(
                                block_id="revenue:b1",
                                claim_id="revenue:b1:p1",
                                verdict="unsupported",
                                category="metric_label_mismatch",
                                error_type="unsupported_claim",
                                action="rewrite",
                                severity="error",
                                offending_span="Lợi nhuận sau thuế",
                                reason="E1 là Doanh thu thuần",
                            )
                        ],
                    )
                ],
            ).model_dump_json()
        ])
        result, log = verify_section_full(
            draft, sample["request"], sample["evidence_by_id"],
            sample["calculations_by_id"], sample["research_results"],
            fake, sample["evidence_aliases"], section, mode="shadow",
        )
        self.assertEqual(result.level, "deterministic")
        self.assertEqual(result.status, "passed")
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].severity, "warning")
        self.assertEqual(log.mode, "shadow")
        self.assertEqual(log.semantic_called, True)
        self.assertEqual(log.semantic_status, "needs_revision")
        self.assertEqual(log.final_level, "deterministic")
        self.assertEqual(len(log.raw_outputs_by_attempt), 1)

    def test_writer_validator_enforces_extremum_and_trend_policy(self):
        from src.agents.citation_recall import scan_template_candidates

        # 1. Valid trend placeholder {{T:...}} passes candidate scan because token is stripped
        hard_ok, _ = scan_template_candidates(
            "Doanh thu thuần ghi nhận xu hướng {{T:revenue:trend:2025}} trong {{P:C:revenue:trend:2025}}."
        )
        self.assertEqual(hard_ok, [])

        # 2. Handwritten trend phrase outside {{T:...}} is rejected as unsupported_trend
        for phrase in ("tăng liên tục", "giảm liên tục", "đi ngang", "diễn biến không đều"):
            hard_err, _ = scan_template_candidates(
                f"Doanh thu thuần {phrase} đạt {{{{E1}}}} vào {{{{Y:E1}}}}."
            )
            self.assertTrue(
                any(item.startswith("unsupported_trend:") for item in hard_err),
                (phrase, hard_err),
            )

        # 3. Extremum terms are rejected as unsupported_extremum
        for extremum in ("đạt đỉnh", "chạm đáy", "cao nhất", "thấp nhất", "kỷ lục"):
            hard_ext, _ = scan_template_candidates(
                f"Tiền mặt trong {{{{Y:E1}}}} đạt {{{{E1}}}} sau khi {extremum} vào năm trước."
            )
            self.assertTrue(
                any(item.startswith("unsupported_extremum:") for item in hard_ext),
                (extremum, hard_ext),
            )


if __name__ == "__main__":
    unittest.main()
