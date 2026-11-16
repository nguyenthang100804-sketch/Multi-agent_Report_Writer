# Tổng hợp tiến độ Multi-Agent Report Writer — ngày 03/11/2026

## 1. Đọc nhanh: dự án đang ở đâu?

Dự án đã có tầng dữ liệu và hợp đồng state đủ rõ để truy ngược một câu trong báo cáo về fact hoặc note gốc. Các tool tra cứu số liệu, tìm note, resolver chỉ tiêu, phép tính, kiểm tra citation và Verifier xác định đã được xây dựng. Researcher không dùng LLM đã chạy được với dữ liệu thật. Một LangGraph bốn node đã được nối theo thứ tự Planner → Researcher → Writer → Verifier, nhưng Planner và Writer hiện là hàm truyền từ bên ngoài; test graph dùng hàm giả cho hai vai trò này. Vì vậy graph chưa tự tạo một báo cáo từ yêu cầu người dùng, chưa có vòng sửa, chưa có kiểm chứng ngữ nghĩa và chưa thể tự đánh dấu run `completed`.

Mốc kiểm tra cuối phiên: DuckDB chứa **141 tài liệu và 38.425 fact** sau khi parse lại toàn corpus. Qdrant vẫn có **30.282 chunk**; `--reconcile-only` báo ID và số lượng khớp. Bộ test hiện tại chạy **69/69 qua**. Các con số đó mô tả snapshot đang dùng, không phải cam kết chất lượng phân tích của báo cáo cuối. Nhiều dòng nguồn có thể mơ hồ, và một số phép tính được ghi `cannot_compute` có chủ ý.

Tài liệu này gom các quyết định và bằng chứng từ [hợp đồng schema/state](../contracts/report-schema-and-state.md), [audit nhất quán kỳ](../audits/period-consistency-audit.md), [audit chỉ tiêu toàn corpus](../audits/metric-coverage-corpus-audit.md), [quyết định Writer](../decisions/writer-contract-decisions.md), [đối chiếu dữ liệu](../audits/fpt-facts-reconciliation.md) và [quyết định scope](../decisions/cross-year-scope-decision.md). Những tài liệu gốc vẫn hữu ích khi cần kiểm một con số hoặc trường schema cụ thể.

## 2. Mục tiêu và đường đi của dữ liệu

Một yêu cầu báo cáo (`ReportRequest`) hiện giới hạn ở **một ticker**, khoảng năm, scope, đối tượng đọc và hướng dẫn. Hệ thống không tự đổi từ `consolidated` sang `general` hoặc `separate`. Sau bước lập dàn ý, mỗi `SectionPlan` chứa các research task. Researcher gọi `AgentTools` để lấy fact hoặc note, chuyển output thành `ResearchResult` và `EvidenceRecord`, sau đó tạo các phép tính phù hợp. Writer tương lai sẽ viết từng `SectionDraft`; Verifier đối chiếu claim và văn bản với evidence rồi renderer chèn citation. Luồng dự kiến:

```text
ReportRequest
  → ReportOutline / SectionPlan / ResearchTask
  → AgentTools: fact, time series, notes
  → ResearchResult + evidence_by_id
  → CalculationResult
  → SectionDraft + Claim
  → Verifier xác định → Verifier ngữ nghĩa (chưa có)
  → renderer citation → báo cáo đã duyệt (chưa có)
```

`ReportState` là `TypedDict` có reducer cho evidence, research result, calculation, draft và verification. Evidence và calculation được gộp theo ID; cùng ID nhưng nội dung khác sẽ báo lỗi thay vì âm thầm ghi đè. Bản nháp và verification có khóa `(section_id, revision)` để một kết quả kiểm chứng cũ không thể duyệt revision mới. `can_complete()` yêu cầu outline hiện hành đã được duyệt và từng section có verification `passed` ở mức `full`; `complete_run()` là đường chuyển trạng thái được hỗ trợ. Graph một lượt hiện chỉ tạo kết quả `deterministic` và giữ `run_status="incomplete"`.

