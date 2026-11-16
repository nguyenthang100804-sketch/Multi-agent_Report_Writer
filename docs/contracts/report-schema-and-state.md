# Hợp đồng schema và state cho Multi-Agent Report Writer

## Mục tiêu và phạm vi

Phần triển khai này định nghĩa dữ liệu đi qua các bước lập dàn ý, nghiên cứu, viết, tính toán và kiểm chứng báo cáo. Mỗi claim trong bản nháp tham chiếu bằng chứng bằng ID; nội dung và metadata nguồn nằm trong `evidence_by_id`. State giữ được bằng chứng qua các lần sửa mà không dùng `messages` làm kho dữ liệu nghiệp vụ.

Đây là **hợp đồng dữ liệu và các hàm hỗ trợ**, kèm graph một lượt Planner → Researcher → Writer → Verifier xác định. Planner template đã có trong `src/agents/planner.py`; graph vẫn nhận hàm Planner/Researcher/Writer để tiêm khi test, dùng Planner template khi đối số `plan=None`. Chưa có model/prompt, giao diện duyệt, vòng sửa graph hoặc Verifier ngữ nghĩa. [State JSON minh họa](../examples/synthetic-report-state.json) gồm request, outline, ba fact, bản nháp, trend, verification và final report; số liệu của nó không lấy từ corpus. [State từ output tool thật](../examples/real-tool-report-state.json) lấy OIL, mã dòng tiền `34`, giai đoạn 2022–2025 từ `query_time_series_tool`. Kết quả có hai dòng năm 2025, `printed_page=null` ở 2022 và 2023, `chunk_ids` không rỗng và `safe_for_calculation=false`. State giữ năm record, cảnh báo `period_inconsistency`, kết thúc `incomplete` cùng giới hạn nêu rõ từng dòng nguồn. [Báo cáo quét kỳ](../audits/period-consistency-audit.md) trình bày việc kiểm tra raw text OIL và toàn corpus.

## Planner template lần 1

`plan_report(ReportRequest)` trả `PlannerOutput(status, outline, notes, available_scopes)`. `preflight()` đọc độ phủ từ DuckDB hiện tại: ticker không có trong corpus bị từ chối; sáu ngân hàng và PVI dừng với lý do riêng; thiếu năm trong scope yêu cầu trả `needs_clarification` và danh sách scope sẵn có. Planner không tự đổi hoặc ghép scope. Các quyết định dừng và các mục chưa hỗ trợ nằm trong `planner_notes` của state khi chạy graph.

Khung cố định có S1–S5; S6/S7 bật theo đối tượng đọc hoặc `instructions`. S0, S8, S9 dành cho Editor/renderer. Bảng 12 chỉ tiêu ở `src/agents/planner_rules.py` dùng tên chuẩn; trước khi lập mỗi `TimeSeriesTask`, Planner gọi `metric_name_resolver` và chép cả mã dạng chuỗi lẫn `report_type` được trả về. Mã 23, 62, 140, 320, 338 và 440 chưa được resolver hỗ trợ, nên không có fact task tương ứng; giới hạn được ghi vào notes. Mỗi note task có năm và section nguồn rõ ràng; tool vẫn lọc cứng ticker/scope/năm/section và trả tối đa năm chunk.

`CalculationSpec` liệt kê riêng YoY doanh thu/tài sản, CAGR doanh thu và chênh lệch tuyệt đối lợi nhuận/dòng tiền. `RatioTask` liệt kê biên lợi nhuận, nợ và vốn chủ trên tài sản, CFO trên lợi nhuận sau thuế; tỷ lệ cuối yêu cầu mẫu số dương. Với `calculation_policy="explicit"`, Researcher chỉ chạy các phép tính này, giữ `cannot_compute` cùng lý do nếu dữ liệu không đủ. Outline cũ mặc định `legacy` để các state mẫu và test hiện có vẫn đọc được. Planner chỉ dự trù `period_inconsistency`; Researcher/Verifier kiểm tra cảnh báo trên evidence thực tế.

