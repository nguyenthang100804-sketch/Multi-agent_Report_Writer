import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
"""Measure FPT fact rows removed by the empty-heading rule without changing files."""
from pathlib import Path
from dataclasses import asdict

import src.ingestion.document_parser as parser

paths = sorted(Path("data/raw_docs/top_100/FPT").rglob("*.txt"))
original = parser._is_empty_heading
for path in paths:
    current = parser.DocumentParser().parse_file(path)
    parser._is_empty_heading = lambda label, raw_current, raw_prior: False
    try:
        prior = parser.DocumentParser().parse_file(path)
    finally:
        parser._is_empty_heading = original
    from collections import Counter
    import json
    old_rows = Counter(json.dumps(asdict(f), ensure_ascii=False, sort_keys=True)
                       for f in prior.facts)
    new_rows = Counter(json.dumps(asdict(f), ensure_ascii=False, sort_keys=True)
                       for f in current.facts)
    removed = [json.loads(row) for row in (old_rows - new_rows).elements()]
    print(current.doc_id, len(prior.facts), len(current.facts),
          [(f["label"], f["raw_current"], f["raw_prior"]) for f in removed])