State có thể ghi/đọc JSON bằng `state_to_json()` và `state_from_json()`. Snapshot fact là ID của dữ liệu logic trong DuckDB, không phải hash byte của file database; `check_snapshot_on_resume()` dừng khi evidence từ checkpoint thuộc snapshot khác. Cơ chế checkpoint và tự chạy lại research khi snapshot đổi **chưa** nằm trong graph. Với note, khi triển khai resume cần đưa thêm version của chỉ mục Qdrant. Điều kiện hoàn tất được kiểm lại khi đọc state, nên chỉ đặt chuỗi `run_status="completed"` không đủ để biến một báo cáo thành đã duyệt.

## 3. Verifier, claim và câu giới hạn

Một **claim** là một khẳng định cụ thể trong báo cáo. Với câu “Doanh thu 2024 đạt 150 tỷ đồng”, claim ghi chỉ tiêu, năm, số và đơn vị trong tài liệu gốc, mã của dòng nguồn (**evidence ID**), cùng cách hiển thị số đó trong câu (`display_value`, `display_unit`, `display_scale`, dấu và mức làm tròn). Claim về số được tính, như tốc độ tăng trưởng, trỏ đến kết quả phép tính và ghi giá trị hoặc hướng xu hướng mà câu khẳng định. Claim định tính trỏ đến đoạn thuyết minh (**note**) làm nguồn. Nhờ các trường này, bộ kiểm chứng (**Verifier**) biết chính xác phải đối chiếu điều gì.

Verifier hiện có một lớp **kiểm tra bằng quy tắc cố định**: nguồn có tồn tại không, citation có đúng trang không, mã cổ phiếu và phạm vi báo cáo (**scope**) có khớp không, số/đơn vị trong câu có đúng fact hoặc phép tính không. Nó cũng phát hiện nhiều dòng cùng chỉ tiêu, cảnh báo giữa các năm và câu nói sai hướng tăng/giảm rõ ràng. Ví dụ, `12.5%` được hiểu là 12,5%, không phải 125%; số `8%` trong câu định tính được chấp nhận nếu có trong note được dẫn. Ngày tháng và số thứ tự mục không bị coi là số liệu tài chính. Các kiểm tra từ ngữ chỉ bắt lỗi dễ thấy, chưa xác nhận được ý nghĩa toàn bộ câu.

Nếu số năm 2024 không khớp cột “năm trước” của báo cáo 2025, hệ thống tạo cảnh báo `period_inconsistency:2024->2025`. Câu chỉ nêu số 2024 vẫn có thể dùng, nhưng mang cảnh báo. Câu tính mức thay đổi **giữa cả 2024 và 2025** phải khai rõ giới hạn này; thiếu khai báo thì Verifier yêu cầu sửa. Writer chỉ cung cấp mã cảnh báo, vị trí đoạn và ID nguồn trong `DraftLimitation`. Verifier kiểm các liên kết đó, rồi bộ dựng văn bản (**renderer**) tự thêm câu giải thích chuẩn và citation ở cuối đoạn. Vì câu giải thích được chèn *sau* bước kiểm chứng, Verifier không tìm nó trong bản nháp của Writer.

Kết quả kiểm chứng ghi rõ mức độ trong `VerificationResult.level`. Mức `deterministic` nghĩa là các quy tắc trên đã qua; nó **chưa đủ** để đánh dấu báo cáo hoàn tất. Mức `full` dự kiến còn cần kiểm ngữ nghĩa: đối chiếu từng claim định tính với note, đồng thời tìm trong mỗi đoạn những câu khẳng định dữ kiện hoặc nguyên nhân nhưng không có claim và nguồn tương ứng. Bước tìm ngược này gọi là **Citation Recall**; nó cũng nhằm bắt các so sánh viết bằng chữ mà bộ quét chữ số không thấy. Lớp ngữ nghĩa và việc cấp mức `full` **chưa được triển khai**.

## 4. Corpus sau khi sửa parser

