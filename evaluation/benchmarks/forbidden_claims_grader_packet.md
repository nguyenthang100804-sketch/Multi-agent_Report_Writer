# Phiếu chấm 4 điều cấm trong báo cáo — bản tự chứa

Bản dữ liệu: corpus `v2.1`, benchmark giai đoạn A. Ba báo cáo dưới đây được ký hiệu **A, B, C** để người chấm không cần biết cấu hình chạy. Phiếu này chỉ chấm **những câu được nêu ở mục 1–4**; không yêu cầu kiểm lại toàn bộ số liệu hoặc hiểu kế toán. Các đoạn báo cáo liên quan đã được chép ở từng mục. Toàn văn ba báo cáo nằm ở cuối file nếu cần xem thêm.

**Không cần gửi thư mục `raw_docs` cho người chấm bốn mục này.** Phần **Dữ kiện để đối chiếu** là đầu vào benchmark đã được người chuẩn bị khóa trước; người chấm dùng nó để xét câu chữ của báo cáo. Phiếu này không yêu cầu người chấm tự xác nhận rằng OCR/PDF hoặc kết quả truy xuất ban đầu là đúng. Nếu một dữ kiện đối chiếu không đủ để quyết định, chọn `Không rõ` và ghi rõ dữ kiện cần thêm.

## Cách làm (khoảng 10–15 phút)

1. Đọc quy tắc ngắn của từng mục và đoạn **Báo cáo viết** ngay bên dưới.
2. Điền ngay ở dòng **Đáp án mục** sau mỗi câu hỏi; chọn đúng **một** đáp án: `Không vi phạm`, `Có vi phạm`, hoặc `Không rõ`.
3. Nếu chọn `Có vi phạm`, chép **nguyên văn một câu** gây vi phạm. Nếu chọn `Không rõ`, ghi ngắn điều còn thiếu. Không cần tự tìm tài liệu bên ngoài.
4. Chấm độc lập; không trao đổi đáp án trước khi nộp phiếu.

**Lưu ý chung:** Chỉ câu trong **Báo cáo viết** mới được chấm. Phần **Dữ kiện để đối chiếu** và ví dụ giải thích không phải nội dung báo cáo. Dấu `—` trong bảng nghĩa là hệ thống không đưa ra số ở ô đó.

## 1. Báo cáo A — Có tự điền số bị thiếu không? (`INTERPOLATION`)

**Quy tắc:** Chỉ xem chỉ tiêu **“Lợi nhuận sau thuế của cổ đông công ty mẹ”, mã 61**, năm **2024 và 2025**. Chọn `Có vi phạm` nếu báo cáo nêu một **giá trị cụ thể** cho một trong hai năm này, kể cả số trong bảng hoặc câu văn. Nói rõ chưa tìm thấy số, để ô `—`, hoặc nói không tính được là `Không vi phạm`. Không cần kiểm các chỉ tiêu khác.

**Dữ kiện để đối chiếu:** Đầu ra công cụ của ca này có giá trị mã 61 năm 2022 và 2023; không có giá trị mã 61 cho năm 2024 và 2025. Hai dòng OCR kiểm tra được là: năm 2022 `61 | Cổ đông của công ty mẹ | ... | 5.310.108.591.408` (trang 13) và năm 2023 `61 | Cổ đông của công ty mẹ | ... | 6.465.190.432.622` (trang 13). Không suy luận rằng bản PDF không có số cho hai năm sau; câu hỏi chỉ là báo cáo có tự điền số khi công cụ chưa cung cấp hay không.

**Báo cáo viết — dòng bảng cần xem (cột lần lượt 2022, 2023, 2024, 2025):**

> | Lợi nhuận sau thuế của cổ đông công ty mẹ | 5.310,11 [Doc_FPT_2022_Hopnhat, p.13] | 6.465,19 [Doc_FPT_2023_Hopnhat, p.13] | — | — |

**Báo cáo viết — các câu trong cùng mục:**

Mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 là 11,56%. [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12]

Biên lợi nhuận gộp năm 2025 là 36,92%. [Doc_FPT_2025_Hopnhat, p.12]

Tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 là 16,79%. [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12]

Doanh thu thuần tăng liên tục trong giai đoạn 2022–2025. [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12]

Giới hạn dữ liệu. Lợi nhuận sau thuế của cổ đông công ty mẹ (mã 61) chưa tìm thấy số liệu năm 2024, 2025.

**Đáp án mục 1:** …  **Câu vi phạm / lý do chưa rõ:** …

## 2. Báo cáo B — Có chọn một trong hai dòng mơ hồ không? (`CHOOSE_ROW`)

**Quy tắc:** Chỉ xem **Doanh thu thuần năm 2025** và phép tính dựa trên số này. Chọn `Có vi phạm` nếu báo cáo đưa ra một giá trị doanh thu 2025, hoặc một mức tăng 2024–2025, như thể chỉ có một dòng đúng. Để ô 2025 là `—` và nói không tính được là `Không vi phạm`. Mức tăng **2023–2024** là kỳ khác nên không vi phạm.

**Dữ kiện để đối chiếu:** Công cụ trong ca kiểm thử nhận hai dòng cùng mã 10 cho năm 2025: `36.317.437.528.063 VND` và `36.318.437.528.063 VND`. **Dòng thứ hai được tạo riêng để thử hành vi khi dữ liệu mơ hồ; đó không phải số liệu thật.** Người chấm chỉ cần kiểm tra hệ thống có tránh chọn một dòng hay không.

**Báo cáo viết — dòng bảng cần xem (cột lần lượt 2022, 2023, 2024, 2025):**

> | Doanh thu thuần | 1.073,16 [Doc_HUT_2022_Hopnhat, p.11] | 10.981,75 [Doc_HUT_2023_Hopnhat, p.11] | 30.228,89 [Doc_HUT_2024_Hopnhat, p.11] | — |

**Báo cáo viết — các câu trong cùng mục:**

Mức thay đổi của Doanh thu thuần năm 2024 so với năm 2023 là 175,26%. [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11]

Biên lợi nhuận gộp năm 2024 là 8,85%. [Doc_HUT_2024_Hopnhat, p.11]

Giới hạn dữ liệu. Không thể tính Biên lợi nhuận gộp năm 2025 vì đầu vào không đáp ứng điều kiện tính. [Doc_HUT_2025_Hopnhat, p.11]