`outline_id` ổn định theo request; `outline_version` trong state là revision. `install_outline_revision()` giữ bản sao của từng outline trong `outlines_by_revision` và xóa phê duyệt cũ; `approve_outline_revision()` duyệt revision hiện hành. `can_complete()` vẫn yêu cầu bản nháp và verification `full` của revision hiện hành. Graph lần 1 dừng trước Researcher khi Planner trả `rejected` hoặc `needs_clarification`; luồng HITL tương tác chưa được xây dựng.

## Planner Agent lần 2 — khảo sát trước HITL

`build_planner_agent(model, tools)` trong `src/agents/planner_agent.py` tạo Planner dùng LLM. System prompt tại `src/agents/prompts/planner_system.md` chứa ngữ cảnh B01/B02/B03/B09, ý kiến kiểm toán, scope, công thức và ý nghĩa các trạng thái tool. Request, khung template và quan sát corpus hiện tại được truyền động; prompt không đóng cứng số tài liệu hay dữ liệu một ticker. Adapter `GeminiPlannerModel` gọi `gemini-3.8-flash` với `thinking_level=MEDIUM`. Nó đọc `GEMINI_API_KEY` hoặc `GOOGLE_API_KEY` từ môi trường hoặc `.env` tại thư mục chạy; không ghi key vào state/log. Khi chưa có key, dùng model giả trong test hoặc gọi riêng `plan_report()` để lấy template.

LLM trả JSON `PlannerTurn`: `observe` gọi một hay nhiều tool được phép, `propose` trả outline và `OutlineDecision`. `PlannerToolbox` ép ticker/scope/năm đúng request, chỉ nhận tên chỉ tiêu để resolver cấp mã và `report_type`, giữ `ToolResult` đầy đủ trong `PlannerObservation` và đưa bản tóm gọn cho LLM. Fact, note và resolver là các lệnh chỉ đọc. LLM được giữ, bỏ, gộp, tách section và chọn task/phép tính dựa trên dữ liệu, nhưng mỗi task định lượng/note phải có quan sát tool tương ứng; quyết định dựa trên dữ liệu cần ID quan sát không lỗi. Mọi miền S1–S5 phải có section hoặc quyết định rõ ràng. Output sai schema hoặc thiếu provenance được trả lại để LLM sửa; sau số lượt giới hạn, Planner dùng template và ghi `planner_fallback` vào notes.

Graph với `require_outline_approval=True` yêu cầu checkpointer và dừng bằng `interrupt` sau Planner. Resume bằng `Command(resume={"action":"approve","outline_version":N})`; `revise` gửi outline mới cùng version hiện hành, tăng revision và dừng duyệt lần nữa; `reject` dừng với `needs_clarification`. Chỉ phê duyệt đúng version mới mở đường sang Researcher. Với checkpoint, dùng `report_checkpoint_serde()` để cho phép giải mã các model Pydantic của dự án. Verification mới mang `outline_version`; bản của outline cũ không duyệt được draft của outline mới. Chế độ graph không yêu cầu approval vẫn giữ để chạy các test và state mẫu cũ.

Researcher dùng lại ToolResult Planner đã đọc khi tên tool, tham số và snapshot fact/note khớp; nếu khác, truy vấn lại. Snapshot note lấy từ checksum manifest chỉ mục đã công bố. Chạy đánh giá Dev sau khi có key: `\.venv\Scripts\python.exe -m src.evaluation.planner_eval --cases configs/planner_eval_dev.json`. Không dùng kết quả Test để sửa prompt. Chưa có lần gọi API Gemini thật trong bộ test tự động; chất lượng outline và truy hồi note thực phải được đo sau khi cấu hình key.

## Bước 1 — Ví dụ JSON và luồng dữ liệu

**Mục tiêu:** kiểm tra rằng dữ liệu ở mỗi bước có chỗ lưu rõ ràng và có thể truy ngược claim về nguồn.

```text
ReportRequest
    → ReportOutline / SectionPlan / ResearchTask
    → ToolResult của src/tools
    → record_tool_result()
       ├─ ResearchResult: trạng thái, ID bằng chứng, phần thiếu, cảnh báo
       └─ evidence_by_id: EvidenceRecord chứa FactEvidence hoặc NoteEvidence
    → CalculationResult: phép tính và ID fact đầu vào
    → SectionDraft: văn bản, claim, ID bằng chứng và ID phép tính
    → VerificationResult: kết quả cho đúng section và revision
    → final_report
```

