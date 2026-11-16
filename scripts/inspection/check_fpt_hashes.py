"""Compare FPT chunk content hashes across parsed JSON, Parquet and Qdrant."""
import hashlib
import json
from pathlib import Path

import pandas as pd
from qdrant_client import QdrantClient, models

client = QdrantClient(path="data/qdrant_local")
for year in range(2022, 2026):
    doc_id = f"FPT_{year}_Hopnhat"
    doc = json.loads(Path(f"data/processed_chunks/{doc_id}.json").read_text(encoding="utf-8"))
    current = {chunk["chunk_id"]: hashlib.sha256(
        chunk.get("embed_text", chunk.get("text", "")).encode("utf-8")).hexdigest()
        for chunk in doc["chunks"]}
    frame = pd.read_parquet(f"data/vector_cache/bge_m3/{doc_id}.parquet")
    print(doc_id, "parquet columns", list(frame.columns))
    cached = dict(zip(frame["chunk_id"], frame["content_hash"]))
    points = []
    offset = None
    while True:
        batch, offset = client.scroll("vnfin_v1_bge_m3_v1",
            scroll_filter=models.Filter(must=[models.FieldCondition(
                key="doc_id", match=models.MatchValue(value=doc_id))]),
            limit=256, offset=offset, with_payload=True, with_vectors=False)
        points.extend(batch)
        if offset is None:
            break
    indexed = {point.payload["chunk_id"]: point.payload["content_hash"] for point in points}
    print(doc_id, "chunks", len(current), "parquet_diff",
          sum(current.get(key) != value for key, value in cached.items()),
          "qdrant_diff", sum(current.get(key) != value for key, value in indexed.items()),
          "id_match", set(current) == set(cached) == set(indexed))
client.close()
