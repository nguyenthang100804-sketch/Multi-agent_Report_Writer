# Tóm tắt các thay đổi sáng 09/11/2026

## Kết quả hiện tại

Snapshot dữ liệu **v2.1 đã được kích hoạt**. Lỗi gắn các bảng thuyết minh thành báo cáo tài chính chính đã được sửa; 141 tài liệu được parse lại và lập chỉ mục trong collection mới. Dữ liệu và collection v1 vẫn được giữ để đối chiếu. Phần định lượng S3–S5 của ba mẫu HUT, GMD và FPT đã được sinh lại bằng TemplateWriter và đều qua Verifier tất định. Phần định tính W6, đặc biệt S7, **chưa được coi là hoàn tất**.

| Chỉ số | Trước (v1) | Đang dùng (v2.1) |
|---|---:|---:|
| Tài liệu | 141 | 141 |
| Chunk | 30.282 | 32.175 (+1.893; +6,3%) |
| Fact trong DuckDB | 38.425 | 18.540 (−19.885; −51,8%) |
| Gating parser | 141/141 `AUTO_INDEX` | 141/141 `AUTO_INDEX` |
| Collection Qdrant | `vnfin_v1_bge_m3_v1` | `vnfin_v2_1_bge_m3_v1` |

Con trỏ đang dùng trỏ đồng thời tới JSON v2.1, DuckDB v2.1, collection mới và manifest mới. Việc đổi con trỏ được thực hiện sau khi đối soát và benchmark; không nạp đè hay xóa collection cũ. Checkpoint dùng evidence v1 bị `check_snapshot_on_resume()` từ chối, còn ba fixture v2.1 được chấp nhận.

## 1. Sửa phân loại phần thuyết minh

Nguyên nhân: sau khi vào mục thuyết minh, parser từng gặp tiêu đề như “Bảng cân đối kế toán” hoặc “Báo cáo kết quả hoạt động kinh doanh” **bên trong thuyết minh** và chuyển nhầm section về báo cáo chính. Bảng note vì thế sinh fact mang `report_type` sai; các phép tính có thể gặp nhiều giá trị cùng mã và cùng năm. Đặc biệt, mã biểu mẫu `B09` của thuyết minh từng bị hiểu như tín hiệu cho phép chuyển mục.

Quy tắc mới giữ trạng thái `NOTES` sau tiêu đề thuyết minh. Chỉ khi có mẫu báo cáo chính tương ứng trong cùng block mới chuyển mục: doanh nghiệp dùng `B01/B02/B03`, ngân hàng dùng `B02/B03/B04-TCTD`; `B09` không cho phép chuyển. Hai ca MCH 2024 và MVN 2023 được kiểm riêng sau khi phát hiện lỗi `B09`. Bản cuối được parse lại đủ 141 tài liệu với `parser_version=v2.1` và đường dẫn raw gốc.

So theo **28.025 nội dung thân chunk khớp duy nhất**, thay vì dựa vào `chunk_id` có thể dịch khi cắt lại: 1.615 chunk trên 88 tài liệu chuyển từ báo cáo chính về `NOTES` (1.125 từ bảng cân đối, 121 từ kết quả kinh doanh, 369 từ lưu chuyển tiền tệ). Trong số chunk khớp thân nội dung, 672 chunk đổi `embed_text`. Cả 141 tài liệu vẫn có đủ ba báo cáo chính. Trường hợp NVB 2022 có biểu mẫu ngân hàng thật xuất hiện sau một đoạn `NOTES` đầu tài liệu; parser vẫn giữ đúng các biểu mẫu đó.

Số chunk tăng vì đổi section làm đổi ranh giới gộp văn bản và tiền tố ngữ cảnh. Trước đây parser còn **hợp nhất bảng liên trang** khi các bảng note bị gắn nhầm là báo cáo chính; sau sửa chúng không bị gộp theo quy tắc dành riêng cho báo cáo chính. Chênh lệch quan sát được là +1.190 chunk văn bản và +703 chunk bảng. Đây là tác động của cắt/gộp lại, không chỉ là đổi nhãn.

## 2. Kiểm tra 19.885 fact bị loại

Không có fact mới và không có fact giữ lại nhưng đổi `report_type`: các dòng bị nhận nhầm được **loại khỏi bảng fact**, không được chuyển thành fact loại `NOTES`. **Không fact nào bị loại trước trang bắt đầu `NOTES` của tài liệu tương ứng.** Trong 141 tài liệu, 56 không mất fact; bốn tài liệu mất trên 80% fact trích xuất trước đây là HUT 2024 (655/804), HUT 2025 (765/915), LGC 2023 (503/617) và LGC 2025 (462/571). Tỷ lệ lớn đến từ các bảng thuyết minh từng sinh nhiều fact giả, không phải việc xóa bảng báo cáo chính.

