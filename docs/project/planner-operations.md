# Hướng dẫn vận hành Planner Agent

Tài liệu này mô tả cách chạy và duyệt dàn ý cho **một ticker** theo mã hiện tại. Planner nhận `ReportRequest`, kiểm tra độ phủ dữ liệu, đọc dữ liệu qua tool khi dùng LLM, rồi trả `PlannerOutput`. Planner không viết báo cáo và không tự chọn một dòng số liệu nguồn để công bố.

## 1. Chuẩn bị

- Chạy lệnh từ thư mục gốc project. Dùng Python trong `.venv` và các dependency của project.
- Có DuckDB facts tại đường dẫn mặc định `data/facts_storage/financial_facts.duckdb` (hoặc `data/financial_facts.duckdb` nếu project đang dùng đường dẫn cũ). Có thể truyền `db_path` khác vào `AgentTools` và `plan_report`.
- Để chạy Planner LLM, đặt `GEMINI_API_KEY=...` hoặc `GOOGLE_API_KEY=...` trong `.env` ở thư mục đang chạy lệnh, hoặc trong biến môi trường. Adapter hiện gọi `gemini-3.8-flash` với mức suy luận `MEDIUM`.
- Truy vấn note cần note index và manifest `configs/manifests/manifest_vnfin_v1_bge_m3_v1.json`. Nếu thiếu manifest, Planner ghi kết quả note là `error`; không được diễn giải đó là không có thông tin trong tài liệu.

Không cần API key cho chế độ template và các kiểm thử dùng model giả.

## 2. Chạy nhanh chế độ template

Lệnh PowerShell dưới đây kiểm tra đầu vào và tạo dàn ý tất định, không gọi LLM hay truy vấn note:

```powershell
@'
from src.agents.planner import plan_report
from src.schemas.report_schema import ReportRequest

request = ReportRequest(
    ticker="HUT", start_year=2022, end_year=2025,
    scope="consolidated", audience="Nhà đầu tư",
)
result = plan_report(request)
print("status:", result.status)
print("sections:", [s.section_id for s in result.outline.sections] if result.outline else [])
print("notes:", [(n.code, n.message) for n in result.notes])
'@ | .\.venv\Scripts\python.exe -
```

`ready` nghĩa là có dàn ý để duyệt; không có nghĩa là tất cả task đã có dữ liệu hoặc báo cáo đã hoàn tất. `needs_clarification` nghĩa là thiếu năm trong scope yêu cầu; xem `available_scopes` và `notes`, rồi tạo **request mới** sau khi người dùng chọn scope. `rejected` nghĩa là ticker ngoài corpus hoặc chưa có bộ mã chuẩn được hỗ trợ; xem mã lý do trong `notes`. Preflight không tự chuyển scope và không gọi LLM cho request bị chặn.

## 3. Chạy Planner LLM để đề xuất dàn ý

Sau khi có API key, chạy từ thư mục gốc project:

```powershell
@'
from src.agents.planner_agent import build_planner_agent
from src.agents.planner_model import GeminiPlannerModel
from src.schemas.report_schema import ReportRequest
from src.tools.agent_tools import AgentTools

request = ReportRequest(
    ticker="HUT", start_year=2022, end_year=2025,
    scope="consolidated", audience="Nhà đầu tư",
)
with AgentTools() as tools:
    plan = build_planner_agent(GeminiPlannerModel(), tools)
    result = plan(request)
    print("status:", result.status, "fallback:", result.used_fallback)
    print("sections:", [s.section_id for s in result.outline.sections] if result.outline else [])
    print("decisions:", [d.model_dump(mode="json") for d in result.decisions])
    print("notes:", [n.model_dump(mode="json") for n in result.notes])
    print("observations:", len(result.observations))
'@ | .\.venv\Scripts\python.exe -
```

Luồng của một lần gọi:

