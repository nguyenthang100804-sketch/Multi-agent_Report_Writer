import json
import uuid
import hashlib
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collections import Counter, defaultdict
from src.indexing.vietnamese_sparse_tokenizer import tokenize_vietnamese_sparse, normalize_vietnamese_sparse

def run_detailed_dry_test():
    print("=" * 80)
    print("BẮT ĐẦU CHẠY KIỂM THỬ DRY-TEST CHI TIẾT TRÊN TOÀN BỘ CORPUS")
    print("=" * 80)
    
    input_dir = Path("data/processed_chunks")
    files = sorted([f for f in input_dir.glob("*.json") if not f.name.startswith("_")])
    
    print(f"1. TẢI VÀ DUYỆT TÀI LIỆU:")
    print(f"- Tổng số file JSON: {len(files)}")
    
    # Trackers
    total_chunks = 0
    chunk_type_counts = Counter()
    section_counts = Counter()
    scope_counts = Counter()
    year_counts = Counter()
    ticker_counts = Counter()
    
    # Integrity checks
    missing_citation_tags = []
    missing_embed_texts = []
    missing_texts = []
    missing_pages = []
    malformed_prefixes = []
    
    # Point ID and Hash checks
    point_ids = set()
    duplicate_point_ids = []
    content_hashes = Counter()
    
    # Dev / Test split mapping
    split_config = json.loads(Path("configs/eval_dataset_split.json").read_text(encoding="utf-8"))
    dev_tickers = set(split_config["dev_tickers"])
    test_tickers = set(split_config["test_tickers"])
    dev_chunks_count = 0
    test_chunks_count = 0
    unmapped_tickers = set()

    t0 = time.perf_counter()

    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc_id = doc.get("doc_id", f.stem)
        ticker = doc.get("ticker", "")
        year = doc.get("fiscal_year", 0)
        scope = doc.get("scope", "consolidated")
        default_unit = doc.get("default_unit", "VND")
        
        ticker_counts[ticker] += 1
        year_counts[year] += 1
        scope_counts[scope] += 1
        
        if ticker in dev_tickers:
            is_dev = True
        elif ticker in test_tickers:
            is_dev = False
        else:
            unmapped_tickers.add(ticker)
            is_dev = True

        chunks = doc.get("chunks", [])
        total_chunks += len(chunks)
        
        for idx, c in enumerate(chunks):
            cid = c.get("chunk_id", f"{doc_id}_chunk_{idx}")
            ctype = c.get("chunk_type", "text")
            sec = c.get("section", "UNKNOWN")
            ctag = c.get("citation_tag", "")
            txt = c.get("text", "")
            etxt = c.get("embed_text", "")
            pages = c.get("physical_pages", [])
            
            chunk_type_counts[ctype] += 1
            section_counts[sec] += 1
            
            if is_dev:
                dev_chunks_count += 1
            else:
                test_chunks_count += 1

            # Check point ID (uuid5)
            pid = str(uuid.uuid5(uuid.NAMESPACE_URL, cid))
            if pid in point_ids:
                duplicate_point_ids.append((cid, pid))
            else:
                point_ids.add(pid)
                
            # Content Hash
            chash = hashlib.sha256(etxt.encode("utf-8")).hexdigest()
            content_hashes[chash] += 1

            # Field checks
            if not ctag:
                missing_citation_tags.append(cid)
            if not etxt:
                missing_embed_texts.append(cid)
            if not txt:
                missing_texts.append(cid)
            if not pages:
                missing_pages.append(cid)
                
            # Prefix check
            if not etxt.startswith("[") or "|" not in etxt.split("]")[0]:
                malformed_prefixes.append((cid, etxt[:60]))

    load_time = time.perf_counter() - t0

    print(f"- Tổng số chunks đọc được: {total_chunks:,} chunks (thời gian: {load_time:.2f}s)")
    print(f"\n2. PHÂN LOẠI CHUNKS:")
    print(f"- Theo loại chunk:")
    for ct, count in chunk_type_counts.items():
        pct = (count / total_chunks) * 100
        print(f"  + {ct:<10}: {count:6,d} ({pct:5.2f}%)")
        
    print(f"\n- Theo Section báo cáo:")
    for sec, count in section_counts.most_common():
        pct = (count / total_chunks) * 100
        print(f"  + {sec:<20}: {count:6,d} ({pct:5.2f}%)")

    print(f"\n3. KIỂM ĐỊNH TÍNH TOÀN VẸN (INTEGRITY & NULL CHECKS):")
    print(f"- Số chunk thiếu citation_tag : {len(missing_citation_tags)}")
    print(f"- Số chunk thiếu embed_text   : {len(missing_embed_texts)}")
    print(f"- Số chunk thiếu text (payload): {len(missing_texts)}")
    print(f"- Số chunk thiếu physical_pages: {len(missing_pages)}")
    print(f"- Số chunk sai định dạng tiền tố: {len(malformed_prefixes)}")
    if malformed_prefixes:
        for cid, pre in malformed_prefixes[:3]:
            print(f"    ! {cid}: {pre}")

    print(f"\n4. KIỂM ĐỊNH POINT ID & BẢN QUYỀN HASH (UUID5 & CONTENT HASH):")
    print(f"- Tổng số Point ID duy nhất (uuid5): {len(point_ids):,}")
    print(f"- Số Point ID bị xung đột/trùng lặp: {len(duplicate_point_ids)}")
    unique_hashes = len(content_hashes)
    dup_hashes = sum(1 for v in content_hashes.values() if v > 1)
    max_dup_count = content_hashes.most_common(1)[0][1] if content_hashes else 0
    print(f"- Tổng số Content Hash duy nhất: {unique_hashes:,} / {total_chunks:,}")
    print(f"- Số Content Hash lặp lại (văn bản mẫu qua các năm): {dup_hashes:,} (lặp nhiều nhất: {max_dup_count} lần)")

    print(f"\n5. PHÂN BỔ TẬP DEV VÀ TEST (COMPANY-LEVEL SPLIT):")
    print(f"- Số mã cổ phiếu: {len(ticker_counts)} (Dev: {len(dev_tickers)}, Test: {len(test_tickers)})")
    print(f"- Không có mã cổ phiếu ngoài danh mục: {len(unmapped_tickers) == 0}")
    print(f"- Số chunk tập DEV  (25 công ty): {dev_chunks_count:6,d} ({(dev_chunks_count/total_chunks)*100:5.2f}%)")
    print(f"- Số chunk tập TEST (10 công ty): {test_chunks_count:6,d} ({(test_chunks_count/total_chunks)*100:5.2f}%)")

    # Sample sparse tokenizer test
    print(f"\n6. THỬ NGHIỆM TƯƠNG THÍCH SPARSE TOKENIZER (1.000 CHUNKS MẪU):")
    t1 = time.perf_counter()
    sample_size = 1000
    sample_tokens_count = 0
    sample_chunks_iter = 0
    for f in files[:10]:
        doc = json.loads(f.read_text(encoding="utf-8"))
        for c in doc.get("chunks", []):
            toks = tokenize_vietnamese_sparse(c.get("text", ""))
            sample_tokens_count += len(toks)
            sample_chunks_iter += 1
            if sample_chunks_iter >= sample_size:
                break
        if sample_chunks_iter >= sample_size:
            break
    tok_time = time.perf_counter() - t1
    tok_speed = sample_size / tok_time if tok_time > 0 else 0
    print(f"- Đã tokenize {sample_size} chunks trong {tok_time:.3f}s ({tok_speed:,.1f} chunks/s)")
    print(f"- Trung bình: {sample_tokens_count/sample_size:.1f} tokens/chunk")
    print(f"- Tốc độ xử lý từ khóa Sparse ước tính cho 30.282 chunks: ~{total_chunks/tok_speed:.2f}s (~{total_chunks/tok_speed/60:.2f} phút)")

    print("\n" + "=" * 80)
    all_passed = (
        len(missing_citation_tags) == 0
        and len(missing_embed_texts) == 0
        and len(missing_texts) == 0
        and len(duplicate_point_ids) == 0
        and len(malformed_prefixes) == 0
        and len(unmapped_tickers) == 0
    )
    if all_passed:
        print("TỔNG KẾT DRY-TEST: 100% CÁC TIÊU CHÍ ĐẠT HOÀN HẢO (ALL CHECKS PASSED!)")
        print("Hệ thống và tập dữ liệu đã sẵn sàng 100% cho bước suy luận Vector Embedding!")
    else:
        print("TỔNG KẾT DRY-TEST: CÓ CẢNH BÁO CẦN XỬ LÝ TRƯỚC KHI CHẠY THẬT!")
    print("=" * 80)

if __name__ == "__main__":
    run_detailed_dry_test()
