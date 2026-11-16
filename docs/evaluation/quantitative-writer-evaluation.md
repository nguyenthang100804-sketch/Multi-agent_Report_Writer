# Đánh giá Writer W4 trên Dev

Chạy `scripts/evaluation/evaluate_writer.py hut gmd` trên research state đã lưu, với `gemini-3.8-flash`, prompt `w4-v1`, nhiệt độ 0. Đã đo trước khi thêm quy tắc validator chống lặp tiền tố kỳ; prompt chưa đổi. Dữ liệu chi tiết từng lượt ở [`writer_w4_eval_dev.json`](../../data/report_output/writer_w4_eval_dev.json). Không dùng ticker Test để chỉnh prompt.

| Chỉ số | HUT | GMD |
|---|---:|---:|
| Section TemplateWriter qua Verifier tất định | 3/3 | 3/3 |
| Section LLM Writer/fallback qua Verifier tất định | 3/3 | 3/3 |
| Section do LLM viết và qua, không tính fallback | 2/3 | 2/3 |
| LLM qua ngay lượt đầu | 2/3 | 1/3 |
| Lượt sửa trung bình mỗi section | 0,67 | 1,00 |
| Fallback về TemplateWriter | 1/3 | 1/3 |
| Lỗi chữ số tự gõ | 0 | 0 |
| Ứng viên nhân quả/so sánh/dự báo bị quét | 0 | 0 |
| Tổng token theo API | 27.786 | 34.243 |
| Thời gian gọi Writer | 205 giây | 121 giây |

HUT S3 và GMD S3 đều trả ít hơn ba câu ở cả ba lượt, nên dùng fallback. GMD S5 cần một lượt sửa rồi qua. Các section còn lại qua ngay lượt đầu. Không thấy số tự gõ; điều này chỉ nói về sáu lượt section của hai mã này.

Đọc bản LLM vẫn thấy câu “Vào năm năm 2025” và “Trong giai đoạn năm 2025 so với năm 2024” ở GMD: model viết tiền tố dù placeholder `P:C:` đã sinh “năm” hoặc “giai đoạn”. Sau phép đo này, validator đã thêm lỗi `duplicated_period_prefix` để buộc sửa hoặc fallback. Bản đo trên phản ánh **trạng thái trước quy tắc mới**; chưa chạy lại API để đo tỷ lệ mới. Bản LLM cũng có câu dài ghép hai phép tính, nên chất lượng diễn đạt chưa rõ hơn TemplateWriter.

Log ở lượt đo ban đầu không lưu JSON thô, số block hoặc thời gian từng lần gọi. W4 hiện có chế độ Dev `record_raw_outputs=True`, lưu `raw_outputs_by_attempt`, `block_counts_by_attempt` và `attempt_elapsed_ms`; phản hồi `need_3_to_5_observations` cũng nói rõ số block nhận được. Các trường này chỉ được điền ở lượt đo mới, không thể khôi phục cho lượt đo cũ. Chưa đổi prompt hoặc mức suy luận trước khi chẩn đoán được ba output S3.

`build_llm_writer()` hiện là lựa chọn tùy chọn; `build_template_writer()` vẫn là mặc định hợp lý cho phần định lượng. Đánh giá từ người đọc ngoài dự án và Verifier ngữ nghĩa mức `full` vẫn cần trước khi dùng bản LLM như báo cáo hoàn tất.

## Chẩn đoán S3 và đo lại với W4-v2

Người dùng cho phép gửi đúng SectionView S3 của HUT và GMD tới Gemini và lưu phản hồi nguyên văn. Log Dev nằm tại [HUT lần chẩn đoán](../../data/report_output/hut_s3_w4_diagnostic.json), [GMD lần chẩn đoán](../../data/report_output/gmd_s3_w4_diagnostic.json), [HUT W4-v2](../../data/report_output/hut_s3_w4_v2.json) và [GMD W4-v2](../../data/report_output/gmd_s3_w4_v2.json). Các log này chứa output thô; không đưa vào dữ liệu gửi cho model ở lượt sau ngoài feedback validator.

