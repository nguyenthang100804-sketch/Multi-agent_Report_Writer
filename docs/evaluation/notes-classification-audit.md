# Kiểm tra tác động phân loại thuyết minh (141 tài liệu)

Trạng thái 09/11/2026: **snapshot `v2.1` đã được kích hoạt** qua `configs/active_corpus.json`. JSON, DuckDB, collection và manifest v1 vẫn được giữ để so A/B; bản con trỏ trước chuyển ở `configs/active_corpus_v1_backup.json`.

## Phạm vi và sửa lỗi

Parser giữ trạng thái `NOTES` sau tiêu đề thuyết minh. Một tiêu đề báo cáo chính xuất hiện sau đó chỉ được chuyển mục khi cùng block có mã biểu mẫu tương ứng: `B01/B02/B03` cho doanh nghiệp, `B02/B03/B04-TCTD` cho ngân hàng. Mã `B09` của thuyết minh không cho phép chuyển mục. Các trường hợp MCH 2024 và MVN 2023 được parse lại riêng sau khi phát hiện lỗi `B09`; bản candidate trước đó được giữ tại `data/report_output/notes_section_candidate_pre_form_guard`.

Candidate cuối: `data/processed_chunks_section_candidate` (141 JSON), `data/report_output/financial_facts_section_candidate_v2.duckdb` (18.540 fact).

Bản parse cuối với metadata thống nhất `parser_version=v2.1` nằm ở `data/processed_chunks_v2_1` và `data/report_output/financial_facts_v2_1.duckdb`. Cả 141 tài liệu là `AUTO_INDEX`; 32.175 chunk và 18.540 fact. So với candidate trước, dữ liệu của 139 tài liệu giống hệt ngoài `parser_version`; hai tài liệu MCH/MVN chỉ khác thêm đường dẫn `source_file` do bản parse thử dùng bản sao của raw file.

| Phép đo | Kết quả |
|---|---:|
| Tài liệu có chunk đổi section theo nội dung khớp duy nhất | 88/141 |
| Chunk khớp nội dung duy nhất | 28.025 |
| Chunk trong nhóm đó chuyển về `NOTES` | 1.615 |
| `BALANCE_SHEET → NOTES` | 1.125 |
| `INCOME_STATEMENT → NOTES` | 121 |
| `CASH_FLOW → NOTES` | 369 |
| Chunk khớp nội dung có `embed_text` đổi | 672 |
| Fact bị loại so với corpus hiện hành | 19.885 |
| Fact thêm mới | 0 |
| Fact bị loại trước trang `NOTES` đầu tiên | 0 |

Các số chunk ở đây dùng nội dung thân chunk khớp duy nhất, không dựa vào `chunk_id` vì rechunking có thể làm ID dịch. Sau `NOTES` đầu tiên, candidate chỉ còn 15 chunk mang nhãn báo cáo chính trong NVB 2022; chúng nằm ở biểu mẫu ngân hàng thật sau một đoạn `NOTES` đầu tài liệu, không phải thuyết minh chi tiết. Cả 141 tài liệu vẫn có đủ ba báo cáo chính.

Năm chuỗi GVR từng không an toàn (mã 10, 20, 50, 60, 61) chuyển sang an toàn trong phạm vi chọn một scope tốt nhất cho mỗi ticker. Kiểm tra **mọi scope** phát hiện thêm ba chuỗi MVN hợp nhất (mã 270, 400 và 30) chuyển `ambiguous → ok`; vì vậy tổng tác động theo mọi scope là tám nhóm chuỗi. Không có chuỗi an toàn nào chuyển thành không an toàn. OIL mã 34 năm 2025 vẫn mơ hồ. Kiểm tra golden facts trên DB candidate v2: Type A exact/page 58/58; Type C 14/14 chuỗi, 56/56 điểm năm. Benchmark hiện hành và candidate trước sửa `B09` cũng có cùng kết quả.

## Kiểm tra fact và đẳng thức theo tài liệu

Phân bố 141 tài liệu: 56 không mất fact; bốn tài liệu mất trên 80% fact được trích xuất trước đây: HUT 2024 (655/804), HUT 2025 (765/915), LGC 2023 (503/617), LGC 2025 (462/571). Đây là các báo cáo có nhiều bảng thuyết minh từng bị gắn nhãn bảng cân đối. Danh sách đầy đủ theo tài liệu ở `data/report_output/notes_candidate_fact_distribution.csv`.

