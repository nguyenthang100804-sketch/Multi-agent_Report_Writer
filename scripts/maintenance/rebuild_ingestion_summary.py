"""Rebuild the corpus-wide summary after parsing a subset of documents."""
import json
from pathlib import Path

root = Path("data/processed_chunks")
auto = []
manual = []
for path in sorted(root.glob("*.json")):
    if path.name.startswith("_"):
        continue
    doc = json.loads(path.read_text(encoding="utf-8"))
    quality = doc["quality"]
    if quality["gating_status"] == "AUTO_INDEX":
        auto.append(doc["doc_id"])
    else:
        manual.append({
            "doc_id": doc["doc_id"], "source_file": doc["source_file"],
            "suspect_cells_count": quality["suspect_cells_count"],
            "identity_checks_passed": quality["identity_checks_passed"],
            "identity_checks_total": quality["identity_checks_total"],
            "gating_reasons": quality["gating_reasons"],
        })
summary = {"total_documents": len(auto) + len(manual),
           "auto_index_count": len(auto), "manual_review_queue_count": len(manual),
           "auto_index_docs": auto, "manual_review_queue_docs": manual}
(root / "_ingestion_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(len(auto), len(manual))
