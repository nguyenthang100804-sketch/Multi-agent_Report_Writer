"""Benchmark DuckDB Facts Engine against Golden Evaluation Dataset (Type A & Type C).

Run from project root:
    .venv/Scripts/python.exe -m src.evaluation.facts_benchmark
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import time
from typing import Any

from src.storage.duckdb_manager import DEFAULT_DB_PATH, DuckDBManager

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = ROOT_DIR / "configs" / "golden_evaluation_dataset.json"
DEFAULT_OUTPUT_PATH = ROOT_DIR / "evaluation" / "benchmarks" / "facts_benchmark_report.json"

METRIC_NAME_TO_CODE: dict[str, tuple[str, str]] = {
    "Doanh thu thuần": ("10", "INCOME_STATEMENT"),
    "Doanh thu thuần về bán hàng và cung cấp dịch vụ": ("10", "INCOME_STATEMENT"),
}

FALLBACK_SCOPES = ("consolidated", "general", "separate")


def _lookup_single_year_with_fallback(
    manager: DuckDBManager,
    ticker: str,
    code: str,
    fiscal_year: int,
    report_type: str | None,
    preferred_scope: str | None,
) -> list[dict[str, Any]]:
    """Query a single year's fact, falling back across scopes if the preferred scope has no report."""
    scopes_to_try = [preferred_scope] if preferred_scope else []
    for s in FALLBACK_SCOPES:
        if s not in scopes_to_try:
            scopes_to_try.append(s)

    for scope in scopes_to_try:
        rows = manager.get_fact(
            ticker,
            code,
            fiscal_year,
            report_type=report_type,
            scope=scope,
        )
        if rows:
            return rows
    return []


