"""Pre-integration rigorous evaluation of the LLM Semantic Verifier (`sv1-v1` frozen).

Addresses the 5 methodological requirements from the smoke test review:
1. Blind manual labeling of 40 real LLM-authored blocks from strictly untouched held-out DEV companies
   (BSR, BWE, DCM, GAS, GEX, QNS) BEFORE calling the Verifier LLM (`blind_labels_locked.json`).
   Includes 36 valid LLM-authored blocks and 4 real subtle LLM Writer errors found in `w4-v3` runs.
2. Implanted subtle errors into 30 real multi-clause LLM-authored blocks (24 from held-out companies
   BSR, BWE, DCM, GAS, GEX, QNS + 6 from HUT/FPT qualitative sections S1, S2, S6, S7), where every
   single block passes `verify_section_deterministically()` 100%.
3. Strictly held-out company evaluation (BSR, BWE, DCM, GAS, GEX, QNS never touched during prompt tuning;
   GMD excluded; `verifier_system.md` frozen at `sv1-v1`).
4. Exact 95% Confidence Intervals (Clopper-Pearson exact binomial 95% CI and Wilson score 95% CI)
   reported alongside point estimates.
5. Evaluation against proposed integration thresholds:
   - Recall on errors implanted into real drafts >= 80% (95% CI lower bound ~ >= 70%)
   - False positive rate on blind-labeled valid real blocks <= 10%
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import truststore

truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.agents.draft_rendering import render_template
from src.agents.state import state_from_json
from src.agents.verification import (
    verify_section_deterministically,
    verify_section_full,
)
from src.agents.verifier_contract import SemanticVerificationOutput
from src.agents.verifier_model import GeminiVerifierModel
from src.schemas.report_schema import DraftBlock, SectionDraft


BLIND_LABELS_LOCKED_PATH = ROOT / "data/report_output/v2_1_fixtures/semantic_verifier_blind_labels_locked.json"
PRE_INTEGRATION_RESULTS_PATH = ROOT / "data/report_output/v2_1_fixtures/semantic_verifier_pre_integration_results.json"
GOLDEN_SET_PATH = ROOT / "configs/semantic_verifier_golden_dev.json"


# =============================================================================
# Statistical Confidence Intervals (Clopper-Pearson Exact & Wilson Score 95% CI)
# =============================================================================

def _beta_cdf(x: float, a: float, b: float) -> float:
    """Regularized incomplete beta function I_x(a, b) via Lentz's continued fraction."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    def _cont_frac(x_val: float, a_val: float, b_val: float) -> float:
        qab = a_val + b_val
        qap = a_val + 1.0
        qam = a_val - 1.0
        c = 1.0
        d = 1.0 - qab * x_val / qap
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        h = d
        for m in range(1, 201):
            m2 = 2 * m
            aa = m * (b_val - m) * x_val / ((qam + m2) * (a_val + m2))
            d = 1.0 + aa * d
            if abs(d) < 1e-30:
                d = 1e-30
            c = 1.0 + aa / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            h *= d * c
            aa = -(a_val + m) * (qab + m) * x_val / ((a_val + m2) * (qap + m2))
            d = 1.0 + aa * d
            if abs(d) < 1e-30:
                d = 1e-30
            c = 1.0 + aa / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            del_h = d * c
            h *= del_h
            if abs(del_h - 1.0) < 1e-12:
                break
        return h

    log_bt = (
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log(1.0 - x)
    )
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _cont_frac(x, a, b) / a
    return 1.0 - bt * _cont_frac(1.0 - x, b, a) / b


def _inv_beta_cdf(p_target: float, a: float, b: float) -> float:
    """Bisection root-finder for I_x(a, b) = p_target."""
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _beta_cdf(mid, a, b) < p_target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def clopper_pearson_ci_95(k: int, n: int) -> tuple[float, float]:
    """Exact Clopper-Pearson 95% confidence interval for binomial proportion k/n."""
    if n <= 0:
        return (0.0, 1.0)
    alpha = 0.05
    lo = 0.0 if k == 0 else _inv_beta_cdf(alpha / 2.0, float(k), float(n - k + 1))
    hi = 1.0 if k == n else _inv_beta_cdf(1.0 - alpha / 2.0, float(k + 1), float(n - k))
    return (round(lo, 4), round(hi, 4))


def wilson_ci_95(k: int, n: int) -> tuple[float, float]:
    """Wilson score 95% confidence interval for binomial proportion k/n."""
    if n <= 0:
        return (0.0, 1.0)
    z = 1.959963984540054
    p = k / n
    denom = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denom
    half_width = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)) / denom
    return (round(max(0.0, center - half_width), 4), round(min(1.0, center + half_width), 4))


def format_rate_with_ci(k: int, n: int) -> dict[str, Any]:
    rate = round(k / n, 4) if n > 0 else 0.0
    cp_lo, cp_hi = clopper_pearson_ci_95(k, n)
    w_lo, w_hi = wilson_ci_95(k, n)
    return {
        "k": k,
        "n": n,
        "point_estimate": rate,
        "point_pct": f"{rate * 100:.2f}%",
        "clopper_pearson_95_ci": [cp_lo, cp_hi],
        "clopper_pearson_95_ci_pct": f"[{cp_lo * 100:.1f}%, {cp_hi * 100:.1f}%]",
        "wilson_95_ci": [w_lo, w_hi],
        "wilson_95_ci_pct": f"[{w_lo * 100:.1f}%, {w_hi * 100:.1f}%]",
    }


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class BlindRealBlockCase:
    case_id: str
    ticker: str
    section_id: str
    source_run: str
    template: str
    rendered_text: str
    q1_metric_matches_number: bool
    q2_year_period_matches: bool
    q3_no_unsupported_cause_or_eval: bool
    human_blind_label: str  # "passed" or "failed"
    blind_rationale: str


@dataclass
class ImplantedRealBlockCase:
    case_id: str
    ticker: str
    section_id: str
    error_category: str  # swapped_metric, swapped_year, reversed_direction, unclaimed_cause, note_extrapolation
    original_template: str
    implanted_template: str
    original_rendered_text: str
    implanted_rendered_text: str
    expected_status: str  # "failed"
    perturbation_rationale: str


# =============================================================================
# State Loading Helpers
# =============================================================================

def load_all_eval_states() -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    for ticker in ("bsr", "bwe", "dcm", "gas", "gex", "qns"):
        path = ROOT / f"data/report_output/{ticker}_writer_eval_research_state.json"
        states[ticker.upper()] = state_from_json(path.read_text(encoding="utf-8"))
    for ticker in ("FPT", "HUT"):
        path = ROOT / f"data/report_output/v2_1_fixtures/qualitative_llm_dev_20261109/full_samples/{ticker}_state.json"
        states[ticker] = state_from_json(path.read_text(encoding="utf-8"))
    return states


def get_section_plan(state: dict[str, Any], section_id: str):
    return next(s for s in state["outline"].sections if s.section_id == section_id)


def get_section_limitations(state: dict[str, Any], section_id: str, target_block_id: str) -> list[Any]:
    drafts = state.get("section_drafts") or {}
    for d in drafts.values():
        if d.section_id == section_id:
            return [lim.model_copy(update={"block_id": target_block_id}) for lim in d.limitations]
    return []


def build_batch_draft_from_templates(
    state: dict[str, Any],
    section_id: str,
    block_items: list[tuple[str, str]],
) -> SectionDraft:
    """Render `(block_id, template)` items into a single SectionDraft."""
    plan = get_section_plan(state, section_id)
    heading = DraftBlock(
        block_id=f"{section_id}:h1",
        template=f"## {plan.title}",
        text=f"## {plan.title}",
        claims=[],
    )
    blocks = [heading]
    for bid, tpl in block_items:
        text, claims = render_template(
            tpl,
            bid,
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["evidence_aliases"],
        )
        blocks.append(DraftBlock(block_id=bid, template=tpl, text=text, claims=claims))
    first_bid = block_items[0][0]
    limitations = get_section_limitations(state, section_id, first_bid)
    return SectionDraft(
        section_id=section_id,
        outline_version=1,
        revision=1,
        blocks=blocks,
        limitations=limitations,
    )


# =============================================================================
# Step 1: 40 Blind-Labeled Real LLM-Authored Blocks from Held-Out Companies
# =============================================================================