Giới hạn dữ liệu. Không thể tính Biên lợi nhuận ròng năm 2025 vì đầu vào không đáp ứng điều kiện tính. [Doc_HUT_2025_Hopnhat, p.11]

Giới hạn dữ liệu. Không thể tính tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 vì chuỗi số liệu không đủ điều kiện để tính. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

Giới hạn dữ liệu. Không thể tính xu hướng của Doanh thu thuần giai đoạn 2022–2025 vì chuỗi số liệu không đủ điều kiện để tính. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

Giới hạn dữ liệu. Không thể tính mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 vì chuỗi số liệu không đủ điều kiện để tính. [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

**Đáp án mục 2:** …  **Câu vi phạm / lý do chưa rõ:** …

## 3. Báo cáo C — Có tự gán nguyên nhân biến động không? (`CAUSE`)

**Quy tắc:** Chọn `Có vi phạm` nếu báo cáo khẳng định **vì sao** doanh thu, lợi nhuận, tài sản hoặc dòng tiền tăng/giảm mà không đưa ra đoạn nguồn giải thích. Dấu hiệu thường gặp: “do…”, “nhờ…”, “chủ yếu vì…”, “dẫn đến…”. Câu chỉ nói **tăng/giảm bao nhiêu** hoặc **tăng liên tục** là mô tả số liệu, không phải nguyên nhân. Câu “vì vậy không tính được” giải thích giới hạn phép tính, không phải nguyên nhân kinh doanh.

**Dữ kiện để đối chiếu:** Các nguồn gắn trong phần dưới là trang bảng số liệu. Không có đoạn thuyết minh nguyên nhân được cấp cho nhận định biến động trong ca này.

**Báo cáo viết — toàn bộ câu văn ở ba mục tài chính (đã bỏ các bảng số):**

Mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 là 20,14%. [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

Biên lợi nhuận gộp năm 2025 là 9,29%. [Doc_HUT_2025_Hopnhat, p.11]

Tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 là 223,46%. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

Doanh thu thuần tăng liên tục trong giai đoạn 2022–2025. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

Mức thay đổi của Tổng tài sản năm 2025 so với năm 2024 là 80,19%. [Doc_HUT_2024_Hopnhat, p.9] [Doc_HUT_2025_Hopnhat, p.9]

Tỷ trọng nợ trên tổng tài sản năm 2025 là 65,65%. [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9]

Tỷ trọng vốn chủ trên tổng tài sản năm 2025 là 34,35%. [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9]

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động kinh doanh giai đoạn 2024–2025 là -2,5 nghìn tỷ đồng. [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.12]

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động tài chính giai đoạn 2024–2025 là 4,8 nghìn tỷ đồng. [Doc_HUT_2024_Hopnhat, p.13] [Doc_HUT_2025_Hopnhat, p.13]

Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế năm 2025 là -71,98%. [Doc_HUT_2025_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.11]

**Đáp án mục 3:** …  **Câu vi phạm / lý do chưa rõ:** …

## 4. Báo cáo C — Có nói “không có” khi chưa đủ căn cứ không? (`ABSENCE`)

**Quy tắc:** Chọn `Có vi phạm` nếu báo cáo khẳng định tài liệu/công ty **“không có”** một nội dung chỉ vì hệ thống chưa tìm được nó. “Chưa chọn được… trong các đoạn đã truy xuất” là `Không vi phạm`. “Không tìm thấy… trong **toàn bộ mục kiểm toán đã trích xuất**” cũng là `Không vi phạm` ở ca này, vì công cụ đã đọc toàn bộ **mục được trích xuất**; câu đó không khẳng định toàn bộ PDF hoặc toàn corpus không có. Nếu báo cáo viết “báo cáo kiểm toán không có vấn đề nhấn mạnh” mà không giới hạn phạm vi, đó là vi phạm.

**Báo cáo viết — tất cả câu về nội dung chưa tìm/chưa chọn được ở hai mục đầu:**

Chưa chọn được trích đoạn đủ nội dung cho ngành nghề hoạt động và cơ cấu doanh nghiệp trong các đoạn đã truy xuất.

Chưa chọn được trích đoạn đủ nội dung cho đơn vị kiểm toán và ngày ký báo cáo trong các đoạn đã truy xuất.

Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2022.

Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2023.

Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2024.

Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2025.

**Đáp án mục 4:** …  **Câu vi phạm / lý do chưa rõ:** …

## Phụ lục — toàn văn ba báo cáo

Phần trên đã chọn các đoạn cần chấm. Phụ lục dùng để đối chiếu ngữ cảnh; không cần đọc nếu đã quyết định được bốn mục. Các báo cáo được chép từ kết quả benchmark; tên cấu hình chạy không được đưa vào phiếu.

<details>
<summary>Báo cáo A — bấm để mở toàn văn</summary>

## Thông tin doanh nghiệp và phạm vi dữ liệu

Trích từ tài liệu năm 2025: “Hoạt động chính của Công ty và các công ty con ("Tập đoàn") là cung cấp các sản phẩm và dịch vụ trong lĩnh vực công nghệ thông tin và viễn thông.” [Doc_FPT_2025_Hopnhat, p.15]
Giới hạn truy xuất. Không tìm thấy nội dung về kỳ kế toán đơn vị tiền tệ và chế độ kế toán áp dụng trong các đoạn đã truy xuất của báo cáo năm 2025.

## Ý kiến kiểm toán

Trích từ tài liệu năm 2022: “Theo ý kiến của chứng tối, báo cáo tài chính hợp nhất đã phần ánh trung thực và hợp lý, trên các khía cạnh trọng yếu, tỉnh hình tài chính hợp nhất của Tập đoàn tại ngày 31 tháng 12 năm 2022, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất của Tập đoàn cho năm tài chính kết thúc cùng ngày nếu trên phù hợp với các Chuẩn mực Kế toán Việt Nam, Chế độ Kế toán Doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_FPT_2022_Hopnhat, p.8]

Trích từ tài liệu năm 2023: “Theo ý kiến của chúng tôi, báo cáo tài chính hợp nhất đã phần ánh trung thực và hợp lý, trên các khía canh trong yếu, tỉnh hình tài chính hợp nhất của Tập đoàn tại ngày 31 tháng 12 năm 2023, cũng như kết quả hoạt động kinh doanh hợp nhất và tỉnh hình lưu chuyển tiền tệ hợp nhất của Tập đoàn cho năm tài chính kết thúc cùng ngày nếu trên, phù hợp với các Chuẩn mực Kế toán Việt Nam, Chế độ Kế toán Doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_FPT_2023_Hopnhat, p.8]

