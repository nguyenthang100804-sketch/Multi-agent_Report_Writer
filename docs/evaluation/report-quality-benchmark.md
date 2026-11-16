# Benchmark chất lượng báo cáo: kết quả giai đoạn A

**Bản dành cho người đọc demo nghiên cứu · 10/11/2026 · corpus v2.1**

## Kết quả chính — đọc trong một phút

> **8/8 ca Dev đạt kiểm tra tự động · 3/3 ca cần dừng đã dừng đúng · 8/8 lỗi cố tình cài vào báo cáo bị phát hiện.**

| Phép đo | Kết quả | Cách đọc con số |
| --- | ---: | --- |
| Yêu cầu báo cáo đạt kỳ vọng tự động đã ghi trước | **8/8 ca** | Gồm 5 ca tạo bản nháp và 3 ca phải dừng; xem kết quả từng ca bên dưới. |
| Ca phải dừng trước khi viết báo cáo | **3/3 ca** | DHG cần làm rõ scope/năm; FOX và ABB bị từ chối đúng. |
| Mục trong 5 bản nháp qua kiểm tra tất định | **27/27 mục** | Kiểm các quy tắc đã mã hóa về nội dung, số liệu, nguồn và giới hạn dữ liệu. |
| Giá trị gold đối chiếu với văn bản OCR gốc | **17/17 giá trị** | So cả số, tên chỉ tiêu và dấu trang; **4/17** giá trị được xem thêm trực tiếp trên PDF. |
| Bản gốc sạch qua bộ chấm | **2/2 bản** | Hai bản HUT/FPT dùng làm đối chứng cho phép thử cài lỗi. |
| Bản sao có lỗi cố tình cài bị bộ chấm phát hiện | **8/8 lỗi** | Mỗi bản sao chỉ chứa một trong tám kiểu lỗi được liệt kê ở mục dưới. |
| Phiếu đọc định tính hiện còn chờ | **1 phiếu** | Ca GMD; chưa thể kết luận phần định tính của cả tám ca đều đạt. |

**Trạng thái đầu ra:** 5 bản nháp `incomplete`, 2 yêu cầu `rejected`, 1 yêu cầu `needs_clarification`; **0 báo cáo `completed` trong benchmark A**. Đây là kết quả của đường chạy dùng mẫu báo cáo và quy tắc kiểm tra bằng code, không phải phép chấm Writer LLM hay Verifier ngữ nghĩa.

**Giới hạn quan trọng:** 13/17 giá trị mới được đối chiếu OCR, chưa xem trực tiếp trên PDF. Tám lỗi cài cho thấy bộ chấm bắt được tám kiểu lỗi cụ thể, không chứng minh nó bắt được mọi sai sót. Ba ca có phần chấm tay trước đây đã có kết quả lịch sử; xem mục “Người chấm”.

## Giai đoạn A thực sự chạy những gì?

Mỗi yêu cầu đi qua bốn bước: **lập kế hoạch → tìm số liệu và đoạn tài liệu → viết báo cáo theo mẫu → kiểm tra bằng quy tắc**. Bước viết theo mẫu chọn số và đoạn trích đã truy xuất, nên đây là đường cơ sở để so sánh với Writer dùng mô hình ngôn ngữ về sau. Giai đoạn A không gọi mô hình ngôn ngữ cho Planner, Writer hay Verifier.

Một số từ dùng trong bảng dưới đây:

| Từ trong hệ thống | Nghĩa khi đọc kết quả |
| --- | --- |
| **Gold** | Đáp án kỳ vọng được ghi trước khi chấm, gồm số, trạng thái và nguồn cần đối chiếu |
| **OCR** | Văn bản được trích từ PDF; có thể giữ lỗi đọc của OCR |
| **Trích dẫn/citation** | Mã tài liệu và trang đứng sau số hoặc câu trong báo cáo |
| **Giới hạn dữ liệu/limitation** | Câu báo rõ thiếu số, không tính được hoặc chưa tìm được đoạn phù hợp |
| **`rejected`** | Từ chối yêu cầu; không tạo báo cáo |
| **`needs_clarification`** | Cần người dùng làm rõ phạm vi hoặc năm; không tự đổi yêu cầu |
| **`incomplete`** | Có bản nháp đã qua kiểm tra tất định, chưa qua mức kiểm ngữ nghĩa để hoàn tất |
| **`completed`** | Chỉ dùng khi outline đã duyệt và mọi mục qua Verifier mức `full`; giai đoạn A không có trạng thái này |

