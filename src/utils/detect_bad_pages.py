#!/usr/bin/env python3
"""Phát hiện, đếm và tính tỉ lệ trang OCR hỏng (lật ngược, vòng lặp, rác) từ file OCR thô.

Chỉ dùng thư viện chuẩn của Python (không cần cài thêm gì).

Cách dùng:
  python detect_bad_pages.py --input data/raw_docs/top_100 --out-dir reports/bad_pages

Ý tưởng:
  1. Tách mỗi file thành các trang theo dòng "===== PAGE n =====" (hoặc [P.n]).
  2. Xây TỪ VỰNG từ chính corpus: một từ được coi là "hợp lệ" nếu xuất hiện ở
     ít nhất --min-pages trang khác nhau VÀ ít nhất --min-files file khác nhau.
     (Trang lật ngược cho ra các "từ" ngẫu nhiên, hiếm khi lặp lại ở nhiều file.)
  3. Với mỗi trang tính: tỉ lệ token nằm trong từ vựng (valid_ratio), tỉ lệ token
     lặp nhiều nhất (top_ratio), số ký tự Hán / LaTeX.
  4. Gán trạng thái: OK, SPARSE (ít chữ, vd. bảng toàn số), SOFT (đáng ngờ),
     HARD (hỏng nặng), REPEAT (vòng lặp suy biến), NOISE (còn LaTeX/CJK).

LƯU Ý: ngưỡng mặc định chỉ là điểm khởi đầu. Hãy mở ~10 trang SOFT và ~10 trang HARD
trong flagged_pages.csv (cột snippet + ảnh gốc) để chỉnh ngưỡng trước khi tin con số %.
Trang tiếng Anh trong báo cáo song ngữ vẫn được tính hợp lệ nếu từ tiếng Anh đó đủ
phổ biến trong corpus.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

PAGE_RE = re.compile(r"^\s*={3,}\s*PAGE\s+(\d+)\s*={3,}\s*$", re.M | re.I)
PMARK_RE = re.compile(r"^\s*\[P\.(\d+)\]\s*$", re.M)
TAG_RE = re.compile(r"<[^>]+>")
TOKEN_RE = re.compile(r"[^\W\d_]{2,}")  # chuỗi chữ cái (có dấu) dài >= 2
CJK_RE = re.compile(r"[一-鿿]")
LATEX_RE = re.compile(r"\\\(|\\\[|\\begin|\\end|\\left|\\right|\\frac|\\mathrm")


def split_pages(text: str):
    """Trả về list[(page_no, page_text)]."""
    for rx in (PAGE_RE, PMARK_RE):
        ms = list(rx.finditer(text))
        if ms:
            pages = []
            for i, m in enumerate(ms):
                end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
                pages.append((int(m.group(1)), text[m.end():end]))
            return pages
    return [(1, text)]


def tokens_of(page_text: str):
    t = html.unescape(TAG_RE.sub(" ", page_text))
    return TOKEN_RE.findall(t.lower())


def infer_ids(path: Path):
    """TICKER/YEAR/file.txt -> (ticker, year); không đúng cấu trúc thì suy từ tên file."""
    year = path.parent.name if path.parent.name.isdigit() else ""
    ticker = path.parent.parent.name if year else path.stem.split("_")[0]
    if not year:
        m = re.search(r"(20\d{2})", path.name)
        year = m.group(1) if m else ""
    return ticker, year


def load_corpus(root: Path, include_giai_trinh: bool):
    files = [root] if root.is_file() else sorted(root.rglob("*.txt"))
    corpus = []
    for f in files:
        if f.name == "giai_trinh_lien_quan.txt" and not include_giai_trinh:
            continue
        raw = f.read_bytes().decode("utf-8", errors="ignore")
        text = unicodedata.normalize("NFC", raw)
        ticker, year = infer_ids(f)
        corpus.append({"file": f, "ticker": ticker, "year": year, "pages": split_pages(text)})
    return corpus


def build_vocab(corpus, min_pages: int, min_files: int, skip_top_ratio: float):
    page_df, file_df = Counter(), Counter()
    for doc in corpus:
        seen_file = set()
        for _, ptxt in doc["pages"]:
            toks = tokens_of(ptxt)
            if len(toks) >= 20 and Counter(toks).most_common(1)[0][1] / len(toks) >= skip_top_ratio:
                continue  # không để trang vòng lặp làm bẩn từ vựng
            s = set(toks)
            page_df.update(s)
            seen_file |= s
        file_df.update(seen_file)
    return {w for w, n in page_df.items() if n >= min_pages and file_df[w] >= min_files}


def score_page(ptxt: str, vocab: set, a):
    toks = tokens_of(ptxt)
    n = len(toks)
    cjk = len(CJK_RE.findall(ptxt))
    latex = len(LATEX_RE.findall(ptxt))
    if n:
        valid = sum(w in vocab for w in toks) / n
        top_tok, top_cnt = Counter(toks).most_common(1)[0]
        top_ratio = top_cnt / n
    else:
        valid, top_tok, top_ratio = 0.0, "", 0.0

    if n >= a.min_tokens and top_ratio >= a.max_top_ratio:
        status = "REPEAT"
    elif n < a.min_tokens:
        status = "SPARSE"
    elif valid < a.hard_valid:
        status = "HARD"
    elif valid < a.soft_valid:
        status = "SOFT"
    elif cjk >= a.max_cjk or latex >= a.max_latex:
        status = "NOISE"
    else:
        status = "OK"
    snippet = re.sub(r"\s+", " ", TAG_RE.sub(" ", ptxt)).strip()[:90]
    return {
        "n_tokens": n, "valid_ratio": round(valid, 3), "top_token": top_tok,
        "top_ratio": round(top_ratio, 3), "cjk_chars": cjk, "latex_hits": latex,
        "status": status, "snippet": snippet,
    }


def pct(a, b):
    return f"{100.0 * a / b:.2f}%" if b else "n/a"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, required=True, help="file .txt hoặc thư mục chứa các file OCR thô")
    ap.add_argument("--out-dir", type=Path, default=Path("bad_pages_report"))
    ap.add_argument("--include-giai-trinh", action="store_true", help="tính cả giai_trinh_lien_quan.txt")
    ap.add_argument("--min-pages", type=int, default=30, help="từ phải có ở >= N trang để vào từ vựng")
    ap.add_argument("--min-files", type=int, default=3, help="từ phải có ở >= N file để vào từ vựng")
    ap.add_argument("--min-tokens", type=int, default=20, help="trang ít chữ hơn mức này -> SPARSE (không chấm)")
    ap.add_argument("--hard-valid", type=float, default=0.55, help="valid_ratio < ngưỡng này -> HARD")
    ap.add_argument("--soft-valid", type=float, default=0.70, help="valid_ratio < ngưỡng này -> SOFT")
    ap.add_argument("--max-top-ratio", type=float, default=0.20, help="một token chiếm >= tỉ lệ này -> REPEAT")
    ap.add_argument("--max-cjk", type=int, default=5)
    ap.add_argument("--max-latex", type=int, default=2)
    ap.add_argument("--save-vocab", type=Path, help="lưu từ vựng ra JSON để dùng lại")
    ap.add_argument("--load-vocab", type=Path, help="dùng từ vựng đã lưu thay vì xây lại")
    a = ap.parse_args()

    corpus = load_corpus(a.input, a.include_giai_trinh)
    if not corpus:
        sys.exit("Không tìm thấy file .txt nào.")
    n_files = len(corpus)

    if a.load_vocab:
        vocab = set(json.loads(a.load_vocab.read_text(encoding="utf-8")))
    else:
        mf = min(a.min_files, n_files)
        if mf < a.min_files:
            print(f"[!] Chỉ có {n_files} file, hạ --min-files xuống {mf}. Từ vựng sẽ kém tin cậy.", file=sys.stderr)
        vocab = build_vocab(corpus, a.min_pages if n_files > 5 else max(2, a.min_pages // 10), mf, a.max_top_ratio)
    if a.save_vocab:
        a.save_vocab.write_text(json.dumps(sorted(vocab), ensure_ascii=False), encoding="utf-8")
    print(f"Số file: {n_files} | Kích thước từ vựng: {len(vocab):,}")
    if len(vocab) < 800:
        print("[!] Từ vựng quá nhỏ: kết quả dễ gắn cờ nhầm. Nên chạy trên toàn bộ corpus.", file=sys.stderr)

    a.out_dir.mkdir(parents=True, exist_ok=True)
    rows, per_file = [], defaultdict(Counter)
    for doc in corpus:
        for pno, ptxt in doc["pages"]:
            r = score_page(ptxt, vocab, a)
            r.update({"ticker": doc["ticker"], "year": doc["year"], "file": doc["file"].name, "page": pno})
            rows.append(r)
            per_file[(doc["ticker"], doc["year"], doc["file"].name)][r["status"]] += 1

    cols = ["ticker", "year", "file", "page", "status", "n_tokens", "valid_ratio",
            "top_token", "top_ratio", "cjk_chars", "latex_hits", "snippet"]

    def dump(path, data):
        with path.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: mở bằng Excel không lỗi dấu
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in data:
                w.writerow({k: r[k] for k in cols})

    dump(a.out_dir / "page_scores.csv", rows)
    bad = [r for r in rows if r["status"] in ("HARD", "REPEAT", "SOFT", "NOISE")]
    bad.sort(key=lambda r: ({"REPEAT": 0, "HARD": 1, "SOFT": 2, "NOISE": 3}[r["status"]], r["valid_ratio"]))
    dump(a.out_dir / "flagged_pages.csv", bad)

    # Tổng hợp theo file
    summ_cols = ["ticker", "year", "file", "pages", "scored_pages", "hard", "repeat", "soft", "noise",
                 "bad_rate_hard", "bad_rate_hard_soft", "bad_pages"]
    with (a.out_dir / "file_summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summ_cols)
        w.writeheader()
        for (t, y, fn), c in sorted(per_file.items()):
            total = sum(c.values())
            scored = total - c["SPARSE"]
            hard = c["HARD"] + c["REPEAT"]
            pages_bad = [str(r["page"]) for r in rows if r["file"] == fn and r["ticker"] == t
                         and r["year"] == y and r["status"] in ("HARD", "REPEAT", "SOFT")]
            w.writerow({
                "ticker": t, "year": y, "file": fn, "pages": total, "scored_pages": scored,
                "hard": c["HARD"], "repeat": c["REPEAT"], "soft": c["SOFT"], "noise": c["NOISE"],
                "bad_rate_hard": round(hard / scored, 4) if scored else 0,
                "bad_rate_hard_soft": round((hard + c["SOFT"]) / scored, 4) if scored else 0,
                "bad_pages": " ".join(pages_bad),
            })

    # Báo cáo tổng
    cnt = Counter(r["status"] for r in rows)
    total = len(rows)
    scored = total - cnt["SPARSE"]
    hard = cnt["HARD"] + cnt["REPEAT"]
    print("\n=== TỔNG KẾT ===")
    print(f"Tổng số trang: {total:,} (chấm điểm được: {scored:,}, ít chữ/SPARSE: {cnt['SPARSE']:,})")
    for k in ("HARD", "REPEAT", "SOFT", "NOISE", "OK"):
        print(f"  {k:7}: {cnt[k]:6,}  ({pct(cnt[k], scored)} số trang chấm được)")
    print(f"Tỉ lệ trang hỏng nặng (HARD+REPEAT): {pct(hard, scored)}")
    print(f"Tỉ lệ trang hỏng + nghi ngờ (HARD+REPEAT+SOFT): {pct(hard + cnt['SOFT'], scored)}")

    files_any = sum(1 for c in per_file.values() if c["HARD"] + c["REPEAT"] > 0)
    files_soft = sum(1 for c in per_file.values() if c["HARD"] + c["REPEAT"] + c["SOFT"] > 0)
    print(f"File có >= 1 trang hỏng nặng: {files_any}/{n_files} ({pct(files_any, n_files)})")
    print(f"File có >= 1 trang hỏng/nghi ngờ: {files_soft}/{n_files} ({pct(files_soft, n_files)})")

    vr = [r["valid_ratio"] for r in rows if r["status"] != "SPARSE"]
    if len(vr) >= 10:
        q = statistics.quantiles(vr, n=20)
        print(f"Phân bố valid_ratio (trang chấm được): P5={q[0]:.2f}  P25={q[4]:.2f}  "
              f"trung vị={q[9]:.2f}  P75={q[14]:.2f}  P95={q[18]:.2f}")
        print("  -> Nếu trung vị < 0.85, từ vựng còn nhỏ hoặc ngưỡng cần chỉnh.")

    by_ticker = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["status"] == "SPARSE":
            continue
        by_ticker[r["ticker"]][1] += 1
        if r["status"] in ("HARD", "REPEAT", "SOFT"):
            by_ticker[r["ticker"]][0] += 1
    worst = sorted(by_ticker.items(), key=lambda kv: -kv[1][0] / max(1, kv[1][1]))[:10]
    print("\nCông ty có tỉ lệ trang hỏng/nghi ngờ cao nhất:")
    for t, (b, s) in worst:
        if b:
            print(f"  {t:8} {b}/{s} ({pct(b, s)})")

    print("\n20 trang đáng kiểm tra trước (REPEAT/HARD trước):")
    for r in bad[:20]:
        print(f"  {r['status']:6} {r['ticker']}_{r['year']} trang {r['page']:>3} "
              f"valid={r['valid_ratio']:.2f} top={r['top_ratio']:.2f} | {r['snippet'][:60]}")
    print(f"\nĐã ghi: {a.out_dir/'page_scores.csv'}, {a.out_dir/'flagged_pages.csv'}, {a.out_dir/'file_summary.csv'}")


if __name__ == "__main__":
    main()