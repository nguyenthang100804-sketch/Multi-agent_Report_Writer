import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
"""Audit standard metric series for all tickers in the fact corpus."""
from collections import Counter

from src.agents.coverage import available_scopes
from src.agents.calculations import calculate_cagr, calculate_yoy
from src.agents.state import snapshot_version_for_db
from src.schemas.report_schema import TimeSeriesTask, record_tool_result
from src.storage.duckdb_manager import DuckDBManager
from src.tools.agent_tools import AgentTools
from src.tools.metric_resolver import METRICS


def main():
    with DuckDBManager() as db:
        tickers = [row[0] for row in db.connection.execute(
            "SELECT DISTINCT ticker FROM financial_facts ORDER BY ticker").fetchall()]
    snapshot = snapshot_version_for_db(AgentTools().db_path)
    totals = Counter()
    print("# Khảo sát 12 chỉ tiêu chuẩn trên 35 ticker\n")
    print("Nguồn: DuckDB hiện có; mỗi ticker dùng scope có nhiều chuỗi safe nhất "
          "(ưu tiên consolidated khi hòa); chạy lại bằng "
          "`\\.venv\\Scripts\\python.exe -m scripts.audits.audit_metric_safety`. "
          "Cột YoY truy vấn riêng cặp 2024–2025; CAGR dùng đủ 2022–2025. "
          "Các ticker ngân hàng vẫn nằm trong mẫu số 420 dù nhiều mã chuẩn không áp dụng.\n")
    print("| Ticker | Scope | Safe / 12 | YoY 2024→2025 / 12 | CAGR 2022→2025 / 12 |")
    print("|---|---|---:|---:|---:|")
    with AgentTools() as tools:
        for ticker in tickers:
            candidates = []
            for scope in available_scopes(ticker, tools.db_path):
                counts = Counter()
                for name, code, report_type, _ in METRICS:
                    result = tools.execute("query_time_series_tool", {
                    "ticker": ticker, "scope": scope, "item_code": code,
                    "report_type": report_type, "start_year": 2022, "end_year": 2025,
                })
                    task = TimeSeriesTask(task_id="audit", item_code=code,
                    report_type=report_type, start_year=2022, end_year=2025)
                    research, evidence = record_tool_result(task, result, snapshot)
                    counts["safe"] += result.safe_for_calculation
                    pair_tool = tools.execute("query_time_series_tool", {
                    "ticker": ticker, "scope": scope, "item_code": code,
                    "report_type": report_type, "start_year": 2024, "end_year": 2025,
                })
                    pair_task = TimeSeriesTask(task_id="audit_pair", item_code=code,
                    report_type=report_type, start_year=2024, end_year=2025)
                    pair, pair_evidence = record_tool_result(pair_task, pair_tool, snapshot)
                    if pair.evidence_ids:
                        counts["yoy"] += calculate_yoy("audit:yoy", pair, pair_evidence,
                                                    2024, 2025).status == "ok"
                    if research.evidence_ids:
                        counts["cagr"] += calculate_cagr("audit:cagr", research, evidence,
                                                      2022, 2025).status == "ok"
                candidates.append((counts["safe"], scope == "consolidated", scope, counts))
            _, _, scope, counts = max(candidates)
            totals.update(counts)
            print(f"| {ticker} | {scope} | {counts['safe']}/12 | {counts['yoy']}/12 | "
                  f"{counts['cagr']}/12 |")
    n = len(tickers) * len(METRICS)
    print(f"| **Toàn corpus** | | **{totals['safe']}/{n}** | "
          f"**{totals['yoy']}/{n}** | **{totals['cagr']}/{n}** |")


if __name__ == "__main__":
    main()
