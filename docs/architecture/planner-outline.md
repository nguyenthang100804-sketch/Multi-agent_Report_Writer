# Outline tham chiếu cho Planner Agent (một ticker)

Phạm vi: một ticker, khoảng năm trong 2022–2025, một scope, doanh nghiệp phi tài chính (có bộ mã chuẩn B01/B02/B03).
Căn cứ khung: B01/B02/B03/B09 theo TT200/TT202; thứ tự trình bày bám bộ BCTC. Đây là **bản đồ nội dung** để đối chiếu với outline hiện hành, không phải yêu cầu mỗi mục con hoặc bảng phải là một object trong `ReportOutline`.

**Kết luận đối chiếu:** template hiện có task cho 12 chỉ tiêu đã được resolver hỗ trợ, phép tính của S3–S5, note nền của S1–S2 và các chủ đề note của S4/S6/S7. Nó chưa lập task cho S3.6; chưa mang metadata thống kê tài liệu S1.1, kết quả kiểm đẳng thức parser S4.5 hoặc danh mục nguồn S9. Các nội dung này không được xem là đã có chỉ vì section tương ứng tồn tại. LLM giữ S1–S7 thành bảy section riêng và điều chỉnh task/mục con theo quan sát dữ liệu.

## 0. Quy ước dùng chung

- **Loại section:** S1–S7 là bảy section chính cố định. S6/S7 mỗi section có task tìm thuyết minh; `Code` nằm ngoài outline Planner.
- **Nguồn:** `DuckDB` = `query_fact_tool` / `query_time_series_tool`; `Qdrant` = `search_notes_tool` (lọc cứng ticker, năm, scope, section; tối đa 5 chunk).
- **ID hiện hành:** section có ID như `S3`; task và phép tính có ID riêng. Schema hỗ trợ `SubsectionPlan`, nhưng template hiện để `subsections=[]`. `S3.2` và `T3.2` dưới đây là nhãn nội dung tham chiếu, chưa phải ID object hoặc bảng được Planner/renderer bảo đảm tạo ra. Claim trỏ về evidence/phép tính qua ID của chính nó.
- **Mọi task fact phải khai `report_type`** (mã 20/30/40 trùng giữa các báo cáo).
- **Mã chỉ tiêu đánh dấu (*)** hiện chưa được `metric_name_resolver` hỗ trợ; Planner không tự tạo task số cho chúng.
- **Khi không tính được:** Researcher tạo `cannot_compute` kèm lý do; bước dựng bảng có thể để trống ô không hợp lệ và bước giới hạn hiển thị lý do. Template chưa duy trì object mục con để bảo đảm mục đó luôn xuất hiện.
- **Không có mục "nguyên nhân biến động":** corpus là BCTC kiểm toán, không có MD&A. Chỉ mô tả *cái gì thay đổi*, không khẳng định *vì sao*.

## 1. Danh sách section

| ID | Section | Loại | Nguồn chính | Dòng B-mẫu |
|---|---|---|---|---|
| S0 | Tóm tắt điều hành | Code/Editor (viết cuối) | Từ S1–S7 đã duyệt | — |
| S1 | Thông tin doanh nghiệp và phạm vi dữ liệu | Bắt buộc | Metadata + Qdrant | B09 I–III |
| S2 | Ý kiến kiểm toán | Bắt buộc | Qdrant `AUDIT_REPORT` | Báo cáo kiểm toán |
| S3 | Kết quả kinh doanh | Bắt buộc | DuckDB | B02 |
| S4 | Tình hình tài chính | Bắt buộc | DuckDB (+ Qdrant cho S4.4) | B01 |
| S5 | Lưu chuyển tiền tệ | Bắt buộc | DuckDB | B03 |
| S6 | Chính sách kế toán và thuyết minh chọn lọc | Bắt buộc | Qdrant `NOTES` | B09 IV–V |
| S7 | Bên liên quan, rủi ro, sự kiện sau niên độ | Bắt buộc | Qdrant `NOTES` | B09 VIII |
| S8 | Giới hạn và phương pháp | Code | `planner_notes`, cảnh báo kỳ | — |
| S9 | Nguồn trích dẫn | Code (renderer) | `evidence_by_id` | — |

