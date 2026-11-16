# Kiểm tra nguồn HUT 2022–2023

Nguồn kiểm tra là văn bản đã trích xuất từ hai báo cáo kiểm toán hợp nhất trong `data/raw_docs/top_100/HUT`. Workspace không có PDF gốc của hai báo cáo này, nên đây là kiểm tra nội dung trang theo dấu `[P.11]`, chưa phải đối chiếu ảnh trang PDF.

| Nguồn | Vị trí trong văn bản trích xuất | Phạm vi và đơn vị | Doanh thu thuần mã 10 |
|---|---|---|---:|
| HUT 2022 | `[P.11]`, dòng 401–414 | Kết quả kinh doanh **hợp nhất**, `Đơn vị tính: VND` | Năm nay `1.073.161.354.752` VND |
| HUT 2023 | `[P.11]`, dòng 429–442 | Kết quả kinh doanh **hợp nhất**, `Đơn vị tính: VND` | Năm nay `10.981.750.221.964` VND; năm trước `1.073.161.354.752` VND |

Cột năm trước trong báo cáo 2023 khớp đúng số năm nay của báo cáo 2022. Tính `(10.981.750.221.964 / 1.073.161.354.752 - 1) × 100` rồi làm tròn hai chữ số thập phân được `923,31%`, khớp `CalculationResult` của Researcher. Kiểm tra này xác nhận phép trích số, đơn vị và phạm vi; nó không xác định nguyên nhân biến động hoặc tính so sánh kinh tế giữa hai kỳ.
