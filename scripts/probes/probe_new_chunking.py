import json
import re
import sys
from pathlib import Path

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from transformers import AutoTokenizer

from src.ingestion.document_parser import (
    step1_read_and_split_pages,
    step2_clean_pages,
    step3_extract_blocks,
    step4_detect_structure,
    _is_header_row_cells,
    DEFAULT_BACKUP_DIR
)
from src.schemas.document_schema import Block, GridRow, ChunkItem

def generate_table_embed_text(context_prefix: str, header_lines: list, slice_rows: list) -> str:
    """
    Sinh văn bản tối ưu cho embedding từ bảng:
    Giữ lại context_prefix, tiêu đề cột và nhãn/mã các khoản mục,
    loại bỏ các chuỗi số tiền lớn để không làm loãng vector.
    """
    lines = [context_prefix]
    
    # Xác định các cột là chữ/nhãn (Mã số, STT, Chỉ tiêu, Thuyết minh)
    text_col_indices = []
    if header_lines:
        first_hdr = header_lines[0]
        hdr_cells = [c.strip() for c in first_hdr.split("|")]
        for idx, col_name in enumerate(hdr_cells):
            folded = col_name.lower()
            if not any(w in folded for w in ["31/12", "01/01", "202", "năm nay", "năm trước", "số cuối", "số đầu", "triệu", "tỷ", "vnd", "usd"]):
                text_col_indices.append(idx)
        if not text_col_indices:
            text_col_indices = [0, 1] if len(hdr_cells) >= 2 else [0]
            
        clean_hdr = " | ".join(hdr_cells[i] for i in text_col_indices if i < len(hdr_cells))
        if clean_hdr:
            lines.append(clean_hdr)
            lines.append("-" * len(clean_hdr))
            
        for r in slice_rows:
            row_items = []
            for i in text_col_indices:
                if i < len(r.cells) and r.cells[i].strip():
                    val = r.cells[i].strip()
                    # Loại bỏ chuỗi chỉ là số tiền lớn
                    if not re.match(r"^[\d.,\s\(\)\-]{5,}$", val):
                        row_items.append(val)
            if row_items:
                lines.append(" | ".join(row_items))
    else:
        for r in slice_rows:
            non_num = [c.strip() for c in r.cells if c.strip() and not re.match(r"^[\d.,\s\(\)\-]{5,}$", c.strip())]
            if non_num:
                lines.append(" | ".join(non_num))
                
    return "\n".join(lines)