**Parser** là chương trình đọc báo cáo gốc và tách các dòng số liệu thành **fact**. Trước đây nó nhận cả dòng tiêu đề “Phân bổ cho:” của FPT là fact mã `61`, dù dòng không có số. Quy tắc mới bỏ một dòng khi nhãn kết thúc bằng `:` và **cả hai ô chữ gốc** (`raw_current`, `raw_prior`) đều rỗng. Không thể chỉ nhìn giá trị sau khi đổi sang số: ô bị con dấu che cũng có thể đổi thất bại thành `None`, nhưng vẫn phải được giữ để kiểm tra. Test xác nhận ô còn chữ hoặc ký hiệu không bị bỏ.

Kiểm riêng bốn báo cáo FPT cho thấy quy tắc bỏ đúng ba dòng “Phân bổ cho:” ở 2023–2025; năm 2022 không đổi. Sau đó chúng tôi chạy parser trên **141 báo cáo** vào thư mục tạm, so với dữ liệu cũ trước khi thay: thêm **0 fact**, bỏ **39 fact**, và không tài liệu nào đổi nội dung đoạn dùng để tìm kiếm. [Danh sách 39 dòng](../audits/empty-heading-facts-audit.md) chủ yếu là đề mục “Điều chỉnh cho các khoản:” trong báo cáo lưu chuyển tiền tệ; tất cả có hai ô gốc rỗng. Số fact trong DuckDB, tức cơ sở dữ liệu số liệu, khớp phép đối chiếu: **38.467 − 3 − 39 = 38.425**.

Chúng tôi kiểm riêng phần tìm kiếm vì nó lưu ở **Parquet và Qdrant**, ngoài DuckDB. Lệnh `--reconcile-only` xác nhận đủ **141 tài liệu, 30.282 đoạn** và mã đoạn khớp. So tiếp dấu vân tay nội dung (`content_hash`) cho FPT giữa JSON, Parquet và Qdrant, rồi cho cả 141 JSON cũ/mới, đều không thấy thay đổi. Do đó không cần tạo lại chỉ mục tìm kiếm. Vì snapshot DuckDB đã đổi, [state OIL mẫu](../examples/real-tool-report-state.json) được sinh lại từ tool hiện tại; test so toàn bộ fact trong mẫu với truy vấn mới. [State ABC](../examples/synthetic-report-state.json) chỉ là ví dụ tự tạo.

Lọc đề mục không tăng tỷ lệ chuỗi an toàn của 12 mã chuẩn: 39 dòng bỏ đi không có mã. FPT mã `61` vẫn thiếu số ở 2024–2025, nên chuỗi bốn năm chưa tính được. Việc sửa giúp các tìm kiếm theo **nhãn dòng** tránh gặp đề mục rỗng; nó chưa giải quyết chuyện một mã xuất hiện ở cả bảng chính và bảng bổ sung.

## 5. Khảo sát 12 chỉ tiêu trên 35 ticker

Bộ nhận diện chỉ tiêu (**resolver**) hiện hỗ trợ 12 chỉ tiêu phổ biến của doanh nghiệp phi ngân hàng: doanh thu và lợi nhuận, tài sản và nguồn vốn, cùng ba dòng tiền thuần. Chúng tôi hỏi tool về từng chỉ tiêu cho **35 mã cổ phiếu × 12 = 420 chuỗi** từ 2022–2025. “Chuỗi an toàn” nghĩa là mỗi năm có đúng một dòng số hợp lệ, cùng đơn vị; điều này chưa bảo đảm mọi công thức tính được. **YoY** là tỷ lệ thay đổi giữa 2024 và 2025, được hỏi riêng hai năm; **CAGR** là tốc độ tăng trưởng bình quân 2022–2025, cần đủ năm và giá trị đầu/cuối dương.

| Tập đo | Chuỗi an toàn | YoY 2024–2025 tính được | CAGR 2022–2025 tính được |
|---|---:|---:|---:|
| Toàn bộ 35 ticker | **289/420** | **257/420** | **217/420** |
| Bỏ sáu ngân hàng, còn 29 ticker | **289/348** | **257/348** | **217/348** |