def build_blind_real_dataset(states: dict[str, dict[str, Any]]) -> list[BlindRealBlockCase]:
    """Construct 40 real LLM-authored blocks from strictly held-out DEV companies (BSR, BWE, DCM, GAS, GEX, QNS).

    - 36 blocks are genuine LLM-authored blocks from `w4-v5` (S3, S4) and `w4-v4` (S5) across
      BSR, BWE, DCM, GAS, GEX, QNS (6 blocks per company).
    - 4 blocks are genuine LLM-authored blocks from `w4-v3` (`writer_w4_v3_six_dev_s345_eval.json`)
      that passed deterministic verification (`verify_section_deterministically`) yet contain
      real LLM Writer errors discovered during our blind audit of the raw logs!
    """
    raw_specs: list[tuple[str, str, str, str, str, bool, bool, bool, str, str]] = [
        # --- BSR (6 valid from w4-v5/w4-v4 + 1 valid multi-metric from w4-v3) ---
        ("BLIND_BSR_01", "BSR", "S3", "w4-v5:S3:b1",
         "Trong {{P:C:revenue:yoy:2025}}, Doanh thu thuần {{D:revenue:yoy:2025}}, đạt {{E3}}.",
         True, True, True, "passed",
         "Doanh thu thuần năm 2025 so với 2024 tăng 15,08%, đạt 141,6 nghìn tỷ đồng (E3=Doanh thu thuần 2025). Khớp 3 câu hỏi."),
        ("BLIND_BSR_02", "BSR", "S3", "w4-v5:S3:b3",
         "Trong {{P:C:profit_before_tax:difference:2025}}, Lợi nhuận trước thuế {{D:profit_before_tax:difference:2025}}, đạt {{E45}}.",
         True, True, True, "passed",
         "LNTT giai đoạn 2024–2025 tăng 5,3 nghìn tỷ đồng, đạt 6,0 nghìn tỷ đồng (E45=LNTT 2025). Khớp 3 câu hỏi."),
        ("BLIND_BSR_03", "BSR", "S3", "w4-v3:S3:b4",
         "Lợi nhuận sau thuế của công ty đạt {{E29}} vào {{Y:E29}}, tương ứng mức biên lợi nhuận ròng là {{C:net_margin:2025}}.",
         True, True, True, "passed",
         "LNST năm 2025 đạt 5,2 nghìn tỷ đồng (E29), biên lợi nhuận ròng đạt 3,68% (net_margin:2025). Câu ghép 2 chỉ tiêu của cùng năm 2025 hoàn toàn chính xác."),
        ("BLIND_BSR_04", "BSR", "S4", "w4-v5:S4:b2",
         "Tổng tài sản {{P:C:assets:yoy:2025}} {{D:assets:yoy:2025}}, đạt {{E41}}.",
         True, True, True, "passed",
         "Tổng tài sản năm 2025 so với 2024 giảm 3,67%, đạt 85,1 nghìn tỷ đồng (E41=Tổng tài sản 2025). Khớp 3 câu hỏi."),
        ("BLIND_BSR_05", "BSR", "S4", "w4-v5:S4:b3",
         "Trong {{Y:E49}}, vốn chủ sở hữu đạt {{E49}}, chiếm tỷ lệ {{C:equity_to_assets:2025}} trên tổng tài sản.",
         True, True, True, "passed",
         "Năm 2025, VCSH đạt 60,5 nghìn tỷ đồng (E49), chiếm 71,07% tổng tài sản (equity_to_assets:2025). Khớp 3 câu hỏi."),
        ("BLIND_BSR_06", "BSR", "S5", "w4-v4:S5:b1",
         "Lưu chuyển tiền thuần từ hoạt động kinh doanh ghi nhận {{E9}} trong {{Y:E9}}, tương ứng {{D:operating_cash_flow:difference:2025}} {{P:C:operating_cash_flow:difference:2025}}.",
         True, True, True, "passed",
         "CFO năm 2025 đạt 5,3 nghìn tỷ đồng (E9), tăng 5,3 nghìn tỷ đồng giai đoạn 2024–2025. Khớp 3 câu hỏi."),
        ("BLIND_BSR_07", "BSR", "S5", "w4-v4:S5:b3",
         "Lưu chuyển tiền thuần từ hoạt động đầu tư {{D:investing_cash_flow:difference:2025}} {{P:C:investing_cash_flow:difference:2025}}, đạt {{E17}}.",
         True, True, True, "passed",
         "CFI giảm 29,7 nghìn tỷ đồng giai đoạn 2024–2025, đạt -21,7 nghìn tỷ đồng (E17=CFI 2025). Khớp 3 câu hỏi."),

        # --- BWE (6 valid from w4-v5/w4-v4/w4-v3 + 2 real errors from w4-v3 S5) ---
        ("BLIND_BWE_01", "BWE", "S3", "w4-v5:S3:b1",
         "Doanh thu thuần {{P:C:revenue:cagr:2025}} đạt tốc độ tăng trưởng kép hằng năm là {{C:revenue:cagr:2025}} và ghi nhận mức {{E19}} vào {{Y:E19}}.",
         True, True, True, "passed",
         "Doanh thu thuần giai đoạn 2022–2025 đạt CAGR 9,25% và đạt 4,5 nghìn tỷ đồng vào năm 2025 (E19). Khớp 3 câu hỏi."),
        ("BLIND_BWE_02", "BWE", "S3", "w4-v3:S3:b2",
         "Doanh thu thuần ghi nhận xu hướng {{T:revenue:trend:2025}} trong {{P:C:revenue:trend:2025}}, với mức tăng trưởng {{C:revenue:yoy:2025}} trong {{P:C:revenue:yoy:2025}}.",
         True, True, True, "passed",
         "Doanh thu thuần tăng liên tục giai đoạn 2022–2025, tăng 14,75% năm 2025 so với 2024. Khớp 3 câu hỏi."),
        ("BLIND_BWE_03", "BWE", "S4", "w4-v5:S4:b2",
         "Vào {{Y:E28}}, nợ phải trả ghi nhận ở mức {{E28}}, tương ứng tỷ lệ nợ phải trả trên tổng tài sản đạt {{C:debt_to_assets:2025}}.",
         True, True, True, "passed",
         "Năm 2025, nợ phải trả đạt 8,9 nghìn tỷ đồng (E28), tỷ lệ nợ/tổng tài sản đạt 58,48%. Khớp 3 câu hỏi."),
        ("BLIND_BWE_04", "BWE", "S4", "w4-v3:S4:b4",
         "Tiền và các khoản tương đương tiền đạt {{E36}} vào {{Y:E36}} so với mức {{E33}} vào {{Y:E33}}.",
         True, True, True, "passed",
         "Tiền và tương đương tiền đạt 1.061,5 tỷ đồng năm 2025 (E36) so với 275,3 tỷ đồng năm 2022 (E33). Khớp 3 câu hỏi."),
        ("BLIND_BWE_05", "BWE", "S5", "w4-v4:S5:b1",
         "Lưu chuyển tiền thuần từ hoạt động kinh doanh trong {{P:C:operating_cash_flow:difference:2025}} {{D:operating_cash_flow:difference:2025}}, đạt {{E40}}.",
         True, True, True, "passed",
         "CFO giai đoạn 2024–2025 giảm 325,4 tỷ đồng, đạt 745,0 tỷ đồng (E40=CFO 2025). Khớp 3 câu hỏi."),
        ("BLIND_BWE_06", "BWE", "S5", "w4-v4:S5:b4",
         "Lưu chuyển tiền thuần từ hoạt động tài chính trong {{P:C:financing_cash_flow:difference:2025}} {{D:financing_cash_flow:difference:2025}}, đạt {{E44}}.",
         True, True, True, "passed",
         "CFF giai đoạn 2024–2025 tăng 864,6 tỷ đồng, đạt 1.387,3 tỷ đồng (E44=CFF 2025). Khớp 3 câu hỏi."),
        ("BLIND_BWE_ERR01", "BWE", "S5", "w4-v3:S5:b1",
         "Lưu chuyển tiền thuần từ hoạt động kinh doanh trong {{Y:E40}} đạt {{E40}}, giảm {{C:operating_cash_flow:difference:2025}} so với năm trước.",
         False, True, True, "failed",
         "LỖI THẬT CỦA WRITER (w4-v3): Viết 'giảm {{C:operating_cash_flow:difference:2025}}' không có |abs nên thành 'giảm -325,4 tỷ đồng' (phủ định kép làm sai dấu/chiều biến động)."),
        ("BLIND_BWE_ERR02", "BWE", "S5", "w4-v3:S5:b3",
         "Lưu chuyển tiền thuần từ hoạt động đầu tư trong {{Y:E48}} ghi nhận mức âm {{E48}}.",
         False, True, True, "failed",
         "LỖI THẬT CỦA WRITER (w4-v3): Viết 'mức âm {{E48}}' không có |abs nên thành 'mức âm -1,8 nghìn tỷ đồng' (lặp dấu âm sai ngữ nghĩa số học)."),

        # --- DCM (6 valid from w4-v5/w4-v4/w4-v3 + 2 real errors from w4-v3 S3/S5) ---
        ("BLIND_DCM_01", "DCM", "S3", "w4-v5:S3:b2",
         "Trong {{P:C:revenue:yoy:2025}}, Doanh thu thuần {{D:revenue:yoy:2025}}, đạt {{E8}}.",
         True, True, True, "passed",
         "Doanh thu thuần năm 2025 so với 2024 tăng 23,60%, đạt 16,6 nghìn tỷ đồng (E8). Khớp 3 câu hỏi."),
        ("BLIND_DCM_02", "DCM", "S3", "w4-v3:S3:b3",
         "Vào {{Y:E24}}, biên lợi nhuận gộp đạt {{C:gross_margin:2025}}, tương ứng với lợi nhuận gộp là {{E24}}.",
         True, True, True, "passed",
         "Năm 2025, biên lợi nhuận gộp đạt 24,34%, tương ứng lợi nhuận gộp đạt 4,0 nghìn tỷ đồng (E24). Khớp 3 câu hỏi."),
        ("BLIND_DCM_03", "DCM", "S4", "w4-v5:S4:b2",
         "Tỷ lệ nợ phải trả trên tổng tài sản {{P:C:debt_to_assets:2025}} ghi nhận ở mức {{C:debt_to_assets:2025}} với nợ phải trả đạt {{E3}}.",
         True, True, True, "passed",
         "Tỷ lệ nợ/tổng tài sản năm 2025 đạt 38,82% với nợ phải trả đạt 6,8 nghìn tỷ đồng (E3). Khớp 3 câu hỏi."),
        ("BLIND_DCM_04", "DCM", "S4", "w4-v5:S4:b3",
         "Tỷ lệ vốn chủ sở hữu trên tổng tài sản {{P:C:equity_to_assets:2025}} ghi nhận mức {{C:equity_to_assets:2025}} khi vốn chủ sở hữu đạt {{E4}}.",
         True, True, True, "passed",
         "Tỷ lệ VCSH/tổng tài sản năm 2025 đạt 61,18% khi VCSH đạt 10,8 nghìn tỷ đồng (E4). Khớp 3 câu hỏi."),
        ("BLIND_DCM_05", "DCM", "S5", "w4-v4:S5:b2",
         "Tỷ lệ lưu chuyển tiền thuần từ hoạt động kinh doanh trên lợi nhuận sau thuế trong {{P:C:cfo_to_net_income:2025}} đạt {{C:cfo_to_net_income:2025}} so với mức {{C:cfo_to_net_income:2024}} trong {{P:C:cfo_to_net_income:2024}}.",
         True, True, True, "passed",
         "Tỷ lệ CFO/LNST năm 2025 đạt -39,55% so với mức 5,43% trong năm 2024. Khớp 3 câu hỏi."),
        ("BLIND_DCM_06", "DCM", "S5", "w4-v4:S5:b4",
         "Lưu chuyển tiền thuần từ hoạt động tài chính trong {{P:C:financing_cash_flow:difference:2025}} {{D:financing_cash_flow:difference:2025}}, ghi nhận ở mức {{E16}}.",
         True, True, True, "passed",
         "CFF giai đoạn 2024–2025 tăng 497,4 tỷ đồng, ghi nhận ở mức -127,4 tỷ đồng (E16). Khớp 3 câu hỏi."),
        ("BLIND_DCM_ERR03", "DCM", "S3", "w4-v3:S3:b4",
         "Lợi nhuận sau thuế của cổ đông công ty mẹ trong {{P:C:net_income:difference:2025}} tăng {{C:net_income:difference:2025}} lên mức {{E28}} vào {{Y:E28}}.",
         False, True, True, "failed",
         "LỖI THẬT CỦA WRITER (w4-v3): Chủ ngữ là 'Lợi nhuận sau thuế của cổ đông công ty mẹ' (code 61, E28), nhưng mức tăng 533,8 tỷ đồng lại lấy từ {{C:net_income:difference:2025}} là Lợi nhuận sau thuế hợp nhất (code 60, từ E31 lên E32). Lẫn lộn hai chỉ tiêu khác nhau trong cùng một câu."),
        ("BLIND_DCM_ERR04", "DCM", "S5", "w4-v3:S5:b1",
         "Lưu chuyển tiền thuần từ hoạt động kinh doanh giảm {{C:operating_cash_flow:difference:2025}} trong {{P:C:operating_cash_flow:difference:2025}}.",
         False, True, True, "failed",
         "LỖI THẬT CỦA WRITER (w4-v3): Viết 'giảm {{C:operating_cash_flow:difference:2025}}' không có |abs nên thành 'giảm -853,4 tỷ đồng' (phủ định kép làm sai dấu/chiều biến động)."),

        # --- GAS (6 valid from w4-v5/w4-v4/w4-v3) ---
        ("BLIND_GAS_01", "GAS", "S3", "w4-v3:S3:b1",
         "Doanh thu thuần {{P:C:revenue:cagr:2025}} đạt tốc độ tăng trưởng kép hằng năm là {{C:revenue:cagr:2025}}, đạt {{E12}} vào {{Y:E12}}.",
         True, True, True, "passed",
         "Doanh thu thuần giai đoạn 2022–2025 đạt CAGR 10,29%, đạt 135,1 nghìn tỷ đồng vào năm 2025 (E12). Khớp 3 câu hỏi."),
        ("BLIND_GAS_02", "GAS", "S3", "w4-v5:S3:b4",
         "Lợi nhuận sau thuế {{P:C:net_income:difference:2025}} {{D:net_income:difference:2025}}, đạt {{E7}}.",
         True, True, True, "passed",
         "LNST giai đoạn 2024–2025 tăng 981,5 tỷ đồng, đạt 11.571,6 tỷ đồng (E7=LNST 2025). Khớp 3 câu hỏi."),
        ("BLIND_GAS_03", "GAS", "S4", "w4-v5:S4:b2",
         "Trong {{Y:E35}}, nợ phải trả ghi nhận ở mức {{E35}}, tương ứng tỷ lệ nợ phải trả trên tổng tài sản là {{C:debt_to_assets:2025}}.",
         True, True, True, "passed",
         "Năm 2025, nợ phải trả đạt 25,9 nghìn tỷ đồng (E35), tỷ lệ nợ/tổng tài sản là 27,70%. Khớp 3 câu hỏi."),
        ("BLIND_GAS_04", "GAS", "S4", "w4-v3:S4:b4",
         "Tiền và các khoản tương đương tiền đạt {{E42}} vào {{Y:E42}} so với {{E41}} vào {{Y:E41}}.",
         True, True, True, "passed",
         "Tiền và tương đương tiền đạt 6,9 nghìn tỷ đồng năm 2025 (E42) so với 5,6 nghìn tỷ đồng năm 2024 (E41). Khớp 3 câu hỏi."),
        ("BLIND_GAS_05", "GAS", "S5", "w4-v4:S5:b1",
         "Lưu chuyển tiền thuần từ hoạt động kinh doanh {{P:C:operating_cash_flow:difference:2025}} {{D:operating_cash_flow:difference:2025}}, đạt {{E27}} trong {{Y:E27}}.",
         True, True, True, "passed",
         "CFO giai đoạn 2024–2025 tăng 4,0 nghìn tỷ đồng, đạt 13,0 nghìn tỷ đồng năm 2025 (E27). Khớp 3 câu hỏi."),
        ("BLIND_GAS_06", "GAS", "S5", "w4-v4:S5:b3",
         "Lưu chuyển tiền thuần từ hoạt động đầu tư {{P:C:investing_cash_flow:difference:2025}} {{D:investing_cash_flow:difference:2025}}, ghi nhận mức {{E20}} vào {{Y:E20}}.",
         True, True, True, "passed",
         "CFI giai đoạn 2024–2025 giảm 13,9 nghìn tỷ đồng, ghi nhận -6,5 nghìn tỷ đồng năm 2025 (E20). Khớp 3 câu hỏi."),

        # --- GEX (6 valid from w4-v5/w4-v4/w4-v3) ---
        ("BLIND_GEX_01", "GEX", "S3", "w4-v5:S3:b1",
         "Doanh thu thuần {{P:C:revenue:cagr:2025}} đạt tốc độ tăng trưởng kép hằng năm là {{C:revenue:cagr:2025}}, với quy mô đạt {{E17}} vào {{Y:E17}}.",
         True, True, True, "passed",
         "Doanh thu thuần giai đoạn 2022–2025 đạt CAGR 7,18%, quy mô đạt 39,5 nghìn tỷ đồng năm 2025 (E17). Khớp 3 câu hỏi."),
        ("BLIND_GEX_02", "GEX", "S3", "w4-v5:S3:b2",
         "Doanh thu thuần {{P:C:revenue:yoy:2025}} {{D:revenue:yoy:2025}}, sau khi {{D:revenue:yoy:2024}} trong {{P:C:revenue:yoy:2024}}.",
         True, True, True, "passed",
         "Doanh thu thuần năm 2025 so với 2024 tăng 17,07%, sau khi tăng 12,52% trong năm 2024 so với 2023. Khớp 3 câu hỏi."),
        ("BLIND_GEX_03", "GEX", "S4", "w4-v3:S4:b2",
         "Vào {{Y:E43}}, Nợ phải trả đạt {{E43}}, đưa tỷ lệ nợ phải trả trên tổng tài sản lên mức {{C:debt_to_assets:2025}} trong {{P:C:debt_to_assets:2025}}.",
         True, True, True, "passed",
         "Năm 2025, Nợ phải trả đạt 43,4 nghìn tỷ đồng (E43), tỷ lệ nợ/tổng tài sản ở mức 59,00% trong năm 2025. Khớp 3 câu hỏi."),
        ("BLIND_GEX_04", "GEX", "S4", "w4-v3:S4:b4",
         "Tiền và các khoản tương đương tiền đạt {{E19}} vào {{Y:E19}} so với mức {{E45}} vào {{Y:E45}}.",
         True, True, True, "passed",
         "Tiền và tương đương tiền đạt 8,7 nghìn tỷ đồng năm 2025 (E19) so với 4,1 nghìn tỷ đồng năm 2024 (E45). Khớp 3 câu hỏi."),
        ("BLIND_GEX_05", "GEX", "S5", "w4-v4:S5:b1",
         "Lưu chuyển tiền thuần từ hoạt động kinh doanh đạt {{E20}} trong {{Y:E20}}, {{D:operating_cash_flow:difference:2025}} {{P:C:operating_cash_flow:difference:2025}}.",
         True, True, True, "passed",
         "CFO đạt 546,2 tỷ đồng năm 2025 (E20), giảm 1.963,0 tỷ đồng giai đoạn 2024–2025. Khớp 3 câu hỏi."),
        ("BLIND_GEX_06", "GEX", "S5", "w4-v3:S5:b2_att0",
         "Tỷ lệ lưu chuyển tiền thuần từ hoạt động kinh doanh trên lợi nhuận sau thuế ghi nhận mức {{C:cfo_to_net_income:2025}} trong {{P:C:cfo_to_net_income:2025}}, giảm so với mức {{C:cfo_to_net_income:2024}} trong {{P:C:cfo_to_net_income:2024}}.",
         True, True, True, "passed",
         "Tỷ lệ CFO/LNST đạt 18,48% năm 2025, giảm so với 94,00% năm 2024 (18,48% < 94,00% nên chữ 'giảm so với' hoàn toàn đúng). Khớp 3 câu hỏi."),

        # --- QNS (5 valid from w4-v5/w4-v4/w4-v3) ---
        ("BLIND_QNS_01", "QNS", "S3", "w4-v5:S3:b1",
         "Doanh thu thuần {{P:C:revenue:cagr:2025}} đạt tốc độ tăng trưởng kép hằng năm là {{C:revenue:cagr:2025}}, từ {{E16}} vào {{Y:E16}} đạt {{E19}} vào {{Y:E19}}.",
         True, True, True, "passed",
         "Doanh thu thuần giai đoạn 2022–2025 đạt CAGR 8,61%, từ 8,3 nghìn tỷ đồng năm 2022 (E16) đạt 10,6 nghìn tỷ đồng năm 2025 (E19). Khớp 3 câu hỏi."),
        ("BLIND_QNS_02", "QNS", "S3", "w4-v5:S3:b4",
         "Lợi nhuận sau thuế {{P:C:net_income:difference:2025}} {{D:net_income:difference:2025}}, đạt {{E11}}.",
         True, True, True, "passed",
         "LNST giai đoạn 2024–2025 giảm 460,2 tỷ đồng, đạt 1.916,5 tỷ đồng (E11=LNST 2025). Khớp 3 câu hỏi."),
        ("BLIND_QNS_03", "QNS", "S4", "w4-v5:S4:b3",
         "Tỷ lệ vốn chủ sở hữu trên tổng tài sản vào {{P:C:equity_to_assets:2025}} đạt {{C:equity_to_assets:2025}} tương ứng quy mô vốn chủ sở hữu là {{E29}}.",
         True, True, True, "passed",
         "Tỷ lệ VCSH/tổng tài sản năm 2025 đạt 74,19%, tương ứng quy mô VCSH đạt 10,6 nghìn tỷ đồng (E29). Khớp 3 câu hỏi."),
        ("BLIND_QNS_04", "QNS", "S4", "w4-v3:S4:b4",
         "Tiền và các khoản tương đương tiền trong {{Y:E32}} đạt {{E32}} sau khi đạt đỉnh {{E31}} vào {{Y:E31}}.",
         True, True, True, "passed",
         "Tiền và tương đương tiền năm 2025 đạt 272,2 tỷ đồng (E32) sau khi đạt đỉnh 539,2 tỷ đồng vào năm 2024 (E31; các năm 2022=202,6 tỷ, 2023=289,5 tỷ, 2024=539,2 tỷ, 2025=272,2 tỷ nên 2024 đúng là đỉnh). Khớp 3 câu hỏi."),
        ("BLIND_QNS_05", "QNS", "S5", "w4-v4:S5:b2",
         "Lưu chuyển tiền thuần từ hoạt động đầu tư ở mức {{E43}} trong {{Y:E43}}, tương ứng biến động {{D:investing_cash_flow:difference:2025}} trong {{P:C:investing_cash_flow:difference:2025}}.",
         True, True, True, "passed",
         "CFI ở mức -946,9 tỷ đồng năm 2025 (E43), tương ứng biến động tăng 204,0 tỷ đồng giai đoạn 2024–2025 (từ -1.151,0 tỷ lên -946,9 tỷ). Khớp 3 câu hỏi."),
    ]

    cases: list[BlindRealBlockCase] = []
    for cid, ticker, sid, src, tpl, q1, q2, q3, label, rationale in raw_specs:
        state = states[ticker]
        text, _ = render_template(
            tpl,
            cid,
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["evidence_aliases"],
        )
        cases.append(
            BlindRealBlockCase(
                case_id=cid,
                ticker=ticker,
                section_id=sid,
                source_run=src,
                template=tpl,
                rendered_text=text,
                q1_metric_matches_number=q1,
                q2_year_period_matches=q2,
                q3_no_unsupported_cause_or_eval=q3,
                human_blind_label=label,
                blind_rationale=rationale,
            )
        )
    return cases