## Tám ca đã thử và kết quả từng ca

Tất cả ca dùng dữ liệu tài chính 2022–2025, trừ DHG `general` chỉ dùng 2023–2025 vì đó là ba năm có cùng phạm vi. Bảng ghi **trạng thái thực tế**, không chỉ là kế hoạch.

| Ca | Điều được kiểm | Kết quả thực tế |
| --- | --- | --- |
| **HUT, hợp nhất** | Doanh thu và tổng tài sản đủ bốn năm. Doanh thu 2025: **36.317,44 tỷ đồng**; tăng **20,14%** so với 2024. | `incomplete`; 5/5 mục qua kiểm tra tất định; **0 lỗi** trong checklist tự động. |
| **FPT, hợp nhất** | Có doanh thu đủ bốn năm nhưng dữ liệu trích xuất thiếu lợi nhuận thuộc cổ đông công ty mẹ năm **2024–2025**. Chênh lệch dòng tiền kinh doanh 2024–2025 không tính được. | `incomplete`; 5/5 mục qua; có câu báo thiếu và không nội suy; **0 lỗi**. |
| **HUT, dòng số xung đột có kiểm soát** | Một dòng doanh thu 2025 khác giá trị được **cài nhân tạo vào câu trả lời công cụ**. Hệ thống phải đánh dấu mơ hồ và không tính YoY từ dòng không xác định. | `incomplete`; 5/5 mục qua; doanh thu được gắn `ambiguous`, YoY `cannot_compute`; **0 lỗi**. |
| **DHG, yêu cầu hợp nhất 2022–2025** | Scope hợp nhất chỉ có **2022** trong corpus; các năm 2023–2025 thuộc scope `general`. | `needs_clarification`; dừng trước khi tìm dữ liệu và viết báo cáo; **0 lỗi**. |
| **FOX** | Mã không có trong corpus. | `rejected`; không tạo báo cáo; **0 lỗi**. |
| **ABB** | Có trong corpus nhưng bộ mã chuẩn cho ngân hàng chưa được hỗ trợ. | `rejected`; không tạo báo cáo; **0 lỗi**. |
| **DHG, scope `general` 2023–2025** | Doanh thu lần lượt **5.015,40; 4.884,87; 5.266,96 tỷ đồng**. Mức tăng 2025 so với 2024 là **7,82%**. | `incomplete`; 5/5 mục qua; ba giá trị đối chiếu OCR; **0 lỗi**. |
| **GMD, hợp nhất, nội dung rủi ro** | Công cụ truy xuất được **5 đoạn ứng viên** cho truy vấn rủi ro tài chính năm 2025, nhưng sau lọc không có đoạn đủ liên quan. Báo cáo phải nói “chưa tìm thấy trong các đoạn đã truy xuất”, không khẳng định công ty không có rủi ro. | `incomplete`; 7/7 mục qua; tác vụ rủi ro là `no_evidence/not_found_yet`; **0 lỗi tự động**, còn một phiếu đọc định tính. |

Ba ca dừng không có phần tìm dữ liệu hay báo cáo. Với năm ca có bản nháp, `incomplete` là **kết quả đúng của giai đoạn A**, không phải lỗi chạy. Dòng HUT xung đột chỉ dùng để thử hành vi khi công cụ trả kết quả mơ hồ; giá trị cài thêm không được coi là số liệu thật của HUT. `general` là tên scope trong dữ liệu DHG, **không đồng nhất với scope `separate`**.

