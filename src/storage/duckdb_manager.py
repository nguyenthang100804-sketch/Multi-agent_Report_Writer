"""Load parsed financial facts and expose citation-preserving agent tools.

Build the database with ``python -m src.storage.duckdb_manager --ingest``.
Queries return every matching source row, never an arbitrary deduplicated value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from .active_corpus import active_path

DEFAULT_DB_PATH = active_path("facts_db")
DEFAULT_INPUT_DIR = active_path("processed_dir")

SCHEMA = """
CREATE TABLE IF NOT EXISTS financial_facts (
    doc_id VARCHAR NOT NULL, fact_index INTEGER NOT NULL,
    ticker VARCHAR NOT NULL, fiscal_year INTEGER NOT NULL,
    scope VARCHAR NOT NULL, source_file VARCHAR NOT NULL,
    source_json VARCHAR NOT NULL, source_sha256 VARCHAR, parser_version VARCHAR,
    report_type VARCHAR NOT NULL, code VARCHAR, stt VARCHAR, label VARCHAR,
    note VARCHAR, current_year DOUBLE, prior_year DOUBLE,
    raw_current VARCHAR, raw_prior VARCHAR, suspect BOOLEAN,
    suspect_reason VARCHAR, unit VARCHAR, physical_page INTEGER,
    printed_page VARCHAR, citation_tag VARCHAR, chunk_ids VARCHAR[],
    PRIMARY KEY (doc_id, fact_index)
);
CREATE INDEX IF NOT EXISTS idx_facts_lookup
    ON financial_facts (ticker, fiscal_year, report_type, code);
