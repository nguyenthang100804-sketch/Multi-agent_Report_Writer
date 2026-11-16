import os
from pathlib import Path

def load_env_file():
    p = Path(".env")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

def test_qdrant_cloud_connection():
    load_env_file()
    url = os.getenv("QDRANT_ENDPOINT") or os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    
    print(f"Connecting to Qdrant Cloud at: {url} ...")
    from qdrant_client import QdrantClient
    client = QdrantClient(url=url, api_key=api_key)
    collections = client.get_collections()
    print("Connection SUCCESSFUL!")
    print(f"Existing collections on cloud: {[c.name for c in collections.collections]}")

if __name__ == "__main__":
    test_qdrant_cloud_connection()
