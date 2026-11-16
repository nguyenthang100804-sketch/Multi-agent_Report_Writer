# Đánh giá Verifier Ngữ nghĩa (SV1) trên Tập Dev

Ngày 10/11/2026, snapshot v2.1. Tài liệu này ghi lại quá trình kiểm thử kỹ thuật và đánh giá bước đầu của `GeminiVerifierModel` (`gemini-3.8-flash`, nhiệt độ `0`, `thinking_level=LOW`, prompt phiên bản `sv1-v1`), đồng thời phân tích thẳng thắn các giới hạn phương pháp luận của đợt kiểm thử hiện tại. Không sử dụng bất kỳ mã nào thuộc tập `Test` (`GEE, LGC, MCH, NAB, NVB, OIL, PAP, PVI, SJG, VCR`) trong suốt quá trình thiết kế, tinh chỉnh và đo lường.

> **Kết luận điều hành:** Các kết quả hiện tại xác nhận Verifier ngữ nghĩa hoạt động đúng thiết kế kỹ thuật (đảm bảo `fail-closed`, bắt được lỗi cấy và một số lỗi thật của LLM Writer), nhưng **chưa đủ bằng chứng thống kê và phương pháp luận để bật chế độ chặn (`blocking`)**. Hệ thống chỉ được tích hợp ở **chế độ không chặn (`verifier_mode="shadow"` — chỉ ghi log và gắn cờ cảnh báo)** cho đến khi hoàn tất kiểm định trên báo cáo đầy đủ 7 section của các mã Dev mới theo đúng thứ tự bốc thăm và ngưỡng đăng ký trước tại [`semantic_verifier_shadow_eval_plan.json`](../../configs/semantic_verifier_shadow_eval_plan.json) (Mục 7).

### Bản kê Neo Mã băm Trước Khi Chạy Giai đoạn Shadow (Pre-API Lock Manifest — `2026-11-10T09:08:30+07:00`)
Do thư mục dự án hiện chưa khởi tạo kho lưu trữ Git (`.git`), toàn bộ mã băm SHA-256 của prompt, validator Writer, file nhãn Giai đoạn 2 và file kế hoạch Giai đoạn `shadow` được neo đồng thời tại phần mở đầu tài liệu này, tại file độc lập [`configs/semantic_verifier_lock_manifest_20261110.txt`](../../configs/semantic_verifier_lock_manifest_20261110.txt) và gửi trực tiếp vào nhật ký hội thoại của người dùng trước khi gọi API ở giai đoạn `shadow`:

```text
a3f2ff6f947ea3667ca8d67f85fc024a4057b26a74a6f6ddca280100e3ee4243  src/agents/prompts/verifier_system.md (sv1-v1, mtime 2026-11-09T15:43:47.657776)
7189e7322f31f1c7224c48a5870e875b55b3e98e4b9c04fa2836d501c7f39197  src/agents/citation_recall.py (mtime 2026-11-10T08:51:46.565435)
111d37aa2fa2ecd98701719e90e1af200b9a15f9f3d9dcf3dacefdcc89de70bb  src/agents/llm_writer.py (w4-v5, mtime 2026-11-09T14:47:40.738186)
22bb021467aa4d7ac75025509bd708bde676e1084e20f875f28d672326096360  data/report_output/v2_1_fixtures/semantic_verifier_blind_labels_locked.json (payload_sha256=0cbb909e86bb6def2f3f65a8b7b45da155e0c6caa159e4bac6ed77c79c45c46b, mtime 2026-11-09T16:27:31.942028)
be5096c6d8cb4b879bd1ed03c4ceba8279ad32312ac0b6065f1eb9d898c12546  data/report_output/v2_1_fixtures/semantic_verifier_pre_integration_results.json (mtime 2026-11-09T16:30:12.091890)
b8264cb1b59488f37d36d7a4e9d1e079d205eefc7ba8cb472588be31bed62bf7  configs/semantic_verifier_shadow_eval_plan.json (sv1-shadow-eval-plan-v3)
```

---

## 1. Bối cảnh và Phạm vi Kiểm tra của Verifier Ngữ nghĩa

Trong kiến trúc hai tầng của hệ thống kiểm chứng ([`semantic-verifier-design.md`](../architecture/semantic-verifier-design.md) và [`verification.py`](../../src/agents/verification.py)):
1. **Tầng 1 — Verifier tất định (`verify_section_deterministically`):** Kiểm tra bằng code 100% đối với chữ số tự gõ (`literal_digit`), định danh nội bộ, đơn vị tiền tệ trộn lẫn trong cùng câu, dấu của từ chỉ hướng đơn giản và tính đầy đủ của các câu khai báo giới hạn dữ liệu (`limitations`).
2. **Tầng 2 — Verifier ngữ nghĩa bằng LLM (`verify_section_full`):** Chỉ chạy sau khi Tầng 1 đã đạt `status == "passed"`, tập trung bắt **5 nhóm lỗi ngữ nghĩa** mà quy tắc tất định không thể phát hiện hết:
   - `metric_label_mismatch`: Tráo tên chỉ tiêu bằng chữ so với con số của placeholder (ví dụ: viết *"Lợi nhuận sau thuế của cổ đông công ty mẹ"* nhưng gắn mức tăng của *"Lợi nhuận sau thuế thu nhập doanh nghiệp"* hợp nhất).
   - `year_or_period_mismatch`: Tráo năm hoặc kỳ kế toán giữa các mệnh đề trong câu ghép (ví dụ: gắn số dư năm 2023 với nhãn thời gian `năm 2022`).
   - `polarity_or_value_judgment`: Nhận định ngược chiều số liệu, lặp dấu âm (`"giảm -325,4 tỷ đồng"`), hoặc đưa ra nhận định vượt quá các năm được trích dẫn trong `cited_facts`.
   - `unclaimed_cause`: Tự suy diễn nguyên nhân kinh doanh/tài chính khi không có đoạn trích thuyết minh hỗ trợ trong section.
   - `note_extrapolation`: Khái quát hóa hoặc bóp méo ý nghĩa của đoạn trích thuyết minh `{{N:...}}`.