Sáu ngân hàng ABB, ACB, BAB, MSB, NAB, NVB đều 0/12 vì **bộ mã đang khảo sát dành cho doanh nghiệp phi ngân hàng**; không thể kết luận ngân hàng không có dữ liệu. Hàm kiểm độ phủ (`check_coverage`) đã trả cờ nhận biết mã chuẩn, nhưng bộ lập kế hoạch (**Planner**) chưa dùng nó để dừng với thông báo “chưa hỗ trợ ngân hàng”. Trong năm công ty xem kỹ, HUT và GMD đạt **12/12 chuỗi an toàn**, FPT **9/12**, GVR **7/12**, OIL **12/12** với bộ mã chuẩn. OIL vẫn có một mã dòng tiền khác bị trùng; nó phù hợp để thử cách báo giới hạn, còn HUT/GMD phù hợp lần chạy chính.

**Scope** là loại báo cáo: hợp nhất (`consolidated`), riêng lẻ (`separate`) hoặc chung (`general`). PAP chỉ có `general`; khảo sát đúng loại báo cáo này cho **9/12**, thay vì 0/12 khi hỏi nhầm `consolidated`. DHG có `consolidated` ở 2022 nhưng `general` ở 2023–2025; VCR có `separate` ở 2022 và `general` ở 2023–2025. Vì một yêu cầu hiện giữ **một scope duy nhất**, không scope nào phủ đủ bốn năm cho DHG/VCR. Khảo sát chọn scope có nhiều chuỗi an toàn nhất **chỉ để đo**, còn pipeline không tự đổi hoặc gộp scope. Muốn gộp, người duy trì corpus phải xác nhận từng ticker/năm từ báo cáo gốc và báo cáo cuối phải nói rõ năm nào dùng `general`.

Không nên đọc tỷ lệ CAGR **217/348** như điểm chất lượng chung: lợi nhuận và dòng tiền có thể âm nên CAGR thường không phù hợp. Giai đoạn đánh giá sau cần đếm riêng **mỗi chỉ tiêu với phép tính mà Planner thực sự cho phép**, kể cả chênh lệch tuyệt đối. Công thức còn có thể bị chặn bởi mẫu số, dấu hoặc cảnh báo giữa hai kỳ dù chuỗi đã được tool đánh dấu an toàn.

## 6. Quyết định Writer đã chốt, phần mã chưa viết

**Writer** là bước viết câu văn. Để giảm lỗi chép số, Writer dự kiến dùng **bí danh** như `E3` thay cho ID nguồn dài, và đặt **chỗ giữ** (placeholder) thay vì tự gõ số. `{{E3}}` lấy số từ fact E3 và giữ dấu; `{{E3|abs}}` lấy trị tuyệt đối của số âm; `{{C:revenue_yoy}}` lấy kết quả phép tính; `{{T:revenue_trend}}` chèn cụm hướng như “tăng liên tục” do code chọn. Code sẽ điền số, đơn vị và tạo claim số tương ứng. Vì chỗ giữ đã in cả đơn vị, Writer không viết thêm “đồng”. Bí danh lạ, chỗ giữ lạ hoặc phép tính không tính được phải gây lỗi rõ ràng, không được đoán thay.

Một đoạn có số 885 tỷ và 22,7 nghìn tỷ nên hiển thị **cùng thang** để người đọc so sánh; nếu làm tròn khiến số nhỏ thành `0,0`, code phải đổi thang hoặc tăng độ chính xác. Cần lưu riêng câu Writer viết (**template**) và câu đã điền số (**text**): kiểm citation tự gõ trên template, kiểm số tự do trên text. Mỗi lần sửa là một **revision** mới, để kết quả kiểm chứng cũ không duyệt nhầm câu mới. Câu như “gấp đôi” không có chữ số nên bộ quét số không bắt được; prompt phải hạn chế và lớp kiểm ngữ nghĩa sẽ rà lại. Câu giải thích giới hạn được code chèn cuối đoạn, không cần placeholder riêng.

