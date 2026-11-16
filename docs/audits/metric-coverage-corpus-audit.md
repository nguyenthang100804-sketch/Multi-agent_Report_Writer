# Khảo sát 12 chỉ tiêu chuẩn trên 35 ticker

Nguồn: DuckDB hiện có; mỗi ticker dùng scope có nhiều chuỗi safe nhất (ưu tiên consolidated khi hòa); chạy lại bằng `\.venv\Scripts\python.exe -m scripts.audits.audit_metric_safety`. Cột YoY truy vấn riêng cặp 2024–2025; CAGR dùng đủ 2022–2025. Các ticker ngân hàng vẫn nằm trong mẫu số 420 dù nhiều mã chuẩn không áp dụng.

| Ticker | Scope | Safe / 12 | YoY 2024→2025 / 12 | CAGR 2022→2025 / 12 |
|---|---|---:|---:|---:|
| ABB | consolidated | 0/12 | 0/12 | 0/12 |
| ACB | consolidated | 0/12 | 0/12 | 0/12 |
| BAB | consolidated | 0/12 | 0/12 | 0/12 |
| BSR | consolidated | 12/12 | 11/12 | 10/12 |
| BWE | consolidated | 12/12 | 11/12 | 10/12 |
| DCM | consolidated | 12/12 | 11/12 | 9/12 |
| DHG | consolidated | 0/12 | 0/12 | 0/12 |
| FPT | consolidated | 9/12 | 8/12 | 8/12 |
| GAS | consolidated | 12/12 | 11/12 | 10/12 |
| GEE | consolidated | 12/12 | 11/12 | 10/12 |
| GEX | consolidated | 12/12 | 10/12 | 10/12 |
| GMD | consolidated | 12/12 | 11/12 | 10/12 |
| GVR | consolidated | 7/12 | 11/12 | 2/12 |
| HAH | consolidated | 10/12 | 8/12 | 8/12 |
| HUT | consolidated | 12/12 | 11/12 | 9/12 |
| LGC | consolidated | 12/12 | 10/12 | 10/12 |
| MCH | consolidated | 11/12 | 10/12 | 9/12 |
| MSB | consolidated | 0/12 | 0/12 | 0/12 |
| MSN | consolidated | 10/12 | 11/12 | 8/12 |
| MVN | consolidated | 9/12 | 10/12 | 4/12 |
| NAB | consolidated | 0/12 | 0/12 | 0/12 |
| NVB | consolidated | 0/12 | 0/12 | 0/12 |
| OIL | consolidated | 12/12 | 10/12 | 9/12 |
| PAP | general | 9/12 | 7/12 | 6/12 |
| PET | consolidated | 9/12 | 9/12 | 9/12 |
| PVI | consolidated | 11/12 | 1/12 | 2/12 |
| PVT | consolidated | 7/12 | 6/12 | 6/12 |
| QNS | consolidated | 12/12 | 10/12 | 10/12 |
| SAB | consolidated | 11/12 | 10/12 | 8/12 |
| SJG | consolidated | 12/12 | 11/12 | 10/12 |
| SSH | consolidated | 12/12 | 11/12 | 8/12 |
| VCR | separate | 0/12 | 0/12 | 0/12 |
| VEA | consolidated | 12/12 | 10/12 | 10/12 |
| VIC | consolidated | 7/12 | 6/12 | 4/12 |
| VRE | consolidated | 11/12 | 11/12 | 8/12 |
| **Toàn corpus** | | **289/420** | **257/420** | **217/420** |

Loại sáu ngân hàng ABB, ACB, BAB, MSB, NAB, NVB khỏi mẫu số: doanh nghiệp phi ngân hàng có **289/348** chuỗi an toàn, **257/348** phép YoY và **217/348** phép CAGR tính được. PAP dùng `general` và đạt 9/12. DHG có `consolidated` chỉ năm 2022, `general` từ 2023–2025; VCR có `separate` chỉ năm 2022, `general` từ 2023–2025. Audit chọn scope để đo, nhưng pipeline báo cáo không tự đổi scope. Chưa có ma trận chỉ tiêu × phép tính trên đúng nhóm được Planner cho phép.