Ở prompt cũ, lượt đầu của **cả hai mã** có bốn câu trong **một block**. Validator đếm block, nên báo `need_3_to_5_observations`. Feedback mới ghi “received 1 blocks; need 3–5 blocks, one sentence per block”; lượt hai của cả hai mã trả bốn block và qua. Đây là lỗi giao thức block và phản hồi sửa lỗi, không phải thiếu nội dung phân tích. HUT mất 29,0 rồi 13,8 giây; GMD mất 22,5 rồi 118,0 giây. Mỗi thời gian là một lần gọi `generate_content`; adapter không có vòng retry nội bộ, nhưng log không chứng minh được có hay không chờ trong SDK hoặc dịch vụ.

W4-v2 chốt `Y:` thành “năm 2025”, cấm tiền tố “năm/giai đoạn” trước `Y:` và `P:C:`, yêu cầu một câu mỗi block, chặn trộn “nghìn tỷ đồng” và “tỷ đồng” trong cùng câu, và chuyển “tương ứng” sang danh sách cảnh báo. Adapter dùng thinking `LOW`; prompt ghi rõ quy tắc block.

| S3 W4-v2 | HUT | GMD |
|---|---:|---:|
| Block ở từng lượt | 4 | 4, 4, 4 |
| Qua lượt đầu | Có | Không |
| Fallback | Không | Không |
| Lỗi sửa | Không | Trộn thang tiền ở lượt 1–2 |
| Thời gian mỗi lượt | 4,45 giây | 4,12; 3,89; 3,62 giây |
| Tổng token | 3.466 | 10.291 |

W4-v2 đã thay đồng thời prompt, validator và mức suy luận; chênh lệch thời gian so với lượt trước **không phải** phép đo riêng tác động của thinking `LOW`. Phạm vi cấp phép vừa rồi chỉ gồm S3 HUT/GMD. Sáu mã Dev có `12/12` chuỗi an toàn theo [khảo sát corpus](../audits/metric-coverage-corpus-audit.md) và thuộc [tập Dev](../../configs/eval_dataset_split.json) là BSR, BWE, DCM, GAS, GEX, QNS; chưa gửi SectionView của các mã đó tới API.

Sau phép đo S3 W4-v2, renderer được sửa để mọi giá trị tiền trong **cùng một câu** dùng chung thang; validator `mixed_monetary_scale` còn giữ để phát hiện hồi quy. Test GMD dùng chênh lệch dòng tiền kinh doanh 2022–2023 và mức năm 2023, cả hai hiển thị bằng tỷ đồng. Chưa chạy lại API sau sửa renderer; kết quả W4-v2 phía trên là mốc trước sửa này. S4/S5 HUT/GMD và sáu mã Dev khác vẫn chưa được phép gửi tới Gemini trong phạm vi cấp phép vừa rồi.

Phát lại **output thô lượt đầu GMD S3 W4-v2** qua renderer mới trên cùng research state cho kết quả qua ngay một lượt, không fallback. Đây là test cục bộ của lỗi thang số; không phải lượt gọi API mới. Đã tạo research state cục bộ cho BSR, BWE, DCM, GAS, GEX, QNS: mỗi mã có 43 phép tính `ok`, không có `cannot_compute`, và ba section S3–S5 của TemplateWriter đều qua Verifier tất định. Fixture nằm trong `data/report_output/*_writer_eval_research_state.json`; chưa gửi dữ liệu của các mã đó ra ngoài workspace.

## Đo W4-v3 trên 22 SectionView được cho phép

Người dùng cho phép gửi S4–S5 của HUT/GMD và S3–S5 của BSR, BWE, DCM, GAS, GEX, QNS tới Gemini. Script đánh giá lọc outline theo `--sections` trước khi dựng SectionView và lưu kết quả theo `--run-label`, nên không ghi đè lượt đo cũ. Log chứa nguyên văn 30 phản hồi của 22 SectionView, gồm mọi lượt sửa: [HUT/GMD](../../data/report_output/writer_w4_v3_hut_gmd_s45_eval.json) và [sáu mã Dev](../../data/report_output/writer_w4_v3_six_dev_s345_eval.json). Báo cáo Markdown từng mã có cùng hậu tố run label trong `data/report_output`.

