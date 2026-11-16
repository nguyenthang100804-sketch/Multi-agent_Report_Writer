# Bộ công cụ chuẩn cho Agent

Tầng `src/tools/` cung cấp bốn công cụ độc lập với framework LLM. Đầu vào và
đầu ra được kiểm tra bằng Pydantic; có JSON Schema cho function calling.

| Công cụ | Nguồn | Kết quả |
| --- | --- | --- |
| `query_fact_tool` | DuckDB | Chỉ tiêu đơn năm, đơn vị, trang PDF/trang in, citation |
| `query_time_series_tool` | DuckDB | Chuỗi số liệu theo năm, năm thiếu, trạng thái sẵn sàng tính toán |
| `search_notes_tool` | Qdrant dense + BM25 tiếng Việt + cross-encoder | Tối đa 5 chunks định tính có trích dẫn |
| `metric_name_resolver` | Danh mục alias xác định | Mã chỉ tiêu + loại báo cáo hoặc các ứng viên cần làm rõ |

## Gọi trực tiếp

```python
from src.tools import query_fact_tool, query_time_series_tool, metric_name_resolver

fact = query_fact_tool({
    "ticker": "FPT", "fiscal_year": 2024, "metric_name": "doanh thu thuần",
})
series = query_time_series_tool({
    "ticker": "FPT", "start_year": 2022, "end_year": 2025,
    "item_code": "10", "report_type": "INCOME_STATEMENT",
})
resolved = metric_name_resolver({"metric_name": "tổng tài sản"})
print(fact.model_dump_json())
```

Cũng có thể truyền các model `FactQueryInput`, `TimeSeriesQueryInput`,
`NotesSearchInput`, `MetricResolverInput`. Dữ liệu trả về là `ToolResult`;
dùng `.model_dump(mode="json")` hoặc `.model_dump_json()` để chuyển cho LLM.

## Function calling và vòng đời tài nguyên

```python
from src.tools import AgentTools, get_function_calling_specs, get_output_schema
from src.tools.notes_retriever import HybridNotesRetriever

definitions = get_function_calling_specs()
output_schema = get_output_schema()

# Mặc định dùng Qdrant local. Chuyển sang cloud bằng use_cloud=True;
# endpoint và API key được đọc bằng cơ chế .env hiện có của project.
notes = HybridNotesRetriever(use_cloud=False, candidate_pool_size=30)
with AgentTools(notes_retriever=notes) as tools:
    # Khi LLM trả về tool name + arguments (dict hoặc JSON string):
    result = tools.execute("search_notes_tool", {
        "query": "Chính sách khấu hao tài sản cố định hữu hình",
        "ticker": "FPT", "fiscal_year": 2024,
    })
    serialized_result = result.model_dump_json()
```

Định nghĩa function có dạng `{"type": "function", "function": {...}}`.
Đây là JSON Schema thông thường; chưa chuyển thành strict schema riêng của từng
nhà cung cấp. Với client cần cấu trúc phẳng, dùng
`[{"type": "function", **d["function"]} for d in definitions]`.
Các ràng buộc liên trường (ví dụ phải có tên chỉ tiêu hoặc cả mã và loại báo cáo)
được kiểm tra khi dispatch. Không cần cài LangGraph/LangChain để dùng interface.

Giữ một `AgentTools` cho một runtime để tái sử dụng index BM25 và model. Dùng
context manager để đóng Qdrant. Model chỉ được nạp khi tìm thuyết minh; gọi facts
hoặc resolver không nạp model. Không dùng chung một runtime giữa nhiều thread
đồng thời nếu chưa có cơ chế đồng bộ; quá trình ghi DuckDB cần tách khỏi đọc.

## Hợp đồng dữ liệu

- Chỉ nhận năm 2022–2025; mã chỉ tiêu phải là chuỗi, giữ nguyên `"01"`.
- Facts nhận `metric_name`, hoặc `item_code` cùng `report_type`. Nếu cung cấp
  cả tên và mã trái nhau, trả `invalid_input`.
- Mặc định `scope="consolidated"`; chọn `"general"` hoặc `"separate"` khi phù hợp.
- Các trạng thái: `ok`, `partial`, `not_found`, `ambiguous`, `invalid_input`, `error`.
  Lỗi kết nối/model được trả là `error`, không giả làm thiếu bằng chứng.
- `facts` giữ mọi dòng nguồn trùng khớp. Không chọn ngẫu nhiên một dòng khi trùng
  chỉ tiêu. `chunk_ids` chỉ là ứng viên theo trang/mục, không phải liên kết dòng đã
  được xác minh. `citation_tag` và cả hai loại số trang được bảo toàn từ storage.
- `value` là số của năm báo cáo; không thay bằng số so sánh `prior_year` của năm sau.
  Dòng suspect bị loại theo mặc định của storage. Giá trị null không được thay bằng 0.
- `safe_for_calculation` chỉ đúng khi mỗi năm yêu cầu có đúng một dòng, giá trị
  khác null và cùng đơn vị có khai báo. Agent vẫn phải kiểm tra điều kiện công thức:
  YoY không chia cho 0; CAGR cần số đầu/cuối và khoảng thời gian hợp lệ. Không tự
  động chuyển đổi đơn vị hoặc tiền tệ.
- Các năm thiếu/null xuất hiện trong `missing_years`. Thiếu năm giữa chuỗi không
  được tự nội suy. Khả năng lấy đủ dữ liệu khác với khả năng tính một công thức.
- Resolver hiện có 12 chỉ tiêu chuẩn và các alias Việt/Anh, không phân biệt dấu
  hoặc chữ hoa. Chỉ alias chính xác mới được tự chọn; tên chung như “lợi nhuận” trả
  ứng viên `ambiguous`. Tên chưa hỗ trợ trả `not_found`.
- Danh mục mã áp dụng cho mẫu BCTC doanh nghiệp thông thường. Ngân hàng có thể
  không dùng mã này: không suy diễn mã hoặc trả 0. Tầng storage vẫn có truy vấn
  nhãn chính xác cho dữ liệu không có mã; resolver theo ngành là bước mở rộng sau.

## Tìm thuyết minh

Mặc định lọc section `NOTES`; có thể truyền
`sections=["NOTES", "AUDIT_REPORT", "MANAGEMENT_REPORT"]`.
Cả dense và BM25 đều lọc ticker, năm, scope và section trước khi hợp nhất.
Lấy tối đa 30 ứng viên mỗi nhánh, hợp nhất RRF (`k=60`) và trả tối đa 5 chunks
đứng đầu. Không nạp Cross-Encoder Reranker.

BM25 dùng index in-memory hiện có; đây không phải Qdrant sparse-vector search.
`rerank_score` là trường tương thích với dữ liệu cũ và có giá trị `null` ở kết quả
truy hồi mới. Thứ hạng RRF không phải xác suất bằng chứng đúng; Writer/Verifier
phải đối chiếu nội dung với yêu cầu trước khi đưa ra kết luận.

## Kiểm chứng

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Đã kiểm thử schema, alias/mơ hồ, citation, thiếu năm/null, xung đột dòng/đơn vị,
đầu vào sai và lỗi backend. Smoke test thực tế trên corpus trả đủ 4 năm doanh thu
FPT; tìm chính sách khấu hao FPT 2024 qua Qdrant local và hai model local trả 5
chunks NOTES có citation. Đây là kiểm tra tích hợp, chưa phải benchmark độ chính xác
trên toàn bộ golden dataset. Baseline benchmark hiện có được giữ nguyên.

Tham khảo cơ chế tạo schema:
[Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/).
