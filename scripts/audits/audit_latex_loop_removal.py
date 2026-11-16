import re
from pathlib import Path

RAW_DIR = Path("data/raw_docs/top_100")

def audit_cleaners():
    files = sorted(RAW_DIR.rglob("*.txt"))
    files = [f for f in files if f.name != "giai_trinh_lien_quan.txt"]
    
    latex_over_100 = []
    loop_collapses = []
    
    loop_pat = re.compile(r"(.{2,50}?)\1{5,}")
    
    def _safe_clean_latex(m: re.Match, fpath: Path, pnum: int):
        s = m.group(0)
        # Check rule
        has_table = "<table" in s
        has_big_num = bool(re.search(r"\d{1,3}(?:\.\d{3}){2,}", s))
        is_long_viet = len(s) > 300 and len(re.findall(r"[a-zA-ZÀ-ỹ]{4,}", s)) > 5
        
        will_keep = has_table or has_big_num or is_long_viet
        
        if len(s) > 100:
            latex_over_100.append({
                "file": fpath.stem,
                "page": pnum,
                "length": len(s),
                "will_keep": will_keep,
                "has_table": has_table,
                "has_big_num": has_big_num,
                "preview": s[:150].replace("\n", " ") + ("..." if len(s) > 150 else "")
            })
        return " " if not will_keep else s

    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        # split pages
        parts = re.split(r"=====\s*PAGE\s*(\d+)\s*=====", text)
        pages = []
        if len(parts) > 1:
            for i in range(1, len(parts), 2):
                pnum = int(parts[i])
                ptext = parts[i+1]
                pages.append((pnum, ptext))
        else:
            pages = [(1, text)]
            
        for pnum, ptext in pages:
            # Audit LaTeX
            re.sub(r"\\\(.*?(?:\\\)|(?=\n|<table|$))", lambda m: _safe_clean_latex(m, f, pnum), ptext, flags=re.DOTALL)
            re.sub(r"\\\[.*?(?:\\\]|(?=\n|<table|$))", lambda m: _safe_clean_latex(m, f, pnum), ptext, flags=re.DOTALL)
            
            # Audit Loop
            for m in loop_pat.finditer(ptext):
                unit = m.group(1)
                full = m.group(0)
                has_letter = bool(re.search(r"[^\W\d_]", unit))
                # Check if it was purely digits/puncts
                if not has_letter:
                    # This was preserved thanks to the fix!
                    loop_collapses.append({
                        "file": f.stem,
                        "page": pnum,
                        "action": "PRESERVED_NUMBER",
                        "unit": unit,
                        "length": len(full),
                        "snippet": full[:60]
                    })
                else:
                    # Collapsed
                    loop_collapses.append({
                        "file": f.stem,
                        "page": pnum,
                        "action": "COLLAPSED_TEXT",
                        "unit": unit,
                        "length": len(full),
                        "snippet": full[:60]
                    })

    print(f"=== KẾT QUẢ RÀ SOÁT LATEX REMOVAL > 100 KÝ TỰ ===")
    print(f"Tổng số trường hợp match LaTeX > 100 ký tự: {len(latex_over_100)}")
    deleted = [x for x in latex_over_100 if not x['will_keep']]
    kept = [x for x in latex_over_100 if x['will_keep']]
    print(f"- Số trường hợp ĐƯỢC GIỮ LẠI (bảo vệ an toàn dữ liệu/bảng/số): {len(kept)}")
    print(f"- Số trường hợp BỊ XÓA (rác LaTeX thực sự không chứa bảng/số): {len(deleted)}")
    
    if deleted:
        print("\nDanh sách các trang bị xóa LaTeX > 100 ký tự (toàn bộ là công thức/chữ rác không chứa số kế toán/bảng):")
        for d in deleted:
            print(f"  + [{d['file']}] Trang {d['page']} (len={d['length']}): {d['preview']}")
    else:
        print("Không có trường hợp nào bị xóa quá 100 ký tự!")
        
    if kept:
        print("\nCác trường hợp được BẢO VỆ KHÔNG BỊ XÓA:")
        for k in kept:
            reason = "BẢNG (<table>)" if k['has_table'] else ("SỐ TIỀN LỚN" if k['has_big_num'] else "VĂN BẢN")
            print(f"  + [{k['file']}] Trang {k['page']} (len={k['length']}, lý do giữ: {reason}): {k['preview']}")

    print(f"\n=== KẾT QUẢ RÀ SOÁT LOOP PATTERN (.{{2,50}}?)\\1{{5,}} ===")
    preserved_nums = [x for x in loop_collapses if x['action'] == "PRESERVED_NUMBER"]
    collapsed_txts = [x for x in loop_collapses if x['action'] == "COLLAPSED_TEXT"]
    print(f"- Số chuỗi lặp được bảo vệ nguyên vẹn (dãy số/dấu, không bị cắt hỏng số): {len(preserved_nums)}")
    for pn in preserved_nums[:5]:
        print(f"  + [{pn['file']}] Trang {pn['page']}: unit='{pn['unit']}' | snippet={pn['snippet']}")
    print(f"- Số chuỗi văn bản lặp được thu gọn (chứa chữ cái): {len(collapsed_txts)}")
    for ct in collapsed_txts[:5]:
        print(f"  + [{ct['file']}] Trang {ct['page']}: unit='{ct['unit']}' | snippet={ct['snippet']}")

if __name__ == "__main__":
    audit_cleaners()
