# Writer W6: đánh giá LLM định tính trên Dev

Ngày 09/11/2026, snapshot v2.1. Thử `GeminiWriterModel` với S1, S2, S6, S7 của FPT, HUT, GMD. Mỗi lời gọi nhận SectionView của đúng section và các note chunk Researcher đã truy xuất. S3–S5 không tham gia phép đo này và hợp đồng Writer định lượng không thay đổi. Log phản hồi thô, draft, kết quả Verifier tất định và Markdown của từng section nằm trong [`qualitative_llm_dev_20261109`](../../data/report_output/v2_1_fixtures/qualitative_llm_dev_20261109). Script chạy lại bỏ qua kết quả đã có để giữ nguyên phản hồi. Ba [báo cáo mẫu S1–S7](../../data/report_output/v2_1_fixtures/qualitative_llm_dev_20261109/full_samples) ghép phần định tính mới với phần định lượng TemplateWriter v2.1 đã kiểm trước đó; mỗi section có SectionView riêng cho Verifier ngữ nghĩa. Các báo cáo ghép này không đo lại LLM S3–S5.

| Chỉ số | Kết quả |
|---|---:|
| Section qua Verifier tất định | 12/12 |
| Section do LLM viết, không tính fallback | 12/12 |
| Qua ngay lượt đầu | 10/12 |
| Cần một lượt sửa | 2/12 (HUT S1, S2) |
| Fallback | 0 |
| Claim định tính được sinh | 39 |
| Tổng thời gian model và validate theo log | 83,03 giây |
| Token API báo cáo | 84.643 tổng; 76.642 đầu vào, 8.001 đầu ra |

Ở lượt FPT S7 đầu tiên, model chọn được hai đoạn có nội dung nhưng Verifier từ chối vì menu `N:` cũ chỉ liệt kê các span do TemplateWriter chọn. Log đó được giữ với hậu tố `pre_menu`. Menu đã được sửa để cho phép span nguyên văn đủ độ dài từ note chunk thuộc section; lần chạy sau qua ngay lượt đầu. HUT S1 ban đầu dùng hai block cho cùng một task; lượt sửa bỏ block trùng. HUT S2 ban đầu chọn tên công ty kiểm toán ngắn hơn độ dài quote tối thiểu; lượt sửa chọn đoạn dài hơn.

Đọc mẫu cho thấy S6 và S7 có nhận định cụ thể hơn đường trích đoạn cố định: FPT chọn chính sách ghi nhận doanh thu và phòng ngừa rủi ro tỷ giá; GMD chọn giao dịch với bên liên quan, tài sản bảo đảm và sự kiện sau niên độ. S2 còn lặp ý kiến chấp nhận toàn phần qua các năm bằng những đoạn quote dài. Một số câu về đơn vị kiểm toán chung chung, không nêu tên dù quote có thông tin; đây là vấn đề chọn và diễn đạt nội dung, không được số liệu qua Verifier tất định phản ánh. Quote giữ nguyên OCR của nguồn nên vẫn có lỗi chữ trong văn bản trích dẫn.

Kết quả này đo tính hợp lệ của draft trên ba mã Dev, chưa đo mức độ hỗ trợ ngữ nghĩa của từng nhận định, độ bao phủ ngoài các chunk đã truy xuất hoặc giá trị đối với người đọc. Các draft là đầu vào thử cho Verifier ngữ nghĩa, chưa phải báo cáo hoàn tất. Bộ kiểm thử repository sau thay đổi: 171/171 đạt.
