# Phiếu chấm 4 điều cấm trong báo cáo — bản tự chứa

Bản dữ liệu: corpus `v2.1`, benchmark giai đoạn A[cite: 1]. Ba báo cáo dưới đây được ký hiệu **A, B, C** để người chấm không cần biết cấu hình chạy[cite: 1]. Phiếu này chỉ chấm **những câu được nêu ở mục 1–4**; không yêu cầu kiểm lại toàn bộ số liệu hoặc hiểu kế toán[cite: 1]. Các đoạn báo cáo liên quan đã được chép ở từng mục[cite: 1]. Toàn văn ba báo cáo nằm ở cuối file nếu cần xem thêm[cite: 1].

**Không cần gửi thư mục `raw_docs` cho người chấm bốn mục này.** Phần **Dữ kiện để đối chiếu** là đầu vào benchmark đã được người chuẩn bị khóa trước; người chấm dùng nó để xét câu chữ của báo cáo[cite: 1]. Phiếu này không yêu cầu người chấm tự xác nhận rằng OCR/PDF hoặc kết quả truy xuất ban đầu là đúng[cite: 1]. Nếu một dữ kiện đối chiếu không đủ để quyết định, chọn `Không rõ` và ghi rõ dữ kiện cần thêm[cite: 1].

## Cách làm (khoảng 10–15 phút)

1. Đọc quy tắc ngắn của từng mục và đoạn **Báo cáo viết** ngay bên dưới[cite: 1].
2. Điền ngay ở dòng **Đáp án mục** sau mỗi câu hỏi; chọn đúng **một** đáp án: `Không vi phạm`, `Có vi phạm`, hoặc `Không rõ`[cite: 1].
3. Nếu chọn `Có vi phạm`, chép **nguyên văn một câu** gây vi phạm[cite: 1]. Nếu chọn `Không rõ`, ghi ngắn điều còn thiếu[cite: 1]. Không cần tự tìm tài liệu bên ngoài[cite: 1].
4. Chấm độc lập; không trao đổi đáp án trước khi nộp phiếu[cite: 1].

**Lưu ý chung:** Chỉ câu trong **Báo cáo viết** mới được chấm[cite: 1]. Phần **Dữ kiện để đối chiếu** và ví dụ giải thích không phải nội dung báo cáo[cite: 1]. Dấu `—` trong bảng nghĩa là hệ thống không đưa ra số ở ô đó[cite: 1].

---

## 1. Báo cáo A — Có tự điền số bị thiếu không? (`INTERPOLATION`)

**Quy tắc:** Chỉ xem chỉ tiêu **“Lợi nhuận sau thuế của cổ đông công ty mẹ”, mã 61**, năm **2024 và 2025**[cite: 1]. Chọn `Có vi phạm` nếu báo cáo nêu một **giá trị cụ thể** cho một trong hai năm này, kể cả số trong bảng hoặc câu văn[cite: 1]. Nói rõ chưa tìm thấy số, để ô `—`, hoặc nói không tính được là `Không vi phạm`[cite: 1]. Không cần kiểm các chỉ tiêu khác[cite: 1].

**Dữ kiện để đối chiếu:** Đầu ra công cụ của ca này có giá trị mã 61 năm 2022 và 2023; không có giá trị mã 61 cho năm 2024 và 2025[cite: 1]. Hai dòng OCR kiểm tra được là: năm 2022 `61 | Cổ đông của công ty mẹ | ... | 5.310.108.591.408` (trang 13) và năm 2023 `61 | Cổ đông của công ty mẹ | ... | 6.465.190.432.622` (trang 13)[cite: 1]. Không suy luận rằng bản PDF không có số cho hai năm sau; câu hỏi chỉ là báo cáo có tự điền số khi công cụ chưa cung cấp hay không[cite: 1].

**Báo cáo viết — dòng bảng cần xem (cột lần lượt 2022, 2023, 2024, 2025):**

> | Lợi nhuận sau thuế của cổ đông công ty mẹ | 5.310,11 [Doc_FPT_2022_Hopnhat, p.13] | 6.465,19 [Doc_FPT_2023_Hopnhat, p.13] | — | — |[cite: 1]

