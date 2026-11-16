# Quyết định trước khi xây Writer

1. **Bí danh nguồn append-only:** Researcher tạo `evidence_aliases` dạng `E1 → evidence_id`. Bảng lưu trong state; evidence mới nhận số tiếp theo, không đánh số lại bí danh cũ. Lượt đầu sắp theo nhãn chỉ tiêu, năm rồi ID để các năm của một chuỗi nằm gần nhau. Prompt Writer chỉ nhận bí danh và metadata cần thiết; code gọi `resolve_evidence_aliases()` để đổi lại ID thật. Bí danh lạ bị từ chối. Không tạo lại bảng từ một tập evidence khác khi đọc output cũ.
2. **Số do code chèn:** Hợp đồng Writer dùng `{{E3}}` cho fact, `{{E3|abs}}` cho trị tuyệt đối, `{{C:...}}` cho kết quả số, `{{T:...}}` cho hướng, `{{Y:E3}}` cho năm của fact và `{{P:C:...}}` cho kỳ của phép tính. `src/agents/draft_rendering.py` điền số, năm, đơn vị, `text` và `claims`; template mới không được chứa chữ số tự gõ. Verifier render lại template và báo `render_mismatch` nếu `text` hoặc claim bị sửa. `DraftBlock.template` còn tùy chọn để đọc draft cũ, nhưng node Writer từ chối mọi draft mới thiếu template. Menu placeholder theo section nằm ở `src/agents/writer_menu.py`.
3. **Mức `full`:** Chỉ cấp khi lớp xác định `passed` và lớp ngữ nghĩa cũng `passed` cho **mọi claim định tính**, đối chiếu với text của note đã dẫn. Lớp ngữ nghĩa còn phải đọc ngược từng block, liệt kê câu khẳng định dữ kiện hoặc nguyên nhân không có claim tương ứng và tạo issue. Đây là chiều Citation Recall; nó cũng cần bắt các so sánh định lượng viết bằng chữ hoặc ngầm hiểu mà bộ quét token số không thấy. Cần ghi kết quả theo đúng section/revision; không nâng `deterministic` thành `full` chỉ vì không có issue. Lớp này **chưa được triển khai**.

Researcher thật duyệt task, gọi `AgentTools`, chuyển kết quả bằng `record_tool_result()`, tạo trend/YoY/CAGR/chênh lệch và bảng bí danh. `build_template_writer()` đã viết được phần định lượng S3–S5; graph vẫn cần truyền Planner, Researcher và Writer khi dựng. Chưa thêm `table_role`; xem [khảo sát toàn corpus](../audits/metric-coverage-corpus-audit.md) và [mẫu demo](../audits/metric-coverage-demo-audit.md).

`RatioTask` cho Planner tham chiếu hai task nguồn `fact` hoặc `time_series` và danh sách năm. `ReportOutline` kiểm tra ID và năm; Researcher chạy task nguồn trước, rồi tạo `CalculationResult(operation="ratio")` cho năm có đúng một fact ở mỗi nguồn. Planner template đã khai các ratio được hỗ trợ. `check_coverage()` trả `has_standard_codes` theo mã `270` của bảng cân đối.

Nếu một nguồn ratio thiếu hoặc có nhiều dòng trong năm, Researcher vẫn lưu `CalculationResult(status="cannot_compute")` cùng lý do và các evidence ID hiện có. `calculate_ratio()` chặn khác ticker/scope/năm/đơn vị, mẫu số 0 và cảnh báo `period_inconsistency` liên quan. Menu Writer chỉ liệt kê phép tính `ok` có ID trong `section.calculations_allowed`.

`DraftLimitation(kind="period_inconsistency")` giữ `warning_code`, `block_id`, `evidence_ids`. `CannotComputeLimitation` neo vào `calculation_id`; `DataGapLimitation` neo vào `research_task_id`. Graph bỏ khai báo hai loại sau từ Writer và sinh lại từ kết quả Researcher; Verifier kiểm neo và yêu cầu mọi phép tính lỗi hoặc task thiếu dữ liệu thuộc section có limitation. Mã audit lần lượt là `period_inconsistency:<a>-><b>`, `cannot_compute:<reason>` (reason chuẩn hóa từ `CalculationResult.reason`) và `data_gap:<status>` (`no_evidence` hoặc `partial` theo `ResearchResult.status`). Renderer chèn câu giới hạn sau kiểm chứng, ngoài `block.text`.