# =============================================================================
# Step 2: 30 Subtle Errors Implanted into Real LLM-Authored Blocks
# =============================================================================

def build_implanted_real_dataset(states: dict[str, dict[str, Any]]) -> list[ImplantedRealBlockCase]:
    """Take 30 real multi-clause LLM-authored blocks and implant one subtle semantic flaw into each.

    Breakdown across 5 subtle error categories (6 cases per category = 30 cases):
    - `swapped_metric` (6 cases on held-out BSR, BWE, DCM, GAS, GEX, QNS):
      In a multi-clause/multi-placeholder real LLM sentence, keep one placeholder right and subtly
      change the metric name of the second clause (or confuse Gross vs Net Margin, PBT vs Net Income,
      Parent vs Consolidated Net Income, Debt vs Equity).
    - `swapped_year` (6 cases on held-out BSR, BWE, DCM, GAS, GEX, QNS):
      In a multi-clause real LLM sentence, keep the YoY/CAGR/difference clause intact, but pair a
      2024/2023 fact value with a 2025 year placeholder (or vice versa) in the second clause.
    - `reversed_direction` (6 cases on held-out BSR, BWE, DCM, GAS, GEX, QNS):
      In a multi-clause real LLM sentence, subtly invert the comparative verb ('tăng' <-> 'giảm',
      'cao hơn' <-> 'thấp hơn', 'cải thiện' when difference is negative) while using `{{C:...}}`
      placeholders that pass deterministic verification.
    - `unclaimed_cause` (6 cases on held-out BSR, BWE, DCM, GAS, GEX, QNS):
      Take a valid multi-clause real LLM sentence and append a plausible-sounding corporate/financial
      rationale (e.g., 'nhờ tối ưu hóa chi phí vận hành', 'do đẩy mạnh giải ngân đầu tư dự án',
      'nhờ thu hồi công nợ khách hàng') that has NO supporting note excerpt in the section.
    - `note_extrapolation` (6 cases on real qualitative w6-v1 blocks from HUT and FPT):
      Take a real `w6-v1` qualitative block (which cites a real note excerpt `{{N:...}}`) and subtly
      over-claim in the observation sentence (e.g., turning a general accounting policy into a claim
      that 100% of contracts completed in 2025, or turning an emphasis-of-matter into a qualified
      audit opinion, or claiming all land use rights are indefinite).
    """
    specs: list[tuple[str, str, str, str, str, str, str]] = [
        # ---------------------------------------------------------------------
        # Category 1: Subtle Swapped Metric in Multi-Clause Real Sentences (6)
        # ---------------------------------------------------------------------
        (
            "IMP_M01", "BSR", "S3", "swapped_metric",
            "Lợi nhuận sau thuế của công ty đạt {{E29}} vào {{Y:E29}}, tương ứng mức biên lợi nhuận ròng là {{C:net_margin:2025}}.",
            "Lợi nhuận sau thuế của công ty đạt {{E29}} vào {{Y:E29}}, tương ứng mức biên lợi nhuận gộp là {{C:net_margin:2025}}.",
            "Mệnh đề đầu đúng (LNST đạt E29 năm 2025), nhưng mệnh đề sau gọi {{C:net_margin:2025}} (Biên lợi nhuận ròng 3,68%) là 'biên lợi nhuận gộp'.",
        ),
        (
            "IMP_M02", "BWE", "S3", "swapped_metric",
            "Lợi nhuận trước thuế {{P:C:profit_before_tax:difference:2025}} {{D:profit_before_tax:difference:2025}}, đạt {{E7}}.",
            "Lợi nhuận trước thuế {{P:C:profit_before_tax:difference:2025}} {{D:profit_before_tax:difference:2025}}, qua đó lợi nhuận sau thuế đạt {{E7}}.",
            "Mệnh đề đầu đúng (LNTT giai đoạn 2024–2025 tăng 445,0 tỷ đồng), nhưng mệnh đề sau gán {{E7}} (LNTT 1.181,7 tỷ đồng) cho 'lợi nhuận sau thuế'.",
        ),
        (
            "IMP_M03", "DCM", "S3", "swapped_metric",
            "Vào {{Y:E24}}, biên lợi nhuận gộp đạt {{C:gross_margin:2025}}, tương ứng với lợi nhuận gộp là {{E24}}.",
            "Vào {{Y:E24}}, biên lợi nhuận gộp đạt {{C:gross_margin:2025}}, tương ứng với lợi nhuận trước thuế là {{E24}}.",
            "Mệnh đề đầu đúng (biên lợi nhuận gộp đạt 24,34% năm 2025), nhưng mệnh đề sau gán {{E24}} (Lợi nhuận gộp 4,0 nghìn tỷ đồng) cho 'lợi nhuận trước thuế'.",
        ),
        (
            "IMP_M04", "GAS", "S4", "swapped_metric",
            "Trong {{Y:E35}}, nợ phải trả ghi nhận ở mức {{E35}}, tương ứng tỷ lệ nợ phải trả trên tổng tài sản là {{C:debt_to_assets:2025}}.",
            "Trong {{Y:E35}}, nợ phải trả ghi nhận ở mức {{E35}}, tương ứng tỷ lệ vốn chủ sở hữu trên tổng tài sản là {{C:debt_to_assets:2025}}.",
            "Mệnh đề đầu đúng (nợ phải trả đạt E35 năm 2025), nhưng mệnh đề sau gọi {{C:debt_to_assets:2025}} (tỷ lệ nợ/tổng tài sản 27,70%) là 'tỷ lệ vốn chủ sở hữu trên tổng tài sản'.",
        ),
        (
            "IMP_M05", "GEX", "S4", "swapped_metric",
            "Vốn chủ sở hữu đạt mức {{E14}} vào {{Y:E14}}, chiếm tỷ trọng {{C:equity_to_assets:2025}} trên tổng tài sản trong {{P:C:equity_to_assets:2025}}.",
            "Vốn chủ sở hữu đạt mức {{E43}} vào {{Y:E14}}, chiếm tỷ trọng {{C:equity_to_assets:2025}} trên tổng tài sản trong {{P:C:equity_to_assets:2025}}.",
            "Mệnh đề sau đúng (tỷ trọng VCSH/tổng tài sản đạt 41,00% năm 2025), nhưng số tiền quy mô VCSH lại lấy {{E43}} (Nợ phải trả 43,4 nghìn tỷ đồng) thay vì E14 (30,2 nghìn tỷ đồng).",
        ),
        (
            "IMP_M06", "QNS", "S5", "swapped_metric",
            "Lưu chuyển tiền thuần từ hoạt động đầu tư ở mức {{E43}} trong {{Y:E43}}, tương ứng biến động {{D:investing_cash_flow:difference:2025}} trong {{P:C:investing_cash_flow:difference:2025}}.",
            "Lưu chuyển tiền thuần từ hoạt động đầu tư ở mức {{E39}} trong {{Y:E43}}, tương ứng biến động {{D:investing_cash_flow:difference:2025}} trong {{P:C:investing_cash_flow:difference:2025}}.",
            "Mệnh đề biến động sau đúng (CFI tăng 204,0 tỷ đồng giai đoạn 2024–2025), nhưng giá trị năm 2025 ở mệnh đề đầu lại lấy {{E39}} (Lưu chuyển tiền thuần từ HĐ tài chính -1.425,7 tỷ đồng) thay vì E43 (-946,9 tỷ đồng).",
        ),

        # ---------------------------------------------------------------------
        # Category 2: Subtle Swapped Year/Period in Multi-Clause Sentences (6)
        # ---------------------------------------------------------------------
        (
            "IMP_Y01", "BSR", "S3", "swapped_year",
            "Doanh thu thuần đạt {{E3}} vào {{Y:E3}}, ghi nhận mức tăng {{C:revenue:yoy:2025}} {{P:C:revenue:yoy:2025}}.",
            "Doanh thu thuần đạt {{E2}} vào {{Y:E3}}, ghi nhận mức tăng {{C:revenue:yoy:2025}} {{P:C:revenue:yoy:2025}}.",
            "Ghép giá trị Doanh thu thuần năm 2024 ({{E2}} = 123,0 nghìn tỷ đồng) với nhãn thời gian năm 2025 ({{Y:E3}}) trong câu có mệnh đề YoY 2025 đúng.",
        ),
        (
            "IMP_Y02", "BWE", "S4", "swapped_year",
            "Tiền và các khoản tương đương tiền đạt {{E36}} vào {{Y:E36}} so với mức {{E33}} vào {{Y:E33}}.",
            "Tiền và các khoản tương đương tiền đạt {{E36}} vào {{Y:E36}} so với mức {{E35}} vào {{Y:E33}}.",
            "Mệnh đề đầu đúng (1.061,5 tỷ đồng vào năm 2025), nhưng mệnh đề so sánh ghép số dư Tiền năm 2024 ({{E35}} = 1.006,7 tỷ đồng) với nhãn thời gian năm 2022 ({{Y:E33}}).",
        ),
        (
            "IMP_Y03", "DCM", "S4", "swapped_year",
            "Tổng tài sản đạt {{E43}} vào {{Y:E43}}, tăng {{C:assets:yoy:2025}} trong {{P:C:assets:yoy:2025}}.",
            "Tổng tài sản đạt {{E42}} vào {{Y:E43}}, tăng {{C:assets:yoy:2025}} trong {{P:C:assets:yoy:2025}}.",
            "Mệnh đề tăng trưởng YoY 2025 đúng (+12,17%), nhưng quy mô Tổng tài sản vào năm 2025 ({{Y:E43}}) lại lấy số liệu năm 2024 ({{E42}} = 15,7 nghìn tỷ đồng thay vì 17,6 nghìn tỷ đồng).",
        ),
        (
            "IMP_Y04", "GAS", "S4", "swapped_year",
            "Tiền và các khoản tương đương tiền đạt {{E42}} vào {{Y:E42}} so với {{E41}} vào {{Y:E41}}.",
            "Tiền và các khoản tương đương tiền đạt {{E42}} vào {{Y:E42}} so với {{E39}} vào {{Y:E41}}.",
            "Mệnh đề đầu đúng (6,9 nghìn tỷ đồng năm 2025), nhưng mệnh đề sau ghép số dư Tiền năm 2022 ({{E39}} = 10,5 nghìn tỷ đồng) với nhãn năm 2024 ({{Y:E41}}).",
        ),
        (
            "IMP_Y05", "GEX", "S3", "swapped_year",
            "Doanh thu thuần {{P:C:revenue:yoy:2025}} {{D:revenue:yoy:2025}}, sau khi {{D:revenue:yoy:2024}} trong {{P:C:revenue:yoy:2024}}.",
            "Doanh thu thuần {{P:C:revenue:yoy:2025}} {{D:revenue:yoy:2024}}, sau khi {{D:revenue:yoy:2025}} trong {{P:C:revenue:yoy:2024}}.",
            "Đảo chéo tốc độ tăng trưởng YoY của hai kỳ liên tiếp: gán mức tăng 12,52% (của năm 2024 so với 2023) cho kỳ 2025 so với 2024, và gán mức tăng 17,07% (của năm 2025 so với 2024) cho kỳ 2024 so với 2023.",
        ),
        (
            "IMP_Y06", "QNS", "S3", "swapped_year",
            "Doanh thu thuần {{P:C:revenue:cagr:2025}} đạt tốc độ tăng trưởng kép hằng năm là {{C:revenue:cagr:2025}}, từ {{E16}} vào {{Y:E16}} đạt {{E19}} vào {{Y:E19}}.",
            "Doanh thu thuần {{P:C:revenue:cagr:2025}} đạt tốc độ tăng trưởng kép hằng năm là {{C:revenue:cagr:2025}}, từ {{E17}} vào {{Y:E16}} đạt {{E19}} vào {{Y:E19}}.",
            "CAGR (8,61%) và số cuối kỳ 2025 (E19 = 10,6 nghìn tỷ đồng) đúng, nhưng mốc đầu kỳ vào năm 2022 ({{Y:E16}}) lại lấy số doanh thu năm 2023 ({{E17}} = 10,0 nghìn tỷ đồng thay vì 8,3 nghìn tỷ đồng).",
        ),

        # ---------------------------------------------------------------------
        # Category 3: Subtle Reversed Direction / Comparison in Real Sentences (6)
        # ---------------------------------------------------------------------
        (
            "IMP_D01", "BSR", "S4", "reversed_direction",
            "Tổng tài sản đạt {{E41}} vào {{Y:E41}}, ghi nhận mức biến động {{C:assets:yoy:2025}} trong {{P:C:assets:yoy:2025}}.",
            "Tổng tài sản đạt {{E41}} vào {{Y:E41}}, ghi nhận mức mở rộng {{C:assets:yoy:2025}} trong {{P:C:assets:yoy:2025}}.",
            "Tổng tài sản năm 2025 của BSR thực tế giảm (-3,67%), nhưng câu viết là 'ghi nhận mức mở rộng -3,67%' (ngược chiều biến động).",
        ),
        (
            "IMP_D02", "BWE", "S4", "reversed_direction",
            "Tiền và các khoản tương đương tiền đạt {{E36}} vào {{Y:E36}} so với mức {{E33}} vào {{Y:E33}}.",
            "Tiền và các khoản tương đương tiền thu hẹp về mức {{E36}} vào {{Y:E36}} so với mức {{E33}} vào {{Y:E33}}.",
            "Tiền năm 2025 đạt 1.061,5 tỷ đồng (E36), cao gấp gần 4 lần mức 275,3 tỷ đồng năm 2022 (E33), nhưng câu lại mô tả là 'thu hẹp về mức 1.061,5 tỷ đồng so với mức 275,3 tỷ đồng'.",
        ),
        (
            "IMP_D03", "DCM", "S5", "reversed_direction",
            "Tỷ lệ lưu chuyển tiền thuần từ hoạt động kinh doanh trên lợi nhuận sau thuế trong {{P:C:cfo_to_net_income:2025}} đạt {{C:cfo_to_net_income:2025}} so với mức {{C:cfo_to_net_income:2024}} trong {{P:C:cfo_to_net_income:2024}}.",
            "Tỷ lệ lưu chuyển tiền thuần từ hoạt động kinh doanh trên lợi nhuận sau thuế trong {{P:C:cfo_to_net_income:2025}} cải thiện lên mức {{C:cfo_to_net_income:2025}} so với mức {{C:cfo_to_net_income:2024}} trong {{P:C:cfo_to_net_income:2024}}.",
            "Tỷ lệ CFO/LNST giảm mạnh từ dương 5,43% (năm 2024) xuống âm -39,55% (năm 2025), nhưng câu lại viết 'cải thiện lên mức -39,55% so với mức 5,43%'.",
        ),
        (
            "IMP_D04", "GAS", "S4", "reversed_direction",
            "Tiền và các khoản tương đương tiền đạt {{E42}} vào {{Y:E42}} so với {{E41}} vào {{Y:E41}}.",
            "Tiền và các khoản tương đương tiền sụt giảm xuống {{E42}} vào {{Y:E42}} so với {{E41}} vào {{Y:E41}}.",
            "Tiền năm 2025 đạt 6,9 nghìn tỷ đồng (E42), tăng so với mức 5,6 nghìn tỷ đồng năm 2024 (E41), nhưng câu lại viết 'sụt giảm xuống 6,9 nghìn tỷ đồng vào năm 2025 so với 5,6 nghìn tỷ đồng vào năm 2024'.",
        ),
        (
            "IMP_D05", "GEX", "S5", "reversed_direction",
            "Tỷ lệ lưu chuyển tiền thuần từ hoạt động kinh doanh trên lợi nhuận sau thuế ghi nhận mức {{C:cfo_to_net_income:2025}} trong {{P:C:cfo_to_net_income:2025}}, giảm so với mức {{C:cfo_to_net_income:2024}} trong {{P:C:cfo_to_net_income:2024}}.",
            "Tỷ lệ lưu chuyển tiền thuần từ hoạt động kinh doanh trên lợi nhuận sau thuế ghi nhận mức {{C:cfo_to_net_income:2025}} trong {{P:C:cfo_to_net_income:2025}}, tăng cao hơn so với mức {{C:cfo_to_net_income:2024}} trong {{P:C:cfo_to_net_income:2024}}.",
            "Tỷ lệ CFO/LNST năm 2025 là 18,48%, thấp hơn nhiều so với 94,00% năm 2024, nhưng câu lại viết 'tăng cao hơn so với mức 94,00%'.",
        ),
        (
            "IMP_D06", "QNS", "S3", "reversed_direction",
            "Lợi nhuận trước thuế trong {{P:C:profit_before_tax:difference:2025}} biến động {{C:profit_before_tax:difference:2025}}, đạt {{E7}} vào {{Y:E7}}.",
            "Lợi nhuận trước thuế trong {{P:C:profit_before_tax:difference:2025}} tăng trưởng {{C:profit_before_tax:difference:2025}}, đạt {{E7}} vào {{Y:E7}}.",
            "Chênh lệch LNTT giai đoạn 2024–2025 của QNS là âm (-432,8 tỷ đồng, giảm từ 2.645,2 tỷ xuống 2.212,4 tỷ), nhưng câu lại viết 'tăng trưởng -432,8 tỷ đồng'.",
        ),

        # ---------------------------------------------------------------------
        # Category 4: Subtle Unsupported Cause/Evaluation in Real Sentences (6)
        # ---------------------------------------------------------------------
        (
            "IMP_C01", "BSR", "S3", "unclaimed_cause",
            "Trong {{P:C:revenue:yoy:2025}}, Doanh thu thuần {{D:revenue:yoy:2025}}, đạt {{E3}}.",
            "Trong {{P:C:revenue:yoy:2025}}, Doanh thu thuần {{D:revenue:yoy:2025}}, đạt {{E3}} nhờ sản lượng tiêu thụ xăng dầu nội địa và biên lợi nhuận lọc dầu phục hồi.",
            "Cấy nguyên nhân 'nhờ sản lượng tiêu thụ xăng dầu nội địa và biên lợi nhuận lọc dầu phục hồi' không có trong evidence của S3.",
        ),
        (
            "IMP_C02", "BWE", "S5", "unclaimed_cause",
            "Lưu chuyển tiền thuần từ hoạt động đầu tư trong {{P:C:investing_cash_flow:difference:2025}} {{D:investing_cash_flow:difference:2025}}, xuống mức {{E48}}.",
            "Lưu chuyển tiền thuần từ hoạt động đầu tư trong {{P:C:investing_cash_flow:difference:2025}} {{D:investing_cash_flow:difference:2025}}, xuống mức {{E48}} do doanh nghiệp đẩy mạnh giải ngân mở rộng mạng lưới cấp nước.",
            "Cấy nguyên nhân 'do doanh nghiệp đẩy mạnh giải ngân mở rộng mạng lưới cấp nước' không có thuyết minh hỗ trợ trong S5.",
        ),
        (
            "IMP_C03", "DCM", "S3", "unclaimed_cause",
            "Lợi nhuận trước thuế {{P:C:profit_before_tax:difference:2025}} {{D:profit_before_tax:difference:2025}}, đạt {{E46}}.",
            "Lợi nhuận trước thuế {{P:C:profit_before_tax:difference:2025}} {{D:profit_before_tax:difference:2025}}, đạt {{E46}} nhờ giá bán phân đạm bình quân tăng và tối ưu chi phí khí đầu vào.",
            "Cấy nguyên nhân 'nhờ giá bán phân đạm bình quân tăng và tối ưu chi phí khí đầu vào' không có trong bằng chứng S3.",
        ),
        (
            "IMP_C04", "GAS", "S5", "unclaimed_cause",
            "Lưu chuyển tiền thuần từ hoạt động kinh doanh {{P:C:operating_cash_flow:difference:2025}} {{D:operating_cash_flow:difference:2025}}, đạt {{E27}} trong {{Y:E27}}.",
            "Lưu chuyển tiền thuần từ hoạt động kinh doanh {{P:C:operating_cash_flow:difference:2025}} {{D:operating_cash_flow:difference:2025}}, đạt {{E27}} trong {{Y:E27}} nhờ tiến độ thu hồi công nợ từ các hộ tiêu thụ khí cải thiện.",
            "Cấy nguyên nhân 'nhờ tiến độ thu hồi công nợ từ các hộ tiêu thụ khí cải thiện' không có trong bằng chứng S5.",
        ),
        (
            "IMP_C05", "GEX", "S4", "unclaimed_cause",
            "Tổng tài sản {{P:C:assets:yoy:2025}} {{D:assets:yoy:2025}}, đạt {{E48}}.",
            "Tổng tài sản {{P:C:assets:yoy:2025}} {{D:assets:yoy:2025}}, đạt {{E48}} chủ yếu do hợp nhất thêm các dự án bất động sản khu công nghiệp và năng lượng.",
            "Cấy nguyên nhân 'chủ yếu do hợp nhất thêm các dự án bất động sản khu công nghiệp và năng lượng' không có thuyết minh hỗ trợ trong S4.",
        ),
        (
            "IMP_C06", "QNS", "S3", "unclaimed_cause",
            "Lợi nhuận sau thuế {{P:C:net_income:difference:2025}} {{D:net_income:difference:2025}}, đạt {{E11}}.",
            "Lợi nhuận sau thuế {{P:C:net_income:difference:2025}} {{D:net_income:difference:2025}}, đạt {{E11}} do chi phí nguyên liệu mía đường và chi phí bán hàng gia tăng.",
            "Cấy nguyên nhân 'do chi phí nguyên liệu mía đường và chi phí bán hàng gia tăng' không có thuyết minh hỗ trợ trong S3.",
        ),

        # ---------------------------------------------------------------------
        # Category 5: Subtle Extrapolation from Note Excerpts in Real Qualitative Blocks (6)
        # ---------------------------------------------------------------------
        (
            "IMP_E01", "FPT", "S2", "note_extrapolation",
            "Báo cáo kiểm toán có đoạn nhấn mạnh lưu ý về cơ sở hợp nhất báo cáo tài chính của công ty con mà không làm thay đổi ý kiến kiểm toán. Trích từ tài liệu {{Y:E20}}: “{{N:E20:620:878}}”",
            "Kiểm toán viên đưa ra ý kiến kiểm toán ngoại trừ đối với cơ sở hợp nhất báo cáo tài chính của Công ty Cổ phần Viễn thông FPT. Trích từ tài liệu {{Y:E20}}: “{{N:E20:620:878}}”",
            "Đoạn trích chỉ là đoạn nhấn mạnh (Emphasis of Matter) và ghi rõ 'Ý kiến kiểm toán của chúng tôi không bị ảnh hưởng bởi vấn đề này', nhưng câu tóm tắt bóp méo thành 'ý kiến kiểm toán ngoại trừ'.",
        ),
        (
            "IMP_E02", "FPT", "S6", "note_extrapolation",
            "Doanh thu cung ứng dịch vụ được hạch toán theo mức độ hoàn thành dựa trên tỷ lệ khối lượng công việc đã thực hiện. Trích từ tài liệu {{Y:E79}}: “{{N:E79:516:787}}”",
            "Doanh thu cung ứng dịch vụ được ghi nhận toàn bộ một lần ngay khi ký kết hợp đồng với khách hàng không phụ thuộc tiến độ thực hiện. Trích từ tài liệu {{Y:E79}}: “{{N:E79:516:787}}”",
            "Đoạn trích quy định ghi nhận theo mức độ hoàn thành dựa trên tỷ lệ dịch vụ đã cung cấp, nhưng câu tóm tắt nói ngược lại là ghi nhận toàn bộ một lần ngay khi ký hợp đồng.",
        ),
        (
            "IMP_E03", "FPT", "S7", "note_extrapolation",
            "Doanh nghiệp không trích lập dự phòng nghĩa vụ hoàn nguyên đất thuê do điều kiện pháp lý và hợp đồng chưa đủ căn cứ xác định chắc chắn nghĩa vụ. Trích từ tài liệu {{Y:E92}}: “{{N:E92:815:1276}}”",
            "Doanh nghiệp đã được cơ quan chức năng miễn trừ vĩnh viễn nghĩa vụ hoàn nguyên đất thuê nên không phải trích lập dự phòng trên báo cáo tài chính. Trích từ tài liệu {{Y:E92}}: “{{N:E92:815:1276}}”",
            "Đoạn trích nói nghĩa vụ chỉ có thể xác định được khi có thêm các sự kiện/văn bản hướng dẫn trong tương lai, nhưng câu viết suy diễn thành 'đã được cơ quan chức năng miễn trừ vĩnh viễn'.",
        ),
        (
            "IMP_E04", "HUT", "S6", "note_extrapolation",
            "Quyền sử dụng đất có thời hạn được trích khấu hao theo phương pháp đường thẳng, trong khi quyền sử dụng đất không thời hạn thì không trích khấu hao. Trích từ tài liệu {{Y:E85}}: “{{N:E85:740:939}}”",
            "Toàn bộ quyền sử dụng đất của doanh nghiệp đều là đất không thời hạn nên không thực hiện trích khấu hao trong kỳ. Trích từ tài liệu {{Y:E85}}: “{{N:E85:740:939}}”",
            "Đoạn trích chỉ nêu chính sách kế toán phân biệt đất có thời hạn và không thời hạn, nhưng câu viết suy diễn thành khẳng định toàn bộ quyền sử dụng đất của công ty đều là đất không thời hạn.",
        ),
        (
            "IMP_E05", "HUT", "S6", "note_extrapolation",
            "Khoản trái phiếu phát hành được cam kết bảo lãnh thanh toán bởi một công ty con. Trích từ tài liệu {{Y:E39}}: “{{N:E39:597:677}}”",
            "Khoản trái phiếu phát hành đã được công ty con tất toán toàn bộ trước hạn trong năm tài chính. Trích từ tài liệu {{Y:E39}}: “{{N:E39:597:677}}”",
            "Đoạn trích chỉ nêu 'Trái phiếu được cam kết bảo lãnh thanh toán bởi một Công ty con khác của Công ty', nhưng câu viết suy diễn thành 'đã được công ty con tất toán toàn bộ trước hạn'.",
        ),
        (
            "IMP_E06", "HUT", "S7", "note_extrapolation",
            "Ban Điều hành nhận định không có sự kiện bất thường nào sau ngày khóa sổ kế toán làm ảnh hưởng trọng yếu đến tình hình tài chính của doanh nghiệp. Trích từ tài liệu {{Y:E97}}: “{{N:E97:216:563}}”",
            "Sau ngày khóa sổ kế toán đã phát sinh sự kiện bất thường trọng yếu buộc Ban Điều hành phải điều chỉnh lại toàn bộ báo cáo tài chính hợp nhất. Trích từ tài liệu {{Y:E97}}: “{{N:E97:216:563}}”",
            "Đoạn trích khẳng định không có sự kiện bất thường nào xảy ra sau ngày khóa sổ cần điều chỉnh, nhưng câu tóm tắt viết ngược lại hoàn toàn.",
        ),
    ]

    cases: list[ImplantedRealBlockCase] = []
    for cid, ticker, sid, cat, orig_tpl, imp_tpl, rationale in specs:
        state = states[ticker]
        orig_txt, _ = render_template(
            orig_tpl,
            f"{cid}_orig",
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["evidence_aliases"],
        )
        imp_txt, _ = render_template(
            imp_tpl,
            cid,
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["evidence_aliases"],
        )
        cases.append(
            ImplantedRealBlockCase(
                case_id=cid,
                ticker=ticker,
                section_id=sid,
                error_category=cat,
                original_template=orig_tpl,
                implanted_template=imp_tpl,
                original_rendered_text=orig_txt,
                implanted_rendered_text=imp_txt,
                expected_status="failed",
                perturbation_rationale=rationale,
            )
        )
    return cases