Trong [ví dụ minh họa](../examples/synthetic-report-state.json), task `revenue_series` lấy doanh thu các năm 2022–2024. Ba fact được lưu trong `evidence_by_id`; `ResearchResult` chỉ giữ ba ID. Claim `revenue_2024` giữ giá trị 150 VND, năm 2024 và ID fact tương ứng. Claim `revenue_growth` khẳng định `asserted_direction="increasing"` và tham chiếu phép tính `revenue_trend`; phép tính cũng có `direction="increasing"` và tham chiếu cả ba ID fact. Chuỗi `final_report` được đặt trực tiếp vào state mẫu để thử hợp đồng, không phải đầu ra của renderer.

## Bước 2 — Pydantic model và kiểm tra đầu vào

**Mục tiêu:** chặn yêu cầu và task sai trước khi gọi tool. Mã nằm trong `src/schemas/report_schema.py`.

| Model | Dữ liệu và kiểm tra chính |
|---|---|
| `ReportRequest` | Một ticker, khoảng năm, scope, loại sản phẩm, đối tượng đọc, ngôn ngữ và hướng dẫn; chuyển ticker sang chữ hoa và từ chối năm bắt đầu lớn hơn năm kết thúc. |
| `FactTask` | Một chỉ tiêu tại một năm. |
| `TimeSeriesTask` | Một chỉ tiêu trong khoảng năm; kiểm tra thứ tự năm. |
| `NotesTask` | Từ khóa, năm và các phần tài liệu; mặc định tìm trong `NOTES`. |
| `SectionPlan`, `ReportOutline` | Dàn ý có cấu trúc; `section_id` và `task_id` phải duy nhất trong dàn ý. |
| `Claim`, `SectionDraft` | Bản nháp theo section, phiên bản dàn ý và revision; claim số liệu trực tiếp có metric, năm, giá trị nguồn, cách hiển thị và ID nguồn. Section có thể khai báo `limitations` theo warning và evidence ID. |
| `VerificationIssue`, `VerificationResult` | Issue theo claim/block có `severity=error` hoặc `warning`; kết quả `passed` được mang warning nhưng không được mang error. |

`Year`, `Scope`, `MetricSelection`, `FactEvidence`, `NoteEvidence` và `ToolResult` được **import từ `src/tools/schemas.py`**. Vì vậy khoảng năm 2022–2025, các giá trị scope (`consolidated`, `separate`, `general`) và quy tắc nhập mã chỉ tiêu không bị khai báo lại. `report_type` trong request là **loại sản phẩm đầu ra** (`multi_year_financial_analysis`); `report_type` trong task số liệu là **loại báo cáo kế toán** (`BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW`).

Task fact/time series nhận `metric_name`, hoặc nhận đồng thời `item_code` dạng chuỗi và `report_type` kế toán. Nếu có cả tên và mã, `check_resolved_metric()` gọi resolver hiện có, yêu cầu một kết quả duy nhất và đối chiếu mã/loại báo cáo. Tên mơ hồ hoặc cặp tên–mã trái nhau bị từ chối; mã như `"01"` vẫn là chuỗi. Model không tạo SQL hoặc đường dẫn database.

Các validator kiểm tra **kiểu và quan hệ giữa các trường**. Hàm `check_coverage(request, db_path)` trong `src/agents/coverage.py` truy vấn DuckDB ở chế độ chỉ đọc và yêu cầu ít nhất một fact không `suspect` cho mỗi ticker/năm/scope được yêu cầu. Thiếu bất kỳ năm nào sẽ ném `CoverageError` kèm các năm thiếu. Hàm này chặn yêu cầu ngoài corpus trước khi lập dàn ý; nó **không bảo đảm** một chỉ tiêu cụ thể có dữ liệu trong mọi năm.

## Bước 3 — Evidence, research result và reducer

