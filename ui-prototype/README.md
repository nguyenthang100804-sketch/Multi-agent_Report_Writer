# Giao diện báo cáo và hỏi đáp

UI dùng CopilotKit để gọi Planner Agent hiện có (`GeminiPlannerModel` và
`AgentTools`) và hiển thị dàn ý trước điểm `interrupt()` của LangGraph. Ghi chú,
quyết định, quan sát dữ liệu và cảnh báo fallback được hiển thị để người dùng
duyệt. Có thể sửa tiêu đề/mục tiêu của từng section trước khi tạo revision mới.
Sau khi duyệt, Researcher chạy các tác vụ tra cứu và UI hiển thị trạng thái,
số bằng chứng, dữ liệu thiếu và cảnh báo theo từng tác vụ. Writer dùng Gemini để
tạo bản nháp theo section, với mẫu dự phòng khi một section không đạt.

Verifier chạy kiểm tra quy tắc trước, rồi gọi Gemini để kiểm chứng ngữ nghĩa ở
chế độ chặn. Graph chỉ chuyển `completed` khi mọi section của revision đã duyệt
đạt mức `full`; nếu không, trạng thái là `incomplete`. Checkpoint nằm trong
`ui-prototype/.data/checkpoints.sqlite` và tồn tại qua lần khởi động lại server.
Phiên `completed` có liên kết mở trang `/report` riêng để đọc `final_report`,
tải bản Markdown và chat với Gemini 3.8 Flash. Trang quy trình giữ các thẻ
Researcher và Writer trong mục chi tiết có thể mở khi cần. Mỗi câu hỏi gửi toàn
bộ báo cáo cùng các tin nhắn gần nhất làm ngữ cảnh. Chat có thể trả lời cả câu
hỏi ngoài báo cáo; lịch sử chat được lưu trong trình duyệt theo mã phiên.

## Chạy trên Windows

Từ thư mục gốc project, nếu chưa có phụ thuộc Python:

```powershell
.\.venv\Scripts\python.exe -m pip install -r ui-prototype\requirements.txt --extra-index-url https://copilotkit.gateway.scarf.sh/simple/
```

Mở hai cửa sổ PowerShell:

```powershell
cd "C:\Research Dataset\Multi-agent_Report_Writer"
.\.venv\Scripts\python.exe -m uvicorn scripts.prototypes.copilotkit_backend:app --host 127.0.0.1 --port 8123
```

```powershell
cd "C:\Research Dataset\Multi-agent_Report_Writer\ui-prototype"
npm.cmd run dev
```

