import sys
sys.path.insert(0, ".")
import re
from pathlib import Path
from src.ingestion.document_parser import (
    step1_read_and_split_pages, step2_clean_pages, step3_extract_blocks,
    step4_detect_structure, step5_extract_facts_and_verify,
    GridRow
)

pages, sha, stats = step1_read_and_split_pages(Path("data/raw_docs/top_100/QNS/2025/QNS_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt"), "QNS", 2025)
pages, stats = step2_clean_pages(pages, stats)
blocks = step3_extract_blocks(pages)

# Look for table with <= 2 rows followed by text block with accounting rows
pat_row = re.compile(r"^([\d\.\-\+\s]*[A-Za-zÀ-ỹ].*?)\s+(\d{1,3}[a-z]?)\s+((?:\(?[\d\.,-]+\)?\s*){1,4})$")

for i, b in enumerate(blocks):
    if b.block_type == "table" and len(b.grid) <= 2 and i + 1 < len(blocks) and blocks[i+1].block_type == "text":
        txt_blk = blocks[i+1]
        matching_rows = []
        lines = txt_blk.text.split("\n")
        num_cols = b.num_cols
        
        extracted_grid_rows = []
        for l in lines:
            l_s = l.strip()
            if not l_s: continue
            m = pat_row.match(l_s)
            if m and re.search(r"\d{3,}", m.group(3)):
                item = m.group(1).strip()
                code = m.group(2).strip()
                nums = m.group(3).strip().split()
                row = [item, code] + nums
                if len(row) < num_cols:
                    row += [""] * (num_cols - len(row))
                elif len(row) > num_cols:
                    row = row[:num_cols]
                extracted_grid_rows.append(GridRow(cells=row, physical_page=txt_blk.physical_page_start, printed_page=txt_blk.printed_pages[0] if txt_blk.printed_pages else None))
            elif re.match(r"^[I|V|X\d\.\-\s]+[A-Za-zÀ-ỹ]", l_s):
                row = [l_s] + [""] * (num_cols - 1)
                extracted_grid_rows.append(GridRow(cells=row, physical_page=txt_blk.physical_page_start, printed_page=txt_blk.printed_pages[0] if txt_blk.printed_pages else None))
                
        if len(extracted_grid_rows) >= 5:
            print(f"Found orphaned table rows after {b.block_id}: {len(extracted_grid_rows)} rows!")
            b.grid.extend(extracted_grid_rows)
            # update txt_blk
            txt_blk.text = ""

# Now run step 4 & step 5
blocks = [b for b in blocks if b.block_type != "text" or b.text]
blocks, default_unit, scope = step4_detect_structure(blocks, "QNS_2025_Hopnhat.txt")
facts, suspect_cells, mode, checks = step5_extract_facts_and_verify(blocks)

print("Report types in facts:", set(f.report_type for f in facts))
cf_facts = [f for f in facts if f.report_type == "CASH_FLOW"]
print(f"Total CASH_FLOW facts: {len(cf_facts)}")
for f in cf_facts[:5]:
    print(f"  CF fact: {f.item_name} | code={f.code} | value={f.value}")