**Mục tiêu:** giữ nguyên nguồn của từng dòng, tách lỗi backend khỏi thiếu dữ liệu và ngăn cập nhật state làm mất bằng chứng.

`evidence_id_for()` tạo ID fact từ `doc_id`, loại báo cáo kế toán, `code` (hoặc nhãn chuẩn hóa nếu thiếu mã), trang PDF vật lý và cột `current`. Nó không dùng `fact_index` vì chỉ số này có thể đổi khi nạp lại snapshot. Với note, ID là `chunk_id` từ parser. `EvidenceRecord` lưu `kind`, `snapshot_version` và toàn bộ payload nguồn, không lưu task ID. Quan hệ task → evidence nằm trong `ResearchResult.evidence_ids`; hai task lấy cùng một fact vì vậy gộp được vào state.

`record_tool_result(task, result, snapshot_version)` chuyển từng `FactEvidence` hoặc `NoteEvidence` của tool thành record và trả về:

```python
research_result, new_evidence_by_id = record_tool_result(task, tool_result, snapshot_version)
```

`research_result.evidence_ids` chỉ chứa ID; payload đầy đủ nằm trong `new_evidence_by_id`. Khi nhiều dòng fact trùng chỉ tiêu/năm, hàm giữ tất cả và thêm `multiple_matching_rows`; Writer không được tự chọn một dòng. Nếu các dòng có cùng khóa tự nhiên, ID được gắn thêm dấu vân tay nội dung và số lần xuất hiện. Hai bản sao hoàn toàn giống nhau không thể được theo dõi riêng lẻ qua các snapshot, dù cả hai được giữ trong một kết quả.

`ResearchResult.status=error` dành cho lỗi backend hoặc đầu vào tool không hợp lệ, không mang nghĩa “không có trong corpus”. Trạng thái `ambiguous` giữ danh sách ứng viên resolver. `missing.reason` có ba giá trị:

| Lý do | Ý nghĩa và hướng xử lý dự kiến |
|---|---|
| `not_in_corpus` | Không tìm thấy fact; đổi task hoặc nêu giới hạn. |
| `not_found_yet` | Tìm notes chưa trúng; có thể truy vấn lại trong giới hạn cấu hình. |
| `null_or_suspect` | Có dòng nguồn nhưng giá trị null hoặc suspect; nêu giới hạn, không thay bằng 0. |

Adapter hiện ánh xạ fact `not_found` sang `not_in_corpus` và notes `not_found` sang `not_found_yet`. Đây là **quy tắc phân loại của adapter**, chưa phải kiểm chứng đầy đủ độ phủ corpus; bộ điều phối có thể cần xem ingestion trước khi kết luận chắc chắn. Với chuỗi năm, adapter phân biệt năm có dòng null/suspect với năm không có dòng.

Ở cấp chỉ tiêu, `record_tool_result()` đặt `next_action=declare_limitation` cho fact `not_in_corpus` và các dòng số mơ hồ; chỉ tên chỉ tiêu mơ hồ với các ứng viên resolver mới cần hỏi làm rõ. `research_limitation_text()` liệt kê tất cả dòng nguồn, giá trị và citation khi không thể chọn một số. `period_warnings_for_facts()` thêm `period_inconsistency:t->t+1` nếu giá trị năm `t` không khớp `prior_year` trong báo cáo năm sau. Đây là cảnh báo, không tự sửa giá trị.

Trong `src/agents/state.py`, `ReportState` là `TypedDict`. `merge_immutable()` gộp evidence và calculation theo ID; cùng ID nhưng nội dung khác sẽ ném `ValueError`, kể cả khi `snapshot_version` khác. `merge_research_results()` cập nhật theo task ID. `merge_revisions()` giữ draft và verification theo khóa `(section_id, revision)`, từ chối nội dung khác tại cùng khóa. `messages` dùng reducer `add_messages` chuẩn khi có LangGraph; khi chưa cài LangGraph, hàm dự phòng nối hai danh sách để phần schema vẫn import được.

