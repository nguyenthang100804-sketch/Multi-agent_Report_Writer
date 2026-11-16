import json
from pathlib import Path
import numpy as np
from transformers import AutoTokenizer

def main():
    print("Loading local tokenizer BAAI/bge-m3...")
    tok = AutoTokenizer.from_pretrained("BAAI/bge-m3", local_files_only=True)
    print("Loaded successfully! Vocab size:", tok.vocab_size)

    chunks_dir = Path("data/processed_chunks")
    files = sorted([f for f in chunks_dir.glob("*.json") if not f.name.startswith("_")])

    all_tokens = []
    text_tokens = []
    table_tokens = []
    under_30_chunks = []
    over_512_chunks = []

    print(f"Analyzing {len(files)} files...")
    for idx, f in enumerate(files):
        data = json.loads(f.read_text(encoding="utf-8"))
        doc_id = data.get("doc_id", f.stem)
        for c in data.get("chunks", []):
            txt = c.get("text", "")
            c_type = c.get("chunk_type", "text")
            
            # Tokenize without special tokens to get pure content length
            n_tok = len(tok.encode(txt, add_special_tokens=False))
            all_tokens.append(n_tok)
            if c_type == "text":
                text_tokens.append(n_tok)
            else:
                table_tokens.append(n_tok)
                
            if n_tok < 30:
                under_30_chunks.append({
                    "doc_id": doc_id,
                    "chunk_id": c.get("chunk_id"),
                    "type": c_type,
                    "section": c.get("section"),
                    "tokens": n_tok,
                    "text": txt[:120].replace("\n", " ")
                })
            elif n_tok > 512:
                over_512_chunks.append({
                    "doc_id": doc_id,
                    "chunk_id": c.get("chunk_id"),
                    "type": c_type,
                    "tokens": n_tok,
                    "chars": len(txt),
                    "rows": c.get("row_count", 0),
                    "text": txt[:120].replace("\n", " ")
                })

    def print_stats(name, arr):
        arr = np.array(arr)
        print(f"=== {name} (N={len(arr):,}) ===")
        print(f"  Min:     {np.min(arr)}")
        print(f"  P25:     {np.percentile(arr, 25):.1f}")
        print(f"  Median:  {np.median(arr):.1f}")
        print(f"  Mean:    {np.mean(arr):.1f} (+/- {np.std(arr):.1f})")
        print(f"  P75:     {np.percentile(arr, 75):.1f}")
        print(f"  P90:     {np.percentile(arr, 90):.1f}")
        print(f"  P95:     {np.percentile(arr, 95):.1f}")
        print(f"  P99:     {np.percentile(arr, 99):.1f}")
        print(f"  Max:     {np.max(arr)}")
        print(f"  < 30:    {np.sum(arr < 30):,} ({np.sum(arr < 30)/len(arr)*100:.2f}%)")
        print(f"  30-100:  {np.sum((arr >= 30) & (arr < 100)):,} ({np.sum((arr >= 30) & (arr < 100))/len(arr)*100:.2f}%)")
        print(f"  100-200: {np.sum((arr >= 100) & (arr < 200)):,} ({np.sum((arr >= 100) & (arr < 200))/len(arr)*100:.2f}%)")
        print(f"  200-500: {np.sum((arr >= 200) & (arr <= 500)):,} ({np.sum((arr >= 200) & (arr <= 500))/len(arr)*100:.2f}%)")
        print(f"  > 500:   {np.sum(arr > 500):,} ({np.sum(arr > 500)/len(arr)*100:.2f}%)")
        print(f"  > 512:   {np.sum(arr > 512):,} ({np.sum(arr > 512)/len(arr)*100:.2f}%)")
        print()

    print_stats("TẤT CẢ CHUNKS", all_tokens)
    print_stats("TEXT CHUNKS", text_tokens)
    print_stats("TABLE CHUNKS", table_tokens)

    print(f"Tổng số chunk < 30 tokens: {len(under_30_chunks):,}")
    print("Mẫu 15 chunk < 30 tokens:")
    for s in under_30_chunks[:15]:
        print(f"  [{s['type']:5s} | {s['tokens']:2d} tok | {s['section']:15s}] {s['text']}")

    print(f"\nTổng số chunk > 512 tokens: {len(over_512_chunks):,}")
    print("Mẫu 15 chunk > 512 tokens:")
    for s in over_512_chunks[:15]:
        print(f"  [{s['type']:5s} | {s['tokens']:4d} tok | chars={s['chars']:5d} | rows={s['rows']:2d}] {s['text']}")

if __name__ == "__main__":
    main()
