# Giới thiệu giao diện Report Writer

Report Writer là giao diện thử nghiệm để lập báo cáo tài chính từ tài liệu đã có trong dự án. Người dùng nhập yêu cầu, xem và duyệt dàn ý, sau đó đọc báo cáo hoàn chỉnh trên một trang riêng. Trang báo cáo có khung chat để hỏi thêm về nội dung hoặc trao đổi các chủ đề khác với Gemini.

Tài liệu này mô tả những gì người dùng thấy và thao tác trên giao diện. Bản hiện tại chạy trong môi trường nội bộ của dự án.

## Hai trang chính

| Trang | Dùng để làm gì? |
| --- | --- |
| **Phiên lập báo cáo** | Tạo yêu cầu, duyệt dàn ý và theo dõi kết quả của các bước tạo báo cáo. |
| **Báo cáo hoàn chỉnh** | Đọc báo cáo, xem bảng và nguồn trích dẫn, tải bản Markdown và chat với Gemini. Trang này chỉ mở được khi báo cáo đã hoàn tất. |

Ở trang đầu, thanh bên trái cho biết bốn bước: **Tạo yêu cầu → Duyệt dàn ý → Tạo và kiểm chứng → Xem báo cáo**. Trên màn hình rộng, mã phiên ở cuối thanh bên giúp nhận biết đúng báo cáo khi tải lại trang hoặc quay lại sau đó.

## Cách lập một báo cáo

### 1. Nhập yêu cầu

Điền **mã doanh nghiệp**, chọn **phạm vi** (Hợp nhất, Riêng hoặc Chung), chọn khoảng năm và viết yêu cầu bổ sung nếu cần. Nhấn **Lập dàn ý** để hệ thống đề xuất cấu trúc báo cáo. Bước này có thể mất thời gian vì hệ thống cần tra cứu dữ liệu và gọi mô hình AI.

Trong lúc chờ, trang hiện danh sách việc Planner đang làm: kiểm tra phạm vi, chuẩn bị cấu trúc báo cáo, gọi Gemini, tra cứu từng mục rồi kiểm tra dàn ý. Danh sách nhận thêm dòng khi backend thực sự chuyển bước hoặc có kết quả; dòng mới nhất luôn được đưa vào vùng nhìn thấy. Nếu một lần gọi Gemini hoặc tra cứu kéo dài, dòng hiện tại sẽ đứng yên cho tới khi có kết quả. Giao diện không hiển thị phần trăm hay thời gian còn lại dự đoán.

### 2. Xem và duyệt dàn ý

Giao diện hiển thị các phần dự kiến của báo cáo, mục tiêu của từng phần và những nội dung cần nghiên cứu. Người dùng có thể:

- Nhấn **Duyệt dàn ý** nếu muốn tiếp tục.
- Sửa tiêu đề hoặc mục tiêu rồi nhấn **Lưu bản sửa**. Mỗi lần lưu tạo một phiên bản dàn ý mới (gọi là *revision*); cần duyệt phiên bản đang hiển thị.
- Nhấn **Từ chối** nếu dàn ý không phù hợp.

Nếu yêu cầu còn thiếu thông tin, giao diện sẽ hiển thị điều cần làm rõ để người dùng tạo yêu cầu mới.

### 3. Chờ tạo và kiểm chứng

Sau khi nhấn **Duyệt dàn ý**, trang hiện **Đang tạo và kiểm chứng báo cáo** cùng danh sách tiến độ mới. Danh sách lần lượt ghi các tác vụ Researcher đã tra cứu và số bằng chứng tìm được, các phần Writer đang viết, rồi kết quả Verifier của từng phần. Đây là hoạt động đang diễn ra, không phải dự đoán tiến độ. Một dòng có thể giữ nguyên khá lâu khi Gemini đang xử lý phần đó.

Khi lượt chạy kết thúc, danh sách chờ biến mất. Trang quy trình hiển thị số tác vụ tra cứu, bằng chứng, phép tính, bản nháp và kết quả kiểm tra. Nếu có phần chưa đạt kiểm chứng đầy đủ, phiên hiện **Chưa hoàn tất** và vẫn cho xem bản nháp cùng các vấn đề cần chú ý. Khi báo cáo đã hoàn tất, các chi tiết từng bước nằm trong mục **Xem các bước tạo và kiểm chứng báo cáo** để trang chính gọn hơn.