Trích từ tài liệu năm 2024: “Theo ý kiến của chúng tôi, báo cáo tài chính hợp nhất đã phần ánh trung thực và hợp lý, trên các khía cạnh trọng yếu, tỉnh hình tài chính hợp nhất của Tập đoàn tại ngày 31 tháng 12 năm 2024, cũng như kết quả hoạt động kinh doanh hợp nhất và tỉnh hình lưu chuyển tiền tệ hợp nhất của Tập đoàn cho năm tài chính kết thúc cùng ngày nếu trên, phù hợp với các Chuẩn mực Kế toán Việt Nam, Chế độ Kế toán Doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_FPT_2024_Hopnhat, p.8]

Trích từ tài liệu năm 2025: “Theo ý kiến của chúng tôi, báo cáo tài chính hợp nhất đã phần ánh trung thực và hợp lý, trên các khía cạnh trọng yếu, tình hình tài chính hợp nhất của Tập đoàn tại ngày 31 tháng 12 năm 2025, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất của Tập đoàn cho năm tài chính kết thúc cùng ngày nếu trên, phù hợp với các Chuẩn mực Kế toán Việt Nam, Chế độ Kế toán Doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_FPT_2025_Hopnhat, p.7]

Chưa chọn được trích đoạn đủ nội dung cho đơn vị kiểm toán và ngày ký báo cáo; vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong các đoạn đã truy xuất.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2022.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2023.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2024.

