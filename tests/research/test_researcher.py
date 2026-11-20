"""Researcher integration with the current fact corpus."""
import unittest

from src.agents.researcher import (_note_matches_topic, _recover_note_result, build_researcher,
                                   evidence_aliases, resolve_evidence_aliases)
from src.schemas.report_schema import NotesTask, RatioTask, ReportOutline, ReportRequest, SectionPlan, TimeSeriesTask
from src.storage.duckdb_manager import DEFAULT_DB_PATH
from src.tools.agent_tools import AgentTools
from src.tools.schemas import NoteEvidence, ToolResult


class ResearcherTests(unittest.TestCase):
    def test_identical_note_reads_are_reused_within_one_run(self):
        request = ReportRequest(ticker="GMD", start_year=2025, end_year=2025,
                                audience="demo")
        query = "Điều khoản và kỳ hạn các khoản vay"
        tasks = [NotesTask(task_id=f"{section}:borrowings:2025", query=query,
                           fiscal_year=2025, sections=["NOTES"])
                 for section in ("S4", "S7")]
        outline = ReportOutline(sections=[SectionPlan(
            section_id=section, title="Nguồn vốn", objective="Demo",
            research_tasks=[task]) for section, task in zip(("S4", "S7"), tasks)])

        class FakeTools:
            db_path = DEFAULT_DB_PATH

            def __init__(self):
                self.public_reads = 0
                self.expanded_reads = 0

            def execute(self, name, args):
                self.public_reads += 1
                return ToolResult(status="not_found")

            def search_notes_candidates(self, args):
                self.expanded_reads += 1
                return ToolResult(status="ok", chunks=[NoteEvidence(
                    chunk_id="loan", doc_id="GMD_2025", ticker="GMD",
                    fiscal_year=2025, scope="consolidated", section="NOTES",
                    text="Khoản vay có thời hạn vay 60 tháng kể từ ngày giải ngân.",
                    source_file="report.pdf", physical_pages=[43],
                    printed_pages=["43"], citation_tag="[Doc_GMD_2025, p.43]")])

        tools = FakeTools()
        update = build_researcher(tools, "note-v1")({
            "request": request, "outline": outline})
        self.assertEqual(tools.public_reads, 1)
        self.assertEqual(tools.expanded_reads, 2)
        for task in tasks:
            self.assertEqual(update["research_results"][task.task_id].evidence_ids,
                             ["loan"])

    def test_audit_section_read_is_reused_without_sharing_task_filter(self):
        request = ReportRequest(ticker="HUT", start_year=2025, end_year=2025,
                                audience="demo")
        tasks = [NotesTask(task_id=f"S2:{topic}:2025", query=query,
                           fiscal_year=2025, sections=["AUDIT_REPORT"])
                 for topic, query in (("opinion", "Loại ý kiến kiểm toán"),
                                      ("emphasis", "Vấn đề nhấn mạnh"))]
        outline = ReportOutline(sections=[SectionPlan(
            section_id="S2", title="Kiểm toán", objective="Demo",
            research_tasks=tasks)])

        class FakeTools:
            db_path = DEFAULT_DB_PATH

            def __init__(self):
                self.reads = 0

            def read_audit_section(self, ticker, fiscal_year, scope):
                self.reads += 1
                return ToolResult(status="ok", chunks=[NoteEvidence(
                    chunk_id="opinion", doc_id="HUT_2025", ticker=ticker,
                    fiscal_year=fiscal_year, scope=scope, section="AUDIT_REPORT",
                    text="Theo ý kiến của chúng tôi, báo cáo phản ánh trung thực.",
                    source_file="report.pdf", physical_pages=[7],
                    printed_pages=["7"], citation_tag="[Doc_HUT_2025, p.7]",
                    topic_roles=["opinion_conclusion"])])

        tools = FakeTools()
        update = build_researcher(tools, "note-v1")({
            "request": request, "outline": outline})
        self.assertEqual(tools.reads, 1)
        self.assertEqual(update["research_results"][tasks[0].task_id].evidence_ids,
                         ["opinion"])
        self.assertEqual(update["research_results"][tasks[1].task_id].evidence_ids,
                         [])

    def test_failed_expanded_search_is_not_reported_as_missing_evidence(self):
        task = NotesTask(task_id="S4:borrowings:2025",
                         query="Điều khoản và kỳ hạn các khoản vay",
                         fiscal_year=2025, sections=["NOTES"])

        class FailedTools:
            def search_notes_candidates(self, args):
                return ToolResult(status="error", message="backend unavailable")

        result = _recover_note_result(FailedTools(), task, {}, ToolResult(status="not_found"))
        self.assertEqual(result.status, "error")

    def test_note_recovery_checks_wider_candidates_after_topic_rejection(self):
        task = NotesTask(task_id="S4:borrowings:2025",
                         query="Điều khoản và kỳ hạn các khoản vay",
                         fiscal_year=2025, sections=["NOTES"])
        request = ReportRequest(ticker="GMD", start_year=2025, end_year=2025,
                                audience="demo")
        outline = ReportOutline(sections=[SectionPlan(
            section_id="S4", title="Nguồn vốn", objective="Demo", research_tasks=[task])])

        def chunk(cid, text):
            return NoteEvidence(chunk_id=cid, doc_id="GMD_2025", ticker="GMD",
                fiscal_year=2025, scope="consolidated", section="NOTES", text=text,
                source_file="report.pdf", physical_pages=[43], printed_pages=["43"],
                citation_tag="[Doc_GMD_2025, p.43]")

        class FakeTools:
            db_path = DEFAULT_DB_PATH
            queries = []

            def execute(self, name, args):
                return ToolResult(status="ok", chunks=[chunk("off", "Chính sách ghi nhận doanh thu")])

            def search_notes_candidates(self, args):
                self.queries.append(args["query"])
                return ToolResult(status="ok", chunks=[
                    chunk("on", "Khoản vay có thời hạn vay 60 tháng kể từ ngày giải ngân.")])

        tools = FakeTools()
        update = build_researcher(tools, "note-v1")({"request": request, "outline": outline})
        result = update["research_results"][task.task_id]
        self.assertEqual(result.status, "sufficient")
        self.assertEqual(result.evidence_ids, ["on"])
        self.assertIn("initial_candidates_rejected_by_topic_gate", result.warnings)
        self.assertIn("expanded_search_recovered", result.warnings)
        self.assertLessEqual(len(tools.queries), 5)

    def test_financial_risk_recovery_preserves_missing_subtopics(self):
        task = NotesTask(task_id="S7:financial_risks:2025",
                         query="Rủi ro thanh khoản tín dụng tỷ giá lãi suất",
                         fiscal_year=2025, sections=["NOTES"])
        request = ReportRequest(ticker="GMD", start_year=2025, end_year=2025,
                                audience="demo")
        outline = ReportOutline(sections=[SectionPlan(
            section_id="S7", title="Rủi ro", objective="Demo", research_tasks=[task])])

        class FakeTools:
            db_path = DEFAULT_DB_PATH

            def execute(self, name, args):
                return ToolResult(status="not_found")

            def search_notes_candidates(self, args):
                query = args["query"]
                if query not in ("Rủi ro thanh khoản", "Rủi ro tỷ giá"):
                    return ToolResult(status="not_found")
                return ToolResult(status="ok", chunks=[NoteEvidence(
                    chunk_id=query, doc_id="GMD_2025", ticker="GMD",
                    fiscal_year=2025, scope="consolidated", section="NOTES",
                    text=f"Tập đoàn quản lý {query.lower()} theo chính sách nội bộ.",
                    source_file="report.pdf", physical_pages=[50], printed_pages=["50"],
                    citation_tag="[Doc_GMD_2025, p.50]")])

        update = build_researcher(FakeTools(), "note-v1")({
            "request": request, "outline": outline})
        result = update["research_results"][task.task_id]
        self.assertEqual(result.status, "partial")
        self.assertEqual(len(result.evidence_ids), 2)
        self.assertEqual(result.next_action, "declare_limitation")
        self.assertEqual([item.description for item in result.missing],
                         ["Rủi ro tín dụng", "Rủi ro lãi suất"])

    def test_note_gate_finds_opinion_not_heading_with_ocr_tolerance(self):
        task = NotesTask(task_id="S2:opinion:2025", query="Loại ý kiến kiểm toán",
                         fiscal_year=2025, sections=["AUDIT_REPORT"])
        self.assertFalse(_note_matches_topic(task, "Ý kiến của Kiểm toán viên"))
        self.assertTrue(_note_matches_topic(task,
            "Theo ý kiến của chúng tôi, báo cáo phần ánh trung thực và hợp lý."))
        self.assertTrue(_note_matches_topic(task,
            "Theo ý kiến của chúng tôi, báo cáo phản ánh trung thục và hợp lý."))
        self.assertTrue(_note_matches_topic(task,
            "Theo ý kiến của chúng tôi, báo cáo phản ánh trunh thực và hợp lý."))
    def test_audit_task_reads_full_section_without_phrase_gate(self):
        request = ReportRequest(ticker="HUT", start_year=2025, end_year=2025,
                                audience="demo")
        task = NotesTask(task_id="S2:opinion:2025", query="Loại ý kiến kiểm toán",
                         fiscal_year=2025, sections=["AUDIT_REPORT"])
        outline = ReportOutline(sections=[SectionPlan(section_id="S2", title="Kiểm toán",
            objective="Demo", research_tasks=[task])])

        class FakeTools:
            db_path = DEFAULT_DB_PATH

            def read_audit_section(self, ticker, fiscal_year, scope):
                return ToolResult(status="ok", chunks=[NoteEvidence(
                    chunk_id=f"audit{i}", doc_id="HUT_2025", ticker=ticker,
                    fiscal_year=fiscal_year, scope=scope, section="AUDIT_REPORT",
                    text=text, source_file="report.pdf", physical_pages=[i],
                    printed_pages=[str(i)], citation_tag=f"[Doc_HUT_2025, p.{i}]")
                    for i, text in enumerate(("Trách nhiệm của Ban Điều hành",
                        "Theo ý kiến của chúng tôi, báo cáo phản ánh trung thực.",
                        "Chữ ký kiểm toán viên"), 1)])

            def execute(self, name, args):
                raise AssertionError("Audit task must not use top-five search")

        update = build_researcher(FakeTools(), "note-v1")({"request": request,
                                                              "outline": outline})
        self.assertEqual(len(update["research_results"][task.task_id].evidence_ids), 3)

    def test_emphasis_absence_is_declared_only_after_full_audit_read(self):
        request = ReportRequest(ticker="HUT", start_year=2025, end_year=2025,
                                audience="demo")
        task = NotesTask(task_id="S2:emphasis:2025", query="Vấn đề nhấn mạnh",
                         fiscal_year=2025, sections=["AUDIT_REPORT"])
        outline = ReportOutline(sections=[SectionPlan(section_id="S2", title="Kiểm toán",
            objective="Demo", research_tasks=[task])])

        class FakeTools:
            db_path = DEFAULT_DB_PATH

            def read_audit_section(self, ticker, fiscal_year, scope):
                return ToolResult(status="ok", chunks=[NoteEvidence(
                    chunk_id="opinion", doc_id="HUT_2025", ticker=ticker,
                    fiscal_year=fiscal_year, scope=scope, section="AUDIT_REPORT",
                    text="Theo ý kiến của chúng tôi, báo cáo phản ánh trung thực.",
                    source_file="report.pdf", physical_pages=[4], printed_pages=["4"],
                    citation_tag="[Doc_HUT_2025, p.4]",
                    topic_roles=["opinion_conclusion"])])

        result = build_researcher(FakeTools(), "note-v1")({"request": request,
                                                              "outline": outline})
        research = result["research_results"][task.task_id]
        self.assertEqual(research.status, "no_evidence")
        self.assertEqual(research.missing[0].reason, "not_in_corpus")
        self.assertIn("toàn bộ mục kiểm toán", research.missing[0].description)

    def test_note_gate_keeps_only_on_topic_chunks(self):
        request = ReportRequest(ticker="HUT", start_year=2025, end_year=2025,
                                audience="demo")
        task = NotesTask(task_id="S7:related_parties:2025",
                         query="Các giao dịch và số dư với bên liên quan", fiscal_year=2025)
        outline = ReportOutline(sections=[SectionPlan(
            section_id="S7", title="Bên liên quan", objective="Demo",
            research_tasks=[task])])

        def chunk(chunk_id, content):
            return NoteEvidence(chunk_id=chunk_id, doc_id="HUT_2025", ticker="HUT",
                fiscal_year=2025, scope="consolidated", section="NOTES", text=content,
                source_file="report.pdf", physical_pages=[1], printed_pages=["1"],
                citation_tag="[Doc_HUT_2025, p.1]")

        class FakeTools:
            db_path = DEFAULT_DB_PATH

            def __init__(self, chunks):
                self.chunks = chunks

            def execute(self, name, args):
                return ToolResult(status="ok", chunks=self.chunks)

        off_topic = chunk("irrelevant", "Chính sách ghi nhận doanh thu và tỷ giá.")
        on_topic = chunk("relevant", "Giao dịch với các BÊN LIÊN QUAN trong năm.")
        state = {"request": request, "outline": outline}
        research = build_researcher(FakeTools([off_topic, on_topic]), "note-v1")(state)
        self.assertEqual(research["research_results"][task.task_id].evidence_ids,
                         ["relevant"])
        self.assertEqual(set(research["evidence_by_id"]), {"relevant"})

        research = build_researcher(FakeTools([off_topic]), "note-v1")(state)
        result = research["research_results"][task.task_id]
        self.assertEqual(result.status, "no_evidence")
        self.assertEqual(result.evidence_ids, [])
        self.assertEqual(result.missing[0].reason, "not_found_yet")
        self.assertEqual(result.missing[0].description,
                         "chưa tìm thấy trong các đoạn được truy xuất")
        self.assertEqual(research["evidence_by_id"], {})

    def test_ratio_task_uses_two_source_tasks(self):
        request = ReportRequest(ticker="HUT", start_year=2022, end_year=2025,
                                audience="demo")
        revenue = TimeSeriesTask(task_id="revenue", metric_name="Doanh thu thuần",
                                 start_year=2022, end_year=2025)
        gross = TimeSeriesTask(task_id="gross", metric_name="Lợi nhuận gộp",
                               start_year=2022, end_year=2025)
        ratio = RatioTask(task_id="gross_margin", numerator_task_id="gross",
                          denominator_task_id="revenue", years=[2024, 2025])
        outline = ReportOutline(sections=[SectionPlan(
            section_id="s", title="Biên lợi nhuận", objective="Demo",
            research_tasks=[revenue, gross, ratio])])
        update = build_researcher(AgentTools())({"request": request, "outline": outline})
        self.assertEqual(update["calculations_by_id"]["gross_margin:2024"].status, "ok")
        self.assertEqual(update["calculations_by_id"]["gross_margin:2025"].unit, "percent")
        with self.assertRaises(ValueError):
            ReportOutline(sections=[SectionPlan(section_id="bad", title="Bad",
                objective="Bad", research_tasks=[ratio])])

    def test_ratio_task_keeps_failure_for_ambiguous_source(self):
        request = ReportRequest(ticker="OIL", start_year=2022, end_year=2025,
                                audience="demo")
        cash = TimeSeriesTask(task_id="cash", item_code="34", report_type="CASH_FLOW",
                              start_year=2022, end_year=2025)
        revenue = TimeSeriesTask(task_id="revenue", metric_name="Doanh thu thuần",
                                 start_year=2022, end_year=2025)
        ratio = RatioTask(task_id="cash_ratio", numerator_task_id="cash",
                          denominator_task_id="revenue", years=[2025])
        outline = ReportOutline(sections=[SectionPlan(
            section_id="s", title="Tỷ lệ", objective="Demo",
            research_tasks=[cash, revenue, ratio])])
        update = build_researcher(AgentTools())({"request": request, "outline": outline})
        failed = update["calculations_by_id"]["cash_ratio:2025"]
        self.assertEqual(failed.status, "cannot_compute")
        self.assertIn("cash has 2 rows", failed.reason)

    def test_ratio_task_keeps_failure_for_missing_source(self):
        request = ReportRequest(ticker="HUT", start_year=2024, end_year=2025,
                                audience="demo")
        absent = TimeSeriesTask(task_id="absent", item_code="999",
                                report_type="INCOME_STATEMENT", start_year=2024,
                                end_year=2025)
        revenue = TimeSeriesTask(task_id="revenue", metric_name="Doanh thu thuần",
                                 start_year=2024, end_year=2025)
        ratio = RatioTask(task_id="requested_ratio", numerator_task_id="absent",
                          denominator_task_id="revenue", years=[2025])
        outline = ReportOutline(sections=[SectionPlan(
            section_id="s", title="Tỷ lệ", objective="Demo",
            research_tasks=[absent, revenue, ratio])])
        result = build_researcher(AgentTools())({"request": request, "outline": outline})
        failed = result["calculations_by_id"]["requested_ratio:2025"]
        self.assertEqual(failed.status, "cannot_compute")
        self.assertIn("absent has 0 rows", failed.reason)

    def test_fpt_series_calculations_and_aliases(self):
        request = ReportRequest(ticker="FPT", start_year=2022, end_year=2025,
                                audience="demo")
        task = TimeSeriesTask(task_id="revenue", metric_name="Doanh thu thuần",
                              start_year=2022, end_year=2025)
        outline = ReportOutline(sections=[SectionPlan(
            section_id="s", title="Doanh thu", objective="Demo", research_tasks=[task])])
        update = build_researcher(AgentTools())({"request": request, "outline": outline})
        result = update["research_results"]["revenue"]
        self.assertEqual(result.status, "sufficient")
        self.assertEqual(len(result.evidence_ids), 4)
        self.assertEqual(len(update["calculations_by_id"]), 6)
        self.assertEqual(update["calculations_by_id"]["revenue:cagr"].status, "ok")
        aliases = update["evidence_aliases"]
        self.assertEqual(set(aliases), {"E1", "E2", "E3", "E4"})
        self.assertEqual(set(resolve_evidence_aliases(list(aliases), aliases)),
                         set(result.evidence_ids))
        self.assertEqual(evidence_aliases(update["evidence_by_id"], aliases), aliases)
        extended = evidence_aliases({**update["evidence_by_id"],
                                     "new-id": next(iter(update["evidence_by_id"].values()))}, aliases)
        self.assertEqual({key: extended[key] for key in aliases}, aliases)
        self.assertEqual(extended["E5"], "new-id")
        with self.assertRaises(KeyError):
            resolve_evidence_aliases(["E9"], aliases)

    def test_oil_duplicate_series_stays_unsafe(self):
        request = ReportRequest(ticker="OIL", start_year=2022, end_year=2025,
                                audience="demo")
        task = TimeSeriesTask(task_id="oil_cash", item_code="34", report_type="CASH_FLOW",
                              start_year=2022, end_year=2025)
        outline = ReportOutline(sections=[SectionPlan(
            section_id="s", title="Dòng tiền", objective="Demo", research_tasks=[task])])
        update = build_researcher(AgentTools())({"request": request, "outline": outline})
        result = update["research_results"]["oil_cash"]
        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(len(result.evidence_ids), 5)
        self.assertFalse(result.safe_for_calculation)
        self.assertEqual(result.next_action, "declare_limitation")
        self.assertEqual(update["calculations_by_id"]["oil_cash:trend"].status,
                         "cannot_compute")


if __name__ == "__main__":
    unittest.main()
