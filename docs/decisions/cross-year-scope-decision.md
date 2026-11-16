# Scope khác nhau theo năm: DHG và VCR

`available_scopes()` trên snapshot hiện tại:

| Ticker | Scope | Năm có fact không suspect |
|---|---|---|
| DHG | `consolidated` | 2022 |
| DHG | `general` | 2023, 2024, 2025 |
| VCR | `separate` | 2022 |
| VCR | `general` | 2023, 2024, 2025 |

Đây là nguyên nhân trực tiếp khiến yêu cầu **một scope cố định** cho 2022–2025 không có chuỗi đủ bốn năm ở hai ticker này. Nó không chứng minh các báo cáo ở các scope khác nhau tương đương về kinh tế.

**Quyết định hiện tại:** `check_coverage()` và Researcher tiếp tục dùng đúng scope người dùng yêu cầu, không tự gộp. Trước khi hỗ trợ DHG/VCR nhiều năm, cần bảng tương đương scope cấu hình **theo ticker và năm**, có người duy trì corpus xác nhận bằng báo cáo gốc. Báo cáo sinh ra từ bảng đó phải nêu các năm dùng báo cáo `general`. Chưa có bảng xác nhận nên DHG/VCR là giới hạn đã biết của demo; HUT/GMD không bị ảnh hưởng.

Kiểm tra toàn vẹn fact: mô phỏng parser FPT cũ và mới trên cùng bốn raw text cho kết quả 2022 `140→140`, 2023 `140→139`, 2024 `141→140`, 2025 `141→140`. Ba dòng bị bỏ đều là “Phân bổ cho:” với hai ô raw rỗng. Cộng 39 dòng bị bỏ ở lượt parse toàn corpus tiếp theo: **38.467 − 3 − 39 = 38.425**, đúng số fact DuckDB hiện tại.

[State OIL từ output tool thật](../examples/real-tool-report-state.json) đã được sinh lại từ DuckDB sau nạp lại, gồm cả `fact_index` hiện hành và snapshot ID. [State ABC](../examples/synthetic-report-state.json) là ví dụ tổng hợp, không đại diện cho corpus.