Đã đọc mẫu các fact bị loại, lưu toàn bộ danh sách của ba tài liệu tại `data/report_output/notes_candidate_removed_fact_samples.json`:

| Tài liệu | Fact bị loại | Ví dụ và vị trí |
|---|---:|---|
| HUT 2025 | 765 | `Tiền mặt`, `Tiền gửi ngân hàng`, trang 32, thuộc bản thuyết minh |
| GVR 2023 | 476 | `Tiền mặt`, `Tiền gửi ngân hàng không kỳ hạn`, trang 41, thuộc bản thuyết minh |
| BAB 2025 (ngân hàng) | 63 | `Tiền mặt bằng VND`, `Tiền gửi thanh toán tại NHNN`, trang 24, mục thuyết minh 4.20 |

Gating vẫn 141/141 `AUTO_INDEX`. Có đúng một tài liệu đổi số phép kiểm: GVR 2023 từ 32/32 xuống 30/30. Hai phép kiểm bị loại dùng dòng thuyết minh trang 75–76 bị nhận nhầm thành báo cáo kết quả kinh doanh; chúng từng được đánh dấu `passed` bằng ghi chú xác nhận OCR mặc dù vế trái và phải khác nhau. Không phép kiểm chung nào đổi kết quả. Chi tiết ở `data/report_output/notes_candidate_quality_differences.json`.

Đã so từng dòng của 12 chỉ tiêu chuẩn trên 35 mã và mọi scope hiện có theo `(fiscal_year, value, physical_page, citation_tag, raw_current, suspect)`. Có tám nhóm ticker/scope/chỉ tiêu khác biệt, tất cả là **loại dòng thuyết minh bị nhận nhầm**, không có dòng mới: năm nhóm GVR đã nêu và ba nhóm MVN (`Tổng tài sản`, `Vốn chủ sở hữu`, `Lưu chuyển tiền thuần từ hoạt động đầu tư`). Các dòng MVN trang 69 và 76 nằm trong thuyết minh mục 38 “Số liệu so sánh”, bảng điều chỉnh hồi tố năm 2022. HUT và GMD không đổi một dòng nào trong 12 chỉ tiêu. Danh sách giá trị, trang và citation cụ thể ở `data/report_output/notes_candidate_metric_differences.json`.

## Vì sao số chunk tăng

Tổng chunk tăng 30.282 → 32.175 (+1.893), gồm text +1.190 và table +703. Đây không chỉ là đổi metadata: `step4_detect_structure` chỉ hợp nhất bảng liên trang khi block mang nhãn một trong ba báo cáo chính; bảng thuyết minh nay mang nhãn `NOTES` nên không còn bị hợp nhất sai theo quy tắc đó. `step6_chunk_document` cũng gộp đoạn văn theo cùng `section` và cắt theo giới hạn ký tự; đổi ranh giới section, tiêu đề trong tiền tố và bảng đầu vào có thể làm điểm cắt thay đổi. Vì vậy `chunk_id` dịch và có hash `embed_text` mới. Các số +1.190/+703 là chênh lệch theo loại chunk; chưa quy toàn bộ +1.893 cho riêng từng cơ chế.

## Dựng chỉ mục, benchmark và chuyển snapshot

Candidate có 32.175 chunk, trong đó khoảng 4.499 hash `embed_text` mới (4.632 lần xuất hiện). Benchmark BGE-M3 trên CPU: 200 chunk/39.869 token trong 107,19 giây; pipeline cũ ước lượng 4,47 giờ nếu tính lại toàn corpus. Cache mới tái dùng vector theo `content_hash` từ 141 Parquet cũ và chỉ tính hash mới, ghi kết quả vào `data/vector_cache_section_v2_1/bge_m3`. Mẫu thực tế: ABB 326/326, BAB 195/195, BWE 194/194 vector chung giống từng bit. Dựng collection mới `vnfin_v2_1_bge_m3_v1` mất 2.935 giây; collection cũ không bị xóa hoặc nạp đè.

`--reconcile-only` độc lập báo `PASSED`: JSON 32.175 chunk/141 tài liệu, Parquet 32.175 hàng/141 tài liệu, Qdrant 32.175 điểm với tập `chunk_id` khớp. Manifest mới ghi `parser_version=v2.1`. Golden facts trên DB v2.1: Type A exact/page 58/58; Type C 14/14 chuỗi và 56/56 điểm năm.

