# Kiểm tra dòng trùng năm 2023 của FPT và GVR

Truy vấn `query_time_series_tool` theo ticker, mã và `scope=consolidated`, năm 2023. So sánh giá trị, đơn vị, trang vật lý, nhãn và `fact_index`.

| Ticker / mã | Các dòng năm 2023 | Kết luận |
|---|---|---|
| FPT / `61` | Trang 13: “Phân bổ cho:” có giá trị `null` (`fact_index=102`); “Cổ đông của công ty mẹ” có `6.465.190.432.622 VND` (`fact_index=103`). | Khác nhãn và giá trị; dòng đầu có vẻ là dòng tiêu đề bị gán mã. Không thuộc trường hợp trùng hoàn toàn. |
| GVR / `10` | Trang 11: `22.138.403.152.486`; trang 75: `25.425.943.612.070`; trang 76: `−683.185.327.802 VND` với nhãn “Tăng, giảm hàng tồn kho”. | Giá trị và trang khác nhau; dòng trang 76 có vẻ bị gán nhầm mã. Không được gộp. |
| GVR / `20`, `50`, `60`, `61` | Mỗi mã có một dòng trang 11 và một dòng trang 75; giá trị hai dòng khác nhau (ví dụ mã `20`: `4.962.898.479.712` và `6.342.113.055.858 VND`). | Xung đột giữa các bảng/trang; cần xem vai trò bảng trước khi chọn nguồn. |

Không có nhóm nào là bản sao **giống hệt giá trị, đơn vị và trang**, nên không thêm quy tắc `identical_duplicate_rows_collapsed`. Parser nay bỏ dòng có nhãn kết thúc bằng `:` khi cả hai cột số đều null; đã parse lại bốn báo cáo FPT và nạp lại DuckDB. Mã `61` của FPT vẫn thiếu fact ở 2024–2025 nên chuỗi bốn năm vẫn `partial`, không tăng tỷ lệ 9/12. GVR trang 76 thực sự bị gán `INCOME_STATEMENT`, trong khi nhãn “Tăng, giảm hàng tồn kho” cũng có ở `CASH_FLOW` trang 12. Trang 75 chứa các giá trị khác trang 11; chưa chọn một trang làm nguồn chính. Với demo, giữ nhánh giới hạn thay vì tự chọn số.