### 4. Mở báo cáo

Khi trang quy trình hiện **Báo cáo đã sẵn sàng**, nhấn **Mở báo cáo hoàn chỉnh**. Trang báo cáo có mục lục để chuyển nhanh đến từng phần, các bảng số liệu và những nhãn nguồn màu xanh nhạt như `[Doc_…, p.…]`. Nhãn nguồn cho biết tài liệu và trang được trích dẫn.

Nút **Tải Markdown** tải nội dung báo cáo dưới dạng tệp văn bản có định dạng Markdown. Trên trang báo cáo, **Quay lại quy trình** mở lại đúng phiên hiện tại; **Lập báo cáo mới** đưa người dùng về form với một mã phiên mới.

## Chat dưới báo cáo

Khung chat nằm bên dưới nội dung báo cáo. Có thể hỏi, chẳng hạn:

> Doanh thu thuần năm 2025 là bao nhiêu, nguồn ở đâu?

> So với năm 2024 thì sao?

Gemini 3.8 Flash nhận nội dung báo cáo và một số tin nhắn gần nhất làm ngữ cảnh cho mỗi câu hỏi. Vì vậy, chat cũng trả lời được câu hỏi tiếp nối hoặc câu hỏi ngoài báo cáo. Câu trả lời hiển thị với định dạng Markdown, gồm tiêu đề, danh sách, chữ đậm và bảng khi có.

**Câu trả lời của chat là phản hồi mới từ AI** và chưa qua bước kiểm chứng của báo cáo. Với thông tin ngoài báo cáo hoặc dữ liệu cần cập nhật theo thời gian thực, người đọc nên kiểm tra nguồn phù hợp trước khi sử dụng. Nội dung báo cáo, câu hỏi và lịch sử hội thoại gần nhất được gửi tới dịch vụ Gemini khi người dùng chat.

## Hiểu trạng thái trên giao diện

| Trạng thái | Ý nghĩa |
| --- | --- |
| **Chưa bắt đầu** | Chưa gửi yêu cầu tạo báo cáo trong phiên này. |
| **Chờ duyệt** | Dàn ý đã có và đang chờ người dùng quyết định. |
| **Đang lập dàn ý** | Planner đang kiểm tra yêu cầu, tra cứu và đề xuất dàn ý; xem danh sách tiến độ ngay trên trang. |
| **Đang tạo và kiểm chứng** | Dàn ý đã được duyệt; Researcher, Writer và Verifier đang chạy; xem danh sách tiến độ ngay trên trang. |
| **Đang xử lý** | Hệ thống đang thực hiện các bước sau khi nhận yêu cầu hoặc dàn ý đã duyệt. |
| **Hoàn tất** | Các phần của phiên bản dàn ý đã duyệt đều đạt bước kiểm chứng đầy đủ; trang báo cáo hoàn chỉnh có thể mở. |
| **Chưa hoàn tất** | Có bản nháp hoặc kết quả từng bước, nhưng chưa đủ điều kiện để gọi là báo cáo hoàn chỉnh. |
| **Cần làm rõ / Đã từ chối** | Xem ghi chú trên trang để điều chỉnh yêu cầu hoặc tạo phiên mới. |

Tải lại trang vẫn giữ báo cáo và trạng thái của phiên đã lưu. Danh sách tiến độ chỉ dùng để theo dõi lượt chạy đang mở; nó không phải lịch sử hoạt động được lưu cùng báo cáo. Lịch sử chat được lưu trong **trình duyệt đang dùng**, theo mã phiên; nó không tự xuất hiện trên trình duyệt hoặc thiết bị khác.

## Khi giới thiệu giao diện

Có thể trình bày theo thứ tự ngắn sau: mở form tạo yêu cầu → xem thẻ duyệt dàn ý → mở một phiên đã hoàn tất → chỉ vào mục lục, bảng và nhãn nguồn → hỏi một câu về báo cáo trong khung chat. Cách này cho thấy cả bước người dùng kiểm soát dàn ý lẫn kết quả cuối cùng, mà không cần chạy lại toàn bộ quá trình trong lúc trình bày.
