# DuckDB Facts Query Tool

> Cập nhật 09/11/2026: DuckDB đang dùng theo `configs/active_corpus.json` chứa 18.540 fact. Các số 38.425/38.467 trong phần mô tả lịch sử thuộc snapshot trước khi loại các bảng thuyết minh bị nhận nhầm là báo cáo chính. Xem [kiểm tra tác động](../evaluation/notes-classification-audit.md).

Build or refresh the persistent snapshot from the project root:

```powershell
.venv/Scripts/python.exe -m src.storage.duckdb_manager --ingest
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Default database: `data/financial_facts.duckdb`. Paths default to the project root,
independent of the caller's current directory. Ingestion replaces the complete
snapshot in one transaction; repeated runs do not append duplicates. All source
rows, including suspect/uncoded facts, are retained. The composite index covers
`(ticker, fiscal_year, report_type, code)`.

```python
from src.storage.duckdb_manager import get_fact, get_time_series

revenue = get_fact("FPT", "10", 2024, report_type="INCOME_STATEMENT")
series = get_time_series("FPT", "10", 2022, 2025,
                         report_type="INCOME_STATEMENT")
```

Both tools return JSON-serializable lists of source rows, including `value`
(alias of `current_year`), `raw_value`, `unit`, `prior_year`, `raw_prior`,
`doc_id`, `source_file`, `physical_page` (PDF page), `printed_page`,
`citation_tag`, `suspect`, and `chunk_ids`. Source JSON path, hash and parser
version are retained for auditing. `chunk_ids` are candidates matched by section
and physical page, not exact row-level evidence matches. `source_file` points to
the extracted text recorded by the parser; no original PDF path is invented.

Rules for agents:

- Codes must be strings: `"01"` differs from `"1"`.
- Specify `report_type` because codes can overlap between statements. An
  ambiguous query raises `ValueError` rather than choosing a statement.
- Default scope is `consolidated`; use `scope="separate"` for separate reports.
  Some documents use `scope="general"`; select that scope explicitly.
  Passing `scope=None` raises an error if results span multiple scopes.
- Suspect rows are excluded by default; use `include_suspect=True` for auditing.
- No evidence returns `[]`. Missing years are omitted, never synthesized as zero.
  Compare returned years with the requested range before describing a trend.
- Multiple matches remain visible; verify conflicts before selecting a value.
- Units/currencies are preserved. Normalize compatible units before arithmetic.
- `value` always refers to the fiscal year's current period, not a restated
  comparison from a later report. `prior_year` remains available separately.
- For uncoded statements (e.g. banks), use an exact label:
  `get_fact("ABB", None, 2024, label="...", report_type="BALANCE_SHEET")`.

These are plain Python tools ready for a future agent/router integration; they
do not modify the existing text-retrieval benchmark or implement an LLM router.
The existing baseline remains unchanged. A combined facts/text benchmark is a
separate next step.

## Initial corpus verification

On 2026-11-02, ingestion loaded 38,467 facts from 141 documents / 35 tickers.
Every stored source fact field was compared against its original JSON and matched.
The composite index was inspected in `duckdb_indexes()`. A sample FPT revenue
query returned all fiscal years 2022–2025 with physical/printed page citations.
Numeric columns preserve the parser's floating-point values; raw cell strings
are retained for exact source verification.

Connection and parameter binding follow the official
[DuckDB Python DB API](https://duckdb.org/docs/2.0/clients/python/dbapi).