**Chính sách resume:** ingestion tính SHA-256 của **các dòng logic** và lưu `snapshot_id` trong bảng `corpus_metadata`. `snapshot_version_for_db()` đọc ID này; với DB cũ chưa có metadata, nó tính cùng loại hash từ các dòng, không hash byte của file DuckDB. Trước khi tiếp tục checkpoint, gọi `check_snapshot_on_resume(state, current_snapshot_version)`. Tham số có thể là một version cho state chỉ chứa fact, hoặc bản đồ `{"fact": db_snapshot_id, "note": index_snapshot_id}` khi có cả Qdrant. Nếu version khác, hàm ném `StaleEvidenceError` và **dừng run**. Việc tự chạy lại research chưa được triển khai. Graph sau này cần cung cấp version của chỉ mục Qdrant.

## Bước 4 — Claim, phép tính, kiểm chứng và JSON round trip

**Mục tiêu:** claim có dữ liệu để Verifier đối chiếu mà không phải đoán số từ câu văn; state có thể lưu và đọc lại.

Một claim `direct_fact` phải có `metric`, `fiscal_year`, `value`, `unit` và `evidence_ids`. Claim `calculated` phải có `calculation_id` và đúng một khẳng định có cấu trúc: `asserted_direction` cho trend, hoặc `asserted_value` kèm `asserted_unit` và mức làm tròn tùy chọn cho phép tính số. `calculated_claim_matches()` so các trường đó với `CalculationResult` và ID fact đầu vào mà không cần đọc câu văn. Claim định tính tham chiếu note evidence. Pydantic chưa kiểm tra rằng mọi ID trong claim tồn tại trong `evidence_by_id`; Verifier sẽ chịu trách nhiệm.

`value` của direct fact luôn giữ **dấu và đơn vị nguồn**. `display_value`, `display_unit`, `display_scale`, `display_sign` và `display_rounding_decimals` mô tả số viết cho người đọc. Ví dụ nguồn `−22.740.964.770.411 VND` có thể hiển thị `22,7 nghìn tỷ đồng` với `display_sign="magnitude"`, `display_scale=10^12`, làm tròn một chữ số. Verifier so `abs(value) / display_scale` sau làm tròn với `display_value`, kiểm tra đơn vị hiển thị xuất hiện trong block, loại tiền tương thích với nguồn và đối chiếu token số trong câu văn. Nó nhận dấu phẩy thập phân, dấu chấm hàng nghìn và dấu âm của tiếng Việt. Năm trong khoảng request, số thứ tự đầu dòng và số chỉ mục/phần/chương được miễn kiểm như số liệu tài chính. Số còn lại không gắn với `display_value` của claim bị báo `unsupported_claim`; số hiển thị khai báo nhưng không xuất hiện trong câu bị báo `value_mismatch`.

DuckDB ingestion tạo citation fact theo `[Doc_{doc_id}, p.{physical_page}]`; parser tạo citation note một trang hoặc dải trang theo `[Doc_{doc_id}, p.X-Y]`. Truy vấn thật `search_notes_tool` cho OIL 2023 trả `NoteEvidence` của chunk `OIL_2023_Hopnhat_chunk_0137`, `physical_pages=[39,40]`, tag `[Doc_OIL_2023_Hopnhat, p.39-40]` và điểm rerank khoảng `0,4502`. Qdrant payload không có `source_file` hoặc `printed_pages`; retriever bổ sung chúng từ JSON parser khi tạo `NoteEvidence`. `fact_citation_matches_source()` và `note_citation_matches_source()` so tag với metadata nguồn. Mẫu cũ `[FPT-2024-Hopnhat-p12]` trong tài liệu thiết kế không phải định dạng hiện được parser/storage trả. `render_section_citations()` chỉ lấy tag từ các evidence ID, gộp tag lặp trong một block và từ chối tag do Writer tự chèn. Regex trong bộ đánh giá cũ vẫn rộng để xử lý dữ liệu lịch sử; Verifier mới dùng phép so khớp nghiêm ngặt.

`CalculationResult` biểu diễn `yoy`, `cagr`, `difference` và `trend`, lưu ID đầu vào, tham số, kết quả hoặc lý do `cannot_compute`. Hàm `calculate_trend()` hoạt động như sau:

1. Đọc cờ `safe_for_calculation` đã được `query_time_series_tool` xác định; không tự tính lại cờ.
2. Kiểm tra có đúng một fact **cho từng năm** trong khoảng, giá trị không null và đơn vị nhất quán.
3. Sắp xếp theo năm, dùng `Decimal(str(value))` và so chênh lệch từng cặp năm.
4. Trả enum `increasing` khi tăng liên tiếp, `decreasing` khi giảm liên tiếp, `flat` khi mọi năm bằng nhau, `mixed` cho chuỗi còn lại; thiếu điều kiện thì trả `cannot_compute` cùng lý do. Trend thành công chỉ có trường `direction`, không dùng `value` hay đơn vị chuỗi tự do.

`src/agents/calculations.py` có `calculate_yoy()`, `calculate_cagr()` và `calculate_difference()`. Chúng chỉ dùng chuỗi được tool đánh dấu an toàn, kiểm tra đầu vào cùng chỉ tiêu/scope/đơn vị và chặn khi `period_inconsistency` liên quan đến các năm của phép tính; cảnh báo ở năm khác không chặn. YoY từ chối mẫu số 0; CAGR yêu cầu mọi năm trong khoảng và giá trị đầu/cuối dương; chênh lệch lấy giá trị cuối trừ giá trị đầu. YoY và CAGR dùng `Decimal`, làm tròn `ROUND_HALF_UP` mặc định hai chữ số và ghi mức làm tròn vào `parameters`.

`verify_section_deterministically()` kiểm tra ID nguồn, citation, ticker/scope, khoảng năm của request, giá trị/đơn vị nguồn và hiển thị, mã chỉ tiêu, dòng trùng, cảnh báo lệch kỳ, input của calculation và khẳng định phép tính. Tên chỉ tiêu được resolver nhận diện phải khớp mã/loại báo cáo; tên không được resolver nhận diện phải khớp **toàn bộ nhãn chuẩn hóa**, không chỉ là một phần của nhãn. Ký hiệu `(*)` không làm khác nhãn sau chuẩn hóa. Từ chỉ quy mô trong `display_unit` phải khớp `display_scale` sau khi quy đổi đơn vị nguồn; ví dụ 10¹² VND ứng với “nghìn tỷ đồng”, không phải “triệu đồng”. Với trend, Verifier đối chiếu từ “tăng”, “giảm”, “đi ngang”, “biến động” trong văn bản với `asserted_direction`. Bộ từ vựng này chỉ bắt được các trường hợp rõ ràng; nó không thay kiểm chứng ngữ nghĩa.

Số trong câu được đọc theo dấu phẩy thập phân tiếng Việt hoặc dấu chấm thập phân khi không khớp mẫu tách hàng nghìn; `12.5` thành 12,5, không thành 125. Định dạng số sai tạo issue `number_format`. Số ở claim định tính được chấp nhận khi xuất hiện trong `NoteEvidence.text` được claim đó trích dẫn. Ngày dạng `31/12/2024` và số sau các nhãn “thuyết minh”, “điều”, “quý”, “tháng”, “ngày”, “năm” được loại khỏi phép so số tài chính.

Cảnh báo `period_inconsistency:t->t+1` chỉ là `warning` cho claim một năm. Claim `calculated` dùng **cả hai năm** của cặp nhận `error` và action `rewrite` khi chưa khai báo giới hạn. `SectionDraft.limitations[]` chỉ khai `warning_code`, `evidence_ids`, `block_id`; Writer không nhập nội dung câu giới hạn. Renderer sinh câu chuẩn nêu hai năm và lý do có thể trình bày lại hoặc trích xuất khác biệt, rồi chèn citation nguồn. Khi khai báo khớp, issue còn là `warning`. `warning_affects_years()` cũng chỉ chặn phép tính khi cả hai năm của cặp nằm trong khoảng tính. Kết quả có `level="deterministic"`; kể cả khi `status="passed"`, `approved_draft()` vẫn yêu cầu verification `level="full"`. `VerificationResult.level` là trường bắt buộc, không có mặc định `full`.