Về mặt an toàn vận hành:
- **Nguyên tắc `Fail-Closed`:** Nếu lệnh gọi LLM gặp lỗi mạng, hết hạn mức, lỗi xác thực API hoặc trả về JSON sai cấu trúc sau 2 lần thử, hệ thống giữ nguyên kết quả Tầng 1 với `level = "deterministic"` (báo cáo giữ trạng thái `incomplete`) và tuyệt đối không nâng lên `level = "full"`.
- **Hỗ trợ chế độ Không chặn (`verifier_mode="shadow"`):** Trong `verify_section_full(..., mode="shadow")` và `build_report_graph(..., verifier_mode="shadow")`, Verifier ngữ nghĩa vẫn thực thi đầy đủ và ghi toàn bộ phát hiện lỗi, JSON thô, thời gian trễ và lượng token vào `verifier_run_logs`, nhưng hạ mức độ các phát hiện ngữ nghĩa xuống `warning` và giữ nguyên trạng thái `deterministic` để không chặn quá trình xuất bản nháp.

---

## 2. Giai đoạn 1: Smoke Test Kỹ thuật (`FPT`, `HUT`, `GMD`)

Lượt kiểm tra đầu tiên ([`smoke_test_semantic_verifier.py`](../../scripts/evaluation/smoke_test_semantic_verifier.py), lưu tại [`semantic_verifier_smoke_results.json`](../../data/report_output/v2_1_fixtures/semantic_verifier_smoke_results.json)) được thực hiện trên 3 mã `FPT`, `HUT`, `GMD` nhằm kiểm tra tính thông suốt kỹ thuật của pipeline:
- **Bộ mẫu tổng hợp cơ bản (78 câu):** Gồm `28` câu đúng (18 câu mẫu trung tính + 10 câu diễn đạt lại) và `50` câu sai có chủ đích (10 câu mỗi loại trên 5 nhóm lỗi ngữ nghĩa). Cả 78 câu đều vượt qua `verify_section_deterministically()`. Kết quả đạt `50/50` trên mẫu lỗi tổng hợp và `0/28` bắt oan trên mẫu đúng tổng hợp.
- **Bộ 30 câu thật từ `full_samples` (`FPT_draft.md`, `HUT_draft.md`, `GMD_draft.md`):** Trong lần chạy đầu tiên, cụm regex `ambiguous_relation: tương ứng` khiến model bắt nhầm 2 câu đúng của `GMD` (`S3` và `S4`). Sau khi chỉnh prompt [`verifier_system.md`](../../src/agents/prompts/verifier_system.md) lúc `2026-11-09T15:43:47` để xử lý từ `"tương ứng"` và chạy lại trên chính bộ này, kết quả đạt `30/30`.
- **Kiểm tra ổn định & an toàn cơ bản:** Chạy lặp lại 3 lần trên 12 mẫu (`12/12` nhất quán), thử 3 câu tiêm lệnh prompt injection (`3/3` bị chặn), và thử API key sai trên 3 section (`3/3` giữ `level = "deterministic"` và `semantic_status = "model_error"`).
- **Chi phí:** `60` lần gọi API, tiêu thụ `206.906` tokens (`193.758` đầu vào, `13.148` đầu ra).

**Hạn chế của Giai đoạn 1:** Mẫu lỗi tổng hợp quá đơn giản (câu đơn 1 mệnh đề); bộ 30 câu thật của `FPT, HUT, GMD` bị mất tính held-out do vừa dùng để chỉnh prompt vừa dùng để đo; và các bản nháp `full_samples` dùng `TemplateWriter` cho `S3–S5` nên không chứa lỗi thật của LLM Writer ở phần định lượng.

---

## 3. Giai đoạn 2: Kiểm thử trên 6 Công ty Khác (`BSR`, `BWE`, `DCM`, `GAS`, `GEX`, `QNS`)

Lượt đánh giá thứ hai ([`evaluate_semantic_verifier_held_out.py`](../../scripts/evaluation/evaluate_semantic_verifier_held_out.py), kết quả tại [`semantic_verifier_pre_integration_results.json`](../../data/report_output/v2_1_fixtures/semantic_verifier_pre_integration_results.json)) giữ nguyên file prompt `sv1-v1` từ sau Giai đoạn 1 (SHA-256: `a3f2ff6f947ea3667ca8d67f85fc024a4057b26a74a6f6ddca280100e3ee4243`) và chuyển sang 6 công ty thuộc tập Dev chưa từng dùng khi sửa prompt: `BSR`, `BWE`, `DCM`, `GAS`, `GEX`, `QNS`.