Nhãn golden DEV được ánh xạ theo nội dung và trang vào `data/report_output/golden_dev_v2_1.json`: 92 câu, ba ID thay đổi trong một câu VEA, không ID nào chưa ánh xạ. Tập TEST không chạy. DEV `hybrid_filtered` trên v2.1: loại A Hit@5 35/42, MRR 0,5140 (v1: 35/42, 0,5015); loại B Hit@5 33/36, MRR 0,8163 (v1: 32/36, 0,8151). Chi tiết ở `data/report_output/retrieval_dev_v2_1_hybrid_filtered.json`.

Research state và báo cáo TemplateWriter HUT, GMD, FPT được sinh lại trong `data/report_output/v2_1_fixtures`; S3–S5 đều qua Verifier 3/3. Các log đánh giá Gemini cũ là kết quả lịch sử của snapshot v1 và không được tính là đánh giá v2.1.
Planner tất định trên ba mã trả `ready`, mỗi mã có S1–S5, 32 research task và 23 calculation spec (`planner_smoke.json`). Smoke test qua runtime mặc định sau chuyển: DuckDB chứa 18.540 fact, HUT mã 10 năm 2025 trả một fact, truy vấn note bên liên quan HUT trả 5 chunk và hạng đầu ở trang 63. `check_snapshot_on_resume()` từ chối fixture HUT v1 và nhận cả ba fixture v2.1. Toàn bộ 152 unit test qua sau chuyển; test ví dụ OIL lịch sử vẫn dùng DB v1 để kiểm provenance của fixture cũ.

Đã truy vấn S7 2025 cho HUT/GMD/FPT trên index v2.1: 12 truy vấn × top 5 = 60 cặp, cổng giữ 24/60. Đây là tỷ lệ giữ, **không phải** precision hay recall. Dữ liệu ở `data/report_output/s7_note_pairs_v2_1.json`; phiếu 20 cặp mù ở `data/report_output/s7_second_annotator_packet_v2_1.md`. Hai bộ nhãn độc lập trên cùng 20 cặp đã được đối chiếu bên dưới. Writer chế độ trích đoạn đã được cài đặt sau phép đo này; phần dưới vẫn là đánh giá cổng Researcher trước khi dùng S7 trong báo cáo hoàn chỉnh.

| Mã | Bên liên quan | Rủi ro tài chính | Cam kết | Sự kiện sau niên độ |
|---|---:|---:|---:|---:|
| HUT | 4/5 | 0/5 | 2/5 | 2/5 |
| GMD | 5/5 | 0/5 | 1/5 | 1/5 |
| FPT | 4/5 | 2/5 | 2/5 | 1/5 |

HUT/GMD không có chunk vượt cổng cho truy vấn rủi ro tài chính trong top 5; chưa thể suy ra báo cáo gốc không có thông tin đó. Nhãn độc lập cần xác định liệu đây là thiếu recall của retriever hay của cổng.

### Nhãn của người thứ hai (20 cặp, 09/11/2026)

Người dùng cung cấp 20 nhãn độc lập cho phiếu trên: 7 `direct`, 6 `context`, 7 `unrelated`. Đối chiếu quyết định cổng **trước sửa**: TP 6, FP 1, FN 1, TN 12; precision và recall trên **mẫu 20 cặp trong top 5** đều 6/7 = 85,7%. Cặp 01 là nghĩa vụ hoàn nguyên đất thuê bị bỏ sót do tiêu đề OCR “NỘ TIỂM TÀNG”; cặp 03 là chính sách kế toán ngoại tệ được giữ nhầm vì chứa “rủi ro tỷ giá”. Nhãn, lý do và ánh xạ chunk ở `data/report_output/s7_second_annotator_labels_v2_1.json`.

Đã thêm cụm `nghĩa vụ hoàn nguyên` cho chủ đề cam kết và loại đoạn chính sách kế toán khỏi chủ đề rủi ro tài chính nếu không có mục quản lý rủi ro. Phát lại toàn bộ 60 cặp làm đổi đúng ba quyết định: FPT cam kết hạng 1 và 4 được giữ thêm; FPT rủi ro hạng 1 bị loại. Cổng giữ 25/60 sau sửa. Trên **chính 20 nhãn dùng để tìm lỗi**, TP 7, FP 0, FN 0, TN 13; đây là test hồi quy, không phải đánh giá độc lập về mức tổng quát. Chi tiết phát lại ở `data/report_output/s7_note_gate_replay_v2_1.json`.

