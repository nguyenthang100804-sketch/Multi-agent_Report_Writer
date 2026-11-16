import sys
sys.path.insert(0, ".")
from pathlib import Path
from src.ingestion.document_parser import step1_read_and_split_pages, step2_clean_pages, step3_extract_blocks

pages, sha, stats = step1_read_and_split_pages(Path("data/raw_docs/top_100/QNS/2025/QNS_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt"), "QNS", 2025)
pages, stats = step2_clean_pages(pages, stats)
for p in pages:
    if "BÁO CÁO LƯU CHUYÊN" in p.cleaned_text:
        print(f"Page {p.physical_page}: has_html_table={'<table' in p.cleaned_text.lower()}, has_pipe={'|' in p.cleaned_text}")
        blocks = step3_extract_blocks([p])
        print(f"Blocks extracted: {len(blocks)}")
        for b in blocks:
            print(f"  {b.block_id} | type={b.block_type} | rows={len(b.grid) if b.grid else 0} | text={b.text[:50] if b.text else ''}")
