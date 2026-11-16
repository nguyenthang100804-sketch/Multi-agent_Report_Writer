"""One snapshot pointer for the JSON corpus, facts DB, and note index."""
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
ACTIVE_CORPUS = json.loads(
    (ROOT_DIR / "configs" / "active_corpus.json").read_text(encoding="utf-8"))


def active_path(key: str) -> Path:
    return ROOT_DIR / ACTIVE_CORPUS[key]