### Độ đồng thuận giữa hai người gắn nhãn (20 cặp, 09/11/2026)

Người dùng cung cấp phiếu của người thứ nhất trên đúng 20 cặp: 4 `direct`, 11 `context`, 5 `unrelated`. Phiếu nguyên văn ở `data/report_output/s7_first_annotator_raw_v2_1.md`; nhãn và lý do được tách ở `data/report_output/s7_first_annotator_labels_v2_1.json`. Đã kiểm ID chunk của từng cặp khớp phiếu người thứ hai. Hai người trùng **13/20 nhãn (65%)**; κ Cohen ba lớp **0,483**. Nếu chỉ tách `direct`/không `direct`, hai người trùng **15/20 (75%)**, κ **0,390**. Mẫu 20 cặp được chọn có chủ đích từ top 5, nên các tỷ lệ này mô tả đúng mẫu, không ước lượng toàn corpus.

| Nhãn người thứ nhất \ người thứ hai | `direct` | `context` | `unrelated` |
|---|---:|---:|---:|
| `direct` | 3 | 1 | 0 |
| `context` | 4 | 5 | 2 |
| `unrelated` | 0 | 0 | 5 |

Bảy bất đồng ở cặp **02, 03, 06, 07, 12, 17, 18**. Cặp 02, 06, 12, 17 chủ yếu là tiêu đề/câu dẫn hoặc lời dẫn trước bảng: người thứ hai coi là trả lời trực tiếp ở mức chủ đề, người thứ nhất yêu cầu nội dung đủ để viết một nhận định cụ thể. Cặp 03 ngược lại: đoạn chính sách FPT thực sự nói các khoản vay ngoại tệ được phòng ngừa bằng giao dịch hoán đổi và mua ngoại tệ tương lai; người thứ nhất coi đây là câu trả lời cụ thể cho rủi ro tỷ giá, người thứ hai chỉ xem là bối cảnh vì không thuộc mục quản lý rủi ro. Cặp 07 và 18 khác nhau ở ranh giới `context`/`unrelated`, không ảnh hưởng phép đo nhị phân `direct`.

Với **nhãn người thứ nhất**, cổng sau sửa có TP 3, FP 4, FN 1, TN 12: precision **3/7 = 42,9%**, recall **3/4 = 75%** trên mẫu. Với nhãn người thứ hai, cùng cổng có TP 7, FP 0, FN 0, TN 13. Chênh lệch này là do định nghĩa `direct` chưa thống nhất; không dùng mức 7/7 để tuyên bố cổng đã đạt. Sau khi đối chiếu hai bộ nhãn, tiêu chí W6 được chốt: `direct` nghĩa là chunk đủ cho **một nhận định cụ thể có citation**. Cổng Researcher được đánh giá theo khả năng giữ lại các đoạn này; quyết định claim có được note hỗ trợ thuộc Verifier ngữ nghĩa mức `full`. Đặc biệt, quy tắc loại chính sách kế toán đã bỏ cặp 03 dù đoạn có câu về biện pháp phòng ngừa tỷ giá. Bốn mươi cặp còn lại chưa gắn nhãn, và recall ngoài top 5 chưa được đo.

### Cổng ưu tiên recall theo định nghĩa W6

Đã cho phép đoạn chính sách kế toán có câu nêu rõ biện pháp **phòng ngừa rủi ro tỷ giá** đi qua cổng. Phát lại 60 cặp trên snapshot v2.1: cổng giữ **26/60**. Trên 20 cặp đã gắn nhãn theo định nghĩa chặt: **TP 4, FP 3, FN 0, TN 13**, tức recall **4/4** và precision **4/7** trong đúng mẫu đó. Đây là phép phát lại trên dữ liệu đã dùng để phát hiện lỗi, không phải hold-out. Quyết định từng cặp được lưu tại `data/report_output/s7_note_gate_replay_recall_v2_1.json`; file replay trước đó được giữ làm mốc lịch sử.

Cổng chỉ giảm nhiễu truy xuất; Writer chọn trích đoạn nguyên văn, còn Verifier ngữ nghĩa đối chiếu **nhận định cụ thể** với chính đoạn được dẫn. Do đó, precision của cổng không được dùng làm điều kiện hoàn tất W6; vẫn cần đo recall ngoài top 5 và kiểm claim định tính đầu cuối trước khi đưa báo cáo cho người đọc.
