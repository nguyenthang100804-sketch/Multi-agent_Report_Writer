import json
from pathlib import Path
from collections import Counter, defaultdict

def main():
    PROCESSED_DIR = Path("data/processed_chunks")
    
    # 1. Inspect duplicate codes (excluding None) across all files
    dups_real = defaultdict(list)
    for f in sorted(PROCESSED_DIR.glob("*.json")):
        if f.name.startswith("_"): continue
        with open(f, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        doc_id = d.get("doc_id", f.stem)
        counts = Counter()
        for fact in d.get("facts", []):
            code = fact.get("code")
            if not code: continue # skip None / empty
            rtype = fact.get("report_type")
            period = fact.get("period")
            item = fact.get("item_name")
            counts[(rtype, code, period)] += 1
            
        for k, v in counts.items():
            if v > 1:
                dups_real[doc_id].append((k, v))
                
    print(f"=== SỐ FILE CÓ MÃ CODE BỊ TRÙNG THỰC SỰ (code != None): {len(dups_real)} ===")
    for doc_id, dup_list in dups_real.items():
        print(f"  + {doc_id}: {dup_list}")

    # 2. Inspect NVB_2023_Hopnhat chunks
    print("\n=== NVB_2023_Hopnhat: Các chunk NOTES có unit != default_unit ===")
    with open(PROCESSED_DIR / "NVB_2023_Hopnhat.json", "r", encoding="utf-8") as fp:
        nvb = json.load(fp)
    def_u = nvb.get("default_unit")
    for c in nvb.get("chunks", []):
        if c.get("section") == "NOTES" and c.get("unit") != def_u:
            print(f"  + Chunk {c['chunk_id']} | unit='{c['unit']}' | header: {c.get('heading', '')}")
            first_lines = [l.strip() for l in c['text'].split('\n') if l.strip()][:3]
            print(f"    Lines: {first_lines}")

    # 3. Inspect ABB_2024_Hopnhat missing BALANCE_SHEET
    print("\n=== ABB_2024_Hopnhat: Vì sao không nhận diện BALANCE_SHEET? ===")
    with open(PROCESSED_DIR / "ABB_2024_Hopnhat.json", "r", encoding="utf-8") as fp:
        abb = json.load(fp)
    print("Report types in facts:", set(f.get("report_type") for f in abb.get("facts", [])))
    print("Chunks sections:", Counter(c.get("section") for c in abb.get("chunks", [])))
    # Check headings in raw doc
    raw_abb = Path("data/raw_docs/top_100/ABB/2024/ABB_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt")
    if raw_abb.exists():
        raw_text = raw_abb.read_text(encoding="utf-8")
        for line in raw_text.split("\n")[:200]:
            if any(k in line.lower() for k in ["báo cáo", "bảng cân đối", "tình hình tài chính"]):
                print("  Raw line:", line.strip())

    # 4. Inspect QNS_2025_Hopnhat missing CASH_FLOW
    print("\n=== QNS_2025_Hopnhat: Vì sao không nhận diện CASH_FLOW? ===")
    with open(PROCESSED_DIR / "QNS_2025_Hopnhat.json", "r", encoding="utf-8") as fp:
        qns = json.load(fp)
    print("Report types in facts:", set(f.get("report_type") for f in qns.get("facts", [])))
    print("Chunks sections:", Counter(c.get("section") for c in qns.get("chunks", [])))
    raw_qns = Path("data/raw_docs/top_100/QNS/2025/QNS_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt")
    if raw_qns.exists():
        raw_text = raw_qns.read_text(encoding="utf-8")
        for line in raw_text.split("\n"):
            if "lưu chuyển tiền tệ" in line.lower() or "luu chuyen" in line.lower():
                print("  Raw line:", line.strip())

if __name__ == "__main__":
    main()
