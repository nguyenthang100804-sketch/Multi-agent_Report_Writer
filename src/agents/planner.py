"""Deterministic, read-only planner for one non-financial ticker."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.agents.coverage import CoverageError, CoverageResult, available_scopes, check_coverage
from src.agents.planner_rules import (
    BANK_TICKERS, METRIC_RULES, OPTIONAL_NOTE_TOPICS, SECTION_TITLES,
    UNREVIEWED_FINANCIAL_TICKERS,
)
from src.schemas.report_schema import (
    CalculationSpec, NotesTask, PlannerNote, PlannerOutput, RatioTask,
    ReportOutline, ReportRequest, SectionPlan, TimeSeriesTask,
)
from src.storage.duckdb_manager import DEFAULT_DB_PATH
from src.tools.metric_resolver import metric_name_resolver
from src.tools.schemas import MetricResolverInput


def preflight(request: ReportRequest, db_path: str | Path = DEFAULT_DB_PATH
              ) -> CoverageResult | PlannerOutput:
    """Return coverage or a visible stop reason; never change the requested scope."""
    scopes = available_scopes(request.ticker, db_path)
    if not scopes:
        return PlannerOutput(status="rejected", notes=[PlannerNote(
            code="ticker_not_in_corpus", message=f"{request.ticker} không có trong corpus")])
    if request.ticker in BANK_TICKERS:
        return PlannerOutput(status="rejected", available_scopes=scopes,
                             notes=[PlannerNote(code="unsupported_bank_codes",
                                                message="Chưa hỗ trợ bộ mã chuẩn cho ngân hàng")])
    if request.ticker in UNREVIEWED_FINANCIAL_TICKERS:
        return PlannerOutput(status="rejected", available_scopes=scopes,
                             notes=[PlannerNote(code="unreviewed_financial_template",
                                                message="Chưa xác nhận bộ mã chuẩn cho doanh nghiệp bảo hiểm")])
    try:
        coverage = check_coverage(request, db_path)
    except CoverageError as exc:
        return PlannerOutput(status="needs_clarification", available_scopes=scopes,
                             notes=[PlannerNote(code="scope_or_year_missing",
                                                message=(f"Scope {request.scope} thiếu năm "
                                                         f"{exc.result.missing_years}; "
                                                         f"các scope có sẵn: {scopes}"))])
    if not coverage.has_standard_codes:
        return PlannerOutput(status="rejected", available_scopes=scopes,
                             notes=[PlannerNote(code="unsupported_standard_codes",
                                                message="Chưa hỗ trợ bộ mã chuẩn cho ticker/scope này")])
    return coverage


def plan_report(request: ReportRequest, db_path: str | Path = DEFAULT_DB_PATH) -> PlannerOutput:
    """Build the fixed outline; qualitative searches and all arithmetic run later."""
    gate = preflight(request, db_path)
    if isinstance(gate, PlannerOutput):
        return gate
    years = list(range(request.start_year, request.end_year + 1))
    sections = {sid: SectionPlan(section_id=sid, title=title, objective=title)
                for sid, title in SECTION_TITLES.items() if sid in {"S1", "S2", "S3", "S4", "S5"}}
    notes: list[PlannerNote] = []

    def note_task(section_id: str, name: str, query: str, year: int,
                  source_sections: list[str] | None = None) -> None:
        sections[section_id].research_tasks.append(NotesTask(
            task_id=f"{section_id}:{name}:{year}", query=query, fiscal_year=year,
            sections=source_sections or ["NOTES"]))

    last = request.end_year
    note_task("S1", "business", "Ngành nghề hoạt động và cơ cấu doanh nghiệp", last,
              ["NOTES", "MANAGEMENT_REPORT"])
    note_task("S1", "accounting_basis", "Kỳ kế toán đơn vị tiền tệ và chế độ kế toán áp dụng", last)
    for year in years:
        note_task("S2", "opinion", "Loại ý kiến kiểm toán đối với báo cáo tài chính", year,
                  ["AUDIT_REPORT"])
        note_task("S2", "emphasis", "Vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ", year,
                  ["AUDIT_REPORT"])
        note_task("S2", "auditor", "Đơn vị kiểm toán và ngày ký báo cáo", year,
                  ["AUDIT_REPORT"])
    note_task("S4", "borrowings", "Điều khoản và kỳ hạn các khoản vay", last)

    present: set[str] = set()
    for section_id, key, name, expected_report_type in METRIC_RULES:
        if key == "parent_profit" and request.scope != "consolidated":
            notes.append(PlannerNote(code="scope_limited_metric", section_id="S3",
                                     message="Phân bổ lợi nhuận cổ đông mẹ chỉ áp dụng cho scope hợp nhất"))
            continue
        resolved = metric_name_resolver(MetricResolverInput(metric_name=name))
        if (resolved.status != "ok" or len(resolved.candidates) != 1 or
                resolved.candidates[0].report_type != expected_report_type):
            notes.append(PlannerNote(code="unresolved_metric", section_id=section_id,
                                     message=f"Không lập task cho chỉ tiêu chưa phân giải duy nhất: {name}"))
            continue
        metric = resolved.candidates[0]
        sections[section_id].research_tasks.append(TimeSeriesTask(
            task_id=key, metric_name=name, item_code=metric.code,
            report_type=metric.report_type, start_year=request.start_year,
            end_year=request.end_year))
        present.add(key)

    def calculation(section_id: str, key: str, operation: str,
                    start_year: int, end_year: int) -> None:
        if key in present:
            sections[section_id].calculation_specs.append(CalculationSpec(
                calculation_id=f"{key}:{operation}:{end_year}", operation=operation,
                source_task_id=key, start_year=start_year, end_year=end_year))

    for year in years[1:]:
        calculation("S3", "revenue", "yoy", year - 1, year)
        calculation("S4", "assets", "yoy", year - 1, year)
        for key in ("profit_before_tax", "net_income"):
            calculation("S3", key, "difference", year - 1, year)
        for key in ("operating_cash_flow", "investing_cash_flow", "financing_cash_flow"):
            calculation("S5", key, "difference", year - 1, year)
    if len(years) > 1:
        calculation("S3", "revenue", "cagr", years[0], years[-1])
        calculation("S3", "revenue", "trend", years[0], years[-1])

    def ratio(section_id: str, name: str, numerator: str, denominator: str,
              positive_denominator: bool = False) -> None:
        if numerator in present and denominator in present:
            sections[section_id].research_tasks.append(RatioTask(
                task_id=name, numerator_task_id=numerator, denominator_task_id=denominator,
                years=years, positive_denominator=positive_denominator))

    ratio("S3", "gross_margin", "gross_profit", "revenue")
    ratio("S3", "net_margin", "net_income", "revenue")
    ratio("S4", "debt_to_assets", "liabilities", "assets")
    ratio("S4", "equity_to_assets", "equity", "assets")
    ratio("S5", "cfo_to_net_income", "operating_cash_flow", "net_income", True)

    for section in sections.values():
        section.calculations_allowed = [spec.calculation_id for spec in section.calculation_specs]
        section.calculations_allowed.extend(
            f"{task.task_id}:{year}" for task in section.research_tasks
            if isinstance(task, RatioTask) for year in task.years)

    audience = request.audience.casefold()
    instructions = (request.instructions or "").casefold()
    enable_s6 = (any(word in audience for word in ("kiểm toán", "ban giám đốc", "audit", "management"))
                 or any(word in instructions for word in ("chính sách", "thuyết minh", "policy")))
    enable_s7 = (any(word in audience for word in ("kiểm toán", "tuân thủ", "audit", "compliance"))
                 or any(word in instructions for word in ("bên liên quan", "rủi ro", "sự kiện", "cam kết")))
    for sid, enabled in (("S6", enable_s6), ("S7", enable_s7)):
        if enabled:
            sections[sid] = SectionPlan(section_id=sid, title=SECTION_TITLES[sid],
                                        objective=SECTION_TITLES[sid])
            for key, query in OPTIONAL_NOTE_TOPICS[sid]:
                note_task(sid, key, query, last)

    for sid, message in (("S3", "Mã 23 và 62 chưa có trong resolver; chưa lập task cho chi phí lãi vay và phần cổ đông không kiểm soát"),
                         ("S4", "Mã 140, 320, 338 và 440 chưa có trong resolver; chưa lập task số cho hàng tồn kho, vay nợ và kiểm tra cân đối")):
        notes.append(PlannerNote(code="unsupported_template_metrics", section_id=sid,
                                 message=message))
    if len(years) > 1:
        notes.append(PlannerNote(code="period_inconsistency_possible",
                                 message="So sánh nhiều năm phải kiểm tra period_inconsistency trước khi tính"))
    digest = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True,
                                       ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    outline = ReportOutline(outline_id=f"outline:{digest}",
                            sections=list(sections.values()), calculation_policy="explicit")
    return PlannerOutput(status="ready", outline=outline, notes=notes,
                         available_scopes=gate.available_scopes)