Đã đọc mẫu fact bị loại của HUT 2025, GVR 2023 và ngân hàng BAB 2025. Các ví dụ như tiền mặt/tiền gửi ở trang 32 HUT, trang 41 GVR và trang 24 BAB đều nằm trong mục thuyết minh. Gating vẫn `AUTO_INDEX` cho 141/141 tài liệu. Không phép kiểm đẳng thức **chung giữa hai snapshot** nào đổi kết quả. Riêng GVR 2023 giảm từ 32/32 xuống 30/30 phép kiểm vì hai phép kiểm trên dòng note nhận nhầm bị loại; ở v1 chúng được đánh dấu `passed` bằng ghi chú xác nhận OCR dù hai vế số học không bằng nhau.

Đã so từng dòng của **12 chỉ tiêu chuẩn × 35 mã, trên mọi scope hiện có**, gồm giá trị, trang, `citation_tag`, giá trị raw và cờ nghi vấn. Chỉ có tám nhóm chuỗi khác: năm nhóm GVR (mã 10, 20, 50, 60, 61) và ba nhóm MVN hợp nhất (270 tổng tài sản, 400 vốn chủ sở hữu, 30 dòng tiền đầu tư). Cả tám chuyển `ambiguous → ok` vì dòng trùng năm 2023 trong thuyết minh bị loại; **giá trị và citation của báo cáo chính không đổi**. Các dòng MVN trang 69/76 thuộc bảng điều chỉnh hồi tố ở thuyết minh mục “Số liệu so sánh”. HUT và GMD không đổi dòng nào trong 12 chỉ tiêu. Người dùng đã xem xét và chấp nhận ngoại lệ MVN trước khi kích hoạt v2.1. OIL mã 34 năm 2025 vẫn mơ hồ.

## 3. Cache embedding và chỉ mục mới

Cache cũ đối chiếu cả danh sách hash của một tài liệu; chỉ một chunk đổi cũng khiến cả tài liệu bị embed lại. Phép đo 200 chunk trên CPU cho tốc độ khoảng 1,87 chunk/giây và dự báo **4,47 giờ** nếu dùng pipeline cũ cho toàn corpus.

Cache mới tái dùng vector theo `content_hash` **ở cấp chunk, trên toàn bộ 141 Parquet cũ**. Trong 32.175 chunk v2.1 có khoảng 4.499 hash mới (4.632 lần xuất hiện); hash giữ nguyên dùng lại vector, rồi metadata/ID được ghi vào Parquet v2.1 riêng. Kiểm trên dữ liệu thật cho thấy các vector chung giống từng bit: ABB 326/326, BAB 195/195, BWE 194/194. Collection `vnfin_v2_1_bge_m3_v1` được dựng cạnh v1, không dùng `--rebuild` trên collection cũ; toàn bộ quá trình mất **2.935 giây (~49 phút)**.

Đối soát độc lập sau dựng báo `PASSED`: JSON có 32.175 chunk thuộc 141 tài liệu, Parquet có 32.175 hàng thuộc 141 tài liệu, Qdrant có 32.175 điểm và tập `chunk_id` khớp chính xác. Manifest ghi `parser_version=v2.1`. Bộ kiểm tra facts đạt Type A **58/58** cả giá trị/trang và Type C **14/14** chuỗi, **56/56** điểm năm.

## 4. Retrieval, fixture và báo cáo mẫu

Nhãn golden **DEV** được ánh xạ theo nội dung và trang: 92 câu, chỉ ba `gold_chunk_ids` đổi và đều thuộc một câu VEA; không có ID chưa ánh xạ. Tập **TEST vẫn niêm phong**, chưa chạy lại. So cùng cấu hình `hybrid_filtered`:

| DEV | v1 Hit@5 | v2.1 Hit@5 | v1 MRR | v2.1 MRR |
|---|---:|---:|---:|---:|
| Loại A: fact (42 câu) | 35/42 | 35/42 | 0,5015 | 0,5140 |
| Loại B: văn bản note (36 câu) | 32/36 | 33/36 | 0,8151 | 0,8163 |

Research state và báo cáo **TemplateWriter** HUT, GMD, FPT đã được sinh lại trên snapshot mới; S3, S4, S5 của cả ba mã đều qua Verifier **3/3**. Planner tất định trả `ready` cho cả ba mã, mỗi mã có S1–S5, 32 research task và 23 calculation spec. Smoke test qua đường mặc định xác nhận DuckDB v2.1 trả 18.540 fact, HUT doanh thu 2025 trả một fact, còn truy vấn “bên liên quan” HUT trả 5 chunk với hạng đầu ở trang 63. Các log đánh giá **Gemini** cũ là kết quả lịch sử trên v1; chúng chưa được đo lại trên v2.1. `run_status` của báo cáo vẫn là `incomplete` vì chưa có Verifier ngữ nghĩa mức `full` và các section định tính.

## 5. Cổng note S7 và nhãn của người thứ hai

