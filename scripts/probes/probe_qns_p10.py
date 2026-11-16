import sys
sys.path.insert(0, ".")
import re
from pathlib import Path
from src.ingestion.document_parser import detect_heading_line, is_unit_line, fold_accents, expand_pipe_table_to_grid

pat_row = re.compile(r"^([\d\.\-\+\s]*[A-Za-zÀ-ỹ].*?)\s+(\d{1,3}[a-z]?)\s+((?:\(?[\d\.,-]+\)?\s*){1,4})$")

def test_split(seg_text):
    lines = seg_text.split("\n")
    items = []
    text_buf = []
    pipe_buf = []

    def flush_text():
        nonlocal text_buf
        joined = "\n".join(text_buf).strip()
        if joined:
            items.append(("text", joined))
        text_buf = []

    def flush_pipe():
        nonlocal pipe_buf
        if pipe_buf:
            grid_2d = expand_pipe_table_to_grid(pipe_buf)
            if grid_2d:
                items.append(("table", grid_2d))
        pipe_buf = []

    def has_table_ahead(start_idx):
        count = 0
        for k in range(start_idx, len(lines)):
            s = lines[k].strip()
            if not s:
                continue
            count += 1
            if detect_heading_line(s, has_form_code_nearby=True) is not None:
                return False
            if "|" in s:
                return True
            m = pat_row.match(s)
            if m and re.search(r"\d{3,}", m.group(3)):
                return True
            if count >= 2:
                break
        return False

    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        ln_strip = ln.strip()

        if "|" in ln_strip:
            flush_text()
            pipe_buf.append(ln_strip)
            i += 1
            continue

        if pipe_buf:
            if not ln_strip:
                if has_table_ahead(i + 1):
                    i += 1
                    continue
            else:
                row_m = pat_row.match(ln_strip)
                if row_m and re.search(r"\d{3,}", row_m.group(3)):
                    nums = row_m.group(3).strip().split()
                    pipe_buf.append(f"{row_m.group(1).strip()} | {row_m.group(2).strip()} | " + " | ".join(nums))
                    i += 1
                    continue
                if detect_heading_line(ln_strip, has_form_code_nearby=True) is None and not is_unit_line(fold_accents(ln_strip)):
                    if has_table_ahead(i + 1):
                        pipe_buf.append(f"| {ln_strip}")
                        i += 1
                        continue

            flush_pipe()

        text_buf.append(ln)
        i += 1

    flush_pipe()
    flush_text()
    return items

raw = Path("data/raw_docs/top_100/QNS/2025/QNS_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt").read_text(encoding="utf-8")
pages = re.split(r"\[P\.(\d+)\]", raw)
for i in range(1, len(pages), 2):
    pnum = int(pages[i])
    ptext = pages[i+1]
    if "BÁO CÁO LƯU CHUYÊN" in ptext:
        items = test_split(ptext)
        print(f"Page {pnum}: {len(items)} items")
        for it_type, payload in items:
            if it_type == "table":
                print(f"  [TABLE] {len(payload)} rows. Sample row 1: {payload[0]}, row 2: {payload[1]}")
            else:
                print(f"  [TEXT] {len(payload)} chars: {payload[:80]}...")
