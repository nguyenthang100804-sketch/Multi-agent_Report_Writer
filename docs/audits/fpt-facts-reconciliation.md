# Kiểm tra sau khi parse lại FPT

`src.indexing.pipeline --reconcile-only`: 141/141 tài liệu, 30.282/30.282 chunk, ID chunk khớp, trạng thái `PASSED`. Lệnh này chỉ kiểm số lượng và ID.

Đối chiếu bổ sung bằng `scripts.inspection.check_fpt_hashes`: cả bốn báo cáo FPT năm 2022–2025 có cùng tập `chunk_id` và **0 `content_hash` khác nhau** giữa JSON parser, Parquet cache và Qdrant. Sau đó parse lại **cả 141 báo cáo** vào thư mục ứng viên và dùng `scripts.analysis.compare_candidate_corpus`: **39 fact bị bỏ, 0 fact thêm, 0 tài liệu đổi hash chunk**. Mọi fact bị bỏ đều có nhãn kết thúc bằng `:` và `raw_current=''`, `raw_prior=''`; đa số là tiêu đề “Điều chỉnh cho các khoản:”. JSON ứng viên đã thay JSON hiện hành, DuckDB đã nạp lại **38.425 fact**, và thư mục ứng viên đã được dọn. Không cần rebuild Qdrant/Parquet vì text dùng cho embedding không đổi.

Điều kiện bỏ dòng tiêu đề hiện kiểm **hai chuỗi raw rỗng**, không kiểm hai giá trị số sau parse. Test xác nhận ô raw có chữ hoặc dấu chú thích không bị bỏ dù phép parse trả null. [Danh sách 39 dòng bị bỏ](empty-heading-facts-audit.md) đã được lưu cùng audit.