def new_step6_chunk_document(
    blocks: list,
    doc_id: str,
    ticker: str,
    year: int,
    doc_scope: str,
    max_text_chars: int = 1200,
    max_table_rows_per_chunk: int = 20,
) -> list:
    """
    Quy tắc chunk mới:
    1. Tiền tố ngữ cảnh: [TICKER | NĂM | PHẠM VI | TIÊU ĐỀ MỤC | Đơn vị: UNIT]
    2. Văn bản: chia theo đoạn, tối đa 1200-1500 ký tự, chồng lấn tối đa 1 đoạn, không tạo chunk trơ trọi < 30 tokens.
    3. Bảng: tối đa 25-30 dòng, lặp lại header cột.
    4. Bảng rất ngắn (< 5 dòng): nếu cùng section thì gộp chung với đoạn văn liền trước.
    5. Với bảng: tạo embed_text không chứa số tiền lớn, lưu bảng đầy đủ trong text để phục vụ Writer.
    """
    scope_vi_map = {"consolidated": "Hợp nhất", "separate": "Riêng lẻ", "general": "Chung"}
    scope_vi = scope_vi_map.get(doc_scope, "Hợp nhất")
    
    chunks = []
    chunk_idx = 0
    i = 0
    n_blocks = len(blocks)
    
    while i < n_blocks:
        blk = blocks[i]
        sec = blk.section
        sec_title = blk.section_title or "Báo cáo tài chính"
        unit = blk.unit or "VND"
        context_prefix = f"[{ticker} | {year} | {scope_vi} | {sec_title} | Đơn vị: {unit}]"
        
        # Kiểm tra nếu khối văn bản đi liền trước một bảng ngắn (< 5 dòng) cùng section
        short_table_attached = None
        if blk.block_type == "text" and i + 1 < n_blocks:
            next_b = blocks[i + 1]
            if next_b.block_type == "table" and next_b.section == sec and len(next_b.grid) <= 5:
                short_table_attached = next_b
        
        if blk.block_type == "text":
            para_items = []
            while i < n_blocks and blocks[i].block_type == "text" and blocks[i].section == sec:
                cur_b = blocks[i]
                for p in re.split(r"\n\s*\n", cur_b.text):
                    p_str = p.strip()
                    if p_str:
                        para_items.append((p_str, cur_b.physical_page_start, cur_b.printed_pages))
                i += 1
                
            # Nếu có bảng ngắn gắn kèm ở cuối khối văn bản
            if short_table_attached is not None and i < n_blocks and blocks[i] == short_table_attached:
                i += 1  # Đã gộp bảng ngắn này vào
                
            buf_texts = []
            buf_phys = []
            buf_printed = []
            current_heading = None
            buf_len = 0
            
            def flush_text_chunk(is_last: bool = False):
                nonlocal chunk_idx, buf_texts, buf_phys, buf_printed, buf_len
                if not buf_texts:
                    return
                # Nếu chunk quá ngắn (< 80 ký tự) và chưa phải đoạn cuối cùng -> không flush lẻ loi
                if not is_last and buf_len < 100:
                    return
                    
                chunk_idx += 1
                p_start = min(buf_phys) if buf_phys else 1
                p_end = max(buf_phys) if buf_phys else 1
                cite_pages = f"p.{p_start}" if p_start == p_end else f"p.{p_start}-{p_end}"
                
                body_str = "\n\n".join(buf_texts)
                full_text = f"{context_prefix}\n{body_str}"
                
                chunks.append({
                    "chunk_id": f"{doc_id}_chunk_{chunk_idx:04d}",
                    "chunk_type": "text",
                    "text": full_text,
                    "embed_text": full_text,  # Văn bản dùng chính full_text đã có tiền tố
                    "physical_page_start": p_start,
                    "physical_page_end": p_end,
                    "citation_tag": f"[Doc_{doc_id}, {cite_pages}]",
                    "section": sec,
                    "section_title": sec_title,
                    "unit": unit,
                    "scope": doc_scope,
                    "row_count": 0,
                })
                
                # Giữ lại đoạn cuối cùng làm chồng lấn (overlap) nếu đoạn đó đủ dài và không phải tiêu đề cộc lốc
                if not is_last and len(buf_texts) > 1 and len(buf_texts[-1]) >= 80 and not re.match(r"^[0-9IVX]+[\.\s]", buf_texts[-1]):
                    overlap_p = buf_texts[-1]
                    overlap_phys = buf_phys[-1:]
                    overlap_pr = buf_printed[-1:]
                    buf_texts = [overlap_p]
                    buf_phys = list(overlap_phys)
                    buf_printed = list(overlap_pr)
                    buf_len = len(overlap_p)
                else:
                    buf_texts = []
                    buf_phys = []
                    buf_printed = []
                    buf_len = 0
                    
            for p_text, phys_p, pr_pages in para_items:
                if len(p_text) < 120 and "\n" not in p_text and re.match(r"^(?:[IVX]+|\d+(?:\.\d+)*|[A-Z])\.\s+\S+", p_text):
                    current_heading = p_text
                    
                if buf_texts and (buf_len + len(p_text) > max_text_chars):
                    flush_text_chunk(is_last=False)
                    if current_heading and current_heading not in buf_texts:
                        buf_texts.append(f"{current_heading} (tiếp theo)")
                        buf_len += len(current_heading) + 12
                        
                buf_texts.append(p_text)
                buf_phys.append(phys_p)
                buf_printed.extend(pr_pages)
                buf_len += len(p_text) + 2
                
            # Đính kèm nội dung bảng ngắn nếu có
            if short_table_attached is not None:
                tbl_grid = short_table_attached.grid
                tbl_lines = [" | ".join(r.cells) for r in tbl_grid]
                buf_texts.append("\n".join(tbl_lines))
                buf_phys.extend([r.physical_page for r in tbl_grid])
                buf_printed.extend([r.printed_page for r in tbl_grid if r.printed_page])
                
            flush_text_chunk(is_last=True)
            
        elif blk.block_type == "table":
            grid = blk.grid
            if not grid:
                i += 1
                continue
                
            header_count = 0
            for r_idx in range(min(3, len(grid))):
                if _is_header_row_cells(grid[r_idx].cells):
                    header_count = r_idx + 1
                else:
                    break
            if header_count == 0:
                header_count = 1
                
            header_rows = grid[:header_count]
            data_rows = grid[header_count:]
            if not data_rows:
                data_rows = header_rows
                header_rows = []
                
            header_lines = [" | ".join(hr.cells) for hr in header_rows]
            
            for start_k in range(0, len(data_rows), max_table_rows_per_chunk):
                slice_rows = data_rows[start_k : start_k + max_table_rows_per_chunk]
                chunk_idx += 1
                
                phys_set = sorted({r.physical_page for r in slice_rows})
                p_start = phys_set[0] if phys_set else 1
                p_end = phys_set[-1] if phys_set else 1
                cite_pages = f"p.{p_start}" if p_start == p_end else f"p.{p_start}-{p_end}"
                pr_pages = list(dict.fromkeys(r.printed_page for r in slice_rows if r.printed_page))
                
                # Toàn văn bảng (kèm số) cho payload
                table_lines = [context_prefix]
                table_lines.extend(header_lines)
                if header_lines:
                    table_lines.append("-" * min(80, max(len(h) for h in header_lines)))
                for r in slice_rows:
                    table_lines.append(" | ".join(r.cells))
                full_table_text = "\n".join(table_lines)
                
                # Văn bản chuyên biệt cho embedding (không chứa số tiền lớn)
                embed_table_text = generate_table_embed_text(context_prefix, header_lines, slice_rows)
                
                chunks.append({
                    "chunk_id": f"{doc_id}_chunk_{chunk_idx:04d}",
                    "chunk_type": "table",
                    "text": full_table_text,
                    "embed_text": embed_table_text,
                    "physical_page_start": p_start,
                    "physical_page_end": p_end,
                    "citation_tag": f"[Doc_{doc_id}, {cite_pages}]",
                    "section": sec,
                    "section_title": sec_title,
                    "unit": unit,
                    "scope": doc_scope,
                    "row_count": len(slice_rows),
                })
                
            i += 1
            
    return chunks