| Chỉ số | HUT/GMD S4–S5 | Sáu mã Dev S3–S5 | Tổng |
|---|---:|---:|---:|
| Section TemplateWriter qua Verifier tất định | 4/4 | 18/18 | 22/22 |
| Section LLM hoặc fallback qua Verifier tất định | 4/4 | 18/18 | 22/22 |
| Section do LLM viết và qua, không tính fallback | 4/4 | 17/18 | 21/22 |
| LLM qua lượt đầu | 2/4 | 13/18 | 15/22 |
| Fallback | 0 | 1 | 1 |
| Tổng thời gian Writer | 27,1 giây | 97,8 giây | 124,9 giây |
| Tổng token do API ghi nhận | 17.081 | 71.752 | 88.833 |

GEX S5 dùng fallback sau ba lượt. Phần lớn lượt sửa ở S5 xuất phát từ model tự thêm `|abs` vào placeholder chênh lệch dòng tiền, dù không có trong menu của section; Verifier chặn được. GEX S5 còn dùng `P:C:` thiếu phần `difference` ở lượt hai. Không thấy lỗi chữ số tự gõ trong các log. Đây là kết quả tính hợp lệ trên 22 section, không phải đánh giá chất lượng văn. `thinking_tokens` được ghi là 0 trong hai file, nên không suy diễn mức suy luận thực tế từ trường này. Các bản vẫn chỉ qua Verifier tất định và có trạng thái `incomplete` cho đến khi có kiểm chứng ngữ nghĩa mức `full`.

## Kết quả đọc mù

Theo đánh giá đọc mù do người dùng thực hiện với mentor, văn do LLM viết tốt hơn TemplateWriter, nhưng mức cải thiện không lớn. Cần đánh giá lại khi báo cáo có thêm phần thuyết minh. Kết luận này là đánh giá của người đọc; chưa có điểm số hoặc số người chọn từng bản được ghi trong tài liệu, nên không suy ra mức chênh lệch định lượng. TemplateWriter tiếp tục là baseline để so sánh ở lượt sau.

## Sửa hợp đồng S5 và đo lại trên tám mã Dev

Phân theo section ở lượt W4-v3: S3 và S4 qua ngay lượt đầu **14/14**, còn S5 chỉ **1/8**. BWE và DCM S5 đã lọt qua với câu “giảm -325,4 tỷ đồng” và “giảm -853,4 tỷ đồng”. Bảy lượt S5 đầu khác dùng `C:...|abs`, nằm ngoài hợp đồng placeholder; lỗi `literal_digit` trong log là hệ quả của việc parser không nhận trọn token. Tổng **11** lỗi `literal_digit_errors` của W4-v3 vì vậy không phải 11 lần model tự gõ số.

Lượt đo W4-v4 dùng prompt phiên bản `w4-v3` và thêm `D:` cho YoY và chênh lệch: renderer lấy hướng và trị tuyệt đối từ `CalculationResult`, ghi claim bằng giá trị có dấu gốc, và dùng chung thang tiền trong câu. Validator chặn “giảm C:” có dấu kép hoặc sai dấu, giữ “tăng C:” khi giá trị dương, và trả đúng một thông báo cho `C:...|abs` mà không cộng lỗi chữ số và định danh phát sinh. Bộ quét nay chặn từ cực trị chưa có claim như “đỉnh”; cảnh báo “tương ứng” được bỏ khi số trước là fact tử số của tỷ lệ ngay sau, và giữ cho quan hệ khác. Prompt và SectionView mô tả `D:` và giá trị hiển thị của nó.

Đã đo lại **chỉ S5** của HUT, GMD, BSR, BWE, DCM, GAS, GEX, QNS dưới prompt W4-v4. [Log W4-v4](../../data/report_output/writer_w4_v4_eight_dev_s5_eval.json) lưu nguyên văn tám phản hồi; báo cáo Markdown từng mã có hậu tố `w4_v4_eight_dev_s5` trong `data/report_output`.

| Chỉ số S5 | W4-v3 | W4-v4 |
|---|---:|---:|
| LLM qua ngay lượt đầu | 1/8 | 8/8 |
| LLM viết và qua, không tính fallback | 7/8 | 8/8 |
| Fallback | 1 | 0 |
| Thời gian Writer cho tám section | Chưa tách trong bảng cũ | 36,2 giây |
| Token API ghi nhận cho tám section | Chưa tách trong bảng cũ | 26.930 |

