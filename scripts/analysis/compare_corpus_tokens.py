import json
from pathlib import Path
import numpy as np
from transformers import AutoTokenizer

def main():
    print("Loading BAAI/bge-m3 tokenizer...")
    tok = AutoTokenizer.from_pretrained("BAAI/bge-m3", local_files_only=True)
    chunks_dir = Path("data/processed_chunks")
    files = sorted([f for f in chunks_dir.glob("*.json") if not f.name.startswith("_")])
    print(f"Reading {len(files)} parsed files...")

    all_text_tokens = []
    text_type_tokens = []
    table_type_tokens = []

    all_embed_tokens = []
    text_embed_tokens = []
    table_embed_tokens = []

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for c in data.get("chunks", []):
            txt = c.get("text", "")
            embed_txt = c.get("embed_text", "")
            c_type = c.get("chunk_type", "text")

            n_tok_txt = len(tok.encode(txt, add_special_tokens=False))
            n_tok_emb = len(tok.encode(embed_txt, add_special_tokens=False)) if embed_txt else n_tok_txt

            all_text_tokens.append(n_tok_txt)
            all_embed_tokens.append(n_tok_emb)

            if c_type == "text":
                text_type_tokens.append(n_tok_txt)
                text_embed_tokens.append(n_tok_emb)
            else:
                table_type_tokens.append(n_tok_txt)
                table_embed_tokens.append(n_tok_emb)

    def compute_metrics(arr):
        arr = np.array(arr)
        return {
            "N": len(arr),
            "min": int(np.min(arr)),
            "p25": float(np.percentile(arr, 25)),
            "median": float(np.median(arr)),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "p75": float(np.percentile(arr, 75)),
            "p90": float(np.percentile(arr, 90)),
            "p95": float(np.percentile(arr, 95)),
            "p99": float(np.percentile(arr, 99)),
            "max": int(np.max(arr)),
            "under_30": int(np.sum(arr < 30)),
            "pct_under_30": float(np.sum(arr < 30) / len(arr) * 100),
            "sweet_spot": int(np.sum((arr >= 200) & (arr <= 500))),
            "pct_sweet_spot": float(np.sum((arr >= 200) & (arr <= 500)) / len(arr) * 100),
            "over_512": int(np.sum(arr > 512)),
            "pct_over_512": float(np.sum(arr > 512) / len(arr) * 100),
            "over_600": int(np.sum(arr > 600)),
            "pct_over_600": float(np.sum(arr > 600) / len(arr) * 100),
        }

    res_all_txt = compute_metrics(all_text_tokens)
    res_text_txt = compute_metrics(text_type_tokens)
    res_tbl_txt = compute_metrics(table_type_tokens)

    res_all_emb = compute_metrics(all_embed_tokens)
    res_text_emb = compute_metrics(text_embed_tokens)
    res_tbl_emb = compute_metrics(table_embed_tokens)

    print("\n" + "=" * 80)
    print("KẾT QUẢ ĐO ĐẠC TOÀN BỘ CORPUS (141 BÁO CÁO / 35 CÔNG TY)")
    print("=" * 80)

    def print_row(title, m):
        print(f"[{title}] (N={m['N']:,})")
        print(f"  Min: {m['min']} | P25: {m['p25']:.1f} | Trung vị: {m['median']:.1f} | Mean: {m['mean']:.1f} (+/- {m['std']:.1f})")
        print(f"  P75: {m['p75']:.1f} | P90: {m['p90']:.1f} | P95: {m['p95']:.1f} | P99: {m['p99']:.1f} | Max: {m['max']}")
        print(f"  < 30 tokens: {m['under_30']:,} ({m['pct_under_30']:.2f}%)")
        print(f"  200-500 tokens: {m['sweet_spot']:,} ({m['pct_sweet_spot']:.2f}%)")
        print(f"  > 512 tokens: {m['over_512']:,} ({m['pct_over_512']:.2f}%)")
        print(f"  > 600 tokens: {m['over_600']:,} ({m['pct_over_600']:.2f}%)")
        print()

    print("--- 1. TEXT (SPARSE BM25 & WRITER PAYLOAD - GIỮ SỐ NGUYÊN BẢN) ---")
    print_row("TẤT CẢ CHUNKS", res_all_txt)
    print_row("TEXT CHUNKS", res_text_txt)
    print_row("TABLE CHUNKS", res_tbl_txt)

    print("--- 2. EMBED_TEXT (DENSE EMBEDDING BGE-M3 - LOẠI BỎ SỐ TIỀN LỚN) ---")
    print_row("TẤT CẢ CHUNKS (DENSE)", res_all_emb)
    print_row("TEXT CHUNKS (DENSE)", res_text_emb)
    print_row("TABLE CHUNKS (DENSE)", res_tbl_emb)

    # Save summary json
    summary_path = Path("evaluation/token_statistics/comparisons/corpus_token_comparison.json")
    summary_path.write_text(json.dumps({
        "sparse_text": {
            "all": res_all_txt,
            "text": res_text_txt,
            "table": res_tbl_txt
        },
        "dense_embed_text": {
            "all": res_all_emb,
            "text": res_text_emb,
            "table": res_tbl_emb
        }
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Đã lưu kết quả chi tiết vào: {summary_path}")

if __name__ == "__main__":
    main()
