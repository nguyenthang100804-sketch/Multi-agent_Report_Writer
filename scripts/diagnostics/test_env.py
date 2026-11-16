import os
from pathlib import Path

def check_env():
    env_vars = {}
    p = Path(".env")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip().strip('"').strip("'")
    
    endpoint = env_vars.get("QDRANT_ENDPOINT") or env_vars.get("QDRANT_URL")
    api_key = env_vars.get("QDRANT_API_KEY")
    
    print("Endpoint present:", bool(endpoint))
    print("API Key present:", bool(api_key))
    if endpoint:
        print("Endpoint URL:", endpoint)

if __name__ == "__main__":
    check_env()