Node Writer của graph từ chối draft mới có block thiếu `template` (`missing_template`); `state_from_json()` vẫn đọc được state cũ không có trường này. `SectionPlan.calculations_allowed` là danh sách ID phép tính được đưa vào menu Writer; `build_placeholder_menu()` chỉ đưa alias fact liên quan đến section và phép tính `ok` nằm trong danh sách. Verifier kiểm từng placeholder với menu section. `build_template_writer()` viết tối đa năm nhận định định lượng cho mỗi section. `src/agents/report_tables.py` dựng bảng năm theo cùng thang tỷ đồng và tỷ lệ phần trăm từ state; phần note định tính chưa được viết.

Giới hạn thiếu nguồn được gộp theo cùng năm và trạng thái gốc; phép tính không được thực hiện được nêu như hệ quả. Ô trống có citation của đúng năm chứa ô trống; năm không có fact không nhận citation của các năm có số. Cảnh báo lệch kỳ nêu tên chỉ tiêu và hai giá trị từ hai báo cáo. Bảng “Biến động theo kỳ” trình bày toàn bộ YoY và chênh lệch từng cặp năm được Planner cho phép, theo cùng quy tắc cho mọi ticker; ô `—` ứng với phép tính không thực hiện được và câu giới hạn giải thích lý do. Không sinh cờ biến động theo ngưỡng. CAGR khả dụng được trình bày bằng câu có nguồn, kể cả khi YoY lớn; trend doanh thu được Planner khai và Researcher tính rồi Writer diễn đạt bằng `T:`.

### S8.4 Quy tắc diễn giải xu hướng

Trend hiện dùng ngưỡng tuyệt đối bằng `0`, ghi dưới khóa `flat_absolute_threshold` trong `CalculationResult.parameters`: “đi ngang” nghĩa là các giá trị bằng nhau tuyệt đối. Vì vậy một thay đổi rất nhỏ vẫn được phân loại là tăng hoặc giảm. Ngưỡng tương đối như 0,5% cần được đánh giá riêng trước khi thay đổi phép tính. Renderer dùng “tăng/giảm” cho hai điểm, “tăng liên tục/giảm liên tục” từ ba điểm, “đi ngang” cho `flat`, và “diễn biến không đều” cho `mixed`. Cụm cuối bao gồm cả chuỗi có đoạn đi ngang, nên không hàm ý luôn có tăng và giảm xen kẽ.

## Gợi ý thao tác cho Planner template

| Nhóm chỉ tiêu | Phép tính mặc định được đề xuất |
|---|---|
| Doanh thu, tổng tài sản, vốn chủ sở hữu | YoY, chênh lệch, CAGR khi đầu/cuối dương và đủ năm. |
| Lợi nhuận và dòng tiền | Chênh lệch; YoY chỉ khi giá trị đầu kỳ dương và cách diễn giải tỷ lệ phù hợp. Không mặc định dùng CAGR. |
| Biên lợi nhuận gộp, nợ/tổng tài sản, ROE | `ratio` từ hai fact cùng năm và đơn vị, mẫu số khác 0. ROE theo vốn chủ sở hữu cuối kỳ chỉ là tỷ lệ đơn giản; nếu cần ROE chuẩn theo vốn bình quân phải thiết kế phép tính riêng. |
| Mọi chỉ tiêu | Trend chỉ khi đủ một dòng đáng tin cậy mỗi năm và không có cảnh báo kỳ liên quan. |

Bảng này là quy tắc chọn phép tính cho Planner, **chưa được mã hóa** trong Planner vì Planner chưa xây. Researcher tạo kết quả phép tính khả dụng nhưng không buộc Writer dùng chúng.