Con số 5 đoạn ứng viên của GMD được quan sát ở một lượt kiểm truy xuất riêng với đúng câu hỏi trong kế hoạch; file kết quả tám ca chỉ lưu trạng thái **sau khi lọc**, không lưu năm đoạn thô.

## Số liệu đã kiểm với nguồn đến đâu?

Đáp án số không chỉ được sao từ cơ sở dữ liệu của hệ thống. Với 17 giá trị HUT, FPT và DHG, bộ chấm đối chiếu lại **giá trị, tên chỉ tiêu và dấu trang** trong văn bản OCR gốc. Bốn giá trị sau được xem thêm trực tiếp trên ảnh trang PDF:

| Giá trị xem trên PDF | Số nguyên trên PDF (VND) | Trang PDF | Kết quả |
| --- | ---: | ---: | --- |
| HUT 2025 — Tổng tài sản | 52.231.240.200.353 | 9 | Khớp OCR/gold |
| HUT 2025 — Doanh thu thuần | 36.317.437.528.063 | 11 | Khớp OCR/gold |
| FPT 2023 — Doanh thu thuần | 52.617.900.827.385 | 13 | Khớp OCR/gold |
| FPT 2023 — Lợi nhuận thuộc cổ đông công ty mẹ | 6.465.190.432.622 | 13 | Khớp OCR/gold |

Mười ba giá trị còn lại mới được kiểm bằng OCR. Vì vậy vẫn có khả năng một lỗi đọc số đã có từ bước OCR mà benchmark chưa phát hiện. Trên hai PDF đã xem có dấu hoặc chữ ký ở trang liên quan, nhưng chúng không đè lên bốn ô số được chọn. [Biên bản kiểm PDF](../../evaluation/benchmarks/report_quality_pdf_spot_check.json) lưu đường dẫn, trang và hash của hai file nguồn.

## Cố tình làm hỏng báo cáo để thử bộ chấm

Nếu chỉ chạy báo cáo sạch rồi thấy “8/8 qua”, ta chưa biết bộ chấm có phát hiện lỗi hay không. Vì vậy phép thử sau lấy **hai bản gốc HUT/FPT đã lưu**, xác nhận chúng qua trước, rồi tạo tám bản sao; mỗi bản sao chỉ sửa một chi tiết. Bộ chấm nhận ra đúng loại lỗi ở cả tám bản sao:

| Chi tiết bị sửa | Bộ chấm đã báo |
| --- | --- |
| Đổi một chữ số doanh thu HUT | Sai giá trị đầu ra |
| Đổi năm 2025 thành 2026 ở đầu bảng | Sai kỳ báo cáo |
| Đổi đơn vị `tỷ đồng` thành `triệu đồng` | Sai đơn vị |
| Chuyển trích dẫn doanh thu sang trang khác | Trích dẫn không khớp ô số |
| Xóa câu báo thiếu dữ liệu FPT | Thiếu câu giới hạn |
| Thêm “Doanh thu tăng do thương vụ sáp nhập” không có note hỗ trợ | Khẳng định nguyên nhân không có nguồn |
| Thêm “Báo cáo kiểm toán không có vấn đề nhấn mạnh” | Khẳng định tuyệt đối khi chưa có căn cứ |
| Xóa giới hạn dữ liệu khỏi cấu trúc bản nháp FPT | Thiếu giới hạn trong bản nháp |

Kết quả **2/2 bản gốc sạch qua, 8/8 bản cài lỗi bị bắt** chỉ nói về tám cách sửa này. Chúng không được cộng vào số báo cáo thật đạt, và phép thử này không chạy lại tìm tài liệu cho mỗi bản sao. [Kết quả từng lỗi cài](../../evaluation/benchmarks/report_quality_phase_a_demo_mutations.json) ghi lỗi kỳ vọng và lỗi thực tế.

## Người chấm đã làm gì, còn việc gì?