Mở [http://localhost:3000](http://localhost:3000). Yêu cầu có dữ liệu sẽ gọi
Gemini với ngữ cảnh Planner và kết quả tra cứu từ corpus. Một yêu cầu thiếu
phạm vi/năm có thể dừng ở `needs_clarification` trước lượt model. Chọn
**Sửa yêu cầu trong phiên mới** để điền lại các trường đã nhập.

## Kiểm tra tiến trình Planner thủ công

Khởi động lại backend để nhận mã mới, rồi mở **Phiên mới** trên UI. Chọn một
yêu cầu có dữ liệu như HUT 2022–2025, phạm vi **Hợp nhất**, và nhấn **Lập dàn ý**.
Trong lúc chờ, trạng thái phải đổi ngay thành **Đang lập dàn ý**. Danh sách
tiến trình bắt đầu bằng **Đã gửi yêu cầu lập dàn ý**, rồi nhận các sự kiện thật:
kiểm tra phạm vi, chuẩn bị cấu trúc và công cụ, bắt đầu/kết thúc lượt Gemini,
số mục cần tra cứu, từng mục đã tra cứu xong, kiểm tra dàn ý. Danh sách tự cuộn
đến mốc mới nhất. Không có phần trăm hoặc đồng hồ ước tính.

Mở tab Network của trình duyệt: request `GET /api/report/progress?threadId=...`
phải có trạng thái đang mở và loại `text/event-stream`; xem tab EventStream để
thấy các dòng `data:` đến **trong lúc** request CopilotKit vẫn đang chạy, trước
khi thẻ duyệt dàn ý xuất hiện. Lần tìm thuyết minh đầu tiên có thể dừng
ở cùng một mốc lâu hơn do phải nạp tài nguyên vào RAM; mốc đó vẫn phải phản
ánh tác vụ đang chạy. Khi dàn ý xuất hiện, thẻ tiến trình chờ biến mất. Nếu
luồng lỗi, ghi lại mốc cuối, trạng thái của request SSE, thông báo trên UI và
traceback backend để chẩn đoán.

## Kiểm tra tiến trình sau khi duyệt dàn ý thủ công

Khởi động lại backend để nhận các mốc Researcher, Writer và Verifier. Nếu phiên
hiện tại vẫn đang chờ duyệt, F5 để tải lại thẻ duyệt từ checkpoint rồi dùng
chính phiên đó; không cần gọi Planner thêm lần nữa. Nếu phiên đã duyệt hoặc lỗi,
tạo phiên mới và lập dàn ý cho HUT 2022–2025. Nhấn **Duyệt dàn ý** khi thẻ hiện ra.
Trang phải đổi trạng thái thành **Đang tạo và kiểm chứng** và hiện danh sách
tiến trình thay cho dòng **Đang tải thẻ duyệt từ CopilotKit…**. Trong DevTools →
Network, request `GET /api/report/progress?threadId=...` phải mở trong lúc
CopilotKit chạy. EventStream lần lượt có các mốc Researcher, tác vụ tra cứu,
Writer theo section, rồi Verifier theo section. Mốc cuối cho biết báo cáo hoàn
tất hay còn phần chưa đạt; nhãn **Hoàn tất** chỉ xuất hiện khi `run_status` thực
sự là `completed`. Nếu một bước mất nhiều thời gian, mốc hiện tại giữ nguyên
cho tới khi có kết quả thật. Không có phần trăm hoặc thời gian dự đoán.

Khi chạy xong, thẻ tiến trình biến mất và trang hiển thị kết quả theo trạng
thái của phiên. F5 để kiểm tra checkpoint vẫn giữ kết quả. Nếu danh sách không
cập nhật, ghi lại mốc cuối và trạng thái của hai request `GET /api/report/progress`
và `POST /api/copilotkit/agent/report_probe/run`, cùng lỗi trong terminal backend.

## Kiểm tra Researcher thủ công

Khởi động lại backend sau khi cập nhật mã và bấm **Phiên mới**. Phiên đã duyệt
trước đó không chạy lại Researcher; phiên đã lỗi ở bước Researcher cũng cần
tạo lại. Với HUT 2022–2025, chọn phạm vi **Hợp nhất**
và bấm **Lập dàn ý**. Trước khi duyệt, chưa có thẻ **Kết quả Researcher**.

Duyệt dàn ý và chờ request AG-UI hoàn tất. Thẻ **Kết quả Researcher** cần xuất
hiện với số tác vụ tra cứu, bằng chứng, phép tính và trạng thái theo từng tác vụ.
Một số tác vụ có thể `partial` hoặc `no_evidence`; đọc mục thiếu/cảnh báo để
phân biệt thiếu dữ liệu với lỗi. Trạng thái toàn phiên phụ thuộc vào kết quả
Verifier sau đó. Tải lại trang để xác nhận kết quả còn trong
checkpoint. Có thể đối chiếu trace LangSmith theo cùng lượt chạy.

Nếu thẻ không xuất hiện, sao chép mã phiên và mở
`http://127.0.0.1:8123/runs/<mã-phiên>` để kiểm tra `research_completed`,
`research_results` và `run_status`; ghi lại lỗi ở terminal backend và mã HTTP
của `POST /api/copilotkit/agent/report_probe/run` trong DevTools.

## Kiểm tra Writer thủ công

Khởi động lại backend và tạo **Phiên mới**; phiên đã duyệt trước khi nối Writer
hoặc dừng vì lỗi AG-UI không tự chạy tiếp. Dùng HUT 2023–2025, phạm vi **Hợp nhất** để đối chiếu
với lượt Researcher đã thành công. Trước khi duyệt dàn ý, chưa có thẻ
**Bản nháp Writer**.

Sau khi duyệt, chờ graph hoàn tất rồi mở thẻ **Bản nháp Writer và kết quả Verifier**. Mỗi section
có bản nháp cần hiển thị nội dung và nguồn **Gemini**, **mẫu dự phòng** hoặc
**mẫu**. Xem mức kiểm chứng của từng section; `passed` ở mức quy tắc chưa phải
kiểm chứng ngữ nghĩa đầy đủ.
Tải lại trang và xác nhận nội dung bản nháp cùng trạng thái kiểm tra còn nguyên.
Đồng thời kiểm tra Console không còn `RUN_ERROR`; thẻ bản nháp xuất hiện riêng
lẻ chưa đủ chứng minh lượt AG-UI đã hoàn tất.

Nếu thẻ Writer không xuất hiện, mở `http://127.0.0.1:8123/runs/<mã-phiên>` và
kiểm tra `writer_completed`, `writer_sections`, `run_status`. Ghi lại lỗi
terminal, request AG-UI trong DevTools và trace LangSmith. Nếu tất cả section
đều dùng mẫu dự phòng, ghi nhận số lượt tạo và lỗi Writer trong trace.

## Kiểm tra bảng số liệu thủ công

Dừng backend cũ rồi khởi động lại. Có thể dùng ngay phiên HUT 2022–2025 đã
chạy trước khi nối Verifier: tải lại trang, không cần gọi lại Gemini.
Mở các section có số liệu như S3, S4, S5 trong thẻ **Bản nháp Writer**. Với
section đạt kiểm tra quy tắc và có dữ liệu số, bảng theo năm cần xuất hiện bên
dưới phần chữ, có cột năm, đơn vị tỷ đồng và trích dẫn nguồn ở ô có dữ liệu.
Ô thiếu hoặc mơ hồ phải là `—`; bảng tỷ lệ và biến động theo kỳ chỉ xuất hiện
khi dàn ý có tác vụ tương ứng. Section có kết quả Verifier khác `passed` không hiển thị
bảng. Nhấn F5 để xác nhận bảng vẫn còn; trạng thái phiên cũ vẫn là `incomplete`.

Nếu không có bảng ở section đang kiểm tra, mở
`http://127.0.0.1:8123/runs/<mã-phiên>` và xem `writer_sections`: ghi lại
`verification_status` và `table_markdown` của section đó cùng lỗi terminal nếu có.

## Kiểm tra Verifier ngữ nghĩa thủ công

Dừng backend cũ, khởi động lại và tạo **Phiên mới**; phiên cũ không tự chạy lại
Verifier. Dùng HUT 2022–2025 phạm vi **Hợp nhất**, bấm **Lập dàn ý**, sau đó
**Duyệt dàn ý**. Lượt này sẽ gọi Gemini cho Planner, Writer và các section đủ
điều kiện để Verifier ngữ nghĩa chạy. Chờ request AG-UI hoàn tất và kiểm tra
Console không có `RUN_ERROR`.

Mở từng section trong thẻ Writer. Section đạt kiểm chứng đầy đủ phải hiển thị
`đầy đủ: passed`; section dừng ở quy tắc hoặc bị Verifier từ chối cần hiện
trạng thái, vấn đề và hành động đề xuất. `completed` chỉ đúng khi tất cả section
đạt `full/passed` ở đúng revision đã duyệt. Nếu còn section chưa đạt, trạng thái
phải là `incomplete`. F5 phải giữ nguyên các kết quả này.

Nếu cần đối chiếu, mở `http://127.0.0.1:8123/runs/<mã-phiên>` và ghi lại
`run_status`, `outline_approved_version` cùng `verification_level`,
`verification_status`, `semantic_status`, `verifier_error` trong
`writer_sections`. Xem trace LangSmith để xác nhận các lượt gọi Gemini Verifier.

## Kiểm tra báo cáo hoàn chỉnh và chat thủ công

Dừng backend và UI cũ rồi khởi động lại. Mở lại phiên HUT 2022–2025 đã có
`completed` và nhấn F5; không cần chạy lại graph. Trang quy trình cần hiện
**Báo cáo đã sẵn sàng**, không hiển thị nội dung báo cáo hoặc chat cùng các thẻ
bản nháp. Bấm **Mở báo cáo hoàn chỉnh** để sang `/report?threadId=<mã-phiên>`.
Trang này cần có mục lục, các section, trích dẫn, bảng S3–S5 và khung chat bên
dưới. Nút **Tải Markdown** cần tải `report.md` chứa đúng `final_report`.
Các trích dẫn dạng `[Doc_…, p.…]` trong đoạn văn và ô bảng cần hiện thành nhãn
nguồn có nền màu, tách rõ khỏi nội dung nhưng giữ nguyên ký hiệu nguồn.

Trong khung **Chat với Gemini**, hỏi “Doanh thu thuần năm 2025 là bao nhiêu,
nguồn ở đâu?”; câu trả lời cần dùng số liệu và trích dẫn có trong báo cáo.
Hỏi tiếp “So với năm 2024 thì sao?” để kiểm tra ngữ cảnh hội thoại. Sau đó hỏi
“Giải thích ngắn gọn định luật II Newton” để xác nhận chat trả lời được câu hỏi
ngoài báo cáo. Hỏi “Giá cổ phiếu HUT hôm nay là bao nhiêu?” để kiểm tra chat
nói rõ khi không thể xác minh dữ liệu hiện tại. F5 trên trang `/report` cần giữ
báo cáo và lịch sử chat; **Quay lại quy trình** cần trở về đúng phiên. Thu nhỏ
cửa sổ trình duyệt để kiểm tra bố cục, font tiếng Việt và bảng cuộn ngang.
Từ trang báo cáo, bấm **Quay lại quy trình** và xác nhận trang mở đúng phiên
`completed` mà không có lỗi `useAgent: Agent 'report_probe_session' not found`.
Mở lại báo cáo, bấm **Lập báo cáo mới**; form tạo yêu cầu cần xuất hiện với mã
phiên mới, còn báo cáo cũ vẫn mở được bằng URL `/report?threadId=<mã-phiên-cũ>`.
Trong câu trả lời Gemini, tiêu đề, chữ đậm, danh sách và dấu phân cách Markdown
cần hiện thành bố cục đã định dạng, không còn hiện ký tự `**`, `##` hoặc `---`
như văn bản thuần. Kiểm tra cả tin nhắn cũ sau F5.

Nếu chat lỗi, ghi mã HTTP của `POST /api/report/chat`, thông báo trên trang và
traceback backend. Có thể mở `http://127.0.0.1:8123/runs/<mã-phiên>` để xác
nhận `run_status=completed` và `final_report` có nội dung. Nội dung báo cáo và
câu hỏi được gửi đến Gemini; khi LangSmith tracing bật, lượt chat cũng được
ghi trace.

Với một phiên `incomplete`, liên kết mở trang báo cáo không xuất hiện. Nếu mở
`/report?threadId=<mã-phiên>` trực tiếp, trang phải báo phiên chưa có báo cáo
hoàn chỉnh; endpoint tải báo cáo và endpoint chat trả HTTP 409.

Để thử luồng không gọi model, chạy bộ test sau:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.report.test_copilotkit_probe -v
cd ui-prototype
npm.cmd run lint
npm.cmd run build
```

Bản mẫu chạy local và chưa có xác thực người dùng. Khi `.env` có
`LANGSMITH_TRACING=true` cùng thông tin truy cập LangSmith, các lượt chạy sau
khi khởi động lại backend sẽ được ghi trace. Backend dùng kho chứng chỉ tin cậy
của Windows qua `truststore` để xác minh kết nối HTTPS với Gemini và LangSmith.
