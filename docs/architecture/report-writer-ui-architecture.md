# Giao diện Report Writer — tài liệu kỹ thuật

Tài liệu này mô tả **bản mẫu giao diện hiện tại** trong `ui-prototype/`: kiến trúc, luồng dữ liệu, điều kiện hiển thị và các điểm cần kiểm tra khi sửa mã. Tài liệu dành cho người dùng và người trình bày ở [Giới thiệu giao diện Report Writer](../project/report-writer-ui-guide.md) được giữ riêng.

## 1. Thành phần và đường đi của dữ liệu

```mermaid
flowchart LR
    B[Trình duyệt<br/>Next.js UI] --> C[CopilotKit Runtime<br/>/api/copilotkit]
    C --> A[FastAPI AG-UI<br/>/agent]
    A --> G[LangGraph<br/>Planner → duyệt → Researcher → Writer → Verifier]
    G --> S[(SQLite checkpoint)]
    G --> D[(Corpus và công cụ tra cứu)]
    G --> M[Gemini]
    B --> P[Next.js API<br/>snapshot, chat, tải báo cáo]
    B -->|EventSource| E[Next.js SSE proxy<br/>/api/report/progress]
    P --> R[FastAPI<br/>/runs/{thread_id}/*]
    E -->|SSE| R
    R --> S
    R --> M
```

- **Next.js/React** hiển thị form, thẻ duyệt, tiến trình, báo cáo và chat. CSS giao diện nằm trong `ui-prototype/app/globals.css`.
- **CopilotKit + AG-UI** chuyển sự kiện chạy graph và `interrupt` duyệt dàn ý giữa trình duyệt và FastAPI.
- **FastAPI** dựng graph thật từ Planner, Researcher, Writer, Verifier; đọc checkpoint để trả snapshot, tệp báo cáo và câu trả lời chat.
- **SQLite checkpointer** giữ trạng thái graph theo `thread_id` tại `ui-prototype/.data/checkpoints.sqlite`. Lịch sử chat không nằm trong checkpoint này.

Đây là ứng dụng chạy local: Next.js thường ở `http://localhost:3000`, FastAPI ở `http://127.0.0.1:8123`. Các proxy Next.js hiện trỏ cố định tới cổng `8123`.

## 2. Các tệp chính

| Tệp | Trách nhiệm |
| --- | --- |
| `ui-prototype/app/page.tsx` | Trang quy trình `/`: form yêu cầu, thẻ duyệt dàn ý, kết quả Researcher/Writer, trạng thái và liên kết mở báo cáo. |
| `ui-prototype/app/report/page.tsx` | Trang `/report`: đọc `final_report`, hiển thị mục lục, tải Markdown và chat. |
| `ui-prototype/app/components/citation-text.tsx` | Tô nhãn các trích dẫn có dạng `[Doc_…]` trong văn bản. |
| `ui-prototype/app/components/markdown-table.tsx` | Hiển thị bảng Markdown và nhãn nguồn trong ô bảng. |
| `ui-prototype/app/providers.tsx` | Khởi tạo `CopilotKitProvider` với runtime agent `report_probe`. |
| `ui-prototype/app/api/copilotkit/[[...slug]]/route.ts` | Nối CopilotKit Runtime tới FastAPI `/agent`. |
| `ui-prototype/app/api/report/{route.ts,chat/route.ts,download/route.ts}` | Proxy đọc snapshot, gửi chat và tải báo cáo. |
| `ui-prototype/app/api/report/progress/route.ts` | Xóa danh sách tiến độ trước một lượt chạy và chuyển tiếp SSE từ backend tới trình duyệt. |
| `scripts/prototypes/copilotkit_backend.py` | FastAPI, AG-UI adapter, SQLite saver, các endpoint `/runs/{thread_id}`. |
| `src/agents/report_graph.py` và `src/agents/state.py` | Luồng graph và quy tắc xác định báo cáo đã hoàn tất. |

## 3. Phiên và luồng tạo báo cáo

Trình duyệt giữ mã phiên hiện tại trong `localStorage` với khóa `planner-ui-thread`. Trang báo cáo có URL `/report?threadId=<id>`. Khi quay về quy trình, URL chuyển mã phiên tương ứng cho trang `/`; trang này lưu mã phiên đó rồi tải lại snapshot. Nút **Phiên mới** hoặc **Lập báo cáo mới** tạo UUID mới. Chỉ việc tạo UUID chưa gọi graph.

Trang quy trình dùng `useAgent({ agentId: "report_probe_session", runtimeAgentId: "report_probe", threadId })`. `report_probe_session` là tên agent cục bộ của một phiên; `report_probe` là agent do runtime/backend công bố. `useInterrupt` được gắn sau khi agent cục bộ sẵn sàng để tránh lỗi tìm agent khi điều hướng từ `/report` về `/`.

Luồng chính:

1. Form gửi `ticker`, `scope`, `start_year`, `end_year`, `instructions` và `audience` mặc định là `"Nhà đầu tư"`. Ô đối tượng đọc đã được bỏ khỏi giao diện nhưng trường này vẫn được gửi vì hợp đồng `ReportRequest` cần nó.
2. Planner trả dàn ý hoặc trạng thái cần làm rõ. Với dàn ý hợp lệ, graph dừng tại `interrupt` và đợi quyết định.
3. Người dùng `approve`, `revise` hoặc `reject`. Khi sửa, UI chỉ cho đổi tiêu đề/mục tiêu; graph tạo `outline_version` mới và đòi duyệt lại. Quyết định phải mang đúng `outline_version` hiện tại.
4. Sau khi duyệt, graph chạy Researcher → Writer → Verifier. Snapshot trả số tác vụ, bằng chứng, phép tính, bản nháp và kết quả kiểm chứng theo section.
5. UI chỉ mở trang báo cáo hoàn chỉnh khi `run_status=completed` và có `final_report`. Khi phiên `incomplete`, các bản nháp và vấn đề kiểm chứng vẫn xem được trên trang quy trình.

Trong lúc Planner chạy, `build_planner_agent` gọi callback tại các mốc thực: kiểm tra phạm vi, chuẩn bị cấu trúc, các lượt Gemini, từng mục tra cứu và kiểm tra dàn ý. Backend gắn sự kiện với `thread_id` trong cấu hình LangGraph, lưu danh sách sự kiện tạm thời trong RAM và phát qua `GET /runs/{thread_id}/progress` dạng SSE. Next.js chuyển tiếp luồng qua `/api/report/progress`; trang `/` đọc bằng `EventSource` và hiển thị các mốc theo thứ tự. UI gọi `POST /api/report/progress` để xóa sự kiện cũ trước khi bắt đầu lượt mới. Danh sách tiến độ chỉ là nhật ký hoạt động trong lần chạy hiện tại, không phải phần trăm hoặc thời gian hoàn thành dự đoán. Checkpoint vẫn là nguồn để khôi phục kết quả sau F5; các sự kiện tạm thời không được lưu vào checkpoint.

Sau khi người dùng duyệt dàn ý, UI xóa danh sách sự kiện cũ và mở lại cùng luồng SSE trước khi gửi quyết định qua `useInterrupt.resolve`. Researcher phát mốc trước và sau từng tác vụ tra cứu, kèm số bằng chứng và trạng thái tra cứu; Writer phát mốc chuẩn bị, từng section và lượt Gemini của các section định lượng; Verifier phát mốc trước và sau từng section cùng kết luận của toàn phiên. Trong lúc đó UI hiển thị trạng thái tạo và kiểm chứng, đồng thời ẩn dòng chờ thẻ duyệt dựa trên snapshot cũ. Khi `resolve` và lần đọc snapshot hoàn tất, UI đóng luồng; nhãn hoàn tất vẫn lấy từ `run_status` trong checkpoint. Một lần gọi Gemini hoặc tra cứu dài sẽ giữ nguyên mốc hiện tại cho tới khi có sự kiện thật tiếp theo.

`src/agents/state.py::can_complete` yêu cầu **mọi section** của dàn ý đang duyệt có bản nháp ở đúng revision với kết quả Verifier `status="passed"` và `level="full"`. Backend kiểm tra lại điều kiện này trước khi trả `final_report`, chat hoặc tệp tải xuống. Vì vậy, nhãn hoàn tất dựa trên trạng thái graph và kết quả kiểm chứng, không dựa vào việc giao diện nhìn thấy bản nháp.

## 4. API và dữ liệu lưu trữ

| Từ trình duyệt | Backend tương ứng | Dùng để làm gì |
| --- | --- | --- |
| `/api/copilotkit/*` | `/agent` | Chạy graph và xử lý sự kiện AG-UI/interrupt. |
| `GET /api/report?threadId=<id>` | `GET /runs/{thread_id}` | Đọc snapshot để dựng lại UI sau F5. |
| `POST /api/report/progress?threadId=<id>` | `POST /runs/{thread_id}/progress` | Xóa sự kiện tiến độ cũ trước lượt Planner hoặc lượt sau duyệt. |
| `GET /api/report/progress?threadId=<id>` | `GET /runs/{thread_id}/progress` | Chuyển tiếp danh sách sự kiện SSE trong lúc graph chạy. |
| `GET /api/report/download?threadId=<id>` | `GET /runs/{thread_id}/report.md` | Tải đúng chuỗi `final_report` dưới tên `report.md`. |
| `POST /api/report/chat` | `POST /runs/{thread_id}/chat` | Gửi câu hỏi, lịch sử gần nhất; nhận `{ "answer": "..." }`. |

Backend còn có `POST /runs/{thread_id}` và `POST /runs/{thread_id}/resume` để gọi trực tiếp, nhưng luồng giao diện hiện dùng AG-UI. `GET /runs/{thread_id}` trả `404` khi không có checkpoint. Endpoint chat và tải báo cáo trả `409` nếu phiên chưa hoàn tất hoặc thiếu `final_report`. Proxy Next.js trả `503` khi không kết nối được backend trên cổng `8123`.