Thứ tự S3 → S4 → S5 bám thứ tự B02 → B01 → B03 để người đọc kế toán/kiểm toán thấy quen. Planner chỉ lập các section được giữ trong S1–S7; S0, S8, S9 không nằm trong outline. Luồng hiện hành có dòng giới hạn và citation theo section, chưa tạo đầy đủ ba section S0/S8/S9 như mô tả mục tiêu bên dưới.

## 2. Mục con chi tiết

### S1. Thông tin doanh nghiệp và phạm vi dữ liệu (Bắt buộc)

| Mục con | Nội dung | Nguồn | Bảng/phép tính |
|---|---|---|---|
| S1.1 Phạm vi báo cáo | Ticker, scope, các năm có dữ liệu, số tài liệu nguồn, đơn vị tiền tệ | Request + metadata DuckDB | T1.1 là mục tiêu trình bày; outline hiện chỉ mang ticker/scope/năm qua request, chưa có task thống kê số tài liệu, đơn vị và doc_id |
| S1.2 Đặc điểm hoạt động | Ngành nghề, vốn điều lệ, cơ cấu công ty (chỉ mô tả) | Qdrant `MANAGEMENT_REPORT`, `NOTES` | Không |
| S1.3 Cơ sở lập báo cáo | Chế độ kế toán áp dụng (TT200/TT202), kỳ kế toán, đơn vị | Qdrant `NOTES` | Không |

Template tạo task S1.2; LLM có thể điều chỉnh task/mục con khi có quan sát phù hợp. Researcher lọc chunk theo cụm từ chủ đề; không có chunk liên quan được ghi là `not_found_yet`, chưa chứng minh tài liệu không có nội dung đó.

### S2. Ý kiến kiểm toán (Bắt buộc)

| Mục con | Nội dung | Nguồn |
|---|---|---|
| S2.1 Loại ý kiến | Chấp nhận toàn phần, ngoại trừ, từ chối, trái ngược, theo từng năm | Qdrant `AUDIT_REPORT` |
| S2.2 Vấn đề nhấn mạnh và ngoại trừ | Nội dung nếu có; nếu truy xuất chưa thấy thì ghi "chưa tìm thấy trong các đoạn được truy xuất" | Qdrant `AUDIT_REPORT` |
| S2.3 Đơn vị kiểm toán và kỳ | Tên đơn vị kiểm toán, ngày báo cáo | Qdrant `AUDIT_REPORT` |

Mỗi năm một truy vấn riêng (lọc cứng `fiscal_year`) để tránh lẫn văn mẫu giữa các năm.

### S3. Kết quả kinh doanh (Bắt buộc, `report_type=INCOME_STATEMENT`)

| Mục con | Nội dung | Chỉ tiêu (mã) | Bảng/phép tính |
|---|---|---|---|
| S3.1 Chuỗi kết quả kinh doanh | Số liệu 4 năm | Doanh thu thuần (10), Lợi nhuận gộp (20), Chi phí lãi vay (23)(*), LN trước thuế (50), LN sau thuế (60) | T3.1: chỉ tiêu × năm |
| S3.2 Tăng trưởng | YoY từng năm; CAGR toàn kỳ | Doanh thu thuần | T3.2: `revenue_yoy`, `revenue_cagr` |
| S3.3 Biên lợi nhuận | Biên gộp, biên ròng | 20/10, 60/10 | T3.3: `gross_margin`, `net_margin` |
| S3.4 Biến động lợi nhuận | Chênh lệch tuyệt đối (không dùng CAGR cho lợi nhuận có thể âm) | 50, 60 | T3.4: `profit_abs_change` |
| S3.5 Phân bổ lợi nhuận (chỉ `consolidated`) | Phần của cổ đông công ty mẹ và cổ đông không kiểm soát | Mã 61, 62(*) | Template có task mã 61; mã 62 chưa được resolver hỗ trợ. Chưa có mục con/bảng T3.5 hoặc điều kiện bật mục con theo `safe_for_calculation` |
| S3.6 Thuyết minh bổ sung | Phân tích doanh thu theo nhóm nếu thuyết minh có | Qdrant `NOTES` | Chưa có task trong template; chỉ có nếu LLM khảo sát và thêm task note được validator chấp nhận |