### 3.1. Quy trình chọn mẫu thực tế và Kiểm toán số lượng block theo nguồn
Để minh bạch về phương pháp luận, quy trình tạo bộ 70 block ở Giai đoạn 2 diễn ra như sau:
1. **Nguồn dữ liệu gốc:** 6 công ty `BSR, BWE, DCM, GAS, GEX, QNS` chưa có bản nháp LLM cho toàn bộ 7 section (`S1–S7`), mà chỉ có các bản nháp định lượng `S3, S4, S5` (tổng cộng `72` block trên 18 section) được lưu trong các log đánh giá Writer trước đó: [`writer_w4_v5_eight_dev_s34_eval.json`](../../data/report_output/writer_w4_v5_eight_dev_s34_eval.json) (`S3, S4`), [`writer_w4_v4_eight_dev_s5_eval.json`](../../data/report_output/writer_w4_v4_eight_dev_s5_eval.json) (`S5`), và [`writer_w4_v3_six_dev_s345_eval.json`](../../data/report_output/writer_w4_v3_six_dev_s345_eval.json) (`S3, S4, S5`).
2. **Cơ cấu chính xác của 40 block trong [`semantic_verifier_blind_labels_locked.json`](../../data/report_output/v2_1_fixtures/semantic_verifier_blind_labels_locked.json):**
   - Người đánh giá đã đọc qua các file log `w4-v5`, `w4-v4`, `w4-v3` của 6 công ty này để trích chọn `40` block (thay vì chạy toàn bộ `72` block của mỗi phiên bản), cụ thể gồm:
     - **`26` block từ `w4-v5` và `w4-v4`:** gồm `16` block từ `w4-v5` (`S3, S4`) và `10` block từ `w4-v4` (`S5`); cả `26/26` block này đều là câu đúng (`human_blind_label = "passed"`).
     - **`14` block từ `w4-v3`:** gồm `10` block được gán nhãn đúng (`human_blind_label = "passed"`, trong đó có ca `BLIND_QNS_04`) và **`4` block lỗi thật của LLM Writer** (`human_blind_label = "failed"`: `BLIND_BWE_ERR01`, `BLIND_BWE_ERR02`, `BLIND_DCM_ERR03`, `BLIND_DCM_ERR04` — những câu đã vượt qua `verify_section_deterministically()` ở thời điểm chạy `w4-v3`).
   - **Việc người thiết kế Verifier tự chọn 40 block sau khi đã đọc log khiến tập này không còn là một mẫu ngẫu nhiên hoặc tập held-out hoàn toàn độc lập.**
3. **Cách tạo 30 block cấy lỗi (`IMP_*`):**
   - Lấy `24` block định lượng (`S3–S5`) từ `BSR..QNS` và `6` block định tính (`S2, S6, S7`) từ `FPT, HUT`, sau đó chính người thiết kế Verifier tự sửa một chi tiết ở mệnh đề thứ hai (tráo tên chỉ tiêu, tráo năm, đảo chiều động từ, thêm mệnh đề nguyên nhân có từ khóa `do`/`nhờ`, hoặc phóng đại thuyết minh) và lọc qua `verify_section_deterministically()` trước khi chấm bằng Verifier.

### 3.2. Kết quả định lượng kèm Khoảng tin cậy 95% (Clopper-Pearson & Wilson)

| Chỉ số đo lường | Kết quả ($k / n$) | Điểm ước lượng | 95% CI Clopper-Pearson (Exact) | 95% CI Wilson Score | Diễn giải thống kê nghiêm ngặt |
|---|---:|---:|---:|---:|---|
| **Recall trên lỗi thật của LLM Writer (`w4-v3`)** | **4 / 4** | **100,00%** | **[39,8%, 100,0%]** | **[51,0%, 100,0%]** | Cỡ mẫu quá nhỏ ($n=4$); giới hạn dưới chỉ đạt `39,8%`, **không thể** dùng để kết luận tỷ lệ bỏ sót lỗi thật (FN) thấp. |
| **Recall trên lỗi cấy do người thiết kế tạo (`IMP_*`)** | **30 / 30** | **100,00%** | **[88,4%, 100,0%]** | **[88,6%, 100,0%]** | Chỉ phản ánh khả năng bắt các lỗi do chính người viết Verifier thiết kế và đã lọc qua tầng tất định. |
| **Tỷ lệ bắt oan (FPR) chính thức theo nhãn khóa trước khi chạy (`BLIND_*`)** | **1 / 36** | **2,78%** | **[0,1%, 14,5%]** | **[0,5%, 14,2%]** | **Kết quả chính thức của Giai đoạn 2.** Khoảng tin cậy 95% trải rộng tới `14,5%` (vượt ngưỡng `10%`), chưa đủ cỡ mẫu để chứng minh tỷ lệ bắt oan thật $\le 10\%$. |
| *Phân tích độ nhạy hậu nghiệm (nếu áp dụng tiêu chuẩn chỉ xét các năm được trích dẫn cho `BLIND_QNS_04`)* | *0 / 35* | *0,00%* | *[0,0%, 10,0%]* | *[0,0%, 9,9%]* | *Chỉ mang tính tham khảo hậu nghiệm (post-hoc sensitivity) vì tiêu chuẩn cho người gán nhãn được chốt sau khi đã thấy kết quả `BLIND_QNS_04`; biên trên CI vẫn chạm `10,0%`.* |

### 3.3. Bốn lỗi thật của LLM Writer trong tập `w4-v3` mà Verifier bắt được
1. **`BLIND_DCM_ERR03` (`DCM S3`, lượt `w4-v3`):**
   - *Văn bản:* *"Lợi nhuận sau thuế của cổ đông công ty mẹ trong giai đoạn 2024–2025 tăng 533,8 tỷ đồng lên mức 1.959,8 tỷ đồng vào năm 2025."*
   - *Bản chất lỗi:* Chủ ngữ là *"Lợi nhuận sau thuế của cổ đông công ty mẹ"* (mã `61`), nhưng mức tăng `533,8 tỷ đồng` lại lấy từ phép tính `{{C:net_income:difference:2025}}` của chỉ tiêu *"Lợi nhuận sau thuế thu nhập doanh nghiệp"* hợp nhất (mã `60`). Tầng tất định cho qua vì cả hai placeholder đều hợp lệ trong `S3`; Verifier ngữ nghĩa bắt đúng `metric_label_mismatch`.