def main():
    tok = AutoTokenizer.from_pretrained("BAAI/bge-m3", local_files_only=True)
    print("Testing on 5 representative reports across sectors: FPT, VCB, BWE, DCM, VIC...")
    
    test_files = [
        ("data/raw_docs/top_100/FPT/2024/FPT_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt", "FPT", 2024),
        ("data/raw_docs/top_100/VCB/2024/VCB_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt", "VCB", 2024),
        ("data/raw_docs/top_100/BWE/2024/BWE_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt", "BWE", 2024),
        ("data/raw_docs/top_100/DCM/2024/DCM_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt", "DCM", 2024),
        ("data/raw_docs/top_100/VIC/2024/VIC_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt", "VIC", 2024),
    ]
    
    old_toks = []
    new_text_payload_toks = []
    new_embed_toks = []
    
    for fpath_str, ticker, year in test_files:
        fpath = Path(fpath_str)
        if not fpath.exists():
            continue
            
        pages, _, stats = step1_read_and_split_pages(fpath, ticker, year, backup_dir=DEFAULT_BACKUP_DIR)
        pages, _ = step2_clean_pages(pages, stats)
        blocks = step3_extract_blocks(pages)
        blocks, doc_scope, def_unit = step4_detect_structure(blocks, fpath.name)
        
        doc_id = f"{ticker}_{year}_Hopnhat"
        
        # Load old chunks from disk
        old_json = Path(f"data/processed_chunks/{doc_id}.json")
        if old_json.exists():
            old_data = json.loads(old_json.read_text(encoding="utf-8"))
            for c in old_data.get("chunks", []):
                old_toks.append(len(tok.encode(c.get("text", ""), add_special_tokens=False)))
                
        # Generate new chunks
        new_chunks = new_step6_chunk_document(blocks, doc_id, ticker, year, doc_scope)
        for c in new_chunks:
            new_text_payload_toks.append(len(tok.encode(c["text"], add_special_tokens=False)))
            new_embed_toks.append(len(tok.encode(c["embed_text"], add_special_tokens=False)))

    def summarize(name, arr):
        a = np.array(arr)
        print(f"=== {name} (N={len(a):,}) ===")
        print(f"  Min: {np.min(a)} | P25: {np.percentile(a, 25):.1f} | Median: {np.median(a):.1f} | Mean: {np.mean(a):.1f} | P75: {np.percentile(a, 75):.1f} | P90: {np.percentile(a, 90):.1f} | P95: {np.percentile(a, 95):.1f} | Max: {np.max(a)}")
        print(f"  < 30 tokens:  {np.sum(a < 30):,} ({np.sum(a < 30)/len(a)*100:.1f}%)")
        print(f"  200-500 tok:  {np.sum((a >= 200) & (a <= 500)):,} ({np.sum((a >= 200) & (a <= 500))/len(a)*100:.1f}%)")
        print(f"  > 512 tokens: {np.sum(a > 512):,} ({np.sum(a > 512)/len(a)*100:.1f}%)")
        print()

    summarize("CŨ (Full text hiện tại)", old_toks)
    summarize("MỚI (Payload text cho Writer)", new_text_payload_toks)
    summarize("MỚI (Embed text cho Embedding)", new_embed_toks)

if __name__ == "__main__":
    main()