Điều kiện tính hiện hành: YoY cần hai năm liền kề và giá trị gốc **dương**. CAGR cần đủ năm, giá trị đầu và cuối dương. Lợi nhuận âm: dùng chênh lệch tuyệt đối. Planner ghi khả năng `period_inconsistency` cho kỳ nhiều năm; Researcher kiểm cảnh báo trên nguồn trước khi tính.

### S4. Tình hình tài chính (Bắt buộc, `report_type=BALANCE_SHEET`)

| Mục con | Nội dung | Chỉ tiêu (mã) | Bảng/phép tính |
|---|---|---|---|
| S4.1 Quy mô tài sản | Tổng tài sản 4 năm, tăng trưởng | Tổng tài sản (270) | T4.1; `assets_yoy` |
| S4.2 Cơ cấu tài sản | Tiền và tương đương tiền, hàng tồn kho | 110, 140 | Template có mã 110; mã 140 và phép tính tỷ trọng tiền/hàng tồn kho chưa có |
| S4.3 Cơ cấu nguồn vốn | Nợ phải trả, vốn chủ sở hữu | 300, 400 | T4.3; `debt_to_assets` (300/270), `equity_to_assets` (400/270) |
| S4.4 Vay nợ | Vay và nợ thuê tài chính (số) và thuyết minh vay (chữ) | 320, 338(*) | Template chỉ có task note về điều khoản/kỳ hạn; mã 320/338 và bảng T4.4 chưa có |
| S4.5 Kiểm tra cân đối | Tổng tài sản bằng tổng nguồn vốn | 270, 440 | Chưa có task hoặc kết quả kiểm đẳng thức parser trong outline; mã 440 chưa được resolver hỗ trợ |

Vì resolver hiện chưa hỗ trợ mã 320/338, template chỉ lập phần thuyết minh và ghi giới hạn `unsupported_template_metrics`; không kết luận doanh nghiệp không có khoản vay.

### S5. Lưu chuyển tiền tệ (Bắt buộc, `report_type=CASH_FLOW`)

| Mục con | Nội dung | Chỉ tiêu (mã) | Bảng/phép tính |
|---|---|---|---|
| S5.1 Ba dòng tiền thuần | Hoạt động kinh doanh, đầu tư, tài chính | 20, 30, 40 (CASH_FLOW) | T5.1 |
| S5.2 Cấu trúc dòng tiền | Dấu của ba dòng và tổng hợp (ví dụ kinh doanh dương, đầu tư âm) | Từ ba task dòng tiền | Outline có đủ giá trị nguồn; chưa có mục con riêng hoặc phép tính/cụm dấu riêng trong template |
| S5.3 Biến động dòng tiền | Chênh lệch tuyệt đối giữa các năm | 20, 30, 40 | T5.3: `cf_abs_change` |
| S5.4 Chất lượng lợi nhuận | Dòng tiền kinh doanh so với LN sau thuế | CFO (20) / LNST (60, INCOME_STATEMENT) | `cfo_to_net_income`; **chỉ tính khi LNST > 0** |

Hai chỉ tiêu cùng mã `20` nhưng khác báo cáo: task phải khai hai `report_type` khác nhau, không dùng chung evidence ID.

### S6. Chính sách kế toán và thuyết minh chọn lọc

S6 luôn có trong dàn ý mẫu. Mỗi mục con là một truy vấn note độc lập, diễn đạt lại bằng từ đồng nghĩa (không chép tiêu đề).

| Mục con | Nội dung |
|---|---|
| S6.1 Ghi nhận doanh thu | Nguyên tắc và thời điểm ghi nhận |
| S6.2 Khấu hao và tài sản cố định | Phương pháp, thời gian hữu dụng |
| S6.3 Dự phòng | Phải thu khó đòi, hàng tồn kho |
| S6.4 Vay và công cụ tài chính | Template truy vấn điều khoản/kỳ hạn khoản vay; chưa khảo sát riêng các công cụ tài chính khác |

Giới hạn tối đa 5 chunk mỗi truy vấn. Outline tạo task note; việc viết claim định tính trỏ về note thuộc Writer và chưa được bảo đảm bởi Planner.

### S7. Bên liên quan, rủi ro, sự kiện sau niên độ