2. **`BLIND_BWE_ERR01` (`BWE S5`, lượt `w4-v3`):** *"Lưu chuyển tiền thuần từ hoạt động kinh doanh trong năm 2025 đạt 745,0 tỷ đồng, giảm -325,4 tỷ đồng so với năm trước."* (lỗi phủ định kép `"giảm -325,4 tỷ đồng"`).
3. **`BLIND_BWE_ERR02` (`BWE S5`, lượt `w4-v3`):** *"Lưu chuyển tiền thuần từ hoạt động đầu tư trong năm 2025 ghi nhận mức âm -1,8 nghìn tỷ đồng."* (lỗi lặp dấu âm `"mức âm -1,8 nghìn tỷ đồng"`).
4. **`BLIND_DCM_ERR04` (`DCM S5`, lượt `w4-v3`):** *"Lưu chuyển tiền thuần từ hoạt động kinh doanh giảm -853,4 tỷ đồng trong giai đoạn 2024–2025."* (lỗi phủ định kép `"giảm -853,4 tỷ đồng"`).

### 3.4. Nhật ký Kiểm toán Mã băm (SHA-256 Audit Log) và Giới hạn của Bằng chứng `mtime` ở Giai đoạn 2
1. **Đính chính lỗi tự gõ mã băm ở bản nháp tài liệu đầu tiên:**
   - Trong bản nháp đầu tiên của tài liệu Markdown này, người viết đã không đọc lại file [`semantic_verifier_blind_labels_locked.json`](../../data/report_output/v2_1_fixtures/semantic_verifier_blind_labels_locked.json) mà tự gõ hai chuỗi hex giả định (`b83a47329d53c529a1b66c339c1cf5b7d26c62448697b5524903ee81a0aa1a1b` — dài 65 ký tự hex — và `872f0fd24034252503e6d6998a1123a6f20b70341a0d6a496f3bf374f1fb5eb5`) cùng con số phân rã sai (`34 + 6` thay vì `26 + 14`).
   - Trên đĩa, mã SHA-256 thực tế của [`verifier_system.md`](../../src/agents/prompts/verifier_system.md) (`mtime: 2026-11-09T15:43:47.657776`) là `a3f2ff6f947ea3667ca8d67f85fc024a4057b26a74a6f6ddca280100e3ee4243`, và mã SHA-256 thực tế của [`semantic_verifier_blind_labels_locked.json`](../../data/report_output/v2_1_fixtures/semantic_verifier_blind_labels_locked.json) (`mtime: 2026-11-09T16:27:31.942028`) là `0cbb909e86bb6def2f3f65a8b7b45da155e0c6caa159e4bac6ed77c79c45c46b` (payload) / `22bb021467aa4d7ac75025509bd708bde676e1084e20f875f28d672326096360` (toàn file).
2. **Giới hạn phương pháp luận của `mtime` và hash tự thân ở Giai đoạn 2:**
   - Ở Giai đoạn 2 (chạy ngày 09/11/2026), hàm `verify_and_lock_datasets()` ghi file nhãn kèm `locked_labels_sha256` rồi chạy tiếp `run_live_evaluation()` trong cùng một lần thực thi script, và không có một neo độc lập bên ngoài (như Git commit hoặc gửi mã băm cho bên thứ ba) trước khi gọi API.
   - Về mặt mật mã học, một file tự chứa hash của chính nó kèm `mtime` trên hệ thống tệp cục bộ **không đủ để chứng minh độc lập tính mù tuyệt đối** (vì bất kỳ lần chạy lại nào ghi đè cả nhãn lẫn hash trước khi chạy API đều tạo ra file tự nhất quán). Đây là một lý do nữa khiến kết quả Giai đoạn 2 chỉ được xem là bước kiểm tra thăm dò và toàn bộ các file cho giai đoạn `shadow` tiếp theo phải được neo mã băm bên ngoài (ở đầu tài liệu này, trong [`configs/semantic_verifier_lock_manifest_20261110.txt`](../../configs/semantic_verifier_lock_manifest_20261110.txt) và trong nhật ký hội thoại của người dùng) trước khi gọi API.

---

## 4. Phân tích Ca `BLIND_QNS_04` và Đối chiếu Chính xác Thời điểm Thực thi giữa Prompt, Validator và Hướng dẫn Gán nhãn

### 4.1. Bản chất của ca `BLIND_QNS_04` dưới góc độ mốc thời gian thực tế
Ở block `S4:b4` của `QNS` (lượt chạy `w4-v3`), LLM Writer viết:
> `Tiền và các khoản tương đương tiền trong {{Y:E32}} đạt {{E32}} sau khi đạt đỉnh {{E31}} vào {{Y:E31}}.`  
> *(Văn bản hiển thị: "Tiền và các khoản tương đương tiền trong năm 2025 đạt 272,2 tỷ đồng sau khi đạt đỉnh 539,2 tỷ đồng vào năm 2024.")*

Để tránh mọi mâu thuẫn về mốc thời gian, cần tách bạch rõ trạng thái của **3 thành phần** vào thời điểm chạy Giai đoạn 2 (`09/11/2026`) và những gì thay đổi vào ngày `10/11/2026`:

1. **Trạng thái của Prompt [`verifier_system.md`](../../src/agents/prompts/verifier_system.md) (`sv1-v1`, khóa lúc `2026-11-09T15:43:47`, không sửa ngày 10/11):**
   - Trong `verifier_system.md` (`sv1-v1`), **không có bất kỳ câu chữ tường minh nào liệt kê từ `"đạt đỉnh"`, `"cao nhất"`, `"thấp nhất"` hay `"tăng liên tục"`**.
   - Prompt `sv1-v1` chỉ chứa quy tắc tổng quát tại dòng 3 (*"nhiệm vụ của bạn là đối chiếu từng `DraftBlock` với `claims`, `cited_facts` và `cited_notes` được cung cấp"*) và dòng 12–13:
     > *- Cách diễn đạt bản chất phép tính (`yoy`, `cagr`, `difference`, `ratio`, `trend`) có trung thực không? Nếu gọi tỷ lệ là mức tăng trưởng hoặc diễn giải sai công thức, báo `category="calculation_semantics_mismatch"`, `error_type="calculation_error"`, `action="rewrite"`.*  
     > *- Chiều biến động bằng chữ ("tăng", "giảm", "mở rộng", "thu hẹp", "suy giảm"...) phải khớp với dấu của `rendered_fragment` và chiều thay đổi giữa các năm trong `cited_facts`; đồng thời chặn nhận định chủ quan hoặc ngược dấu kinh tế (như gọi mức lỗ/dòng tiền âm nặng hơn là “cải thiện tích cực”, tự nhận “tốt nhất ngành”): báo `category="polarity_or_value_judgment"`, `error_type="unsupported_claim"`, `action="rewrite"`.*
   - Khi chấm `BLIND_QNS_04` vào ngày 09/11, model `gemini-3.8-flash` tự áp dụng quy tắc tổng quát trên (vì `cited_facts` chỉ có năm 2024 và 2025 nên không đủ căn cứ cho chữ `"đạt đỉnh"`) và trả về `failed` (`polarity_or_value_judgment`). Như vậy, đối với bản thân model Verifier, hành vi này xuất phát từ quy tắc tổng quát đã có từ `09/11 15:43`.
2. **Trạng thái của Hướng dẫn Gán nhãn cho Người chấm (`09/11` so với `10/11`):**
   - Vào ngày `09/11`, 3 câu hỏi gán nhãn thủ công chưa quy định rằng người chấm chỉ được xét các năm được gắn placeholder trong câu văn. Vì nhìn bảng số liệu 4 năm (`2022–2025`) thấy năm 2024 đúng là số lớn nhất nên người chấm gán nhãn `passed`.
   - Vào ngày `10/11` (sau khi thấy sự lệch chuẩn giữa người chấm và Verifier ở ca `BLIND_QNS_04`), quy tắc gán nhãn cho người chấm mới được chốt lại: người chấm chỉ đánh `passed` cho từ cực trị/xu hướng đa kỳ nếu chính câu văn đó trích dẫn đủ chuỗi thời gian hoặc có claim `{{T:...}}`. Vì quy tắc gán nhãn này được chốt ngày `10/11`, `BLIND_QNS_04` **vẫn phải giữ nguyên là `1/36` trong kết quả chính thức của Giai đoạn 2**, và tiêu chuẩn mới chỉ áp dụng từ giai đoạn `shadow` trở đi.
3. **Trạng thái của Validator Writer ([`src/agents/citation_recall.py`](../../src/agents/citation_recall.py)) qua từng phiên bản:**
   - **Thời điểm sinh bản nháp `w4-v3`:** `citation_recall.py` chưa có cả `unsupported_extremum` lẫn `unsupported_trend` (nên câu `"đạt đỉnh"` ở `QNS S4 w4-v3` mới lọt qua).
   - **Thời điểm sinh bản nháp `w4-v4` và `w4-v5` (ngày 09/11):** `citation_recall.py` đã có `unsupported_extremum` (`đỉnh|cao nhất|thấp nhất|kỷ lục|lớn nhất`) và `unsupported_sequence` (`tiếp tục|chuyển sang|đảo chiều|quay lại`), nhưng **chưa có** `unsupported_trend` và chưa có `"đáy"`, `"nhỏ nhất"`.
   - **Cập nhật ngày `10/11/2026` (`mtime: 2026-11-10T08:51:46`, SHA-256: `7189e732...`):** `citation_recall.py` mới được bổ sung thêm `"đáy"`, `"nhỏ nhất"` vào `unsupported_extremum` và thêm mới regex `unsupported_trend` (`tăng liên tục|giảm liên tục|tăng đều|giảm dần|đi ngang|diễn biến không đều`). **Toàn bộ các bản nháp `w4-v3`, `w4-v4`, `w4-v5` đã dùng trong Giai đoạn 2 đều được sinh dưới validator cũ trước ngày 10/11.**

### 4.2. Bảng Đối chiếu Thực tế Giữa Validator Writer, Prompt Verifier (`sv1-v1`) và Tiêu chuẩn Gán nhãn