CREATE TABLE IF NOT EXISTS corpus_metadata (
    snapshot_id VARCHAR NOT NULL
);
"""


def _logical_snapshot_id(connection: duckdb.DuckDBPyConnection) -> str:
    """Hash stored rows, not DuckDB file bytes or checkpoint layout."""
    digest = hashlib.sha256()
    rows = connection.execute(
        "SELECT * EXCLUDE (source_json) FROM financial_facts ORDER BY doc_id, fact_index"
    ).fetchall()
    for row in rows:
        digest.update(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


class DuckDBManager:
    """Persistent facts store; use as a context manager to close connections."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH,
                 read_only: bool = True) -> None:
        self.db_path = Path(db_path)
        if not read_only:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(str(self.db_path), read_only=read_only)
        if not read_only:
            self.connection.execute(SCHEMA)

    def __enter__(self) -> DuckDBManager:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Release the database connection."""
        self.connection.close()

    def ingest(self, input_dir: str | Path = DEFAULT_INPUT_DIR) -> dict[str, int]:
        """Atomically replace the corpus snapshot; repeated loads do not duplicate facts.

        All facts, including suspect rows and rows without item codes, are retained.
        An empty input or malformed document fails before replacing stored data.
        """
        files = sorted(f for f in Path(input_dir).glob("*.json")
                       if not f.name.startswith("_"))
        if not files:
            raise ValueError(f"No document JSON files found in {input_dir}")
        rows: list[dict[str, Any]] = []
        doc_ids: set[str] = set()
        for path in files:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc["doc_id"] in doc_ids:
                raise ValueError(f"Duplicate doc_id: {doc['doc_id']}")
            doc_ids.add(doc["doc_id"])
            chunks_by_page: dict[tuple[str, int], list[str]] = {}
            for chunk in doc["chunks"]:
                for page in chunk.get("physical_pages", []):
                    chunks_by_page.setdefault((chunk["section"], page), []).append(chunk["chunk_id"])
            for index, fact in enumerate(doc["facts"]):
                page = fact["physical_page"]
                rows.append({
                    "doc_id": doc["doc_id"], "fact_index": index,
                    "ticker": doc["ticker"].upper(), "fiscal_year": doc["fiscal_year"],
                    "scope": doc["scope"], "source_file": doc["source_file"],
                    "source_json": str(path.resolve()), "source_sha256": doc.get("sha256"),
                    "parser_version": doc.get("parser_version"),
                    **{key: fact.get(key) for key in (
                        "report_type", "code", "stt", "label", "note", "current_year",
                        "prior_year", "raw_current", "raw_prior", "suspect",
                        "suspect_reason", "unit", "physical_page", "printed_page")},
                    "citation_tag": f"[Doc_{doc['doc_id']}, p.{page}]",
                    "chunk_ids": chunks_by_page.get((fact["report_type"], page), []),
                })
        if not rows:
            raise ValueError("Input corpus contains no facts")
        frame = pd.DataFrame(rows)
        self.connection.register("incoming_facts", frame)
        try:
            self.connection.execute("BEGIN TRANSACTION")
            self.connection.execute("DELETE FROM financial_facts")
            self.connection.execute("INSERT INTO financial_facts BY NAME SELECT * FROM incoming_facts")
            count = self.connection.execute("SELECT count(*) FROM financial_facts").fetchall()[0][0]
            if count != len(rows):
                raise RuntimeError("Fact count reconciliation failed")
            snapshot_id = _logical_snapshot_id(self.connection)
            self.connection.execute("DELETE FROM corpus_metadata")
            self.connection.execute("INSERT INTO corpus_metadata VALUES (?)", [snapshot_id])
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        finally:
            self.connection.unregister("incoming_facts")
        return {"documents": len(files), "facts": count}

    def get_snapshot_id(self) -> str:
        """Read ingestion metadata; support older read-only DBs via logical-row hash."""
        exists = self.connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'corpus_metadata'"
        ).fetchall()[0][0]
        if exists:
            rows = self.connection.execute("SELECT snapshot_id FROM corpus_metadata LIMIT 1").fetchall()
            if rows:
                return rows[0][0]
        return _logical_snapshot_id(self.connection)

    def _lookup(self, ticker: str, item_code: str | None, start_year: int,
                end_year: int, report_type: str | None, scope: str | None,
                include_suspect: bool, label: str | None = None) -> list[dict[str, Any]]:
        if start_year > end_year:
            raise ValueError("start_year must not exceed end_year")
        if item_code is None and label is None:
            raise ValueError("Supply item_code or an exact label for uncoded facts")
        clauses = ["ticker = ?", "fiscal_year BETWEEN ? AND ?"]
        params: list[Any] = [ticker.strip().upper(), start_year, end_year]
        for column, value in (("code", item_code), ("report_type", report_type),
                              ("scope", scope), ("label", label)):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(str(value))
        if not include_suspect:
            clauses.append("suspect IS NOT TRUE")
        result = self.connection.execute(
            "SELECT *, current_year AS value, raw_current AS raw_value "
            "FROM financial_facts WHERE " + " AND ".join(clauses)
            + " ORDER BY fiscal_year, doc_id, fact_index", params)
        columns = [column[0] for column in result.description]
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        if report_type is None and len({r["report_type"] for r in rows}) > 1:
            raise ValueError("Ambiguous item code/label: supply report_type")
        if scope is None and len({r["scope"] for r in rows}) > 1:
            raise ValueError("Ambiguous reporting scope: supply scope")
        return rows

    def get_fact(self, ticker: str, item_code: str | None, fiscal_year: int,
                 *, report_type: str | None = None, scope: str | None = "consolidated",
                 include_suspect: bool = False, label: str | None = None) -> list[dict[str, Any]]:
        """Return matching current-period facts with PDF/printed pages and citations.

        Empty results mean missing evidence. Multiple rows remain visible to the
        caller for conflict checking. ``chunk_ids`` are page/section candidates,
        not verified row-level matches. Codes are strings (preserve leading zeros).
        """
        return self._lookup(ticker, item_code, fiscal_year, fiscal_year,
                            report_type, scope, include_suspect, label)

    def get_time_series(self, ticker: str, item_code: str, start_year: int,
                        end_year: int, *, report_type: str | None = None,
                        scope: str | None = "consolidated",
                        include_suspect: bool = False) -> list[dict[str, Any]]:
        """Return current-period facts ordered by fiscal year, with original units.

        Missing years are omitted, never filled with zero or prior-period values.
        No aggregation or conversion across currencies/units is performed.
        """
        return self._lookup(ticker, item_code, start_year, end_year,
                            report_type, scope, include_suspect)


def get_fact(ticker: str, item_code: str | None, fiscal_year: int,
             *, db_path: str | Path = DEFAULT_DB_PATH, **filters: Any) -> list[dict[str, Any]]:
    """Agent-callable single-year lookup using a short-lived read-only connection."""
    with DuckDBManager(db_path) as manager:
        return manager.get_fact(ticker, item_code, fiscal_year, **filters)


def get_time_series(ticker: str, item_code: str, start_year: int, end_year: int,
                    *, db_path: str | Path = DEFAULT_DB_PATH,
                    **filters: Any) -> list[dict[str, Any]]:
    """Agent-callable multi-year lookup using a short-lived read-only connection."""
    with DuckDBManager(db_path) as manager:
        return manager.get_time_series(ticker, item_code, start_year, end_year, **filters)


def main() -> None:
    """CLI for building the persistent facts database."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--ingest", action="store_true", required=True)
    args = parser.parse_args()
    with DuckDBManager(args.db_path, read_only=False) as manager:
        print(json.dumps(manager.ingest(args.input_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
