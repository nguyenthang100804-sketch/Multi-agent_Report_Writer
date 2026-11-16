# Multi-agent Report Writer

Hệ thống lập báo cáo tài chính từ tài liệu, sử dụng DuckDB facts, Qdrant,
BGE-M3 và các công cụ retrieval có metadata trích dẫn.

## Cấu trúc thư mục

| Thư mục | Nội dung |
| --- | --- |
| `src/agents/` | Planner, Researcher, graph, state, tính toán và kiểm chứng |
| `src/agents/prompts/` | Prompt dùng trong runtime |
| `src/tools/` | Giao diện và schema cho Agent tools |
| `src/schemas/` | Schema tài liệu và báo cáo |
| `src/ingestion/` | Làm sạch, parser và xuất danh sách kiểm tra thủ công |
| `src/indexing/` | Embedding, cache, Qdrant và indexing pipeline |
| `src/storage/` | Quản lý DuckDB facts |
| `src/evaluation/` | Mã benchmark và metrics |
| `src/utils/` | Tiện ích dữ liệu và token |
| `tests/planner/`, `tests/research/`, `tests/writer/` | Test tự động theo agent |
| `tests/report/`, `tests/data/` | Test tự động cho báo cáo, dữ liệu và công cụ |
| `tests/test_project_paths.py` | Test đường dẫn của toàn dự án |
| `configs/` | Golden dataset, chia tập, cấu hình đánh giá và manifests |
| `data/raw_docs/`, `data/backup_data/` | Tài liệu đầu vào và bản sao lưu |
| `data/processed_chunks/` | JSON parser: chunks, facts và metadata |
| `data/facts_storage/`, `data/qdrant_local/`, `data/vector_cache/` | Database và cache đang sử dụng |
| `data/catalogs/` | Danh mục doanh nghiệp/dataset |
| `data/report_output/` | Đầu ra báo cáo |
| `models/` | Model và tokenizer local |
| `evaluation/benchmarks/` | Kết quả benchmark facts và retrieval |
| `evaluation/audits/` | Dữ liệu kiểm tra chất lượng |
| `evaluation/planner/` | Kết quả đánh giá và bản chạy thử Planner |
| `evaluation/smoke/` | Kết quả chạy thử toàn bộ graph |
| `evaluation/experiments/` | Kết quả thử nghiệm chưa đưa vào benchmark chính |
| `evaluation/token_statistics/` | Thống kê token gốc/sau làm sạch và so sánh |
| `scripts/audits/` | Script audit corpus, số liệu và kỳ báo cáo |
| `scripts/inspection/` | Script kiểm tra sâu từng tài liệu/doanh nghiệp |
| `scripts/analysis/` | So sánh corpus và đo token |
| `scripts/maintenance/` | Cập nhật ingestion summary và ví dụ state |
| `scripts/diagnostics/` | Kiểm tra môi trường và kết nối |
| `scripts/probes/` | Các phép dò parser/chunking chạy thủ công, không thuộc bộ test tự động |
| `scripts/evaluation/` | Script đánh giá và chạy thử |
| `docs/` | Tài liệu theo nhóm, xem bên dưới |

Môi trường `.venv`, `.env`, models, corpus và nội dung database được giữ ở vị trí
đang sử dụng. Chi tiết đợt sắp xếp trước được ghi trong
[file-organization-manifest.json](docs/project/file-organization-manifest.json).

## Tài liệu chính

- [Báo cáo tổng hợp dự án](docs/project/multi-agent-report-writer.md)
- [Tổng quan và lịch dự án](docs/project/project-scope-and-plan.txt)
- [Tiến độ ngày 03/11/2026](docs/project/early-project-progress.md)
- [Kiến trúc](docs/architecture/orchestration-and-tech-stack.md)
- [Hợp đồng state và báo cáo](docs/contracts/report-schema-and-state.md)
- [Agent Tool Interface](docs/contracts/agent-tool-interface.md)
- [DuckDB Facts Query Tool](docs/contracts/duckdb-facts-query.md)

Các nhóm tài liệu khác: `docs/datasets/`, `docs/evaluation/`, `docs/audits/`,
`docs/decisions/`. Ví dụ state JSON nằm trong `docs/examples/`.

## Chạy từ thư mục gốc project

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests -q
.venv/Scripts/python.exe -m src.evaluation.facts_benchmark --help
.venv/Scripts/python.exe -m src.evaluation.planner_eval --help
.venv/Scripts/python.exe -m scripts.audits.verify_corpus_invariants
.venv/Scripts/python.exe -m scripts.diagnostics.test_env
```

Các helper script được nhóm lại nên lệnh `python -m scripts.<tên>` cũ đổi thành
`python -m scripts.<nhóm>.<tên>`. Các entry point `src.*` giữ nguyên.
Script maintenance/ingestion có thể ghi dữ liệu; đọc chức năng trước khi chạy.

`tests/` chỉ chứa kiểm thử tự động qua `unittest discover`; `scripts/` chứa
chương trình chạy thủ công để đánh giá, kiểm tra và bảo trì. Các file JSON trong
`data/processed_chunks*/` giữ dạng phẳng vì parser, indexing và benchmark đọc
trực tiếp bằng `glob("*.json")` tại thư mục gốc của từng snapshot.