| Nhóm cụm từ | Trạng thái trong Validator Writer (`citation_recall.py`) khi sinh `w4-v3 / v4 / v5` | Trạng thái trong Validator Writer (`citation_recall.py`, SHA-256 `7189e732...`) từ `10/11/2026` | Nội dung thực tế trong Prompt Verifier (`verifier_system.md` `sv1-v1`, SHA-256 `a3f2ff6f...` từ `09/11 15:43`) | Tiêu chuẩn cho Người gán nhãn ở Giai đoạn `Shadow` (chốt `10/11/2026`) |
|---|---|---|---|---|
| **1. Cụm từ xu hướng đa kỳ** (`"tăng liên tục"`, `"giảm liên tục"`, `"tăng đều"`, `"giảm dần"`, `"đi ngang"`, `"diễn biến không đều"`) | **Chưa có regex chặn riêng** nếu LLM tự gõ ngoài `{{T:...}}`. | Đã thêm regex `unsupported_trend` chặn cứng nếu tự gõ ngoài `{{T:...}}` (token `{{T:...}}` được xóa trước khi quét nên câu dùng `{{T:...}}` hợp lệ). | Có quy tắc kiểm tra bản chất phép tính `trend` (dòng 12) và đối chiếu chiều thay đổi giữa các năm trong `cited_facts` (dòng 13); **chưa liệt kê tường minh danh sách từng cụm từ**. | Chỉ gán nhãn `passed` khi câu văn dùng `{{T:...}}` hoặc trích dẫn đầy đủ tất cả các năm trong chuỗi phân tích. |
| **2. Cụm từ cực trị toàn chuỗi** (`"đỉnh"`, `"đáy"`, `"cao nhất"`, `"thấp nhất"`, `"kỷ lục"`, `"lớn nhất"`, `"nhỏ nhất"`) | - `w4-v3`: **Chưa chặn.**<br>- `w4-v4/v5`: Chặn `đỉnh, cao nhất, thấp nhất, kỷ lục, lớn nhất` (`unsupported_extremum`). | Chặn toàn bộ `đỉnh, đáy, cao nhất, thấp nhất, kỷ lục, lớn nhất, nhỏ nhất` trong template định lượng `S3–S5`. | **Không có quy tắc riêng nhắc chữ `"đỉnh"` hay `"cao nhất"`**; model chỉ dựa vào quy tắc tổng quát (dòng 3 & dòng 13) là mọi nhận định phải được chứng minh bởi các năm có trong `cited_facts`. | Chỉ gán nhãn `passed` nếu câu văn trích dẫn đầy đủ tất cả các năm trong giai đoạn phân tích chứng minh cực trị; nếu chỉ trích dẫn 1–2 năm thì gán nhãn `failed`. |
| **3. Cụm từ chuỗi tiếp diễn** (`"tiếp tục"`, `"chuyển sang"`, `"đảo chiều"`, `"quay lại"`) | - `w4-v3`: **Chưa chặn.**<br>- `w4-v4/v5`: Đã chặn qua `unsupported_sequence`. | Giữ nguyên regex `unsupported_sequence` chặn cứng trong template định lượng `S3–S5`. | Dựa vào quy tắc tổng quát dòng 13 (đối chiếu với các năm được trích dẫn trong `cited_facts`). | Chỉ gán nhãn `passed` nếu câu văn trích dẫn đủ các kỳ liên tiếp chứng minh sự tiếp diễn/đảo chiều. |

---

## 5. Tổng hợp 5 Lý do Chưa thể Bật Chế độ Chặn (`Blocking Mode`)

1. **Con số 100% recall hiện tại không chứng minh được tỷ lệ bỏ sót lỗi thật (FN) thấp:**
   - `30/30` lỗi cấy (`IMP_*`) là do chính người viết Verifier thiết kế và đã lọc trước qua tầng tất định.
   - Với `4/4` lỗi thật từ bản nháp `w4-v3`, khoảng tin cậy 95% dưới chỉ là `39,8%` (Clopper-Pearson) hoặc `51,0%` (Wilson) — cỡ mẫu quá nhỏ để khẳng định bất kỳ điều gì về tỷ lệ bỏ sót lỗi tự nhiên của Writer.
2. **Tập đánh giá 6 công ty (`BSR..QNS`) bị chọn lọc thủ công và thiếu các phần định tính:**
   - `BSR..QNS` mới chỉ có bản nháp LLM ở `S3–S5` (`72` block), chưa có `S1, S2, S6, S7`. Việc chọn ra `40` block (`26` block từ `w4-v5`/`w4-v4` và `14` block từ `w4-v3`) sau khi đã xem các file log đánh giá Writer tạo ra thiên lệch chọn mẫu (selection bias).
3. **Nhãn mù ở Giai đoạn 2 thiếu neo mã băm bên ngoài và tiêu chuẩn từ cực trị cho người gán nhãn được chốt hậu nghiệm:**
   - Người gán nhãn và người thiết kế Verifier là cùng một bên; file khóa nhãn Giai đoạn 2 chỉ có hash tự thân kèm `mtime` cục bộ; và quy định gán nhãn cho ca `BLIND_QNS_04` được chốt sau khi đã thấy kết quả của Verifier.
4. **Khoảng tin cậy của tỷ lệ bắt oan (FPR) còn quá rộng:**
   - Với kết quả chính thức `1/36` (`2,78%`, 95% CI Clopper-Pearson `[0,1%, 14,5%]`, Wilson `[0,5%, 14,2%]`), biên trên của khoảng tin cậy 95% vượt quá ngưỡng `10%`.
5. **Thiếu 4 phép đối chứng quan trọng:**
   - *Chưa đếm toàn diện các ca bất đồng trên toàn bộ bản nháp:* Mới chỉ chạy trên 40 block trích chọn thay vì toàn bộ các block của các báo cáo hoàn chỉnh.
   - *Chưa đo độ ổn định lặp lại (repeatability) trên tập 70 block:* Mới chỉ chạy lặp lại 3 lần trên 12 mẫu ở Giai đoạn 1.
   - *Chưa đo chi phí và độ trễ (latency) trên báo cáo đầy đủ 7 section (`S1–S7`) theo batch thực tế:* Con số `20k–25k` tokens/báo cáo mới chỉ là ngoại suy từ các batch rời rạc.
   - *Trục 3 (`unclaimed_cause`) chưa có mẫu lỗi nhân quả ngầm (implicit causality):* Toàn bộ 6 mẫu `IMP_C01..C06` đều chứa từ khóa nhân quả tường minh (`"do"`, `"nhờ"`). Chưa kiểm tra các câu ghép suy diễn nguyên nhân/động lực kinh doanh mà không dùng từ khóa nhân quả.

