# Kiểm tra nhất quán kỳ của corpus facts

## Kết quả quét

Chạy `python -m scripts.audits.audit_period_consistency` trên DuckDB hiện có tạo [danh sách đầy đủ 1.298 cờ](../../evaluation/audits/period_consistency_issues.csv). Hàm quét đọc toàn bộ facts 2022–2025, không sửa database hoặc giá trị nguồn.

| Chỉ số | Kết quả |
|---|---:|
| Nhóm chỉ tiêu/năm có thể đối chiếu | 16.262 |
| Nhóm không khớp (`period_inconsistency`) | 1.298 (7,98%) |
| Trong đó có nhiều dòng ở ít nhất một năm | 392 |
| Chỉ tiêu có mã số | 335 |
| Chỉ tiêu không mã, ghép theo nhãn chuẩn hóa | 963 |
| Bảng cân đối kế toán | 843 |
| Kết quả kinh doanh | 235 |
| Lưu chuyển tiền tệ | 220 |
| Một giá trị đổi dấu đúng bằng nhau | 29 |

Quy tắc: nhóm theo ticker, scope, loại báo cáo và mã chỉ tiêu; với dòng không mã, dùng nhãn chuẩn hóa. Với mỗi năm `t`, so tập giá trị `current_year` của năm đó với tập `prior_year` trong báo cáo `t+1`. Chỉ so khi cả hai phía có số, cùng đơn vị và không bị đánh dấu `suspect`. Nếu hai tập không giao nhau, ghi một cờ. Nhiều dòng được giữ và đánh dấu `ambiguous_rows`; không chọn một dòng. Đây là **bộ lọc để rà soát**, không phải kết luận rằng mọi cờ là lỗi parser: báo cáo có thể trình bày lại số so sánh, đổi quy ước dấu hoặc dùng cùng mã cho ngữ cảnh khác.

## Đối chiếu OIL 2025 trực tiếp với raw text

Trong `data/raw_docs/top_100/OIL/2025/OIL_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt`, trang vật lý 13, dòng 520–535:

| Vị trí | Dòng mã `34` | Năm nay | Năm trước |
|---|---|---:|---:|
| Bảng lưu chuyển tiền tệ chính, dòng 521 | Tiền trả nợ gốc vay `(*)` | −885.348.286.243 VND | −4.170.391.674.018 VND |
| Bảng bổ sung sau phần giải thích, dòng 535 | Tiền trả nợ gốc vay | −39.144.671.502.995 VND | −28.154.928.419.321 VND |

Đoạn giải thích ở dòng 531 nói giao dịch vay/trả ngắn hạn dưới ba tháng được trình bày **trên cơ sở thuần** trong lưu chuyển tiền tệ phía trên; bảng sau cung cấp thêm thông tin về tiền vay và trả nợ của nhóm hợp đồng đó. Hai con số không phải hai lần OCR của cùng một ô. Parser đã trích được cả hai số nhưng fact schema/tool hiện không gắn vai trò “bảng chính” hay “bảng bổ sung”; truy vấn chỉ theo mã `34` vì vậy trả hai dòng và phải được coi là mơ hồ. Không được chọn dòng theo nhãn `(*)` một cách tự phát.

Báo cáo OIL 2024 ghi giá trị năm 2024 của mã `34` là −32.325.320.093.339 VND. Cả hai số `prior_year` năm 2025 đều khác số này. Thay đổi cách trình bày thuần/gộp nêu ở tài liệu 2025 là một lời giải thích khả dĩ; cần đối chiếu thêm thuyết minh trước khi khẳng định có trình bày lại hoặc lỗi parser. Báo cáo 2023 và 2024 của mã này vẫn khớp theo quy tắc đối chiếu kỳ.

## Ảnh hưởng tới báo cáo

`record_tool_result()` chuyển sai khác phát hiện trong một chuỗi tool thành cảnh báo `period_inconsistency:t->t+1`. Các phép tính chặn đầu vào có cảnh báo này. Với nhiều dòng nguồn, `next_action=declare_limitation`; [state OIL thật](../examples/real-tool-report-state.json) kết thúc `incomplete` kèm cả năm dòng nguồn và citation, không hỏi người dùng chọn một số. Verifier xác định cũng ghi issue `period_mismatch` để nguồn được rà soát trước khi phê duyệt claim.

Những cờ trong CSV cần phân loại tiếp theo nguyên nhân (trình bày lại, đổi dấu, dòng bổ sung, parser sai, ghép nhãn sai). Tỷ lệ 7,98% cho thấy không nên dùng kiểm tra này làm quy tắc tự sửa số hoặc tự loại mọi dòng khỏi corpus.