| Mục con | Nội dung |
|---|---|
| S7.1 Giao dịch với bên liên quan | Loại giao dịch, số dư nếu thuyết minh nêu |
| S7.2 Rủi ro tài chính | Thanh khoản, tín dụng, tỷ giá, lãi suất |
| S7.3 Cam kết và nợ tiềm tàng | Nếu có thuyết minh |
| S7.4 Sự kiện sau niên độ | Nếu có |

Researcher chỉ giữ chunk khớp cụm từ chủ đề. Với task không có chunk đủ liên quan, ghi "chưa tìm thấy trong các đoạn được truy xuất"; `not_found` không chứng minh nội dung vắng mặt trong toàn bộ tài liệu.

### S8. Giới hạn và phương pháp (mục tiêu trình bày ngoài Planner)

| Mục con | Nguồn sinh |
|---|---|
| S8.1 Chỉ tiêu không tính được | Danh sách `cannot_compute` kèm lý do |
| S8.2 Cảnh báo nhất quán kỳ | Mã `period_inconsistency` và ID nguồn |
| S8.3 Phạm vi và chế độ kế toán | Scope trong request; chế độ kế toán chỉ khẳng định khi có note nguồn đúng năm. Không tự gộp năm `general` với scope khác |
| S8.4 Công thức đã dùng | YoY, CAGR, biên, tỷ trọng, chênh lệch tuyệt đối |
| S8.5 Điều báo cáo không kết luận được | Nguyên nhân biến động, dự báo, so sánh với doanh nghiệp khác |

Luồng hiện có ghi `cannot_compute`, `data_gap` và cảnh báo kỳ trong từng section. Chưa có bước dựng riêng S8.1–S8.5 hoặc tổng hợp `planner_notes` vào báo cáo cuối.

### S9. Nguồn trích dẫn (mục tiêu trình bày ngoài Planner)

`evidence_by_id` có metadata nguồn để renderer gắn citation vào nội dung. Chưa có section S9 tổng hợp danh mục tài liệu, trang vật lý và trang in.

## 3. Trọng tâm theo đối tượng đọc

| Đối tượng | Giữ nguyên | Nhấn mạnh |
|---|---|---|
| Nhà đầu tư | S6, S7 | S3, S5 |
| Ban giám đốc | S6, S7 | S4 (S4.3, S4.4) |
| Kiểm toán/tuân thủ | S6, S7 | S2 |

LLM giữ S1–S7 và có thể điều chỉnh task/mục con dựa trên quan sát dữ liệu. Người dùng có thể sửa mục con trong bước HITL; ID, tiêu đề và mục tiêu của bảy section chính được giữ qua các revision. Task số phải được resolver phân giải duy nhất và đã được truy vấn; task note phải có quan sát cùng query/năm/nhóm tài liệu. Validator không bảo đảm mọi nội dung tham chiếu ở bảng trên đều xuất hiện trong outline đã duyệt.

## 4. Điều kiện từ chối hoặc dừng sớm (trước khi lập outline)

- Ticker ngoài corpus: từ chối.
- Ngân hàng (ABB, ACB, BAB, MSB, NAB, NVB): dừng, "chưa hỗ trợ bộ mã chuẩn".
- Cần kiểm tra thêm: bảo hiểm (PVI) và công ty chứng khoán dùng mẫu khác; chưa xác nhận bộ 12 chỉ tiêu áp dụng được.
- Scope yêu cầu thiếu năm (DHG, VCR, PAP): trả gợi ý scope có sẵn, chờ xác nhận, không tự gộp.

## 5. Giới hạn đã xác nhận và việc cần khảo sát thêm

1. `metric_name_resolver` hiện hỗ trợ 12 chỉ tiêu của template, gồm mã 61; chưa hỗ trợ 23, 62, 140, 320, 338 và 440. Planner ghi giới hạn và không tự gán mã thay thế.
2. Cần khảo sát tính nhất quán của mã vay nợ 320/338 giữa các ticker trước khi mở rộng resolver.
3. Cần đối chiếu mục lục B09 thực tế của HUT/GMD và chất lượng chunk để tinh chỉnh truy vấn S6–S7; một kết quả `not_found` chỉ nói về truy vấn đã thực hiện.
4. S1.1, S3.6, S4.5, S8 và S9 cần nguồn hoặc bước xử lý riêng nếu muốn xuất đúng toàn bộ nội dung trong bảng tham chiếu. Đây chưa phải dữ liệu mà Planner template hiện cung cấp.