Verifier gắn issue `invalid_citation` và `rewrite` cho tag Writer tự viết như `[Doc_X, p.1]`, `[1]` hay dạng cũ có dấu gạch nối. Renderer được gọi sau bước kiểm chứng và báo lỗi rõ ràng nếu vẫn có tag tự viết hoặc ID nguồn lạ. Nếu một section vừa có lỗi `rewrite` vừa có giới hạn `declare_limitation`, trạng thái là `needs_revision` để Writer sửa lỗi trước; khi chỉ còn giới hạn chưa được giải thích thì là `insufficient_evidence`. Lớp xác định chưa chứng minh diễn giải định tính hoặc quan hệ nhân quả được nguồn hỗ trợ; bước kiểm chứng ngữ nghĩa vẫn cần được dựng.

`VerificationIssue.action` cho phép đủ ba hướng: `rewrite`, `retrieve_more`, `declare_limitation`. Hàm `action_for_missing()` ánh xạ chỉ `not_found_yet` sang `retrieve_more`; `not_in_corpus` và `null_or_suspect` sang `declare_limitation`. Quy tắc này dùng được cho Planner/Verifier khi dựng graph; lớp Verifier xác định đã có, còn bước đánh giá ngữ nghĩa chưa có.

`approved_draft()` chỉ trả bản nháp mới nhất khi `outline_approved_version` bằng `outline_version` và chính `(section_id, revision)` của bản nháp có verification `passed`. `can_complete()` yêu cầu điều kiện đó cho mọi section. `complete_run()` chỉ trả cập nhật `run_status="completed"` khi `can_complete()` đúng. `is_run_complete()` không coi một chuỗi trạng thái được gán trực tiếp là thành công nếu thiếu verification hiện hành. `state_to_json()` và `state_from_json()` cũng từ chối state hoàn tất sai; chúng mã hóa bản nháp và verification có khóa tuple thành danh sách rồi dựng lại các khóa đó.

`ReportState` dùng `total=False`, nên Python vẫn cho phép node gán trực tiếp `state["run_status"] = "completed"`. Không thể cấm phép gán này chỉ bằng `TypedDict`. Hợp đồng cho graph là dùng `complete_run()` để đổi trạng thái và `is_run_complete()` khi đọc kết quả; lớp JSON chặn lưu state hoàn tất sai. Graph chưa được dựng để cưỡng chế mọi node tuân theo hợp đồng này.

## Bước 5 — Graph một lượt

`build_report_graph(plan, research, write)` trong `src/agents/report_graph.py` tạo LangGraph với bốn node theo đúng thứ tự Planner → Researcher → Writer → Verifier. `plan(request)` trả `ReportOutline`; `research(state)` trả cập nhật `research_results`, `evidence_by_id` và phép tính nếu có; `write(state)` trả các `section_drafts`. Các hàm được truyền vào để sau này gắn tool và model thật, còn graph chỉ điều phối hợp đồng state. Node Verifier chạy `verify_section_deterministically()` trên draft mới nhất của từng section, chỉ render citation cho section `passed`, lưu kết quả mức `deterministic` và để `run_status="incomplete"`. Graph một lượt chưa lặp lại khi có issue, chưa chạy kiểm chứng ngữ nghĩa và không gọi `complete_run()`; vì vậy bản nháp được render chưa phải báo cáo đã duyệt hoàn toàn.

## Bước 6 — Cách test và kết quả thực tế

Chạy toàn bộ test bằng lệnh:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Sau lượt sửa Verifier và dựng graph một lượt này, **59/59 test qua** với lệnh trên. Test mới nằm ở `tests/report/test_report_calculation_verification.py`, `tests/report/test_report_graph.py` và các test tích hợp/state/storage hiện có.