---

## 6. Quyết định Hiện tại: Tích hợp ở Chế độ Không Chặn (`Shadow / Log-Only Mode`)

Để thu thập bằng chứng thực tế mà không làm gián đoạn luồng chạy của dự án khi Writer đang hoàn thiện:
1. **Cơ chế kỹ thuật đã triển khai:**
   - Hàm [`verify_section_full`](../../src/agents/verification.py) và [`build_report_graph`](../../src/agents/report_graph.py) đã được bổ sung tham số `mode: Literal["blocking", "shadow"] = "blocking"` (`verifier_mode` ở cấp graph).
   - Khi chạy với `verifier_mode="shadow"`, Verifier ngữ nghĩa vẫn kiểm tra toàn bộ các section vượt qua tầng tất định và ghi đầy đủ `semantic_status`, `raw_outputs_by_attempt`, `token_usage`, `elapsed_ms` vào `verifier_run_logs`, nhưng chuyển các phát hiện ngữ nghĩa thành `severity="warning"` và giữ `level="deterministic"` để không chặn bản nháp.
2. **Dữ liệu kiểm thử đã lưu trữ:**
   - Bộ mẫu hiện tại (`78` mẫu tổng hợp + `30` câu `full_samples` + `40` block `BSR..QNS` + `30` block cấy lỗi) được lưu tại [`semantic_verifier_golden_dev.json`](../../configs/semantic_verifier_golden_dev.json) như bộ hồi quy kỹ thuật (regression suite), không dùng làm bằng chứng cuối cùng để bật `blocking`.

---

## 7. Giao thức và Ngưỡng Đăng ký Trước (Pre-registered Criteria) Để Chuyển sang `Blocking Mode`

Toàn bộ thông số lấy mẫu, thứ tự mở rộng pool, mã băm của prompt/validator và ngưỡng quyết định dưới đây đã được khóa trước vào file cấu hình [`configs/semantic_verifier_shadow_eval_plan.json`](../../configs/semantic_verifier_shadow_eval_plan.json) (SHA-256: `b8264cb1b59488f37d36d7a4e9d1e079d205eefc7ba8cb472588be31bed62bf7`) và bản kê [`configs/semantic_verifier_lock_manifest_20261110.txt`](../../configs/semantic_verifier_lock_manifest_20261110.txt) trước khi chạy bất kỳ lượt `shadow` nào.

### 7.1. Quy trình bốc thăm có hạt giống cố định và Thứ tự mở rộng Pool đã khóa
1. **Xác định danh sách 11 công ty Dev hợp lệ chưa từng sử dụng (`eligible_unused_dev_pool`):**
   - Từ `25` mã thuộc `dev_tickers` trong [`configs/eval_dataset_split.json`](../../configs/eval_dataset_split.json) (hoàn toàn tách biệt với 10 mã `test_tickers`), loại trừ:
     - `9` mã Dev đã sử dụng trong Giai đoạn 1 và Giai đoạn 2: `BSR, BWE, DCM, FPT, GAS, GEX, GMD, HUT, QNS`.
     - `4` mã ngân hàng có `0/12` chỉ tiêu doanh nghiệp phi tài chính (`ABB, ACB, BAB, MSB`) và `1` mã chuyển đổi `scope` thiếu chuỗi `consolidated` (`DHG`) theo [`metric-coverage-corpus-audit.md`](../audits/metric-coverage-corpus-audit.md).
   - Danh sách `11` công ty Dev hợp lệ còn lại: `["GVR", "HAH", "MSN", "MVN", "PET", "PVT", "SAB", "SSH", "VEA", "VIC", "VRE"]`.
2. **Khóa toàn bộ hoán vị 11 công ty bằng hạt giống cố định `seed = 20261110`:**
   - Thực thi lệnh tạo hoán vị đầy đủ:
     ```bash
     python -c "import random; pool = ['GVR', 'HAH', 'MSN', 'MVN', 'PET', 'PVT', 'SAB', 'SSH', 'VEA', 'VIC', 'VRE']; print(random.Random(20261110).sample(pool, len(pool)))"
     ```
   - Kết quả hoán vị đầy đủ 11 mã:
     `['PET', 'MSN', 'SSH', 'PVT', 'VIC', 'HAH', 'VRE', 'SAB', 'GVR', 'VEA', 'MVN']`
   - Từ hoán vị cố định này, file [`configs/semantic_verifier_shadow_eval_plan.json`](../../configs/semantic_verifier_shadow_eval_plan.json) khóa cứng:
     - **3 mã chạy chính ban đầu (`selected_shadow_tickers`):** **`["PET", "MSN", "SSH"]`**.
     - **Thứ tự mở rộng bắt buộc (`locked_expansion_order`):** **`["PVT", "VIC", "HAH", "VRE", "SAB", "GVR", "VEA", "MVN"]`**.
     - **Quy tắc dừng khi mở rộng (`expansion_stopping_rule`):** Chạy toàn bộ 7 section (`S1–S7`) trên 3 mã `PET, MSN, SSH`. Nếu tổng số block nội dung được Verifier đánh `passed` trên 3 báo cáo này nhỏ hơn `64`, bắt buộc lấy tiếp từng công ty một **theo đúng thứ tự trong `locked_expansion_order`** (`PVT` trước, nếu vẫn chưa đủ `64` block `passed` mới lấy đến `VIC`, rồi `HAH`...), mỗi công ty phải chạy trọn vẹn cả 7 section (`S1–S7`) và đưa toàn bộ các block của công ty đó vào mẫu đánh giá cho đến khi tổng số block `passed` lũy kế đạt $\ge 64$. Tuyệt đối không được nhảy cóc mã hoặc chọn lọc từng section/block.
   - **Khóa nhãn mù trước khi gọi API Verifier ở giai đoạn `Shadow`:** Khi các bản nháp của `PET, MSN, SSH` (và mã mở rộng nếu có) được sinh xong, file nhãn mù của người chấm phải được tính SHA-256 và gửi trực tiếp vào nhật ký hội thoại của người dùng (hoặc commit Git nếu đã khởi tạo repo) **trước khi** chạy `verify_section_full()`.
