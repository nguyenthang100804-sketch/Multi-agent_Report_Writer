from pathlib import Path
import re

raw = Path("data/raw_docs/top_100/QNS/2025/QNS_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt").read_text(encoding="utf-8")
parts = re.split(r"=====\s*PAGE\s*(\d+)\s*=====", raw)

for i in range(1, len(parts), 2):
    pnum = int(parts[i])
    ptext = parts[i+1]
    if "BÁO CÁO LƯU CHUYÊN" in ptext or "báo cáo lưu chuyển" in ptext.lower():
        print(f"Page {pnum} contains Cash Flow heading!")
        print("Has <table>?:", "<table" in ptext.lower())
        print("Has '|'?:", "|" in ptext)
        print("Sample 300 chars:")
        print(ptext[:400])
        print("="*60)