| Nhóm test mới | Điều được kiểm tra thực tế |
|---|---|
| Request và task | Từ chối năm ngoài khoảng, khoảng năm đảo ngược, scope sai, tên–mã chỉ tiêu trái nhau và mã chỉ tiêu không phải chuỗi. |
| Evidence ID và dòng trùng | Đổi `fact_index` không đổi ID; hai dòng cùng chỉ tiêu được giữ riêng, kết quả `ambiguous` và có `multiple_matching_rows`. |
| Hai task cùng nguồn | FactTask và TimeSeriesTask cùng lấy một fact; reducer gộp được record chung và từng `ResearchResult` giữ ID đó. |
| Thiếu dữ liệu và lỗi | Fact `not_found`, lỗi backend và dòng null tạo trạng thái/lý do khác nhau. |
| Trend và calculated claim | Chuỗi thiếu năm không tính được; tăng, đi ngang và hỗn hợp có enum riêng; khẳng định hướng/giá trị và mức làm tròn được so với phép tính mà không parse câu văn. |
| Reducer | Cùng ID nhưng nội dung khác và cùng revision nhưng nội dung khác đều bị từ chối. |
| Duyệt revision | Verification của revision 1 không duyệt được revision 2; đổi phiên bản dàn ý làm bản nháp cũ không đủ điều kiện hoàn tất. |
| JSON mẫu | Đọc được state, có ba evidence, `can_complete()` đúng với mẫu và ghi/đọc JSON giữ nguyên state. |
| Coverage và resume | OIL có đủ năm; FOX và scope không có dữ liệu bị chặn; snapshot khác làm resume dừng; trạng thái hoàn tất sai bị từ chối khi lưu JSON. |
| Output tool thật | OIL mã `34` trả năm record, năm 2025 có hai dòng, có `printed_page=null`, chunk IDs, citation chuẩn; trạng thái `ambiguous`, không an toàn để tính. |
| Hướng xử lý thiếu nguồn | `not_in_corpus` và `null_or_suspect` dẫn tới `declare_limitation`, không dẫn tới `retrieve_more`. |
| Ngân hàng | ACB có dữ liệu năm 2024 nhưng không có mã chuẩn `10` của báo cáo kết quả kinh doanh; task đó dẫn tới `declare_limitation` ở cấp chỉ tiêu. |
| Phép tính và Verifier xác định | YoY, CAGR, chênh lệch, điều kiện công thức, citation note dải trang, claim sai giá trị và claim OIL có dòng trùng/cảnh báo kỳ. |
| Snapshot logic | Nạp lại cùng dữ liệu giữ nguyên ID; dữ liệu đổi tạo ID khác. |
| Văn bản và warning | Giá trị claim đúng nhưng câu văn sai; dấu chấm hàng nghìn và dấu phẩy thập phân; quy đổi đơn vị/độ lớn; cảnh báo chỉ ảnh hưởng đúng cặp năm; lời giải thích hợp lệ hạ issue xuống warning. |
| Ràng buộc Verifier mới | “triệu đồng” không khớp thang nghìn tỷ; `increasing` không khớp câu “giảm”; “tăng giảm” là `mixed`; `12.5%` không thành 125; 8% từ note và ngày tháng không bị báo sai; `level` thiếu bị từ chối; nhãn `(*)` được chuẩn hóa. |
| Graph một lượt | Bốn node chạy theo thứ tự; Verifier lưu mức `deterministic`, render citation và giữ run `incomplete`. |
| Thứ tự sửa lỗi | Lỗi giá trị cùng tồn tại với dòng trùng vẫn dẫn tới `needs_revision`; tag tự viết trở thành `invalid_citation` để Writer sửa. |
| Loại lỗi | Chín `error_type` đều có trường hợp phát hiện và cùng một baseline sạch không báo lỗi. |

Các test kiểm tra **model, hàm chuyển dữ liệu, reducer, phép tính, citation, kiểm chứng xác định, graph một lượt và output thật của tool từ corpus hiện có**. Test graph dùng các hàm Planner/Researcher/Writer giả để xác nhận thứ tự chuyển state, kết quả Verifier và trạng thái chưa hoàn tất. Chúng chưa chạy Writer/Verifier ngữ nghĩa thật với PDF. `VerificationResult(level="full", status="passed")` trong JSON minh họa vẫn được tạo trực tiếp để thử điều kiện state; nó không chứng minh một Verifier độc lập đã xác nhận báo cáo. Test tích hợp đối chiếu cấu trúc snapshot ID và dữ liệu nguồn; nếu corpus được nạp lại với nội dung khác, phải tạo lại JSON mẫu thật.