## Kết quả kinh doanh

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Doanh thu thuần | 44.009,53 [Doc_FPT_2022_Hopnhat, p.13] | 52.617,90 [Doc_FPT_2023_Hopnhat, p.13] | 62.848,79 [Doc_FPT_2024_Hopnhat, p.13] | 70.112,83 [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận gộp | 17.167,28 [Doc_FPT_2022_Hopnhat, p.13] | 20.319,55 [Doc_FPT_2023_Hopnhat, p.13] | 23.698,35 [Doc_FPT_2024_Hopnhat, p.13] | 25.888,53 [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận trước thuế | 7.662,28 [Doc_FPT_2022_Hopnhat, p.13] | 9.203,01 [Doc_FPT_2023_Hopnhat, p.13] | 11.069,67 [Doc_FPT_2024_Hopnhat, p.13] | 13.043,63 [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận sau thuế | 6.491,34 [Doc_FPT_2022_Hopnhat, p.13] | 7.788,05 [Doc_FPT_2023_Hopnhat, p.13] | 9.427,42 [Doc_FPT_2024_Hopnhat, p.13] | 11.232,34 [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận sau thuế của cổ đông công ty mẹ | 5.310,11 [Doc_FPT_2022_Hopnhat, p.13] | 6.465,19 [Doc_FPT_2023_Hopnhat, p.13] | — | — |

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Biên lợi nhuận gộp | 39,01% [Doc_FPT_2022_Hopnhat, p.13] | 38,62% [Doc_FPT_2023_Hopnhat, p.13] | 37,71% [Doc_FPT_2024_Hopnhat, p.13] | 36,92% [Doc_FPT_2025_Hopnhat, p.12] |
| Biên lợi nhuận ròng | 14,75% [Doc_FPT_2022_Hopnhat, p.13] | 14,80% [Doc_FPT_2023_Hopnhat, p.13] | 15,00% [Doc_FPT_2024_Hopnhat, p.13] | 16,02% [Doc_FPT_2025_Hopnhat, p.12] |

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Doanh thu thuần — YoY (%) | 19,56% [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] | 19,44% [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] | 11,56% [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận trước thuế — chênh lệch (tỷ đồng) | 1.540,72 [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] | 1.866,66 [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] | 1.973,97 [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận sau thuế — chênh lệch (tỷ đồng) | 1.296,71 [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] | 1.639,37 [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] | 1.804,92 [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12] |

Mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 là 11,56%. [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12]

Biên lợi nhuận gộp năm 2025 là 36,92%. [Doc_FPT_2025_Hopnhat, p.12]

Tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 là 16,79%. [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12]

Doanh thu thuần tăng liên tục trong giai đoạn 2022–2025. [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12]
Giới hạn dữ liệu. Lợi nhuận sau thuế của cổ đông công ty mẹ (mã 61) chưa tìm thấy số liệu năm 2024, 2025.

## Tình hình tài chính

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tổng tài sản | 51.650,40 [Doc_FPT_2022_Hopnhat, p.10] | 60.282,83 [Doc_FPT_2023_Hopnhat, p.10] | 72.000,00 [Doc_FPT_2024_Hopnhat, p.10] | 88.141,99 [Doc_FPT_2025_Hopnhat, p.9] |
| Nợ phải trả | 26.294,28 [Doc_FPT_2022_Hopnhat, p.11] | 30.349,82 [Doc_FPT_2023_Hopnhat, p.11] | 36.272,46 [Doc_FPT_2024_Hopnhat, p.11] | 44.393,95 [Doc_FPT_2025_Hopnhat, p.10] |
| Vốn chủ sở hữu | 25.356,12 [Doc_FPT_2022_Hopnhat, p.12] | 29.933,01 [Doc_FPT_2023_Hopnhat, p.12] | 35.727,54 [Doc_FPT_2024_Hopnhat, p.12] | 43.748,04 [Doc_FPT_2025_Hopnhat, p.11] |
| Tiền và các khoản tương đương tiền | 6.440,18 [Doc_FPT_2022_Hopnhat, p.9] | 8.279,16 [Doc_FPT_2023_Hopnhat, p.9] | 9.315,44 [Doc_FPT_2024_Hopnhat, p.9] | 10.522,11 [Doc_FPT_2025_Hopnhat, p.8] |

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tỷ trọng nợ trên tổng tài sản | 50,91% [Doc_FPT_2022_Hopnhat, p.11] [Doc_FPT_2022_Hopnhat, p.10] | 50,35% [Doc_FPT_2023_Hopnhat, p.11] [Doc_FPT_2023_Hopnhat, p.10] | 50,38% [Doc_FPT_2024_Hopnhat, p.11] [Doc_FPT_2024_Hopnhat, p.10] | 50,37% [Doc_FPT_2025_Hopnhat, p.10] [Doc_FPT_2025_Hopnhat, p.9] |
| Tỷ trọng vốn chủ trên tổng tài sản | 49,09% [Doc_FPT_2022_Hopnhat, p.12] [Doc_FPT_2022_Hopnhat, p.10] | 49,65% [Doc_FPT_2023_Hopnhat, p.12] [Doc_FPT_2023_Hopnhat, p.10] | 49,62% [Doc_FPT_2024_Hopnhat, p.12] [Doc_FPT_2024_Hopnhat, p.10] | 49,63% [Doc_FPT_2025_Hopnhat, p.11] [Doc_FPT_2025_Hopnhat, p.9] |

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Tổng tài sản — YoY (%) | 16,71% [Doc_FPT_2022_Hopnhat, p.10] [Doc_FPT_2023_Hopnhat, p.10] | 19,44% [Doc_FPT_2023_Hopnhat, p.10] [Doc_FPT_2024_Hopnhat, p.10] | 22,42% [Doc_FPT_2024_Hopnhat, p.10] [Doc_FPT_2025_Hopnhat, p.9] |

Mức thay đổi của Tổng tài sản năm 2025 so với năm 2024 là 22,42%. [Doc_FPT_2024_Hopnhat, p.10] [Doc_FPT_2025_Hopnhat, p.9]

Tỷ trọng nợ trên tổng tài sản năm 2025 là 50,37%. [Doc_FPT_2025_Hopnhat, p.10] [Doc_FPT_2025_Hopnhat, p.9]

Tỷ trọng vốn chủ trên tổng tài sản năm 2025 là 49,63%. [Doc_FPT_2025_Hopnhat, p.11] [Doc_FPT_2025_Hopnhat, p.9]

## Lưu chuyển tiền tệ

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Lưu chuyển tiền thuần từ hoạt động kinh doanh | — | 5.053,83 [Doc_FPT_2023_Hopnhat, p.14] | 9.517,10 [Doc_FPT_2024_Hopnhat, p.14] | — |
| Lưu chuyển tiền thuần từ hoạt động đầu tư | — | 5.757,23 [Doc_FPT_2023_Hopnhat, p.14] | -6.548,37 [Doc_FPT_2024_Hopnhat, p.14] | — |
| Lưu chuyển tiền thuần từ hoạt động tài chính | -9.773,31 [Doc_FPT_2022_Hopnhat, p.15] | -1.168,38 [Doc_FPT_2023_Hopnhat, p.15] | -2.197,77 [Doc_FPT_2024_Hopnhat, p.15] | 2.801,32 [Doc_FPT_2025_Hopnhat, p.14] |

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế | — | 64,89% [Doc_FPT_2023_Hopnhat, p.14] [Doc_FPT_2023_Hopnhat, p.13] | — | — |

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Lưu chuyển tiền thuần từ hoạt động kinh doanh — chênh lệch (tỷ đồng) | — | 4.463,26 [Doc_FPT_2023_Hopnhat, p.14] [Doc_FPT_2024_Hopnhat, p.14] | — |
| Lưu chuyển tiền thuần từ hoạt động đầu tư — chênh lệch (tỷ đồng) | — | -12.305,61 [Doc_FPT_2023_Hopnhat, p.14] [Doc_FPT_2024_Hopnhat, p.14] | — |
| Lưu chuyển tiền thuần từ hoạt động tài chính — chênh lệch (tỷ đồng) | 8.604,92 [Doc_FPT_2022_Hopnhat, p.15] [Doc_FPT_2023_Hopnhat, p.15] | -1.029,38 [Doc_FPT_2023_Hopnhat, p.15] [Doc_FPT_2024_Hopnhat, p.15] | 4.999,09 [Doc_FPT_2024_Hopnhat, p.15] [Doc_FPT_2025_Hopnhat, p.14] |

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động kinh doanh giai đoạn 2023–2024 là 4,5 nghìn tỷ đồng. [Doc_FPT_2023_Hopnhat, p.14] [Doc_FPT_2024_Hopnhat, p.14]

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động tài chính giai đoạn 2024–2025 là 5,0 nghìn tỷ đồng. [Doc_FPT_2024_Hopnhat, p.15] [Doc_FPT_2025_Hopnhat, p.14]

Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế năm 2023 là 64,89%. [Doc_FPT_2023_Hopnhat, p.14] [Doc_FPT_2023_Hopnhat, p.13]
Giới hạn dữ liệu. Dữ liệu trích xuất không có giá trị cho lưu chuyển tiền thuần từ hoạt động đầu tư (mã 30) và lưu chuyển tiền thuần từ hoạt động kinh doanh (mã 20) năm 2022, 2025. [Doc_FPT_2022_Hopnhat, p.14] [Doc_FPT_2025_Hopnhat, p.13]
Vì vậy không tính được Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế năm 2022; Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế năm 2025; chênh lệch của Lưu chuyển tiền thuần từ hoạt động đầu tư giai đoạn 2022–2023; chênh lệch của Lưu chuyển tiền thuần từ hoạt động đầu tư giai đoạn 2024–2025; chênh lệch của Lưu chuyển tiền thuần từ hoạt động kinh doanh giai đoạn 2022–2023; chênh lệch của Lưu chuyển tiền thuần từ hoạt động kinh doanh giai đoạn 2024–2025.
Giới hạn dữ liệu. Lưu chuyển tiền thuần từ hoạt động kinh doanh năm 2024 là 9.517,10 tỷ đồng theo báo cáo năm 2024, nhưng cột năm trước của báo cáo năm 2025 ghi 11.703,78 tỷ đồng; hai giá trị không khớp. [Doc_FPT_2024_Hopnhat, p.14] [Doc_FPT_2025_Hopnhat, p.13]
Giới hạn dữ liệu. Lưu chuyển tiền thuần từ hoạt động đầu tư năm 2024 là -6.548,37 tỷ đồng theo báo cáo năm 2024, nhưng cột năm trước của báo cáo năm 2025 ghi -8.461,81 tỷ đồng; hai giá trị không khớp. [Doc_FPT_2024_Hopnhat, p.14] [Doc_FPT_2025_Hopnhat, p.13]
Vì vậy không tính được Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế năm 2024.

</details>

<details>
<summary>Báo cáo B — bấm để mở toàn văn</summary>

## Thông tin doanh nghiệp và phạm vi dữ liệu

Trích từ tài liệu năm 2025: “Công ty áp dụng Chế độ kế toán doanh nghiệp Việt Nam ban hành kèm theo Thông tư 200/2014/TT-BTC ngày 22/12/2014 ("Thông tư 200"), Thông tư 53/2016/TT-BTC ngày 21/03/2016 sửa đổi bổ sung một số điều của Thông tư 200 của Bộ Tài chính hướng dẫn chế độ kế toán doanh nghiệp và Thông tư 202/2014/TT-BTC ngày 22/12/2014 hướng dẫn phương pháp lập và trình bày Báo cáo tài chính hợp nhất.” [Doc_HUT_2025_Hopnhat, p.19]

Chưa chọn được trích đoạn đủ nội dung cho ngành nghề hoạt động và cơ cấu doanh nghiệp trong các đoạn đã truy xuất.

## Ý kiến kiểm toán

Trích từ tài liệu năm 2022: “Theo ý kiến của chúng tôi, báo cáo tài chính kèm theo đã phần ánh trung thực và hợp lý, trên các khía cạnh trọng yếu tình hình tài chính hợp nhất của Công ty cổ phần Tasco tại ngày 31 tháng 12 năm 2022, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất cho năm tài chính kết thúc cùng ngày, phù hợp với chuẩn mục kế toán, chế độ kế toán doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_HUT_2022_Hopnhat, p.7-8]

Trích từ tài liệu năm 2023: “Theo ý kiến của chúng tôi, báo cáo tài chính kèm theo đã phân ánh trung thực và hợp lý, trên các khía cạnh trọng yếu tình hình tài chính hợp nhất của Công ty cổ phần Tasco tại ngày 31 tháng 12 năm 2023, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất cho năm tài chính kết thúc cùng ngày, phù hợp với chuẩn mục kế toán, chế độ kế toán doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_HUT_2023_Hopnhat, p.7]

Trích từ tài liệu năm 2024: “Theo ý kiến của chúng tôi, báo cáo tài chính kèm theo đã phần ánh trung thực và hợp lý, trên các khóa cạnh trọng yếu tình hình tài chính hợp nhất của Công ty cổ phần Tasco tại ngày 31 tháng 12 năm 2024, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất cho năm tài chính kết thúc cùng ngày, phù hợp với chuẩn mục kế toán, chế độ kế toán doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_HUT_2024_Hopnhat, p.7]

Trích từ tài liệu năm 2025: “Theo ý kiến của chúng tôi, báo cáo tài chính hợp nhất kèm theo đã phân ánh trung thực và hợp lý, trên các khía cạnh trọng yếu tình hình tài chính hợp nhất của Công ty cổ phần Tasco tại ngày 31 tháng 12 năm 2025, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất cho năm tài chính kết thúc cùng ngày, phù hợp với chuẩn mục kế toán, chế độ kế toán doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_HUT_2025_Hopnhat, p.7]

Chưa chọn được trích đoạn đủ nội dung cho đơn vị kiểm toán và ngày ký báo cáo trong các đoạn đã truy xuất.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2022.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2023.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2024.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2025.

## Kết quả kinh doanh

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Doanh thu thuần | 1.073,16 [Doc_HUT_2022_Hopnhat, p.11] | 10.981,75 [Doc_HUT_2023_Hopnhat, p.11] | 30.228,89 [Doc_HUT_2024_Hopnhat, p.11] | — |
| Lợi nhuận gộp | 390,05 [Doc_HUT_2022_Hopnhat, p.11] | 1.031,79 [Doc_HUT_2023_Hopnhat, p.11] | 2.674,16 [Doc_HUT_2024_Hopnhat, p.11] | 3.373,70 [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận trước thuế | 190,98 [Doc_HUT_2022_Hopnhat, p.11] | 55,85 [Doc_HUT_2023_Hopnhat, p.11] | 425,82 [Doc_HUT_2024_Hopnhat, p.11] | 788,00 [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận sau thuế | 143,85 [Doc_HUT_2022_Hopnhat, p.11] | 56,35 [Doc_HUT_2023_Hopnhat, p.11] | 304,75 [Doc_HUT_2024_Hopnhat, p.11] | 630,26 [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận sau thuế của cổ đông công ty mẹ | 144,57 [Doc_HUT_2022_Hopnhat, p.11] | 47,20 [Doc_HUT_2023_Hopnhat, p.11] | 156,25 [Doc_HUT_2024_Hopnhat, p.11] | 492,18 [Doc_HUT_2025_Hopnhat, p.11] |

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Biên lợi nhuận gộp | 36,35% [Doc_HUT_2022_Hopnhat, p.11] | 9,40% [Doc_HUT_2023_Hopnhat, p.11] | 8,85% [Doc_HUT_2024_Hopnhat, p.11] | — |
| Biên lợi nhuận ròng | 13,40% [Doc_HUT_2022_Hopnhat, p.11] | 0,51% [Doc_HUT_2023_Hopnhat, p.11] | 1,01% [Doc_HUT_2024_Hopnhat, p.11] | — |

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Doanh thu thuần — YoY (%) | 923,31% [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] | 175,26% [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] | — |
| Lợi nhuận trước thuế — chênh lệch (tỷ đồng) | -135,14 [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] | 369,98 [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] | 362,18 [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận sau thuế — chênh lệch (tỷ đồng) | -87,50 [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] | 248,40 [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] | 325,52 [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11] |

Mức thay đổi của Doanh thu thuần năm 2024 so với năm 2023 là 175,26%. [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11]

Biên lợi nhuận gộp năm 2024 là 8,85%. [Doc_HUT_2024_Hopnhat, p.11]
Giới hạn dữ liệu. Không thể tính Biên lợi nhuận gộp năm 2025 vì đầu vào không đáp ứng điều kiện tính. [Doc_HUT_2025_Hopnhat, p.11]
Giới hạn dữ liệu. Không thể tính Biên lợi nhuận ròng năm 2025 vì đầu vào không đáp ứng điều kiện tính. [Doc_HUT_2025_Hopnhat, p.11]
Giới hạn dữ liệu. Không thể tính tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 vì chuỗi số liệu không đủ điều kiện để tính. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]
Giới hạn dữ liệu. Không thể tính xu hướng của Doanh thu thuần giai đoạn 2022–2025 vì chuỗi số liệu không đủ điều kiện để tính. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]
Giới hạn dữ liệu. Không thể tính mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 vì chuỗi số liệu không đủ điều kiện để tính. [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

## Tình hình tài chính

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tổng tài sản | 11.632,37 [Doc_HUT_2022_Hopnhat, p.9] | 26.749,00 [Doc_HUT_2023_Hopnhat, p.9] | 28.987,31 [Doc_HUT_2024_Hopnhat, p.9] | 52.231,24 [Doc_HUT_2025_Hopnhat, p.9] |
| Nợ phải trả | 7.758,90 [Doc_HUT_2022_Hopnhat, p.10] | 15.435,70 [Doc_HUT_2023_Hopnhat, p.10] | 17.436,45 [Doc_HUT_2024_Hopnhat, p.10] | 34.288,93 [Doc_HUT_2025_Hopnhat, p.10] |
| Vốn chủ sở hữu | 3.873,47 [Doc_HUT_2022_Hopnhat, p.10] | 11.313,30 [Doc_HUT_2023_Hopnhat, p.10] | 11.550,87 [Doc_HUT_2024_Hopnhat, p.10] | 17.942,31 [Doc_HUT_2025_Hopnhat, p.10] |
| Tiền và các khoản tương đương tiền | 953,43 [Doc_HUT_2022_Hopnhat, p.9] | 1.701,72 [Doc_HUT_2023_Hopnhat, p.8] | 2.876,16 [Doc_HUT_2024_Hopnhat, p.8] | 4.843,29 [Doc_HUT_2025_Hopnhat, p.8] |

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tỷ trọng nợ trên tổng tài sản | 66,70% [Doc_HUT_2022_Hopnhat, p.10] [Doc_HUT_2022_Hopnhat, p.9] | 57,71% [Doc_HUT_2023_Hopnhat, p.10] [Doc_HUT_2023_Hopnhat, p.9] | 60,15% [Doc_HUT_2024_Hopnhat, p.10] [Doc_HUT_2024_Hopnhat, p.9] | 65,65% [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9] |
| Tỷ trọng vốn chủ trên tổng tài sản | 33,30% [Doc_HUT_2022_Hopnhat, p.10] [Doc_HUT_2022_Hopnhat, p.9] | 42,29% [Doc_HUT_2023_Hopnhat, p.10] [Doc_HUT_2023_Hopnhat, p.9] | 39,85% [Doc_HUT_2024_Hopnhat, p.10] [Doc_HUT_2024_Hopnhat, p.9] | 34,35% [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9] |

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Tổng tài sản — YoY (%) | 129,95% [Doc_HUT_2022_Hopnhat, p.9] [Doc_HUT_2023_Hopnhat, p.9] | 8,37% [Doc_HUT_2023_Hopnhat, p.9] [Doc_HUT_2024_Hopnhat, p.9] | 80,19% [Doc_HUT_2024_Hopnhat, p.9] [Doc_HUT_2025_Hopnhat, p.9] |

Mức thay đổi của Tổng tài sản năm 2025 so với năm 2024 là 80,19%. [Doc_HUT_2024_Hopnhat, p.9] [Doc_HUT_2025_Hopnhat, p.9]

Tỷ trọng nợ trên tổng tài sản năm 2025 là 65,65%. [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9]

Tỷ trọng vốn chủ trên tổng tài sản năm 2025 là 34,35%. [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9]

## Lưu chuyển tiền tệ

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Lưu chuyển tiền thuần từ hoạt động kinh doanh | 479,86 [Doc_HUT_2022_Hopnhat, p.12] | 1.592,11 [Doc_HUT_2023_Hopnhat, p.12] | 2.062,62 [Doc_HUT_2024_Hopnhat, p.12] | -453,68 [Doc_HUT_2025_Hopnhat, p.12] |
| Lưu chuyển tiền thuần từ hoạt động đầu tư | 149,58 [Doc_HUT_2022_Hopnhat, p.12] | 88,05 [Doc_HUT_2023_Hopnhat, p.12] | -1.175,62 [Doc_HUT_2024_Hopnhat, p.12] | -2.712,00 [Doc_HUT_2025_Hopnhat, p.12] |
| Lưu chuyển tiền thuần từ hoạt động tài chính | -317,56 [Doc_HUT_2022_Hopnhat, p.13] | -931,86 [Doc_HUT_2023_Hopnhat, p.13] | 287,53 [Doc_HUT_2024_Hopnhat, p.13] | 5.132,71 [Doc_HUT_2025_Hopnhat, p.13] |

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế | 333,59% [Doc_HUT_2022_Hopnhat, p.12] [Doc_HUT_2022_Hopnhat, p.11] | 2.825,46% [Doc_HUT_2023_Hopnhat, p.12] [Doc_HUT_2023_Hopnhat, p.11] | 676,83% [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2024_Hopnhat, p.11] | -71,98% [Doc_HUT_2025_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.11] |

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Lưu chuyển tiền thuần từ hoạt động kinh doanh — chênh lệch (tỷ đồng) | 1.112,25 [Doc_HUT_2022_Hopnhat, p.12] [Doc_HUT_2023_Hopnhat, p.12] | 470,51 [Doc_HUT_2023_Hopnhat, p.12] [Doc_HUT_2024_Hopnhat, p.12] | -2.516,29 [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.12] |
| Lưu chuyển tiền thuần từ hoạt động đầu tư — chênh lệch (tỷ đồng) | -61,53 [Doc_HUT_2022_Hopnhat, p.12] [Doc_HUT_2023_Hopnhat, p.12] | -1.263,67 [Doc_HUT_2023_Hopnhat, p.12] [Doc_HUT_2024_Hopnhat, p.12] | -1.536,38 [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.12] |
| Lưu chuyển tiền thuần từ hoạt động tài chính — chênh lệch (tỷ đồng) | -614,30 [Doc_HUT_2022_Hopnhat, p.13] [Doc_HUT_2023_Hopnhat, p.13] | 1.219,40 [Doc_HUT_2023_Hopnhat, p.13] [Doc_HUT_2024_Hopnhat, p.13] | 4.845,18 [Doc_HUT_2024_Hopnhat, p.13] [Doc_HUT_2025_Hopnhat, p.13] |

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động kinh doanh giai đoạn 2024–2025 là -2,5 nghìn tỷ đồng. [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.12]

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động tài chính giai đoạn 2024–2025 là 4,8 nghìn tỷ đồng. [Doc_HUT_2024_Hopnhat, p.13] [Doc_HUT_2025_Hopnhat, p.13]

Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế năm 2025 là -71,98%. [Doc_HUT_2025_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.11]

</details>

<details>
<summary>Báo cáo C — bấm để mở toàn văn</summary>

## Thông tin doanh nghiệp và phạm vi dữ liệu

Trích từ tài liệu năm 2025: “Công ty áp dụng Chế độ kế toán doanh nghiệp Việt Nam ban hành kèm theo Thông tư 200/2014/TT-BTC ngày 22/12/2014 ("Thông tư 200"), Thông tư 53/2016/TT-BTC ngày 21/03/2016 sửa đổi bổ sung một số điều của Thông tư 200 của Bộ Tài chính hướng dẫn chế độ kế toán doanh nghiệp và Thông tư 202/2014/TT-BTC ngày 22/12/2014 hướng dẫn phương pháp lập và trình bày Báo cáo tài chính hợp nhất.” [Doc_HUT_2025_Hopnhat, p.19]

Chưa chọn được trích đoạn đủ nội dung cho ngành nghề hoạt động và cơ cấu doanh nghiệp trong các đoạn đã truy xuất.

## Ý kiến kiểm toán

Trích từ tài liệu năm 2022: “Theo ý kiến của chúng tôi, báo cáo tài chính kèm theo đã phần ánh trung thực và hợp lý, trên các khía cạnh trọng yếu tình hình tài chính hợp nhất của Công ty cổ phần Tasco tại ngày 31 tháng 12 năm 2022, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất cho năm tài chính kết thúc cùng ngày, phù hợp với chuẩn mục kế toán, chế độ kế toán doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_HUT_2022_Hopnhat, p.7-8]

Trích từ tài liệu năm 2023: “Theo ý kiến của chúng tôi, báo cáo tài chính kèm theo đã phân ánh trung thực và hợp lý, trên các khía cạnh trọng yếu tình hình tài chính hợp nhất của Công ty cổ phần Tasco tại ngày 31 tháng 12 năm 2023, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất cho năm tài chính kết thúc cùng ngày, phù hợp với chuẩn mục kế toán, chế độ kế toán doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_HUT_2023_Hopnhat, p.7]

Trích từ tài liệu năm 2024: “Theo ý kiến của chúng tôi, báo cáo tài chính kèm theo đã phần ánh trung thực và hợp lý, trên các khóa cạnh trọng yếu tình hình tài chính hợp nhất của Công ty cổ phần Tasco tại ngày 31 tháng 12 năm 2024, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất cho năm tài chính kết thúc cùng ngày, phù hợp với chuẩn mục kế toán, chế độ kế toán doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_HUT_2024_Hopnhat, p.7]

Trích từ tài liệu năm 2025: “Theo ý kiến của chúng tôi, báo cáo tài chính hợp nhất kèm theo đã phân ánh trung thực và hợp lý, trên các khía cạnh trọng yếu tình hình tài chính hợp nhất của Công ty cổ phần Tasco tại ngày 31 tháng 12 năm 2025, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất cho năm tài chính kết thúc cùng ngày, phù hợp với chuẩn mục kế toán, chế độ kế toán doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_HUT_2025_Hopnhat, p.7]

Chưa chọn được trích đoạn đủ nội dung cho đơn vị kiểm toán và ngày ký báo cáo trong các đoạn đã truy xuất.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2022.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2023.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2024.
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2025.

## Kết quả kinh doanh

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Doanh thu thuần | 1.073,16 [Doc_HUT_2022_Hopnhat, p.11] | 10.981,75 [Doc_HUT_2023_Hopnhat, p.11] | 30.228,89 [Doc_HUT_2024_Hopnhat, p.11] | 36.317,44 [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận gộp | 390,05 [Doc_HUT_2022_Hopnhat, p.11] | 1.031,79 [Doc_HUT_2023_Hopnhat, p.11] | 2.674,16 [Doc_HUT_2024_Hopnhat, p.11] | 3.373,70 [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận trước thuế | 190,98 [Doc_HUT_2022_Hopnhat, p.11] | 55,85 [Doc_HUT_2023_Hopnhat, p.11] | 425,82 [Doc_HUT_2024_Hopnhat, p.11] | 788,00 [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận sau thuế | 143,85 [Doc_HUT_2022_Hopnhat, p.11] | 56,35 [Doc_HUT_2023_Hopnhat, p.11] | 304,75 [Doc_HUT_2024_Hopnhat, p.11] | 630,26 [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận sau thuế của cổ đông công ty mẹ | 144,57 [Doc_HUT_2022_Hopnhat, p.11] | 47,20 [Doc_HUT_2023_Hopnhat, p.11] | 156,25 [Doc_HUT_2024_Hopnhat, p.11] | 492,18 [Doc_HUT_2025_Hopnhat, p.11] |

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Biên lợi nhuận gộp | 36,35% [Doc_HUT_2022_Hopnhat, p.11] | 9,40% [Doc_HUT_2023_Hopnhat, p.11] | 8,85% [Doc_HUT_2024_Hopnhat, p.11] | 9,29% [Doc_HUT_2025_Hopnhat, p.11] |
| Biên lợi nhuận ròng | 13,40% [Doc_HUT_2022_Hopnhat, p.11] | 0,51% [Doc_HUT_2023_Hopnhat, p.11] | 1,01% [Doc_HUT_2024_Hopnhat, p.11] | 1,74% [Doc_HUT_2025_Hopnhat, p.11] |

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Doanh thu thuần — YoY (%) | 923,31% [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] | 175,26% [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] | 20,14% [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận trước thuế — chênh lệch (tỷ đồng) | -135,14 [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] | 369,98 [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] | 362,18 [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11] |
| Lợi nhuận sau thuế — chênh lệch (tỷ đồng) | -87,50 [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] | 248,40 [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] | 325,52 [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11] |

Mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 là 20,14%. [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

Biên lợi nhuận gộp năm 2025 là 9,29%. [Doc_HUT_2025_Hopnhat, p.11]

Tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 là 223,46%. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

Doanh thu thuần tăng liên tục trong giai đoạn 2022–2025. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11]

## Tình hình tài chính

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tổng tài sản | 11.632,37 [Doc_HUT_2022_Hopnhat, p.9] | 26.749,00 [Doc_HUT_2023_Hopnhat, p.9] | 28.987,31 [Doc_HUT_2024_Hopnhat, p.9] | 52.231,24 [Doc_HUT_2025_Hopnhat, p.9] |
| Nợ phải trả | 7.758,90 [Doc_HUT_2022_Hopnhat, p.10] | 15.435,70 [Doc_HUT_2023_Hopnhat, p.10] | 17.436,45 [Doc_HUT_2024_Hopnhat, p.10] | 34.288,93 [Doc_HUT_2025_Hopnhat, p.10] |
| Vốn chủ sở hữu | 3.873,47 [Doc_HUT_2022_Hopnhat, p.10] | 11.313,30 [Doc_HUT_2023_Hopnhat, p.10] | 11.550,87 [Doc_HUT_2024_Hopnhat, p.10] | 17.942,31 [Doc_HUT_2025_Hopnhat, p.10] |
| Tiền và các khoản tương đương tiền | 953,43 [Doc_HUT_2022_Hopnhat, p.9] | 1.701,72 [Doc_HUT_2023_Hopnhat, p.8] | 2.876,16 [Doc_HUT_2024_Hopnhat, p.8] | 4.843,29 [Doc_HUT_2025_Hopnhat, p.8] |

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tỷ trọng nợ trên tổng tài sản | 66,70% [Doc_HUT_2022_Hopnhat, p.10] [Doc_HUT_2022_Hopnhat, p.9] | 57,71% [Doc_HUT_2023_Hopnhat, p.10] [Doc_HUT_2023_Hopnhat, p.9] | 60,15% [Doc_HUT_2024_Hopnhat, p.10] [Doc_HUT_2024_Hopnhat, p.9] | 65,65% [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9] |
| Tỷ trọng vốn chủ trên tổng tài sản | 33,30% [Doc_HUT_2022_Hopnhat, p.10] [Doc_HUT_2022_Hopnhat, p.9] | 42,29% [Doc_HUT_2023_Hopnhat, p.10] [Doc_HUT_2023_Hopnhat, p.9] | 39,85% [Doc_HUT_2024_Hopnhat, p.10] [Doc_HUT_2024_Hopnhat, p.9] | 34,35% [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9] |

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Tổng tài sản — YoY (%) | 129,95% [Doc_HUT_2022_Hopnhat, p.9] [Doc_HUT_2023_Hopnhat, p.9] | 8,37% [Doc_HUT_2023_Hopnhat, p.9] [Doc_HUT_2024_Hopnhat, p.9] | 80,19% [Doc_HUT_2024_Hopnhat, p.9] [Doc_HUT_2025_Hopnhat, p.9] |

Mức thay đổi của Tổng tài sản năm 2025 so với năm 2024 là 80,19%. [Doc_HUT_2024_Hopnhat, p.9] [Doc_HUT_2025_Hopnhat, p.9]

Tỷ trọng nợ trên tổng tài sản năm 2025 là 65,65%. [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9]

Tỷ trọng vốn chủ trên tổng tài sản năm 2025 là 34,35%. [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9]

## Lưu chuyển tiền tệ

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Lưu chuyển tiền thuần từ hoạt động kinh doanh | 479,86 [Doc_HUT_2022_Hopnhat, p.12] | 1.592,11 [Doc_HUT_2023_Hopnhat, p.12] | 2.062,62 [Doc_HUT_2024_Hopnhat, p.12] | -453,68 [Doc_HUT_2025_Hopnhat, p.12] |
| Lưu chuyển tiền thuần từ hoạt động đầu tư | 149,58 [Doc_HUT_2022_Hopnhat, p.12] | 88,05 [Doc_HUT_2023_Hopnhat, p.12] | -1.175,62 [Doc_HUT_2024_Hopnhat, p.12] | -2.712,00 [Doc_HUT_2025_Hopnhat, p.12] |
| Lưu chuyển tiền thuần từ hoạt động tài chính | -317,56 [Doc_HUT_2022_Hopnhat, p.13] | -931,86 [Doc_HUT_2023_Hopnhat, p.13] | 287,53 [Doc_HUT_2024_Hopnhat, p.13] | 5.132,71 [Doc_HUT_2025_Hopnhat, p.13] |

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế | 333,59% [Doc_HUT_2022_Hopnhat, p.12] [Doc_HUT_2022_Hopnhat, p.11] | 2.825,46% [Doc_HUT_2023_Hopnhat, p.12] [Doc_HUT_2023_Hopnhat, p.11] | 676,83% [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2024_Hopnhat, p.11] | -71,98% [Doc_HUT_2025_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.11] |

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Lưu chuyển tiền thuần từ hoạt động kinh doanh — chênh lệch (tỷ đồng) | 1.112,25 [Doc_HUT_2022_Hopnhat, p.12] [Doc_HUT_2023_Hopnhat, p.12] | 470,51 [Doc_HUT_2023_Hopnhat, p.12] [Doc_HUT_2024_Hopnhat, p.12] | -2.516,29 [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.12] |
| Lưu chuyển tiền thuần từ hoạt động đầu tư — chênh lệch (tỷ đồng) | -61,53 [Doc_HUT_2022_Hopnhat, p.12] [Doc_HUT_2023_Hopnhat, p.12] | -1.263,67 [Doc_HUT_2023_Hopnhat, p.12] [Doc_HUT_2024_Hopnhat, p.12] | -1.536,38 [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.12] |
| Lưu chuyển tiền thuần từ hoạt động tài chính — chênh lệch (tỷ đồng) | -614,30 [Doc_HUT_2022_Hopnhat, p.13] [Doc_HUT_2023_Hopnhat, p.13] | 1.219,40 [Doc_HUT_2023_Hopnhat, p.13] [Doc_HUT_2024_Hopnhat, p.13] | 4.845,18 [Doc_HUT_2024_Hopnhat, p.13] [Doc_HUT_2025_Hopnhat, p.13] |

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động kinh doanh giai đoạn 2024–2025 là -2,5 nghìn tỷ đồng. [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.12]

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động tài chính giai đoạn 2024–2025 là 4,8 nghìn tỷ đồng. [Doc_HUT_2024_Hopnhat, p.13] [Doc_HUT_2025_Hopnhat, p.13]

Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế năm 2025 là -71,98%. [Doc_HUT_2025_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.11]

</details>