Đã lấy top 5 cho bốn chủ đề S7 (bên liên quan, rủi ro tài chính, cam kết, sự kiện sau niên độ) trên HUT/GMD/FPT năm 2025: **12 truy vấn, 60 cặp truy vấn–chunk**. Trước khi nhận nhãn, cổng giữ 24/60; đó chỉ là **tỷ lệ giữ**, không phải precision. Việc sửa chỉ mục giúp truy vấn bên liên quan trả về các trang thuyết minh sâu, ví dụ HUT trang 61–66.

Người thứ hai gắn nhãn độc lập 20 cặp: **7 `direct`, 6 `context`, 7 `unrelated`**. Đối chiếu với cổng trước sửa: TP 6, FP 1, FN 1, TN 12; precision và recall **trong đúng mẫu 20 cặp thuộc top 5** đều 6/7 = **85,7%**. Hai lỗi:

1. Bỏ sót nghĩa vụ hoàn nguyên đất thuê FPT: nội dung trả lời trực tiếp nhưng tiêu đề OCR là “NỘ TIỂM TÀNG”.
2. Giữ nhầm đoạn chính sách kế toán ngoại tệ FPT: có chữ “rủi ro tỷ giá” nhưng không phải thuyết minh quản lý rủi ro tài chính.

Đã thêm cụm `nghĩa vụ hoàn nguyên` cho cam kết và loại đoạn chính sách kế toán khỏi chủ đề rủi ro tài chính nếu không có mục quản lý rủi ro. Phát lại **toàn bộ 60 cặp** làm đổi đúng ba quyết định: giữ thêm hai chunk cam kết FPT và loại một chunk chính sách FPT; cổng giữ **25/60**. Trên **chính 20 cặp dùng để tìm lỗi**, TP 7, FP 0, FN 0, TN 13. Con số 7/7 này là **test hồi quy của bản sửa**, không phải đánh giá hold-out mới.

Sau bản tóm tắt buổi sáng, người dùng cung cấp phiếu của người thứ nhất trên cùng 20 cặp. Hai người trùng **13/20 nhãn (65%)**, κ Cohen ba lớp **0,483**; với phép chia `direct`/không `direct`, trùng **15/20**, κ **0,390**. Bảy bất đồng ở cặp 02, 03, 06, 07, 12, 17, 18; các cặp 02, 03, 06, 12, 17 khác nhau ở ranh giới `direct` với `context`. Người thứ nhất yêu cầu chunk có đủ nội dung cho nhận định cụ thể, còn người thứ hai có lúc coi tiêu đề/câu dẫn là `direct`. Theo nhãn người thứ nhất, cổng sau sửa chỉ đạt TP 3, FP 4, FN 1, TN 12 trên đúng mẫu 20 cặp; cặp 03 FPT bị loại dù có câu cụ thể về phòng ngừa rủi ro tỷ giá. Đã lưu phiếu nguyên văn và nhãn tách riêng trong `data/report_output/s7_first_annotator_raw_v2_1.md` và `data/report_output/s7_first_annotator_labels_v2_1.json`; chi tiết đối chiếu ở `docs/evaluation/notes-classification-audit.md`. Bốn mươi cặp còn lại chưa được gắn nhãn, và HUT/GMD không có chunk vượt cổng cho truy vấn rủi ro tài chính trong top 5; điều đó không chứng minh báo cáo gốc thiếu thông tin. Vì vậy **chưa coi cổng S7 là đã đạt để viết W6 S7**.

## Kiểm thử và việc còn lại

Sau bản sửa cổng và test hồi quy nhãn S7, toàn bộ **153 unit test qua**. Đã kiểm đường runtime mặc định sau chuyển snapshot; fixture v1 bị chặn khi resume, fixture v2.1 được nhận. Không gửi thêm SectionView hay chạy Gemini trong đợt này.

Các bước còn lại:

1. Chốt tiêu chí `direct` theo khả năng viết một nhận định cụ thể có citation, phân xử năm bất đồng `direct`/`context`, rồi đánh giá thêm các cặp chưa gắn nhãn trước khi dùng cổng cho văn bản người đọc.
2. Viết W6 ở chế độ **trích đoạn có citation**, bắt đầu từ các section định tính có evidence trực tiếp; không suy diễn nguyên nhân hoặc kết luận `not_found` cho toàn báo cáo từ top 5.
3. Bổ sung Verifier ngữ nghĩa mức `full`, rồi mới xem xét nâng `run_status` khỏi `incomplete`.

Các bảng benchmark v1 và báo cáo cũ vẫn được giữ như hiện vật lịch sử. Thư mục làm việc không có Git repository nên không có Git diff để đính kèm; dữ liệu v1 không bị xóa.

### Nơi tra cứu sâu khi cần

- [Báo cáo kiểm tra tác động và bằng chứng chi tiết](../evaluation/notes-classification-audit.md).
- [Dữ liệu 20 nhãn và quyết định cổng](../../data/report_output/s7_second_annotator_labels_v2_1.json).
- [Cấu hình snapshot đang dùng](../../configs/active_corpus.json).
