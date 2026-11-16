# Audit cổng liên quan note HUT

Đo `_note_matches_topic()` trên năm chunk đầu đã lưu cho mỗi NotesTask trong `hut_research_state.json`. Phạm vi 11 truy vấn: 2 ở S1, 8 truy vấn ý kiến/nhấn mạnh ở S2, 1 truy vấn vay nợ ở S4; bốn task định danh kiểm toán viên S2 được tách khỏi phép đo này. [JSON audit](../../data/report_output/hut_note_gate_11_query_audit.json) ghi truy vấn, thứ hạng, chunk ID, trang in, quyết định giữ/loại và trích đoạn ngắn của cả 55 chunk. Đây là phát lại cổng trên fixture cục bộ, không gọi công cụ tìm kiếm hay model mới.

| Nhóm truy vấn | Chunk được giữ | Nhận xét khi đọc nguồn |
|---|---:|---|
| Ngành nghề và cơ cấu S1 | 5/5 | Các bảng công ty con có nhãn ngành nghề; phù hợp chủ đề. |
| Cơ sở kế toán S1 | 3/5 | Có đoạn về chế độ kế toán; một đoạn hợp nhất chung cũng được giữ. |
| Ý kiến kiểm toán S2, bốn năm | 4/20 | Mỗi năm giữ một chunk nói về cơ sở và tiêu đề ý kiến, nhưng loại đoạn kết luận bắt đầu “Theo ý kiến của chúng tôi”. |
| Vấn đề nhấn mạnh S2, bốn năm | 0/20 | Không chunk nào khớp cụm từ khóa; không suy ra báo cáo gốc không có vấn đề nhấn mạnh. |
| Điều khoản và kỳ hạn vay S4 | 2/5 | Hai chunk giữ lại nói về chính sách ghi nhận và chi phí lãi vay, chưa cung cấp điều khoản/kỳ hạn của khoản vay cụ thể. |
| **Tổng** | **14/55** | **7/11** truy vấn còn ít nhất một chunk sau cổng. |

Cổng hiện dùng trùng khớp cụm từ trong toàn chunk. Cách này nhận tiêu đề “Ý kiến của Kiểm toán viên” ở cuối một chunk nhưng bỏ đoạn kết luận ở chunk kế tiếp, đồng thời nhận từ “kỳ hạn” trong chính sách kế toán như bằng chứng cho điều khoản vay cụ thể. Tỷ lệ 14/55 là **tỷ lệ giữ**, không phải precision hoặc recall vì chưa có nhãn đúng/sai đầy đủ cho 55 chunk.

Trước W6 cần đánh giá độ liên quan ở mức đoạn trích, gắn nhãn các chunk/đoạn đại diện và sửa cổng để giữ đoạn kết luận kiểm toán thực sự, không chỉ tiêu đề. Với truy vấn không có đoạn phù hợp, Researcher phải thể hiện `not_found`; Writer không được suy diễn rằng báo cáo gốc không có thông tin.

## Nhãn và lần đo sau sửa

Đã gắn nhãn sơ bộ cả 55 cặp truy vấn–chunk HUT trong [JSON audit](../../data/report_output/hut_note_gate_11_query_audit.json): 11 `direct`, 42 `context`, 2 `unrelated`. Nhãn `direct` nghĩa là chính chunk trả lời được truy vấn; `context` chỉ giúp định vị hoặc cung cấp nền, không được trích làm câu trả lời; `unrelated` khác chủ đề. Mỗi cặp có lý do nhãn. Đây là nhãn thủ công của một lượt đọc dự án, chưa có người chấm thứ hai.

| Cổng trên 55 cặp HUT | Trước sửa | Sau sửa |
|---|---:|---:|
| Chunk được giữ | 14 | 11 |
| Chunk trả lời trực tiếp được giữ | 7/11 | 11/11 |
| Precision theo nhãn `direct` | 7/14 = 50,0% | 11/11 = 100% |
| Recall theo nhãn `direct` trong top-5 đã lưu | 7/11 = 63,6% | 11/11 = 100% |

Cổng mới dùng chuẩn hóa Unicode/bỏ dấu chung với BM25 và dung sai một ký tự trong cụm dài. Ý kiến kiểm toán cần đoạn kết luận “Theo ý kiến của chúng tôi … phản ánh trung thực”; tiêu đề đơn lẻ không đủ. Cơ sở kế toán và điều khoản vay dùng quy tắc riêng; vay nợ đòi dấu hiệu số dư/lãi suất/kỳ hạn cùng số liệu trong một đoạn, nên chính sách ghi nhận chung không được coi là câu trả lời. [GMD đối chiếu](../../data/report_output/gmd_note_gate_11_query_holdout.json) có 55 cặp gắn nhãn sơ bộ: giữ 10, gồm 9 `direct` và 1 `context` (precision 90%, recall 9/9 trong top-5). Kết quả này chỉ áp dụng cho chunk đầu đã truy xuất; không đo được recall trên toàn báo cáo.

S2 giờ đọc **toàn bộ** chunk `AUDIT_REPORT` theo ticker/năm/scope qua tầng tool, không gọi tìm kiếm top-5. [Danh sách HUT/GMD 2022–2025](../../data/report_output/audit_sections_hut_gmd_full_read.json) có 5–6 chunk mỗi năm và một chunk chứa kết luận ý kiến mỗi năm; chunk được giữ nguyên và gắn vai trò như `opinion_conclusion`, `opinion_basis`, `responsibility`, `signature`. Nếu toàn mục đã trích xuất không có chunk `emphasis`, Researcher trả `no_evidence` với lý do “không tìm thấy trong toàn bộ mục kiểm toán đã trích xuất”; đây không phải khẳng định báo cáo gốc không có vấn đề nhấn mạnh. Đường tool thật đã được kiểm với HUT/GMD 2025.

## Rào cản chỉ mục của S7

> Cập nhật 09/11/2026: chỉ mục `v2.1` đã sửa phân loại thuyết minh và được kích hoạt. Đánh giá S7 trên HUT/GMD/FPT cùng 20 nhãn của người thứ hai, các lỗi cổng và trạng thái W6 nằm trong [kiểm tra tác động v2.1](notes-classification-audit.md). Phần dưới ghi lại rào cản lịch sử của chỉ mục v1.

Trong `HUT_2025_Hopnhat.json`, “bên liên quan” xuất hiện trong 20 chunk, tới `HUT_2025_Hopnhat_chunk_0204` (trang in 64). Tuy nhiên các chunk thuyết minh chi tiết thuộc mục V–VII bị gắn `section=BALANCE_SHEET`, `INCOME_STATEMENT` hoặc `CASH_FLOW`; retriever định tính hiện chỉ lập chỉ mục `NOTES`, `AUDIT_REPORT`, `MANAGEMENT_REPORT`. Đây là lỗi phân loại section/index, không phải thiếu nội dung trong JSON. Cần sửa phân loại và dựng lại chỉ mục trước khi dùng truy vấn S7 hoặc đánh giá `not_found` của S7. Vì vậy chưa viết W6 ở chế độ trích đoạn.