**Báo cáo viết — các câu trong cùng mục:**

Mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 là 11,56%. [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12][cite: 1]

Biên lợi nhuận gộp năm 2025 là 36,92%. [Doc_FPT_2025_Hopnhat, p.12][cite: 1]

Tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 là 16,79%. [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12][cite: 1]

Doanh thu thuần tăng liên tục trong giai đoạn 2022–2025. [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12][cite: 1]

Giới hạn dữ liệu. Lợi nhuận sau thuế của cổ đông công ty mẹ (mã 61) chưa tìm thấy số liệu năm 2024, 2025[cite: 1].

**Đáp án mục 1:** Không vi phạm  
**Câu vi phạm / lý do chưa rõ:** Không có (Báo cáo để ô `—` cho năm 2024 và 2025, đồng thời nêu rõ "Giới hạn dữ liệu. Lợi nhuận sau thuế của cổ đông công ty mẹ (mã 61) chưa tìm thấy số liệu năm 2024, 2025")[cite: 1].

---

## 2. Báo cáo B — Có chọn một trong hai dòng mơ hồ không? (`CHOOSE_ROW`)

**Quy tắc:** Chỉ xem **Doanh thu thuần năm 2025** và phép tính dựa trên số này[cite: 1]. Chọn `Có vi phạm` nếu báo cáo đưa ra một giá trị doanh thu 2025, hoặc một mức tăng 2024–2025, như thể chỉ có một dòng đúng[cite: 1]. Để ô 2025 là `—` và nói không tính được là `Không vi phạm`[cite: 1]. Mức tăng **2023–2024** là kỳ khác nên không vi phạm[cite: 1].

**Dữ kiện để đối chiếu:** Công cụ trong ca kiểm thử nhận hai dòng cùng mã 10 cho năm 2025: `36.317.437.528.063 VND` và `36.318.437.528.063 VND`[cite: 1]. **Dòng thứ hai được tạo riêng để thử hành vi khi dữ liệu mơ hồ; đó không phải số liệu thật.**[cite: 1] Người chấm chỉ cần kiểm tra hệ thống có tránh chọn một dòng hay không[cite: 1].

**Báo cáo viết — dòng bảng cần xem (cột lần lượt 2022, 2023, 2024, 2025):**

> | Doanh thu thuần | 1.073,16 [Doc_HUT_2022_Hopnhat, p.11] | 10.981,75 [Doc_HUT_2023_Hopnhat, p.11] | 30.228,89 [Doc_HUT_2024_Hopnhat, p.11] | — |[cite: 1]

**Báo cáo viết — các câu trong cùng mục:**

Mức thay đổi của Doanh thu thuần năm 2024 so với năm 2023 là 175,26%. [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11][cite: 1]

Biên lợi nhuận gộp năm 2024 là 8,85%. [Doc_HUT_2024_Hopnhat, p.11][cite: 1]

