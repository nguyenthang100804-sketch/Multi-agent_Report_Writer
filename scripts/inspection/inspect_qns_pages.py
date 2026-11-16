import re
from pathlib import Path

raw = Path("data/raw_docs/top_100/QNS/2025/QNS_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt").read_text(encoding="utf-8")
pages = re.split(r"\[P\.(\d+)\]", raw)
for i in range(1, len(pages), 2):
    pnum = int(pages[i])
    ptext = pages[i+1]
    if "BÁO CÁO LƯU CHUYÊN" in ptext or "Mẫu số B 03" in ptext or "Mẫu số B03" in ptext:
        print(f"Page {pnum}: has <table>: {'<table' in ptext.lower()}, has pipe: {'|' in ptext}")
        lines = [l.strip() for l in ptext.split('\n') if l.strip()]
        for l in lines[:10]:
            print("  ", l)