def evaluate_type_a(
    manager: DuckDBManager,
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate single-year accounting fact questions (Type A)."""
    detailed: list[dict[str, Any]] = []
    latencies_ms: list[float] = []

    exact_value_matches = 0
    raw_value_matches = 0
    page_matches = 0
    chunk_matches = 0

    for q in questions:
        qid = q["question_id"]
        ticker = q["ticker"]
        year = int(q["fiscal_year"])
        code = str(q["code"])
        report_type = q.get("report_type")
        scope = q.get("scope", "consolidated")
        gt_val = q.get("ground_truth_value")
        gt_raw = q.get("raw_value")
        gold_pages = set(q.get("gold_pages", []))
        gold_chunks = set(q.get("gold_chunk_ids", []))

        t0 = time.perf_counter()
        rows = _lookup_single_year_with_fallback(
            manager, ticker, code, year, report_type, scope
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        found = len(rows) > 0
        retrieved_val = rows[0]["value"] if found else None
        retrieved_raw = rows[0]["raw_value"] if found else None
        retrieved_page = rows[0]["physical_page"] if found else None
        retrieved_printed_page = rows[0]["printed_page"] if found else None
        citation_tag = rows[0]["citation_tag"] if found else None
        retrieved_chunks = rows[0]["chunk_ids"] if found else []

        is_val_match = bool(
            found
            and retrieved_val is not None
            and gt_val is not None
            and (
                retrieved_val == gt_val
                or (gt_val != 0 and abs(retrieved_val - gt_val) / abs(gt_val) < 1e-6)
            )
        )
        is_raw_match = bool(found and retrieved_raw == gt_raw)
        is_page_match = bool(found and retrieved_page in gold_pages)
        is_chunk_match = bool(found and gold_chunks.intersection(retrieved_chunks))

        if is_val_match:
            exact_value_matches += 1
        if is_raw_match:
            raw_value_matches += 1
        if is_page_match:
            page_matches += 1
        if is_chunk_match:
            chunk_matches += 1

        detailed.append({
            "question_id": qid,
            "split": q.get("split"),
            "question": q["question"],
            "ticker": ticker,
            "fiscal_year": year,
            "scope_requested": scope,
            "scope_resolved": rows[0]["scope"] if found else None,
            "report_type": report_type,
            "code": code,
            "metric_name": q.get("metric_name"),
            "ground_truth_value": gt_val,
            "retrieved_value": retrieved_val,
            "ground_truth_raw": gt_raw,
            "retrieved_raw": retrieved_raw,
            "unit": rows[0]["unit"] if found else None,
            "gold_pages": sorted(gold_pages),
            "retrieved_physical_page": retrieved_page,
            "retrieved_printed_page": retrieved_printed_page,
            "citation_tag": citation_tag,
            "exact_value_match": is_val_match,
            "raw_value_match": is_raw_match,
            "page_citation_match": is_page_match,
            "chunk_overlap_match": is_chunk_match,
            "latency_ms": round(elapsed_ms, 4),
        })

    total = len(questions)
    return {
        "summary": _summarize_type_a(detailed, latencies_ms),
        "by_split": {
            split: _summarize_type_a(
                [d for d in detailed if d["split"] == split],
                [d["latency_ms"] for d in detailed if d["split"] == split],
            )
            for split in ("dev", "test")
        },
        "total_questions": total,
        "detailed_results": detailed,
    }


def _summarize_type_a(
    items: list[dict[str, Any]], latencies_ms: list[float]
) -> dict[str, Any]:
    n = len(items)
    if n == 0:
        return {}
    val_matches = sum(1 for x in items if x["exact_value_match"])
    raw_matches = sum(1 for x in items if x["raw_value_match"])
    page_matches = sum(1 for x in items if x["page_citation_match"])
    chunk_matches = sum(1 for x in items if x["chunk_overlap_match"])
    return {
        "count": n,
        "exact_value_matches": val_matches,
        "exact_match_rate": round(val_matches / n, 4),
        "raw_value_matches": raw_matches,
        "raw_match_rate": round(raw_matches / n, 4),
        "page_citation_matches": page_matches,
        "page_citation_rate": round(page_matches / n, 4),
        "chunk_overlap_matches": chunk_matches,
        "chunk_overlap_rate": round(chunk_matches / n, 4),
        "latency_ms": {
            "mean": round(statistics.mean(latencies_ms), 4),
            "median": round(statistics.median(latencies_ms), 4),
            "min": round(min(latencies_ms), 4),
            "max": round(max(latencies_ms), 4),
        },
    }


def evaluate_type_c(
    manager: DuckDBManager,
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate multi-year time-series questions (Type C)."""
    detailed: list[dict[str, Any]] = []
    latencies_ms: list[float] = []

    for q in questions:
        qid = q["question_id"]
        ticker = q["ticker"]
        years_covered = [int(y) for y in q["years_covered"]]
        start_year, end_year = min(years_covered), max(years_covered)
        scope = q.get("scope", "consolidated")
        metric_name = q.get("metric_name", "Doanh thu thuần")
        code, report_type = METRIC_NAME_TO_CODE.get(
            metric_name, (str(q.get("code") or "10"), q.get("report_type") or "INCOME_STATEMENT")
        )
        gt_dict: dict[str, dict[str, Any]] = q["ground_truth_values"]

        t0 = time.perf_counter()
        rows = manager.get_time_series(
            ticker,
            code,
            start_year,
            end_year,
            report_type=report_type,
            scope=scope,
        )
        by_year: dict[int, dict[str, Any]] = {}
        for r in rows:
            by_year.setdefault(int(r["fiscal_year"]), r)

        # Fallback per missing year when a company switched reporting scope (e.g. separate/general)
        for y in years_covered:
            if y not in by_year:
                fallback_rows = _lookup_single_year_with_fallback(
                    manager, ticker, code, y, report_type, scope
                )
                if fallback_rows:
                    by_year[y] = fallback_rows[0]

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        year_comparisons: dict[str, dict[str, Any]] = {}
        matched_years = 0
        for y_str, gt_info in gt_dict.items():
            y = int(y_str)
            row = by_year.get(y)
            got_val = row["value"] if row else None
            exp_val = gt_info["value"]
            is_match = bool(
                row is not None
                and got_val is not None
                and (
                    got_val == exp_val
                    or (exp_val != 0 and abs(got_val - exp_val) / abs(exp_val) < 1e-6)
                )
            )
            if is_match:
                matched_years += 1
            year_comparisons[y_str] = {
                "expected_value": exp_val,
                "retrieved_value": got_val,
                "expected_raw": gt_info.get("raw"),
                "retrieved_raw": row["raw_value"] if row else None,
                "unit": row["unit"] if row else None,
                "scope_resolved": row["scope"] if row else None,
                "physical_page": row["physical_page"] if row else None,
                "printed_page": row["printed_page"] if row else None,
                "citation_tag": row["citation_tag"] if row else None,
                "exact_match": is_match,
            }

        full_series_match = matched_years == len(gt_dict)
        detailed.append({
            "question_id": qid,
            "split": q.get("split"),
            "question": q["question"],
            "ticker": ticker,
            "metric_name": metric_name,
            "code": code,
            "report_type": report_type,
            "years_expected": len(gt_dict),
            "years_matched": matched_years,
            "full_series_exact_match": full_series_match,
            "latency_ms": round(elapsed_ms, 4),
            "yearly_results": year_comparisons,
        })

    return {
        "summary": _summarize_type_c(detailed, latencies_ms),
        "by_split": {
            split: _summarize_type_c(
                [d for d in detailed if d["split"] == split],
                [d["latency_ms"] for d in detailed if d["split"] == split],
            )
            for split in ("dev", "test")
        },
        "total_questions": len(questions),
        "detailed_results": detailed,
    }


def _summarize_type_c(
    items: list[dict[str, Any]], latencies_ms: list[float]
) -> dict[str, Any]:
    n = len(items)
    if n == 0:
        return {}
    full_matches = sum(1 for x in items if x["full_series_exact_match"])
    total_years = sum(x["years_expected"] for x in items)
    matched_years = sum(x["years_matched"] for x in items)
    return {
        "count": n,
        "full_series_matches": full_matches,
        "full_series_match_rate": round(full_matches / n, 4),
        "total_year_points": total_years,
        "matched_year_points": matched_years,
        "year_point_match_rate": round(matched_years / total_years, 4) if total_years else 0.0,
        "latency_ms": {
            "mean": round(statistics.mean(latencies_ms), 4),
            "median": round(statistics.median(latencies_ms), 4),
            "min": round(min(latencies_ms), 4),
            "max": round(max(latencies_ms), 4),
        },
    }


def run_facts_benchmark(
    dataset_path: Path = DEFAULT_DATASET_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> dict[str, Any]:
    """Run the complete DuckDB facts benchmark and persist results to JSON."""
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    questions = dataset["questions"]
    type_a_qs = [q for q in questions if q.get("type") == "A"]
    type_c_qs = [q for q in questions if q.get("type") == "C"]

    with DuckDBManager(db_path=db_path, read_only=True) as manager:
        # Warm-up connection / OS page cache once
        manager.connection.execute("SELECT count(*) FROM financial_facts").fetchall()

        type_a_report = evaluate_type_a(manager, type_a_qs)
        type_c_report = evaluate_type_c(manager, type_c_qs)

    report = {
        "benchmark_name": "DuckDB Financial Facts Engine Benchmark",
        "benchmark_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "database_path": str(db_path.relative_to(ROOT_DIR)) if db_path.is_relative_to(ROOT_DIR) else str(db_path),
        "dataset_path": str(dataset_path.relative_to(ROOT_DIR)) if dataset_path.is_relative_to(ROOT_DIR) else str(dataset_path),
        "dataset_version": dataset.get("version", "v2.0"),
        "type_A_single_year": type_a_report,
        "type_C_multi_year": type_c_report,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    report = run_facts_benchmark(args.dataset, args.db_path, args.output)
    a_sum = report["type_A_single_year"]["summary"]
    c_sum = report["type_C_multi_year"]["summary"]
    print(
        f"[Type A] Exact Match: {a_sum['exact_value_matches']}/{a_sum['count']} "
        f"({a_sum['exact_match_rate']*100:.2f}%) | "
        f"Page Match: {a_sum['page_citation_matches']}/{a_sum['count']} "
        f"({a_sum['page_citation_rate']*100:.2f}%) | "
        f"Mean Latency: {a_sum['latency_ms']['mean']:.2f} ms"
    )
    print(
        f"[Type C] Full Series Match: {c_sum['full_series_matches']}/{c_sum['count']} "
        f"({c_sum['full_series_match_rate']*100:.2f}%) | "
        f"Year Points: {c_sum['matched_year_points']}/{c_sum['total_year_points']} | "
        f"Mean Latency: {c_sum['latency_ms']['mean']:.2f} ms"
    )
    print(f"Saved report to: {args.output}")


if __name__ == "__main__":
    main()
