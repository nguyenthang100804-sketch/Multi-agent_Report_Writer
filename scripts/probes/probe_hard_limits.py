import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from transformers import AutoTokenizer
from src.ingestion.document_parser import (
    step1_read_and_split_pages,
    step2_clean_pages,
    step3_extract_blocks,
    step4_detect_structure,
    _is_header_row_cells,
)
from src.schemas.document_schema import Block, GridRow, ChunkItem

def generate_table_embed_text(context_prefix: str, header_lines: list, slice_rows: list) -> str:
    lines = [context_prefix]
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


def smart_chunk_document(
    blocks: list,
    doc_id: str,
    ticker: str,
    year: int,
    doc_scope: str,
    max_text_chars: int = 1200,
    max_table_rows_per_chunk: int = 20,
    max_table_chars_per_chunk: int = 1400,
) -> list:
    scope_vi_map = {"consolidated": "Hợp nhất", "separate": "Riêng lẻ", "general": "Chung"}
    scope_vi = scope_vi_map.get(doc_scope, "Hợp nhất")
    
    raw_chunks = []
    chunk_idx = 0
    i = 0
    n_blocks = len(blocks)
    
    while i < n_blocks:
        blk = blocks[i]
        sec = blk.section
        sec_title = blk.section_title or "Báo cáo tài chính"
        unit = blk.unit or "VND"
        context_prefix = f"[{ticker} | {year} | {scope_vi} | {sec_title} | Đơn vị: {unit}]"
        
        # Kiểm tra bảng rất ngắn (< 5 dòng) liền kề cùng section để gộp với đoạn văn
        short_table_attached = None
        if blk.block_type == "text" and i + 1 < n_blocks:
            next_b = blocks[i + 1]
            if next_b.block_type == "table" and next_b.section == sec and len(next_b.grid) < 5:
                short_table_attached = next_b
        
        if blk.block_type == "text":
            para_items = []
            while i < n_blocks and blocks[i].block_type == "text" and blocks[i].section == sec:
                cur_b = blocks[i]
                for p in re.split(r"\n\s*\n", cur_b.text):
                    p_str = p.strip()
                    if p_str:
                        # Tách đoạn quá dài (> 1200 ký tự) thành các câu
                        if len(p_str) > max_text_chars:
                            sents = re.split(r"(?<=[.!?])\s+", p_str)
                            sub_p = []
                            sub_len = 0
                            for s in sents:
                                if sub_len + len(s) > max_text_chars and sub_p:
                                    para_items.append((" ".join(sub_p), cur_b.physical_page_start, cur_b.printed_pages))
                                    sub_p = [s]
                                    sub_len = len(s)
                                else:
                                    sub_p.append(s)
                                    sub_len += len(s) + 1
                            if sub_p:
                                para_items.append((" ".join(sub_p), cur_b.physical_page_start, cur_b.printed_pages))
                        else:
                            para_items.append((p_str, cur_b.physical_page_start, cur_b.printed_pages))
                i += 1
                
            if short_table_attached is not None and i < n_blocks and blocks[i] == short_table_attached:
                i += 1  # Đã gộp bảng ngắn này
                
            buf_texts = []
            buf_phys = []
            buf_printed = []
            current_heading = None
            buf_len = 0
            
            def flush_text_chunk(is_last: bool = False):
                nonlocal chunk_idx, buf_texts, buf_phys, buf_printed, buf_len
                if not buf_texts:
                    return
                # Anti-orphan: không tạo chunk cộc lốc (< 100 ký tự) nếu chưa phải đoạn cuối cùng
                if not is_last and buf_len < 100:
                    return
                    
                chunk_idx += 1
                p_start = min(buf_phys) if buf_phys else 1
                p_end = max(buf_phys) if buf_phys else 1
                cite_pages = f"p.{p_start}" if p_start == p_end else f"p.{p_start}-{p_end}"
                
                body_str = "\n\n".join(buf_texts)
                full_text = f"{context_prefix}\n{body_str}"
                
                raw_chunks.append(ChunkItem(
                    chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
                    chunk_type="text",
                    text=full_text,
                    physical_pages=sorted(set(buf_phys)),
                    physical_page_start=p_start,
                    physical_page_end=p_end,
                    printed_pages=list(dict.fromkeys(p for p in buf_printed if p)),
                    citation_tag=f"[Doc_{doc_id}, {cite_pages}]",
                    section=sec,
                    section_title=sec_title,
                    unit=unit,
                    scope=doc_scope,
                    embed_text=full_text,
                    row_count=0,
                ))
                
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
                
            # Đính kèm bảng ngắn (< 5 dòng) nếu có: BẢO TOÀN NGUYÊN VẸN HEADER CỘT
            if short_table_attached is not None:
                tbl_grid = short_table_attached.grid
                hdr_count = 0
                for r_idx in range(min(3, len(tbl_grid))):
                    if _is_header_row_cells(tbl_grid[r_idx].cells):
                        hdr_count = r_idx + 1
                    else:
                        break
                if hdr_count == 0:
                    hdr_count = 1
                hdr_rows = tbl_grid[:hdr_count]
                d_rows = tbl_grid[hdr_count:]
                if not d_rows:
                    d_rows = hdr_rows
                    hdr_rows = []
                short_hdr_lines = [" | ".join(hr.cells) for hr in hdr_rows]
                short_tbl_lines = []
                short_tbl_lines.extend(short_hdr_lines)
                if short_hdr_lines:
                    short_tbl_lines.append("-" * min(80, max(len(h) for h in short_hdr_lines)))
                for r in d_rows:
                    short_tbl_lines.append(" | ".join(r.cells))
                
                buf_texts.append("\n".join(short_tbl_lines))
                buf_phys.extend([r.physical_page for r in tbl_grid])
                buf_printed.extend([r.printed_page for r in tbl_grid if r.printed_page])
                
            flush_text_chunk(is_last=True)
            
        elif blk.block_type == "table":
            grid = blk.grid
            if not grid:
                i += 1
                continue
                
            hdr_count = 0
            for r_idx in range(min(3, len(grid))):
                if _is_header_row_cells(grid[r_idx].cells):
                    hdr_count = r_idx + 1
                else:
                    break
            if hdr_count == 0:
                hdr_count = 1
                
            header_rows = grid[:hdr_count]
            data_rows = grid[hdr_count:]
            if not data_rows:
                data_rows = header_rows
                header_rows = []
                
            header_lines = [" | ".join(hr.cells) for hr in header_rows]
            
            # Xử lý ô bảng siêu dài (giant cells) > 800 ký tự -> bẻ thành nhiều dòng logic
            normalized_data_rows = []
            for r in data_rows:
                max_c_len = max(len(c) for c in r.cells) if r.cells else 0
                if max_c_len > 800:
                    # Bẻ ô dài nhất thành các đoạn 600 ký tự
                    split_cells = []
                    for c in r.cells:
                        if len(c) > 800:
                            chunks_c = [c[k:k+600] for k in range(0, len(c), 600)]
                            split_cells.append(chunks_c)
                        else:
                            split_cells.append([c])
                    max_parts = max(len(sc) for sc in split_cells)
                    for p_i in range(max_parts):
                        new_cells = [sc[p_i] if p_i < len(sc) else "" for sc in split_cells]
                        normalized_data_rows.append(GridRow(cells=new_cells, physical_page=r.physical_page, printed_page=r.printed_page))
                else:
                    normalized_data_rows.append(r)
                    
            # Cắt bảng theo cả số dòng (<= 20) VÀ dung lượng ký tự (<= 1400)
            cur_slice = []
            cur_slice_chars = 0
            
            def flush_table_slice(slice_rows):
                nonlocal chunk_idx
                if not slice_rows:
                    return
                chunk_idx += 1
                phys_set = sorted({r.physical_page for r in slice_rows})
                p_start = phys_set[0] if phys_set else 1
                p_end = phys_set[-1] if phys_set else 1
                cite_pages = f"p.{p_start}" if p_start == p_end else f"p.{p_start}-{p_end}"
                pr_pages = list(dict.fromkeys(r.printed_page for r in slice_rows if r.printed_page))
                
                table_lines = [context_prefix]
                table_lines.extend(header_lines)
                if header_lines:
                    table_lines.append("-" * min(80, max(len(h) for h in header_lines)))
                for r in slice_rows:
                    table_lines.append(" | ".join(r.cells))
                full_table_text = "\n".join(table_lines)
                
                embed_table_text = generate_table_embed_text(context_prefix, header_lines, slice_rows)
                
                raw_chunks.append(ChunkItem(
                    chunk_id=f"{doc_id}_chunk_{chunk_idx:04d}",
                    chunk_type="table",
                    text=full_table_text,
                    physical_pages=phys_set,
                    physical_page_start=p_start,
                    physical_page_end=p_end,
                    printed_pages=pr_pages,
                    citation_tag=f"[Doc_{doc_id}, {cite_pages}]",
                    section=sec,
                    section_title=sec_title,
                    unit=unit,
                    scope=doc_scope,
                    embed_text=embed_table_text,
                    row_count=len(slice_rows),
                ))
                
            for r in normalized_data_rows:
                r_chars = sum(len(c) for c in r.cells) + len(r.cells) * 3
                if cur_slice and (len(cur_slice) >= max_table_rows_per_chunk or cur_slice_chars + r_chars > max_table_chars_per_chunk):
                    flush_table_slice(cur_slice)
                    cur_slice = []
                    cur_slice_chars = 0
                cur_slice.append(r)
                cur_slice_chars += r_chars
                
            if cur_slice:
                flush_table_slice(cur_slice)
                
            i += 1
            
    # Lưới an toàn cứng (Hard Token Safety Net): Đảm bảo không chunk nào vượt quá 600 tokens (~1800 ký tự)
    final_chunks = []
    for c in raw_chunks:
        if len(c.text) > 1800:
            lines = c.text.split("\n")
            prefix = lines[0] if lines else ""
            sub_lines = []
            sub_len = len(prefix)
            sub_part = 1
            for l in lines[1:]:
                if sub_len + len(l) > 1600 and sub_lines:
                    part_text = f"{prefix}\n" + "\n".join(sub_lines)
                    final_chunks.append(ChunkItem(
                        chunk_id=f"{c.chunk_id}_p{sub_part}",
                        chunk_type=c.chunk_type,
                        text=part_text,
                        physical_pages=c.physical_pages,
                        physical_page_start=c.physical_page_start,
                        physical_page_end=c.physical_page_end,
                        printed_pages=c.printed_pages,
                        citation_tag=c.citation_tag,
                        section=c.section,
                        section_title=c.section_title,
                        unit=c.unit,
                        scope=c.scope,
                        embed_text=part_text if c.chunk_type == "text" else c.embed_text[:1600],
                        row_count=c.row_count,
                    ))
                    sub_part += 1
                    sub_lines = [l]
                    sub_len = len(prefix) + len(l)
                else:
                    sub_lines.append(l)
                    sub_len += len(l) + 1
            if sub_lines:
                part_text = f"{prefix}\n" + "\n".join(sub_lines)
                final_chunks.append(ChunkItem(
                    chunk_id=f"{c.chunk_id}_p{sub_part}",
                    chunk_type=c.chunk_type,
                    text=part_text,
                    physical_pages=c.physical_pages,
                    physical_page_start=c.physical_page_start,
                    physical_page_end=c.physical_page_end,
                    printed_pages=c.printed_pages,
                    citation_tag=c.citation_tag,
                    section=c.section,
                    section_title=c.section_title,
                    unit=c.unit,
                    scope=c.scope,
                    embed_text=part_text if c.chunk_type == "text" else c.embed_text[:1600],
                    row_count=c.row_count,
                ))
        else:
            final_chunks.append(c)
            
    return final_chunks

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained("BAAI/bge-m3", local_files_only=True)
    test_files = [
        ("data/raw_docs/top_100/PET/2022/PET_2022_BCTC_Kiemtoan_Hopnhat_extracted.txt", "PET", 2022),
        ("data/raw_docs/top_100/ACB/2025/ACB_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt", "ACB", 2025),
        ("data/raw_docs/top_100/FPT/2024/FPT_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt", "FPT", 2024),
    ]
    for fp, tk, yr in test_files:
        p = Path(fp)
        pages, _, stats = step1_read_and_split_pages(p, tk, yr)
        pages, stats = step2_clean_pages(pages, stats)
        blocks = step3_extract_blocks(pages)
        blocks, doc_scope, default_unit = step4_detect_structure(blocks, p.name)
        scope_tag = {"consolidated": "Hopnhat", "separate": "Riengle", "general": "Chung"}.get(doc_scope, "BCTC")
        doc_id = f"{tk}_{yr}_{scope_tag}"
        chunks = smart_chunk_document(blocks, doc_id, tk, yr, doc_scope)
        tokens = [len(tok.encode(c.text, add_special_tokens=False)) for c in chunks]
        embed_tokens = [len(tok.encode(c.embed_text, add_special_tokens=False)) for c in chunks]
        print(f"=== {tk} {yr} ===")
        print(f"  Chunks count: {len(chunks)}")
        print(f"  Text tokens: max={max(tokens)}, min={min(tokens)}, mean={sum(tokens)/len(tokens):.1f}")
        print(f"  Embed tokens: max={max(embed_tokens)}, min={min(embed_tokens)}, mean={sum(embed_tokens)/len(embed_tokens):.1f}")
        print(f"  > 512 tokens (text): {sum(1 for t in tokens if t > 512)} ({sum(1 for t in tokens if t > 512)/len(tokens)*100:.1f}%)")
        print(f"  > 512 tokens (embed): {sum(1 for t in embed_tokens if t > 512)} ({sum(1 for t in embed_tokens if t > 512)/len(embed_tokens)*100:.1f}%)")
        print(f"  < 30 tokens: {sum(1 for t in tokens if t < 30)} ({sum(1 for t in tokens if t < 30)/len(tokens)*100:.1f}%)")