Ở bộ năm ca cũ, hai người từng đọc độc lập **4 mục cấm** trong ba báo cáo HUT/FPT; cả hai chọn “không vi phạm” cho 4/4 mục. Vì tất cả nhãn đều cùng một loại, kết quả đó **không tính được kappa có ý nghĩa** và không tự chứng minh người chấm nhận ra lỗi thật. Một bộ đối chứng riêng đã trộn 4 đoạn có lỗi với 4 đoạn sạch; cả hai người phân loại đúng **8/8 đoạn**. Đây là kết quả lịch sử, không phải yêu cầu tìm thêm người chấm cho demo hiện tại.

Ca GMD mới có [phiếu đọc một người](../../evaluation/benchmarks/report_quality_phase_a_demo_manual_review.md) và **chưa được chấm**. Người chấm chỉ cần xác định báo cáo có biến việc “chưa tìm thấy đoạn phù hợp” thành khẳng định “GMD không có rủi ro” hay không, rồi ghi câu làm căn cứ. Mentor/giảng viên có thể xem lại nếu thuận tiện. Không tính kappa hay điểm khả dụng 1–5 cho bộ demo này.

Trong JSON kết quả có `manual_review_pending_count=4`: trường này ghi tình trạng **ngay lúc chạy** của ba ca cũ và GMD. Ba ca cũ đã có phiếu lịch sử sau đó; hiện còn **một phiếu GMD chưa điền**. Vì thế chưa báo “không có vi phạm định tính ở cả tám ca”.

## Kết luận có thể dùng khi trình bày

> Trên corpus v2.1, benchmark giai đoạn A gồm tám ca Dev đã đạt mọi kiểm tra tự động được xác định trước; ba ca cần dừng đều dừng đúng. Mười bảy giá trị gold được đối chiếu OCR, bốn giá trị trong số đó được xem thêm trên PDF. Bộ chấm phát hiện tám trong tám lỗi cài trên hai bản nháp sạch. Các báo cáo tạo ra ở giai đoạn A vẫn là bản nháp `incomplete`; một phiếu đọc định tính của ca GMD còn chờ hoàn tất.

Không suy từ các con số trên rằng Writer LLM hoặc Verifier ngữ nghĩa đã được kiểm định chất lượng trên toàn bộ corpus. Một lượt graph thật đạt `completed` là phép thử kỹ thuật riêng, không nằm trong tám ca A. Tập Test được tách theo **công ty**, chưa dùng để tính các con số ở trang này.

## Tài liệu để kiểm tra lại

- [Kết quả tám ca, gồm báo cáo và finding của từng ca](../../evaluation/benchmarks/report_quality_phase_a_demo.json).
- [Gold của từng ca](../../configs/report_quality_dev/) và [cách chia Dev/Test](../../configs/eval_dataset_split.json).
- [Kết quả tám lỗi cài](../../evaluation/benchmarks/report_quality_phase_a_demo_mutations.json) và [biên bản xem PDF](../../evaluation/benchmarks/report_quality_pdf_spot_check.json).
- [Phiếu GMD chưa chấm](../../evaluation/benchmarks/report_quality_phase_a_demo_manual_review.md); [kết quả hai người chấm cũ](../../evaluation/benchmarks/forbidden_claims_two_grader_result.json) và [bộ đối chứng của họ](../../evaluation/benchmarks/forbidden_claims_control_two_grader_result.json).

Để tạo lại hai artifact mới từ thư mục gốc dự án:

```powershell
.venv/Scripts/python.exe -B -m src.evaluation.report_quality_benchmark --output evaluation/benchmarks/report_quality_phase_a_demo.json
.venv/Scripts/python.exe -B -m src.evaluation.report_quality_demo_mutations
```

Lượt kết quả trên được tạo ngày **10/11/2026** với corpus **v2.1**. Trong giai đoạn A, các trường model và phiên bản prompt của Planner, Writer, Verifier là `null` vì ba tầng đó chạy tất định; JSON kết quả còn ghi snapshot dữ liệu và hash code/gold để phát hiện thay đổi giữa các lượt chạy.