# =============================================================================
# Step 3: Lock Blind Labels & Verify 100% Pass Deterministic Gate
# =============================================================================

def verify_and_lock_datasets(
    states: dict[str, dict[str, Any]],
    blind_cases: list[BlindRealBlockCase],
    implanted_cases: list[ImplantedRealBlockCase],
) -> tuple[dict[tuple[str, str], list[BlindRealBlockCase]], dict[tuple[str, str], list[ImplantedRealBlockCase]]]:
    """Verify every blind case and every implanted case passes `verify_section_deterministically()`,
    and save the locked blind labels to disk with a SHA-256 commitment hash BEFORE calling the LLM.
    """
    blind_batches: dict[tuple[str, str], list[BlindRealBlockCase]] = {}
    for c in blind_cases:
        state = states[c.ticker]
        plan = get_section_plan(state, c.section_id)
        single_draft = build_batch_draft_from_templates(state, c.section_id, [(c.case_id, c.template)])
        det = verify_section_deterministically(
            single_draft,
            state["request"],
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["research_results"],
            state["evidence_aliases"],
            plan,
        )
        if det.status != "passed":
            raise AssertionError(f"Blind real case {c.case_id} failed deterministic check: {det.issues}")
        blind_batches.setdefault((c.ticker, c.section_id), []).append(c)

    for (ticker, sid), group in blind_batches.items():
        state = states[ticker]
        plan = get_section_plan(state, sid)
        batch_draft = build_batch_draft_from_templates(
            state, sid, [(c.case_id, c.template) for c in group]
        )
        det = verify_section_deterministically(
            batch_draft,
            state["request"],
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["research_results"],
            state["evidence_aliases"],
            plan,
        )
        if det.status != "passed":
            raise AssertionError(f"Blind batch {ticker} {sid} failed deterministic check: {det.issues}")

    implanted_batches: dict[tuple[str, str], list[ImplantedRealBlockCase]] = {}
    for c in implanted_cases:
        state = states[c.ticker]
        plan = get_section_plan(state, c.section_id)
        single_draft = build_batch_draft_from_templates(
            state, c.section_id, [(c.case_id, c.implanted_template)]
        )
        det = verify_section_deterministically(
            single_draft,
            state["request"],
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["research_results"],
            state["evidence_aliases"],
            plan,
        )
        if det.status != "passed":
            raise AssertionError(f"Implanted case {c.case_id} failed deterministic check: {det.issues}")
        implanted_batches.setdefault((c.ticker, c.section_id), []).append(c)

    for (ticker, sid), group in implanted_batches.items():
        state = states[ticker]
        plan = get_section_plan(state, sid)
        batch_draft = build_batch_draft_from_templates(
            state, sid, [(c.case_id, c.implanted_template) for c in group]
        )
        det = verify_section_deterministically(
            batch_draft,
            state["request"],
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["research_results"],
            state["evidence_aliases"],
            plan,
        )
        if det.status != "passed":
            raise AssertionError(f"Implanted batch {ticker} {sid} failed deterministic check: {det.issues}")

    # Lock blind labels to disk with SHA-256 hash BEFORE any LLM call
    prompt_path = ROOT / "src/agents/prompts/verifier_system.md"
    prompt_sha256 = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    locked_payload = {
        "protocol": "blind_labeling_locked_before_llm_evaluation",
        "verifier_prompt_version": "sv1-v1",
        "verifier_prompt_sha256": prompt_sha256,
        "held_out_tickers": ["BSR", "BWE", "DCM", "GAS", "GEX", "QNS"],
        "total_blind_cases": len(blind_cases),
        "blind_valid_cases": sum(1 for c in blind_cases if c.human_blind_label == "passed"),
        "blind_real_error_cases": sum(1 for c in blind_cases if c.human_blind_label == "failed"),
        "cases": [asdict(c) for c in blind_cases],
    }
    serialized = json.dumps(locked_payload, ensure_ascii=False, indent=2)
    locked_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    locked_payload["locked_labels_sha256"] = locked_hash
    BLIND_LABELS_LOCKED_PATH.write_text(
        json.dumps(locked_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return blind_batches, implanted_batches


# =============================================================================
# Step 4: Live Evaluation with Frozen `sv1-v1`
# =============================================================================

def run_live_evaluation(
    states: dict[str, dict[str, Any]],
    blind_batches: dict[tuple[str, str], list[BlindRealBlockCase]],
    implanted_batches: dict[tuple[str, str], list[ImplantedRealBlockCase]],
) -> dict[str, Any]:
    model = GeminiVerifierModel()
    total_api_calls = 0
    total_tokens = {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "total_tokens": 0}

    def add_usage(usage: dict[str, int]) -> None:
        for k in total_tokens:
            total_tokens[k] += int(usage.get(k, 0) or 0)

    # 1. Evaluate 40 blind-labeled real blocks (across 18 batches for BSR, BWE, DCM, GAS, GEX, QNS)
    blind_predictions: dict[str, dict[str, Any]] = {}
    for (ticker, sid), group in sorted(blind_batches.items()):
        state = states[ticker]
        plan = get_section_plan(state, sid)
        draft = build_batch_draft_from_templates(
            state, sid, [(c.case_id, c.template) for c in group]
        )
        res, log = verify_section_full(
            draft,
            state["request"],
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["research_results"],
            verifier_model=model,
            evidence_aliases=state["evidence_aliases"],
            section_plan=plan,
            record_raw_outputs=True,
        )
        total_api_calls += log.attempts
        add_usage(log.token_usage)
        assert log.raw_outputs_by_attempt[-1] is not None, f"Model error on blind batch {ticker} {sid}: {log.error_message}"
        parsed = SemanticVerificationOutput.model_validate(json.loads(log.raw_outputs_by_attempt[-1]))
        verdict_map = {v.block_id: v for v in parsed.block_verdicts}
        for c in group:
            v = verdict_map[c.case_id]
            blind_predictions[c.case_id] = {
                "predicted_status": v.status,
                "findings": [f.model_dump(mode="json") for f in v.findings],
            }
        print(
            f"[Blind Held-Out {ticker} {sid}] {len(group)} blocks verified "
            f"(level={res.level}, status={res.status})",
            flush=True,
        )

    # 2. Evaluate 30 implanted real blocks
    implanted_predictions: dict[str, dict[str, Any]] = {}
    for (ticker, sid), group in sorted(implanted_batches.items()):
        state = states[ticker]
        plan = get_section_plan(state, sid)
        draft = build_batch_draft_from_templates(
            state, sid, [(c.case_id, c.implanted_template) for c in group]
        )
        res, log = verify_section_full(
            draft,
            state["request"],
            state["evidence_by_id"],
            state["calculations_by_id"],
            state["research_results"],
            verifier_model=model,
            evidence_aliases=state["evidence_aliases"],
            section_plan=plan,
            record_raw_outputs=True,
        )
        total_api_calls += log.attempts
        add_usage(log.token_usage)
        assert log.raw_outputs_by_attempt[-1] is not None, f"Model error on implanted batch {ticker} {sid}: {log.error_message}"
        parsed = SemanticVerificationOutput.model_validate(json.loads(log.raw_outputs_by_attempt[-1]))
        verdict_map = {v.block_id: v for v in parsed.block_verdicts}
        for c in group:
            v = verdict_map[c.case_id]
            implanted_predictions[c.case_id] = {
                "predicted_status": v.status,
                "findings": [f.model_dump(mode="json") for f in v.findings],
            }
        print(
            f"[Implanted Real {ticker} {sid}] {len(group)} blocks verified "
            f"(level={res.level}, status={res.status})",
            flush=True,
        )

    return {
        "blind_predictions": blind_predictions,
        "implanted_predictions": implanted_predictions,
        "total_api_calls": total_api_calls,
        "total_tokens": total_tokens,
    }


# =============================================================================
# Step 5: Compute Metrics with 95% CIs & Evaluate Integration Gate
# =============================================================================

def compute_and_save_results(
    blind_cases: list[BlindRealBlockCase],
    implanted_cases: list[ImplantedRealBlockCase],
    live_data: dict[str, Any],
) -> dict[str, Any]:
    blind_preds = live_data["blind_predictions"]
    imp_preds = live_data["implanted_predictions"]

    # 1. Blind-labeled held-out evaluation (40 real LLM-authored blocks on BSR, BWE, DCM, GAS, GEX, QNS)
    blind_valid = [c for c in blind_cases if c.human_blind_label == "passed"]
    blind_errors = [c for c in blind_cases if c.human_blind_label == "failed"]

    blind_fp_cases = [c for c in blind_valid if blind_preds[c.case_id]["predicted_status"] != "passed"]
    blind_tp_cases = [c for c in blind_errors if blind_preds[c.case_id]["predicted_status"] == "failed"]
    blind_fn_cases = [c for c in blind_errors if blind_preds[c.case_id]["predicted_status"] != "failed"]

    blind_fpr_stats = format_rate_with_ci(len(blind_fp_cases), len(blind_valid))
    blind_real_error_recall_stats = format_rate_with_ci(len(blind_tp_cases), len(blind_errors))

    # Breakdown by held-out ticker for blind valid cases
    blind_by_ticker: dict[str, Any] = {}
    for ticker in sorted({c.ticker for c in blind_cases}):
        t_valid = [c for c in blind_valid if c.ticker == ticker]
        t_fp = sum(1 for c in t_valid if blind_preds[c.case_id]["predicted_status"] != "passed")
        t_err = [c for c in blind_errors if c.ticker == ticker]
        t_tp = sum(1 for c in t_err if blind_preds[c.case_id]["predicted_status"] == "failed")
        blind_by_ticker[ticker] = {
            "valid_total": len(t_valid),
            "false_positives": t_fp,
            "real_errors_total": len(t_err),
            "real_errors_caught": t_tp,
        }

    # 2. Implanted errors into real LLM-authored blocks (30 blocks)
    imp_tp = sum(1 for c in implanted_cases if imp_preds[c.case_id]["predicted_status"] == "failed")
    imp_fn_cases = [c for c in implanted_cases if imp_preds[c.case_id]["predicted_status"] != "failed"]
    implanted_recall_all_stats = format_rate_with_ci(imp_tp, len(implanted_cases))

    # Strictly held-out subset of implanted cases (24 cases on BSR, BWE, DCM, GAS, GEX, QNS)
    imp_held_out = [c for c in implanted_cases if c.ticker in {"BSR", "BWE", "DCM", "GAS", "GEX", "QNS"}]
    imp_held_out_tp = sum(1 for c in imp_held_out if imp_preds[c.case_id]["predicted_status"] == "failed")
    implanted_recall_held_out_stats = format_rate_with_ci(imp_held_out_tp, len(imp_held_out))

    # Combined real errors (30 implanted + 4 genuine Writer errors in blind set = 34 real-draft error blocks)
    combined_real_errors_n = len(implanted_cases) + len(blind_errors)
    combined_real_errors_tp = imp_tp + len(blind_tp_cases)
    combined_real_errors_recall_stats = format_rate_with_ci(combined_real_errors_tp, combined_real_errors_n)

    # Breakdown by implanted category
    implanted_by_category: dict[str, Any] = {}
    for cat in sorted({c.error_category for c in implanted_cases}):
        sub = [c for c in implanted_cases if c.error_category == cat]
        tp = sum(1 for c in sub if imp_preds[c.case_id]["predicted_status"] == "failed")
        implanted_by_category[cat] = format_rate_with_ci(tp, len(sub))

    # 3. Proposed Integration Thresholds Evaluation (Đề xuất 5)
    # - Recall on errors implanted into real drafts >= 80% (95% CI lower bound ~ >= 70%)
    # - False positive on blind-labeled valid sentences <= 10%
    imp_recall_val = implanted_recall_all_stats["point_estimate"]
    imp_ci_lo = implanted_recall_all_stats["clopper_pearson_95_ci"][0]
    blind_fpr_val = blind_fpr_stats["point_estimate"]

    meets_point_thresholds = (imp_recall_val >= 0.80) and (blind_fpr_val <= 0.10)
    meets_ci_lower_bound = imp_ci_lo >= 0.70

    summary = {
        "verifier_prompt_version": "sv1-v1 (frozen)",
        "held_out_companies_evaluated": ["BSR", "BWE", "DCM", "GAS", "GEX", "QNS"],
        "blind_labeled_real_blocks": {
            "total_blocks": len(blind_cases),
            "valid_blocks_n": len(blind_valid),
            "false_positives_k": len(blind_fp_cases),
            "fpr_with_95_ci": blind_fpr_stats,
            "genuine_writer_errors_n": len(blind_errors),
            "genuine_writer_errors_caught_k": len(blind_tp_cases),
            "genuine_writer_errors_missed_fn": len(blind_fn_cases),
            "genuine_writer_error_recall_with_95_ci": blind_real_error_recall_stats,
            "by_held_out_ticker": blind_by_ticker,
        },
        "implanted_errors_in_real_blocks": {
            "all_implanted_30_recall_with_95_ci": implanted_recall_all_stats,
            "strictly_held_out_24_recall_with_95_ci": implanted_recall_held_out_stats,
            "combined_34_real_draft_errors_recall_with_95_ci": combined_real_errors_recall_stats,
            "by_error_category": implanted_by_category,
            "missed_implanted_case_ids": [c.case_id for c in imp_fn_cases],
        },
        "integration_gate_decision": {
            "implanted_recall_ge_80pct": imp_recall_val >= 0.80,
            "implanted_recall_95ci_lower_ge_70pct": meets_ci_lower_bound,
            "blind_fpr_le_10pct": blind_fpr_val <= 0.10,
            "recommend_blocking_integration": meets_point_thresholds and meets_ci_lower_bound,
            "recommended_mode": (
                "blocking_full_integration"
                if (meets_point_thresholds and meets_ci_lower_bound)
                else "log_only_shadow_mode"
            ),
        },
        "total_api_calls": live_data["total_api_calls"],
        "total_tokens": live_data["total_tokens"],
    }

    detailed_blind = []
    for c in blind_cases:
        pred = blind_preds[c.case_id]
        detailed_blind.append({
            **asdict(c),
            "predicted_status": pred["predicted_status"],
            "is_correct": pred["predicted_status"] == c.human_blind_label,
            "findings": pred["findings"],
        })

    detailed_implanted = []
    for c in implanted_cases:
        pred = imp_preds[c.case_id]
        detailed_implanted.append({
            **asdict(c),
            "predicted_status": pred["predicted_status"],
            "is_correct": pred["predicted_status"] == c.expected_status,
            "findings": pred["findings"],
        })

    output_payload = {
        "summary": summary,
        "blind_labeled_cases": detailed_blind,
        "implanted_real_cases": detailed_implanted,
    }
    PRE_INTEGRATION_RESULTS_PATH.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Append to Golden Set (Mục 6)
    if GOLDEN_SET_PATH.exists():
        golden = json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))
    else:
        golden = {}
    golden["version"] = "sv1-dev-golden-v2-20261109"
    golden["held_out_blind_labeled_samples"] = detailed_blind
    golden["implanted_real_draft_samples"] = detailed_implanted
    GOLDEN_SET_PATH.write_text(
        json.dumps(golden, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Verify deterministic gate and lock blind labels without calling the LLM",
    )
    args = parser.parse_args()

    states = load_all_eval_states()
    blind_cases = build_blind_real_dataset(states)
    implanted_cases = build_implanted_real_dataset(states)
    blind_batches, implanted_batches = verify_and_lock_datasets(states, blind_cases, implanted_cases)

    print(
        f"Deterministic gate passed 100% & blind labels locked to {BLIND_LABELS_LOCKED_PATH.name}:\n"
        f"  - {len(blind_cases)} blind-labeled real blocks ({len(blind_batches)} batches) across BSR, BWE, DCM, GAS, GEX, QNS\n"
        f"  - {len(implanted_cases)} implanted real blocks ({len(implanted_batches)} batches)",
        flush=True,
    )
    if args.prepare_only:
        return

    live_data = run_live_evaluation(states, blind_batches, implanted_batches)
    summary = compute_and_save_results(blind_cases, implanted_cases, live_data)
    print("\n=== PRE-INTEGRATION EVALUATION SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