Checkpoint SQLite giữ dàn ý, revision, kết quả nghiên cứu, bản nháp, kiểm chứng và báo cáo. Sự kiện tiến độ chỉ nằm trong RAM của tiến trình backend; khởi động lại backend sẽ mất danh sách sự kiện, nhưng không xóa checkpoint. Trình duyệt giữ **lịch sử chat** bằng khóa `report-chat-<threadId>` trong `localStorage`; mỗi câu hỏi chỉ gửi tối đa 12 tin nhắn gần nhất cho backend. Lịch sử này tồn tại sau F5 trên cùng trình duyệt, nhưng không đồng bộ giữa thiết bị.

## 5. Trang báo cáo và chat

Trang `/report` gọi API snapshot rồi kiểm tra `run_status` và `final_report`. Nội dung báo cáo được tách thành tiêu đề, đoạn văn và bảng. Mục lục dẫn tới các tiêu đề phần. Thành phần `CitationText` chỉ nhận diện mẫu `[Doc_…]` để tô nhãn; nó giữ nguyên mã trích dẫn, không mở tài liệu gốc. Câu trả lời Gemini được hiển thị dưới dạng Markdown bằng `Streamdown`; nội dung tải xuống vẫn là Markdown gốc.

Chat là một request độc lập với graph. Backend đọc **toàn bộ báo cáo hoàn chỉnh từ checkpoint** cho mỗi câu hỏi, ghép với tối đa 12 tin nhắn gần nhất và câu hỏi mới, rồi gọi `gemini-3.8-flash`. Hướng dẫn hệ thống cho phép hỏi ngoài báo cáo và yêu cầu phân biệt dữ kiện trong báo cáo với kiến thức chung. Chat không sửa `final_report`, không đổi `run_status` và không chạy lại Verifier.

Giới hạn hiện tại của API chat: câu hỏi tối đa 2.000 ký tự, tối đa 12 tin nhắn lịch sử, mỗi tin tối đa 16.000 ký tự; cấu hình Gemini đặt `max_output_tokens=2048`, `temperature=0`, mức suy nghĩ `LOW`. Các giới hạn này là giới hạn kích thước đầu vào/đầu ra, không phải giới hạn chủ đề hỏi.

## 6. Cấu hình và lưu ý vận hành

- Backend đọc `GEMINI_API_KEY` hoặc `GOOGLE_API_KEY` từ biến môi trường hoặc `.env`. Planner, Writer, Verifier và chat đều dùng Gemini 3.8 Flash trong cấu hình hiện tại.
- Khi `LANGSMITH_TRACING=true`, client Gemini thật được bọc để ghi trace qua LangSmith. Nội dung gửi tới Gemini và trace cần được xem xét theo chính sách dữ liệu của môi trường triển khai.
- Bản mẫu chưa có xác thực người dùng hay phân quyền theo mã phiên. Không nên đưa trực tiếp các endpoint này lên mạng nhiều người dùng khi chưa bổ sung kiểm soát truy cập.
- Chat history nằm trong trình duyệt; xóa dữ liệu trình duyệt sẽ xóa phần lịch sử chat cục bộ. Checkpoint báo cáo là tệp SQLite riêng.
- `GET /api/report` trả snapshot phục vụ giao diện, gồm cả thông tin nghiên cứu và bản nháp; không nên coi phản hồi này là API công khai ổn định nếu chưa chốt hợp đồng dữ liệu.

## 7. Kiểm tra thủ công sau khi sửa giao diện

1. Mở phiên đã hoàn tất, F5 ở cả `/` và `/report`; kiểm tra cùng mã phiên, cùng revision, báo cáo và bảng còn hiển thị.
2. Từ `/report`, bấm **Quay lại quy trình** rồi mở lại báo cáo; kiểm tra không có lỗi `report_probe_session not found`.
3. Hỏi một câu có dữ kiện trong báo cáo và một câu ngoài báo cáo; kiểm tra câu trả lời Markdown, nguồn trích dẫn và lịch sử chat sau F5.
4. Bấm **Lập báo cáo mới**; kiểm tra UUID mới và form tạo yêu cầu với các giá trị mặc định. Báo cáo cũ vẫn mở được bằng URL chứa `threadId` cũ.
5. Mở trực tiếp `/report?threadId=<id>` của phiên `incomplete`; trang cần báo chưa có báo cáo hoàn chỉnh, còn API chat và tải xuống trả `409`.
6. Với phiên mới, nhấn **Lập dàn ý**; trong Network, `GET /api/report/progress` phải nhận các dòng `data:` trước khi thẻ duyệt xuất hiện. Danh sách trên trang cập nhật theo các mốc Planner thật.
7. Với phiên đang chờ duyệt, nhấn **Duyệt dàn ý**; luồng SSE mới phải nhận các mốc Researcher → Writer → Verifier trong khi request CopilotKit còn chạy. Trang không hiện dòng chờ thẻ duyệt cũ; chỉ hiện **Hoàn tất** nếu snapshot cuối có `run_status=completed`.

Các bước này dùng trình duyệt và backend đang chạy; việc biên soạn tài liệu không tạo phiên hoặc gọi Gemini.