1. `preflight()` kiểm tra ticker, năm, scope và bộ mã chuẩn. Nếu không qua, trả trạng thái dừng ngay.
2. `plan_report()` tạo dàn ý tham chiếu S1–S5; S6/S7 có thể xuất hiện theo đối tượng đọc hoặc hướng dẫn.
3. LLM nhận request, dàn ý tham chiếu, scope có sẵn và prompt chuyên biệt. LLM có thể yêu cầu `observe`: resolver, fact, time series hoặc note. `PlannerToolbox` khóa ticker, scope, khoảng năm và yêu cầu tên chỉ tiêu đi qua resolver. Mỗi quan sát có ID và snapshot nguồn.
4. LLM đề xuất `outline`, `decisions` và `notes`. Nó có thể giữ, bỏ, gộp, tách hoặc thêm section theo dữ liệu đã đọc. `_validate_proposal()` kiểm tra cấu trúc, liên kết với quan sát, mã chỉ tiêu đã phân giải và task đã được kiểm tra qua tool. Kiểm tra này **không bảo đảm** lý do phân tích của LLM là đúng; người dùng vẫn phải duyệt.
5. Nếu JSON, schema hoặc proposal sai, Planner gửi lỗi cho LLM thử sửa. Sau giới hạn lượt, nó trả dàn ý template với `used_fallback=True` và note `planner_fallback`.

Mặc định giới hạn là 6 lượt LLM và 64 tool call. Trạng thái `ready` có thể đi kèm `used_fallback=True`; luôn kiểm tra cả hai trường.

## 4. Duyệt dàn ý trước Researcher

`build_report_graph()` nhận một hàm Planner qua tham số `plan`. Bật `require_outline_approval=True` và cung cấp LangGraph checkpointer để dừng tại bước Human in the Loop. Ví dụ sau chỉ minh họa cơ chế duyệt bằng Planner template; `research` và `write` là hàm trống, nên **không tạo báo cáo thật**:

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents.planner import plan_report
from src.agents.report_graph import build_report_graph
from src.agents.state import report_checkpoint_serde
from src.schemas.report_schema import ReportRequest

graph = build_report_graph(
    plan_report,
    research=lambda state: {},
    write=lambda state: {},
    require_outline_approval=True,
    checkpointer=InMemorySaver(serde=report_checkpoint_serde()),
)
config = {"configurable": {"thread_id": "planner-demo-001"}}
request = ReportRequest(
    ticker="HUT", start_year=2022, end_year=2025,
    audience="Nhà đầu tư",
)
pending = graph.invoke({"request": request}, config)
print(pending["run_status"], pending["outline_version"])
print(pending["__interrupt__"])  # outline, decisions, planner_notes để duyệt

