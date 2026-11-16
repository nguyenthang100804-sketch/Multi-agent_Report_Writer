# Kiểm tra ba điểm nguồn FPT cho W3

Đọc trực tiếp bảng `financial_facts` trong `data/facts_storage/financial_facts.duckdb` ở chế độ chỉ đọc, scope `consolidated`. Các giá trị dưới đây là dữ liệu parser lưu trong DuckDB, chưa phải đối chiếu ảnh PDF gốc.

| Chỉ tiêu | Năm | `raw_current` | `suspect` | Kết luận cho câu giới hạn |
|---|---:|---|---|---|
| Dòng tiền kinh doanh, mã 20 | 2022 | chuỗi rỗng | `False` | Dữ liệu trích xuất không có giá trị. |
| Dòng tiền kinh doanh, mã 20 | 2025 | chuỗi rỗng | `False` | Dữ liệu trích xuất không có giá trị. |
| Dòng tiền đầu tư, mã 30 | 2022 | chuỗi rỗng | `False` | Dữ liệu trích xuất không có giá trị. |
| Dòng tiền đầu tư, mã 30 | 2025 | chuỗi rỗng | `False` | Dữ liệu trích xuất không có giá trị. |

Cảnh báo `period_inconsistency:2024->2025` áp dụng cho **hai chỉ tiêu**: mã 20 có số năm 2024 trong báo cáo 2024 là `9.517.095.698.405` VND, còn cột năm trước của báo cáo 2025 là `11.703.777.188.868` VND; mã 30 lần lượt là `-6.548.374.165.711` và `-8.461.812.173.101` VND. Câu giới hạn mới nêu tên và hai giá trị của từng chỉ tiêu, kèm citation cho cả hai báo cáo.

Tổng tài sản mã 270 năm 2024 có `raw_current='71.999.995.678.620'` VND, `suspect=False`, `current_year=71.999.995.678.620` VND trong DuckDB. Bảng quy đổi và làm tròn đến hai chữ số thập phân theo tỷ đồng nên hiển thị **72.000,00 tỷ đồng**; đó không phải raw value đúng tròn 72.000 tỷ.

YoY tổng tài sản 2024 và 2025 lần lượt là **19,44%** và **22,42%**, được tính từ `value` gốc của từng năm trước bước làm tròn để hiển thị. `calculate_yoy()` dùng `Decimal(str(FactEvidence.value))`, còn bảng mới quy đổi và làm tròn; test đối chiếu trực tiếp các `input_evidence_ids` của hai `CalculationResult`.
