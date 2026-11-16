# Khảo sát 12 chỉ tiêu chuẩn cho 5 ticker demo

Chạy `\.venv\Scripts\python.exe -m scripts.audits.audit_metric_safety` trên DuckDB hiện có, scope `consolidated`, giai đoạn 2022–2025. Mỗi ô là kết quả `safe_for_calculation`; `✓` là `true`, `—` là `false`.

| Chỉ tiêu | FPT | HUT | GVR | GMD | OIL |
|---|:---:|:---:|:---:|:---:|:---:|
| Doanh thu thuần | ✓ | ✓ | — | ✓ | ✓ |
| Lợi nhuận gộp | ✓ | ✓ | — | ✓ | ✓ |
| Lợi nhuận trước thuế | ✓ | ✓ | — | ✓ | ✓ |
| Lợi nhuận sau thuế | ✓ | ✓ | — | ✓ | ✓ |
| Lợi nhuận sau thuế của cổ đông công ty mẹ | — | ✓ | — | ✓ | ✓ |
| Tổng tài sản | ✓ | ✓ | ✓ | ✓ | ✓ |
| Nợ phải trả | ✓ | ✓ | ✓ | ✓ | ✓ |
| Vốn chủ sở hữu | ✓ | ✓ | ✓ | ✓ | ✓ |
| Tiền và các khoản tương đương tiền | ✓ | ✓ | ✓ | ✓ | ✓ |
| Lưu chuyển tiền thuần từ hoạt động kinh doanh | — | ✓ | ✓ | ✓ | ✓ |
| Lưu chuyển tiền thuần từ hoạt động đầu tư | — | ✓ | ✓ | ✓ | ✓ |
| Lưu chuyển tiền thuần từ hoạt động tài chính | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Tổng an toàn** | **9/12** | **12/12** | **7/12** | **12/12** | **12/12** |

FPT có một chuỗi trùng năm 2023 và hai chuỗi lưu chuyển tiền tệ `partial`; GVR có năm chuỗi `ambiguous` do dòng trùng năm 2023. HUT và GMD sạch trong bộ 12 chỉ tiêu này. OIL sạch trong bộ 12 chỉ tiêu, nhưng ca dòng trùng mã `34` đã ghi ở ví dụ riêng và không thuộc bộ resolver. Kết quả này chưa chứng minh `table_role` không cần cho toàn corpus; với demo, có thể chọn HUT/GMD hoặc chín chuỗi FPT an toàn và giữ nhánh giới hạn cho dữ liệu mơ hồ.

`safe_for_calculation=true` là điều kiện ban đầu của tool. Hàm tính còn kiểm tra cảnh báo lệch kỳ, mẫu số 0, dấu của CAGR và năm đầu vào; vì thế dấu ✓ không bảo đảm mọi phép tính đều thành công.