approved = graph.invoke(
    Command(resume={"action": "approve", "outline_version": pending["outline_version"]}),
    config,
)
print(approved["run_status"])
```

Khi tích hợp thật, dùng `build_agent_report_graph(GeminiPlannerModel(), tools, write, checkpointer=...)` trong `src/agents/report_graph.py`. Hàm này nối Planner Agent và Researcher, đồng thời bắt buộc `require_outline_approval=True`; ứng dụng vẫn phải cung cấp hàm Writer và checkpointer. Giữ `AgentTools` hoạt động trong suốt lần gọi graph. `InMemorySaver` chỉ phù hợp demo hoặc một tiến trình; triển khai vận hành cần checkpointer bền vững.

Trước khi bấm duyệt, kiểm tra:

- Ticker, năm, scope và đối tượng đọc của request; các section, task và phép tính trong `outline`.
- `outline_decisions`: section nào bị bỏ/gộp/tách/thêm, lý do, và `observation_ids` hỗ trợ quyết định dựa trên dữ liệu.
- `planner_observations`: `status`, `missing_years`, `safe_for_calculation`, cảnh báo, đơn vị, citation và snapshot. `error`/`invalid_input` là lỗi truy vấn; `not_found` là không thấy dữ liệu trong truy vấn đó; không đồng nhất hai trường hợp.
- `planner_notes`, `planner_used_fallback` và `planner_prompt_version`. Với kỳ nhiều năm, xem cảnh báo `period_inconsistency` trước khi cho phép so sánh.

Muốn chỉnh dàn ý, sửa một bản JSON của `pending["outline"].model_dump(mode="json")` và gửi:

```python
revised = pending["outline"].model_dump(mode="json")
# Chỉnh revised theo quyết định đã duyệt; giữ đúng schema ReportOutline.
pending = graph.invoke(
    Command(resume={
        "action": "revise",
        "outline_version": pending["outline_version"],
        "outline": revised,
    }),
    config,
)
print(pending["outline_version"], pending["__interrupt__"])
```

Lần sửa tạo revision mới và dừng lại để duyệt tiếp. Khi `approve`, `revise` hoặc `reject`, luôn gửi `outline_version` đang chờ; phiên bản cũ bị từ chối. `reject` kết thúc ở `needs_clarification`. Sau `approve`, graph đi qua Researcher → Writer → Verifier. Verifier hiện chỉ kiểm tra tất định và để `run_status="incomplete"`; một bước kiểm chứng ngữ nghĩa đầy đủ còn cần thiết trước khi coi báo cáo là hoàn thành. Nếu bỏ `require_outline_approval`, graph chạy thẳng từ Planner đến Researcher; không dùng cấu hình đó khi cần người dùng duyệt.

## 5. Kiểm thử và xử lý sự cố

Kiểm thử offline:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_planner tests.test_planner_agent tests.test_report_graph -q
```

Đánh giá Dev bằng Gemini sau khi cấu hình API key:

```powershell
.\.venv\Scripts\python.exe -m src.evaluation.planner_eval --cases configs/planner_eval_dev.json
```

Kết quả đánh giá ghi tỷ lệ proposal qua validator, số section trong template bị bỏ mà không có giải thích, tỷ lệ decision dựa trên dữ liệu có observation ID, số lượt sửa, lượt gọi tool, thời gian và token khi adapter nhận được usage metadata. Các chỉ số này chưa đo mức chấp nhận thực tế của người duyệt HITL.

Các ca đánh giá hiện gồm HUT/GMD đầy đủ, FPT có chỉ tiêu thiếu năm trong Dev, DHG thiếu scope và FOX ngoài corpus. Dùng kết quả để kiểm tra trạng thái, section bắt buộc, dấu vết quyết định và fallback. Không dùng ticker held-out để tinh chỉnh quy tắc.

| Hiện tượng | Cách xử lý |
|---|---|
| Thiếu `GEMINI_API_KEY`/`GOOGLE_API_KEY` | Thêm key vào `.env` hoặc biến môi trường, rồi chạy lại chế độ LLM. Chế độ template vẫn chạy được. |
| `needs_clarification` | Đọc `available_scopes` và `scope_or_year_missing`; hỏi người dùng chọn scope/năm, sau đó tạo request mới. |
| `rejected` | Đọc `notes` để phân biệt ngoài corpus, ngân hàng hoặc bộ mã chưa hỗ trợ. |
| `used_fallback=True` | Đọc `planner_fallback` và các note khác; dàn ý là template, cần duyệt thủ công trước khi nghiên cứu. |
| Note có `error` | Kiểm tra manifest, note index và retriever; không ghi nhận là bằng chứng vắng mặt. |
| Duyệt outline báo lỗi | Kiểm tra checkpointer, `thread_id`, `action` và `outline_version` hiện hành. |

Các điểm mã nguồn: `src/agents/planner.py` (preflight/template), `src/agents/planner_agent.py` (vòng LLM và kiểm tra proposal), `src/agents/planner_toolbox.py` (tool đọc dữ liệu), `src/agents/report_graph.py` (graph và HITL), `src/schemas/report_schema.py` (hợp đồng dữ liệu).
