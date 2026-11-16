"""Compare candidate parse to current JSON before replacing any corpus files."""
from collections import Counter
import hashlib
import json
from pathlib import Path

current = Path("data/processed_chunks")
candidate = Path("data/processed_chunks_candidate")
removed = []
added = []
hash_diffs = []
for path in sorted(candidate.glob("*.json")):
    if path.name.startswith("_"):
        continue
    old = json.loads((current / path.name).read_text(encoding="utf-8"))
    new = json.loads(path.read_text(encoding="utf-8"))
    old_facts = Counter(json.dumps(fact, ensure_ascii=False, sort_keys=True)
                        for fact in old["facts"])
    new_facts = Counter(json.dumps(fact, ensure_ascii=False, sort_keys=True)
                        for fact in new["facts"])
    removed.extend((old["doc_id"], json.loads(fact))
                   for fact in (old_facts - new_facts).elements())
    added.extend((new["doc_id"], json.loads(fact))
                 for fact in (new_facts - old_facts).elements())
    old_hash = {chunk["chunk_id"]: hashlib.sha256(
        chunk.get("embed_text", chunk.get("text", "")).encode()).hexdigest()
        for chunk in old["chunks"]}
    new_hash = {chunk["chunk_id"]: hashlib.sha256(
        chunk.get("embed_text", chunk.get("text", "")).encode()).hexdigest()
        for chunk in new["chunks"]}
    if old_hash != new_hash:
        hash_diffs.append(old["doc_id"])
print("removed", len(removed), "added", len(added), "chunk_hash_docs", hash_diffs)
for doc_id, fact in removed:
    print("REMOVED", doc_id, fact.get("report_type"), fact.get("code"),
          fact.get("label"), repr(fact.get("raw_current")), repr(fact.get("raw_prior")))
for doc_id, fact in added[:20]:
    print("ADDED", doc_id, fact.get("report_type"), fact.get("code"), fact.get("label"))