Cả tám output mới dùng `D:`; không thấy “tăng -” hoặc “giảm -” trong Markdown. Đây là đo lại trên **chính các mã dùng để tìm lỗi**, nên xác nhận bản sửa giải quyết lỗi quan sát được, chưa đo khả năng tổng quát trên mã khác. Bộ 132 test qua. Verifier ngữ nghĩa và đánh giá lại sau khi có phần thuyết minh vẫn còn mở.

## Kiểm tra câu hướng và hồi quy S3–S4

Đọc Markdown W4-v4 cho thấy DCM S5 “tăng ... lên mức” và BWE/GMD S5 “giảm ... xuống mức/còn” đều khớp dấu phép tính. Dù vậy, các từ hướng do model tự viết ở cạnh `D:` không có claim riêng; HUT S5 còn viết “chuyển sang” và “tiếp tục”. Validator hiện cấm từ hướng tự viết trong câu có `D:`, so dấu khi câu dùng một phép YoY/chênh lệch `C:`, và bộ quét chặn “tiếp tục”, “chuyển sang”, “đảo chiều”, “quay lại”. Test phát lại output thô DCM, BWE, GMD, HUT S5 và QNS S4 cũ, xác nhận từng lỗi bị chặn.

Đo [S3–S4 của tám mã Dev](../../data/report_output/writer_w4_v5_eight_dev_s34_eval.json) dưới prompt `w4-v4`: 16/16 section do LLM viết và qua Verifier, 0 fallback; **15/16 qua ngay lượt đầu** trong phép gọi API. HUT S3 cần ba lượt vì Verifier cũ cắt “hằng năm 223,46%” thành số thứ tự “năm 223” và số lạc “46”. Đã bỏ “năm” khỏi quy tắc bỏ qua số thứ tự; phát lại nguyên văn output đầu HUT S3 qua code sửa cho kết quả qua một lượt. Đây là kết quả phát lại cục bộ, không phải một phép gọi API mới. Cả 135 test qua.

Đánh giá cổng liên quan Researcher trên 11 truy vấn note HUT được ghi riêng tại [audit HUT](hut-note-relevance-audit.md). Kết quả hiện chưa đủ để viết chế độ trích đoạn an toàn.

## Kiểm tra FPT và hợp đồng render

Prompt `w4-v4` đã bỏ sót `T:`; phiên bản `w4-v5` mô tả rõ cách dùng xu hướng có claim. [Lượt FPT S3–S5](../../data/report_output/writer_w4_v6_fpt_s345_eval.json) dưới prompt mới có **3/3 section do LLM viết và qua ngay lượt đầu**, không fallback; S3 dùng `T:` một lần. [Báo cáo FPT](../../data/report_output/fpt_w4_v6_fpt_s345_llm_writer_report.md) vẫn hiển thị giới hạn mã 61 thiếu năm 2024–2025, dữ liệu trích xuất thiếu ở mã 20/30, các phép tính không làm được và hai chênh lệch cột năm trước; các câu giới hạn do code sinh. GVR chưa có research state cục bộ; OIL thuộc tập Test nên không chạy.

Validator nay kiểm dấu của từ hướng giữa hai `E:` cùng chỉ tiêu theo phép trừ giá trị gốc; test HUT chấp nhận chiều 2022→2025 và bác chiều đảo lại. Test property phát lại **2.322 token hợp lệ** từ menu `E/Y/C/P/D/T` của chín fixture trong các câu mẫu có kỳ, qua renderer rồi Verifier tất định. Quy tắc đọc số của Verifier cũng không nuốt phần thập phân sau “năm”, “tháng” hay “quý”; có test cho “điểm phần trăm”. Đây là test từng token trong câu mẫu, chưa bao quát mọi cách ghép nhiều token trong văn xuôi.

Kiểm Markdown W4-v5: HUT S3 “từ 1,1 nghìn tỷ … lên 36,3 nghìn tỷ” khớp dữ liệu; GEX S3 nêu YoY 12,52% rồi 17,07% theo đúng thứ tự 2024→2025. Sau kiểm này, TemplateWriter vẫn là đường mặc định cho phần định lượng. Phần định tính chờ sửa phân loại/index các mục thuyết minh chi tiết như [audit cổng note](hut-note-relevance-audit.md) ghi rõ.