Đó mới là **hợp đồng thiết kế**: parser/renderer placeholder, prompt Writer và test của chúng chưa được viết. Planner cũng chưa tự tạo dàn ý, yêu cầu tỷ lệ từ hai nguồn, hay chọn danh sách phép tính cho Writer. Mức kiểm chứng `full` mô tả ở mục 3 cũng chưa có đường thực thi.

## 7. Test đã chứng minh gì và chưa chứng minh gì?

Chạy `\.venv\Scripts\python.exe -m unittest discover -s tests -q` cho kết quả gần nhất: **69 test qua**. Một nhóm test kiểm dữ liệu đầu vào sai, ID nguồn, version bản nháp và việc hai task cùng lấy một fact. Nhóm phép tính thử năm thiếu, dòng trùng, mẫu số 0, gốc âm và cảnh báo kỳ. Nhóm Verifier thử số/đơn vị trong câu, citation, hướng xu hướng, note và câu giới hạn. Test tích hợp truy vấn dữ liệu FPT, HUT, OIL, kiểm scope của PAP và so **toàn bộ fact** trong JSON OIL mẫu với database hiện tại.

Test graph xác nhận bốn bước chuyển dữ liệu đúng thứ tự, nhưng **Planner và Writer trong test là hàm giả**; chỉ Verifier xác định là mã thật. Vì vậy 69 test chưa chứng minh hệ thống tự viết được báo cáo đúng, tự sửa khi bị từ chối, khôi phục sau checkpoint hay hoàn tất với mức kiểm chứng `full`. Khảo sát 35 mã cổ phiếu chỉ đo 12 chỉ tiêu đã chọn. Các trường hợp GVR/OIL vẫn cần đọc báo cáo gốc và đánh giá thủ công trước khi đặt quy tắc chọn dòng.

## 8. Bước tiếp theo nên triển khai

1. **Parser và renderer placeholder:** chốt model lưu template/text, sinh claim từ evidence và calculation, dùng chung thang trong một block, từ chối alias/placeholder sai, chặn số/đơn vị Writer tự thêm. Test tối thiểu: hai fact khác cỡ, số làm tròn về 0, `|abs` trên fact dương, calculation thất bại, đủ bốn hướng `T:`, citation thủ công, render hai lần như nhau.
2. **Planner template một ticker:** kiểm `check_coverage()` và `has_standard_codes`, gợi ý scope có sẵn thay vì tự đổi, chọn nhóm chỉ tiêu/phép tính theo bảng, phát `RatioTask` cho biên lợi nhuận/nợ trên tài sản khi có nguồn. Với ngân hàng, dừng sớm và thông báo chưa hỗ trợ bộ mã chuẩn. Chưa gộp scope DHG/VCR nếu không có xác nhận.
3. **Writer và kiểm chứng ngữ nghĩa:** nối Writer dùng placeholder vào graph, chạy HUT hoặc GMD làm ca chính; thêm Verifier định tính và Citation Recall, chỉ cấp `full` sau hai lớp. Sau đó mới thêm vòng sửa có giới hạn số lần, checkpoint và resume.
4. **Đo Phase 5:** phân loại mẫu cờ `period_inconsistency`, xem vai trò trang 75–76 GVR và OIL mã `34`, xây ma trận chỉ tiêu × phép tính đúng menu Planner, đánh giá false positive của Citation Recall. `table_role` chỉ nên làm khi số liệu cho thấy việc phân vai bảng giải quyết đủ nhiều ca thật.

Thứ tự này giữ demo đầu tiên ở HUT/GMD, nơi bộ 12 chỉ tiêu sạch, trong khi các nhánh giới hạn FPT/OIL được kiểm riêng. Mỗi bước cần một kết quả có thể test trước khi mở rộng, và mọi báo cáo chỉ nên mang trạng thái `completed` khi verification đúng revision đạt `full`.