3. **Độc lập hóa bộ 30 mẫu thử thách Nhân quả ngầm (`implicit_causality_challenge_set`):**
   - Tối thiểu **`30` mẫu lỗi suy diễn nguyên nhân/động lực kinh doanh ngầm** (không chứa bất kỳ từ khóa nhân quả tường minh nào như `do`, `nhờ`, `bởi vì`, `vì`, `dẫn đến`, `góp phần` trong `HARD_PATTERNS` của `citation_recall.py`) **bắt buộc phải do người không thiết kế Verifier viết hoặc rà soát/phê duyệt trước khi chạy Verifier** để tránh thiên lệch tự kiểm.

### 7.2. Bảng ngưỡng định lượng đăng ký trước (Pre-registered Thresholds)

| Tiêu chí | Ngưỡng bắt buộc trước khi bật `blocking` | Cơ sở toán học & Cách xử lý nếu không đạt |
|---|---|---|
| **1. Tỷ lệ bắt oan (False Positive Rate) trên các báo cáo `shadow` mới** | Điểm ước lượng $\le \mathbf{5,0\%}$ **và** cận trên khoảng tin cậy 95% (Wilson) $\le \mathbf{10,0\%}$ (ví dụ: tối đa `1/64` hoặc `2/80` block đúng bị bắt oan). | Nếu vượt ngưỡng: phân tích nhóm lỗi gây bắt oan, chỉnh prompt (nâng phiên bản lên `sv1-v2` kèm hash mới) và bắt buộc lấy các mã tiếp theo trong `locked_expansion_order` chưa từng dùng để đo lại từ đầu. |
| **2. Tỷ lệ bỏ sót lỗi thật (False Negative Rate) trên mẫu `passed` kiểm tra mù** | Mẫu kiểm tra mù tối thiểu $\mathbf{n \ge 64}$ block `passed` (tối thiểu đại số để cận trên Wilson $\le 6,0\%$ là $n = 61$ vì $3,8415 / (60 + 3,8415) = 6,02\% > 6,0\%$) và có $\mathbf{0}$ lỗi thật bị bỏ sót ($\mathbf{0/64}$, tương ứng cận trên 95% Wilson là $\mathbf{5,66\%} \le 6,0\%$ và Clopper-Pearson là $\mathbf{5,60\%} \le 6,0\%$). | Nếu phát hiện $\ge 1$ lỗi thật bị bỏ sót: chưa bật `blocking`; bổ sung quy tắc tất định hoặc cập nhật `VerifierSectionView`/prompt (`sv1-v2`) rồi kiểm định lại trên các mã tiếp theo trong `locked_expansion_order`. |
| **3. Recall trên tập Nhân quả ngầm (Implicit Causality — không từ khóa, độc lập thiết kế)** | Cỡ mẫu tối thiểu $\mathbf{n \ge 30}$ mẫu nhân quả ngầm không từ khóa (được người không thiết kế Verifier viết hoặc phê duyệt trước); **cận dưới khoảng tin cậy 95% (Wilson) $\ge \mathbf{70,0\%}$** (với $n = 30$, đòi hỏi bắt đúng ít nhất $\mathbf{26/30 = 86,67\%}$, khi đó cận dưới 95% Wilson đạt $\mathbf{70,3\%}$). | Nếu cận dưới Wilson $< 70,0\%$: củng cố hướng dẫn Trục 3 trong `verifier_system.md` (nâng lên `sv1-v2`) để xét mọi mệnh đề giải thích/đánh giá vượt phạm vi con số. |
| **4. Độ ổn định lặp lại (3x Repeatability Flip Rate)** | Chạy 3 lần trên tối thiểu $\mathbf{70}$ block; **ngưỡng điểm ước lượng vận hành (operational point estimate)** $\le \mathbf{2,0\%}$ (tối đa `1/70` block đổi nhãn giữa `passed` và `failed`). *Lưu ý: đây là ngưỡng điểm ước lượng vận hành để kiểm tra tính tất định ở `temperature=0`, không phải ngưỡng cận trên khoảng tin cậy thống kê (do `1/70` có cận trên Wilson 95% là `7,66%`).* | Nếu có $\ge 2/70$ block đổi nhãn: kiểm tra các block dao động và làm rõ tiêu chí phân loại biên trong prompt. |
| **5. Độ trễ và chi phí trên báo cáo đầy đủ 7 section (`S1–S7`)** | Tổng thời gian kiểm chứng ngữ nghĩa trung bình $\le \mathbf{45\text{ giây/báo cáo}}$ (tuần tự) hoặc $\le \mathbf{15\text{ giây/báo cáo}}$ (song song theo section); tổng token $\le \mathbf{35.000\text{ tokens/báo cáo}}$; tỷ lệ `model_error` / repair fail $= \mathbf{0\%}$. | Tối ưu độ dài `VerifierSectionView` nếu vượt ngân sách thời gian hoặc token. |