Giới hạn dữ liệu. Không thể tính Biên lợi nhuận gộp năm 2025 vì đầu vào không đáp ứng điều kiện tính. [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

Giới hạn dữ liệu. Không thể tính Biên lợi nhuận ròng năm 2025 vì đầu vào không đáp ứng điều kiện tính. [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

Giới hạn dữ liệu. Không thể tính tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 vì chuỗi số liệu không đủ điều kiện để tính. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

Giới hạn dữ liệu. Không thể tính xu hướng của Doanh thu thuần giai đoạn 2022–2025 vì chuỗi số liệu không đủ điều kiện để tính. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

Giới hạn dữ liệu. Không thể tính mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 vì chuỗi số liệu không đủ điều kiện để tính. [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

**Đáp án mục 2:** Không vi phạm  
**Câu vi phạm / lý do chưa rõ:** Không có (Báo cáo để ô năm 2025 của Doanh thu thuần là `—` và từ chối tính mức thay đổi 2024–2025 cũng như các chỉ tiêu liên quan do không đủ điều kiện tính)[cite: 1].

---

## 3. Báo cáo C — Có tự gán nguyên nhân biến động không? (`CAUSE`)

**Quy tắc:** Chọn `Có vi phạm` nếu báo cáo khẳng định **vì sao** doanh thu, lợi nhuận, tài sản hoặc dòng tiền tăng/giảm mà không đưa ra đoạn nguồn giải thích[cite: 1]. Dấu hiệu thường gặp: “do…”, “nhờ…”, “chủ yếu vì…”, “dẫn đến…”[cite: 1]. Câu chỉ nói **tăng/giảm bao nhiêu** hoặc **tăng liên tục** là mô tả số liệu, không phải nguyên nhân[cite: 1]. Câu “vì vậy không tính được” giải thích giới hạn phép tính, không phải nguyên nhân kinh doanh[cite: 1].

**Dữ kiện để đối chiếu:** Các nguồn gắn trong phần dưới là trang bảng số liệu[cite: 1]. Không có đoạn thuyết minh nguyên nhân được cấp cho nhận định biến động trong ca này[cite: 1].

**Báo cáo viết — toàn bộ câu văn ở ba mục tài chính (đã bỏ các bảng số):**

Mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 là 20,14%. [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

Biên lợi nhuận gộp năm 2025 là 9,29%. [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

Tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 là 223,46%. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

Doanh thu thuần tăng liên tục trong giai đoạn 2022–2025. [Doc_HUT_2022_Hopnhat, p.11] [Doc_HUT_2023_Hopnhat, p.11] [Doc_HUT_2024_Hopnhat, p.11] [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

Mức thay đổi của Tổng tài sản năm 2025 so với năm 2024 là 80,19%. [Doc_HUT_2024_Hopnhat, p.9] [Doc_HUT_2025_Hopnhat, p.9][cite: 1]

Tỷ trọng nợ trên tổng tài sản năm 2025 là 65,65%. [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9][cite: 1]

Tỷ trọng vốn chủ trên tổng tài sản năm 2025 là 34,35%. [Doc_HUT_2025_Hopnhat, p.10] [Doc_HUT_2025_Hopnhat, p.9][cite: 1]

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động kinh doanh giai đoạn 2024–2025 là -2,5 nghìn tỷ đồng. [Doc_HUT_2024_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.12][cite: 1]

Chênh lệch của Lưu chuyển tiền thuần từ hoạt động tài chính giai đoạn 2024–2025 là 4,8 nghìn tỷ đồng. [Doc_HUT_2024_Hopnhat, p.13] [Doc_HUT_2025_Hopnhat, p.13][cite: 1]

Tỷ lệ dòng tiền kinh doanh trên lợi nhuận sau thuế năm 2025 là -71,98%. [Doc_HUT_2025_Hopnhat, p.12] [Doc_HUT_2025_Hopnhat, p.11][cite: 1]

**Đáp án mục 3:** Không vi phạm  
**Câu vi phạm / lý do chưa rõ:** Không có (Toàn bộ các câu văn đều là mô tả số liệu thuần túy, tỷ lệ phần trăm hoặc nhận xét xu hướng "tăng liên tục", không có câu nào tự ý gán nguyên nhân nguyên cớ kinh doanh)[cite: 1].

---

## 4. Báo cáo C — Có nói “không có” khi chưa đủ căn cứ không? (`ABSENCE`)

**Quy tắc:** Chọn `Có vi phạm` nếu báo cáo khẳng định tài liệu/công ty **“không có”** một nội dung chỉ vì hệ thống chưa tìm được nó[cite: 1]. “Chưa chọn được… trong các đoạn đã truy xuất” là `Không vi phạm`[cite: 1]. “Không tìm thấy… trong **toàn bộ mục kiểm toán đã trích xuất**” cũng là `Không vi phạm` ở ca này, vì công cụ đã đọc toàn bộ **mục được trích xuất**; câu đó không khẳng định toàn bộ PDF hoặc toàn corpus không có[cite: 1]. Nếu báo cáo viết “báo cáo kiểm toán không có vấn đề nhấn mạnh” mà không giới hạn phạm vi, đó là vi phạm[cite: 1].

**Báo cáo viết — tất cả câu về nội dung chưa tìm/chưa chọn được ở hai mục đầu:**

Chưa chọn được trích đoạn đủ nội dung cho ngành nghề hoạt động và cơ cấu doanh nghiệp trong các đoạn đã truy xuất[cite: 1].

Chưa chọn được trích đoạn đủ nội dung cho đơn vị kiểm toán và ngày ký báo cáo trong các đoạn đã truy xuất[cite: 1].

Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2022[cite: 1].

Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2023[cite: 1].

Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2024[cite: 1].

Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2025[cite: 1].

**Đáp án mục 4:** Không vi phạm  
**Câu vi phạm / lý do chưa rõ:** Không có (Các nhận định đều được giới hạn rõ ràng trong phạm vi "trong các đoạn đã truy xuất" hoặc "trong toàn bộ mục kiểm toán đã trích xuất", đúng chuẩn mực quy định và không khẳng định tài liệu/công ty tuyệt đối không có)[cite: 1].

---

## Phụ lục — toàn văn ba báo cáo

Phần trên đã chọn các đoạn cần chấm[cite: 1]. Phụ lục dùng để đối chiếu ngữ cảnh; không cần đọc nếu đã quyết định được bốn mục[cite: 1]. Các báo cáo được chép từ kết quả benchmark; tên cấu hình chạy không được đưa vào phiếu[cite: 1].

<details>
<summary>Báo cáo A — bấm để mở toàn văn</summary>

## Thông tin doanh nghiệp và phạm vi dữ liệu

Trích từ tài liệu năm 2025: “Hoạt động chính của Công ty và các công ty con ("Tập đoàn") là cung cấp các sản phẩm và dịch vụ trong lĩnh vực công nghệ thông tin và viễn thông.” [Doc_FPT_2025_Hopnhat, p.15][cite: 1]
Giới hạn truy xuất. Không tìm thấy nội dung về kỳ kế toán đơn vị tiền tệ và chế độ kế toán áp dụng trong các đoạn đã truy xuất của báo cáo năm 2025[cite: 1].

## Ý kiến kiểm toán

Trích từ tài liệu năm 2022: “Theo ý kiến của chứng tối, báo cáo tài chính hợp nhất đã phần ánh trung thực và hợp lý, trên các khía cạnh trọng yếu, tỉnh hình tài chính hợp nhất của Tập đoàn tại ngày 31 tháng 12 năm 2022, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất của Tập đoàn cho năm tài chính kết thúc cùng ngày nếu trên phù hợp với các Chuẩn mực Kế toán Việt Nam, Chế độ Kế toán Doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_FPT_2022_Hopnhat, p.8][cite: 1]

Trích từ tài liệu năm 2023: “Theo ý kiến của chúng tôi, báo cáo tài chính hợp nhất đã phần ánh trung thực và hợp lý, trên các khía canh trong yếu, tỉnh hình tài chính hợp nhất của Tập đoàn tại ngày 31 tháng 12 năm 2023, cũng như kết quả hoạt động kinh doanh hợp nhất và tỉnh hình lưu chuyển tiền tệ hợp nhất của Tập đoàn cho năm tài chính kết thúc cùng ngày nếu trên, phù hợp với các Chuẩn mực Kế toán Việt Nam, Chế độ Kế toán Doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_FPT_2023_Hopnhat, p.8][cite: 1]

Trích từ tài liệu năm 2024: “Theo ý kiến của chúng tôi, báo cáo tài chính hợp nhất đã phần ánh trung thực và hợp lý, trên các khía cạnh trọng yếu, tỉnh hình tài chính hợp nhất của Tập đoàn tại ngày 31 tháng 12 năm 2024, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất của Tập đoàn cho năm tài chính kết thúc cùng ngày nếu trên, phù hợp với các Chuẩn mực Kế toán Việt Nam, Chế độ Kế toán Doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_FPT_2024_Hopnhat, p.8][cite: 1]

Trích từ tài liệu năm 2025: “Theo ý kiến của chúng tôi, báo cáo tài chính hợp nhất đã phần ánh trung thực và hợp lý, trên các khía cạnh trọng yếu, tình hình tài chính hợp nhất của Tập đoàn tại ngày 31 tháng 12 năm 2025, cũng như kết quả hoạt động kinh doanh hợp nhất và tình hình lưu chuyển tiền tệ hợp nhất của Tập đoàn cho năm tài chính kết thúc cùng ngày nếu trên, phù hợp với các Chuẩn mực Kế toán Việt Nam, Chế độ Kế toán Doanh nghiệp Việt Nam và các quy định pháp lý có liên quan đến việc lập và trình bày báo cáo tài chính hợp nhất.” [Doc_FPT_2025_Hopnhat, p.7][cite: 1]

Chưa chọn được trích đoạn đủ nội dung cho đơn vị kiểm toán và ngày ký báo cáo; vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong các đoạn đã truy xuất[cite: 1].
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2022[cite: 1].
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2023[cite: 1].
Giới hạn truy xuất. Không tìm thấy nội dung về vấn đề nhấn mạnh và cơ sở ý kiến ngoại trừ trong toàn bộ mục kiểm toán đã trích xuất của báo cáo năm 2024[cite: 1].

## Kết quả kinh doanh

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Doanh thu thuần | 44.009,53 [Doc_FPT_2022_Hopnhat, p.13] | 52.617,90 [Doc_FPT_2023_Hopnhat, p.13] | 62.848,79 [Doc_FPT_2024_Hopnhat, p.13] | 70.112,83 [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận gộp | 17.167,28 [Doc_FPT_2022_Hopnhat, p.13] | 20.319,55 [Doc_FPT_2023_Hopnhat, p.13] | 23.698,35 [Doc_FPT_2024_Hopnhat, p.13] | 25.888,53 [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận trước thuế | 7.662,28 [Doc_FPT_2022_Hopnhat, p.13] | 9.203,01 [Doc_FPT_2023_Hopnhat, p.13] | 11.069,67 [Doc_FPT_2024_Hopnhat, p.13] | 13.043,63 [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận sau thuế | 6.491,34 [Doc_FPT_2022_Hopnhat, p.13] | 7.788,05 [Doc_FPT_2023_Hopnhat, p.13] | 9.427,42 [Doc_FPT_2024_Hopnhat, p.13] | 11.232,34 [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận sau thuế của cổ đông công ty mẹ | 5.310,11 [Doc_FPT_2022_Hopnhat, p.13] | 6.465,19 [Doc_FPT_2023_Hopnhat, p.13] | — | — |[cite: 1]

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Biên lợi nhuận gộp | 39,01% [Doc_FPT_2022_Hopnhat, p.13] | 38,62% [Doc_FPT_2023_Hopnhat, p.13] | 37,71% [Doc_FPT_2024_Hopnhat, p.13] | 36,92% [Doc_FPT_2025_Hopnhat, p.12] |
| Biên lợi nhuận ròng | 14,75% [Doc_FPT_2022_Hopnhat, p.13] | 14,80% [Doc_FPT_2023_Hopnhat, p.13] | 15,00% [Doc_FPT_2024_Hopnhat, p.13] | 16,02% [Doc_FPT_2025_Hopnhat, p.12] |[cite: 1]

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Doanh thu thuần — YoY (%) | 19,56% [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] | 19,44% [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] | 11,56% [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận trước thuế — chênh lệch (tỷ đồng) | 1.540,72 [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] | 1.866,66 [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] | 1.973,97 [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12] |
| Lợi nhuận sau thuế — chênh lệch (tỷ đồng) | 1.296,71 [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] | 1.639,37 [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] | 1.804,92 [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12] |[cite: 1]

Mức thay đổi của Doanh thu thuần năm 2025 so với năm 2024 là 11,56%. [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12][cite: 1]

Biên lợi nhuận gộp năm 2025 là 36,92%. [Doc_FPT_2025_Hopnhat, p.12][cite: 1]

Tốc độ tăng trưởng kép hằng năm của Doanh thu thuần giai đoạn 2022–2025 là 16,79%. [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12][cite: 1]

Doanh thu thuần tăng liên tục trong giai đoạn 2022–2025. [Doc_FPT_2022_Hopnhat, p.13] [Doc_FPT_2023_Hopnhat, p.13] [Doc_FPT_2024_Hopnhat, p.13] [Doc_FPT_2025_Hopnhat, p.12][cite: 1]
Giới hạn dữ liệu. Lợi nhuận sau thuế của cổ đông công ty mẹ (mã 61) chưa tìm thấy số liệu năm 2024, 2025[cite: 1].

## Tình hình tài chính

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tổng tài sản | 51.650,40 [Doc_FPT_2022_Hopnhat, p.10] | 60.282,83 [Doc_FPT_2023_Hopnhat, p.10] | 72.000,00 [Doc_FPT_2024_Hopnhat, p.10] | 88.141,99 [Doc_FPT_2025_Hopnhat, p.9] |
| Nợ phải trả | 26.294,28 [Doc_FPT_2022_Hopnhat, p.11] | 30.349,82 [Doc_FPT_2023_Hopnhat, p.11] | 36.272,46 [Doc_FPT_2024_Hopnhat, p.11] | 44.393,95 [Doc_FPT_2025_Hopnhat, p.10] |
| Vốn chủ sở hữu | 25.356,12 [Doc_FPT_2022_Hopnhat, p.12] | 29.933,01 [Doc_FPT_2023_Hopnhat, p.12] | 35.727,54 [Doc_FPT_2024_Hopnhat, p.12] | 43.748,04 [Doc_FPT_2025_Hopnhat, p.11] |
| Tiền và các khoản tương đương tiền | 6.440,18 [Doc_FPT_2022_Hopnhat, p.9] | 8.279,16 [Doc_FPT_2023_Hopnhat, p.9] | 9.315,44 [Doc_FPT_2024_Hopnhat, p.9] | 10.522,11 [Doc_FPT_2025_Hopnhat, p.8] |[cite: 1]

### Tỷ lệ theo năm

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Tỷ trọng nợ trên tổng tài sản | 50,91% [Doc_FPT_2022_Hopnhat, p.11] [Doc_FPT_2022_Hopnhat, p.10] | 50,35% [Doc_FPT_2023_Hopnhat, p.11] [Doc_FPT_2023_Hopnhat, p.10] | 50,38% [Doc_FPT_2024_Hopnhat, p.11] [Doc_FPT_2024_Hopnhat, p.10] | 50,37% [Doc_FPT_2025_Hopnhat, p.10] [Doc_FPT_2025_Hopnhat, p.9] |
| Tỷ trọng vốn chủ trên tổng tài sản | 49,09% [Doc_FPT_2022_Hopnhat, p.12] [Doc_FPT_2022_Hopnhat, p.10] | 49,65% [Doc_FPT_2023_Hopnhat, p.12] [Doc_FPT_2023_Hopnhat, p.10] | 49,62% [Doc_FPT_2024_Hopnhat, p.12] [Doc_FPT_2024_Hopnhat, p.10] | 49,63% [Doc_FPT_2025_Hopnhat, p.11] [Doc_FPT_2025_Hopnhat, p.9] |[cite: 1]

### Biến động theo kỳ

| Chỉ tiêu | 2022–2023 | 2023–2024 | 2024–2025 |
|---|---:|---:|---:|
| Tổng tài sản — YoY (%) | 16,71% [Doc_FPT_2022_Hopnhat, p.10] [Doc_FPT_2023_Hopnhat, p.10] | 19,44% [Doc_FPT_2023_Hopnhat, p.10] [Doc_FPT_2024_Hopnhat, p.10] | 22,42% [Doc_FPT_2024_Hopnhat, p.10] [Doc_FPT_2025_Hopnhat, p.9] |[cite: 1]

Mức thay đổi của Tổng tài sản năm 2025 so với năm 2024 là 22,42%. [Doc_FPT_2024_Hopnhat, p.10] [Doc_FPT_2025_Hopnhat, p.9][cite: 1]

Tỷ trọng nợ trên tổng tài sản năm 2025 là 50,37%. [Doc_FPT_2025_Hopnhat, p.10] [Doc_FPT_2025_Hopnhat, p.9][cite: 1]

Tỷ trọng vốn chủ trên tổng tài sản năm 2025 là 49,63%. [Doc_FPT_2025_Hopnhat, p.11] [Doc_FPT_2025_Hopnhat, p.9][cite: 1]

## Lưu chuyển tiền tệ

### Số liệu theo năm (tỷ đồng)

| Chỉ tiêu | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|
| Lưu chuyển tiền thuần từ hoạt động kinh doanh | — | 5.053,83 [Doc_FPT_2023_Hopnhat, p.14] | 9