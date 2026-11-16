import json
import re
from pathlib import Path

def main():
    # 1. QNS 2025 CASH_FLOW
    raw_qns = Path("data/raw_docs/top_100/QNS/2025/QNS_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt")
    print("QNS raw exists:", raw_qns.exists())
    if raw_qns.exists():
        text = raw_qns.read_text(encoding="utf-8")
        print("QNS has <table> in CASH_FLOW?:", "<table" in text[text.find("BÁO CÁO LƯU CHUYÊN"):text.find("BÁO CÁO LƯU CHUYÊN")+5000] if "BÁO CÁO LƯU CHUYÊN" in text else "Not found")

    # Check backup for QNS
    backup_qns = Path("data/backup_data/raw_docs_top_100_backup/QNS/2025")
    print("QNS backup dir exists:", backup_qns.exists())
    if backup_qns.exists():
        for f in backup_qns.glob("*.txt"):
            print("  Backup file:", f.name)
            btext = f.read_text(encoding="utf-8")
            print("  Backup has <table>:", "<table" in btext)

    # 2. ABB 2024 BALANCE_SHEET
    print("\n--- ABB 2024 HEADINGS IN RAW ---")
    raw_abb = Path("data/raw_docs/top_100/ABB/2024/ABB_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt")
    if raw_abb.exists():
        raw_text = raw_abb.read_text(encoding="utf-8")
        lines = raw_text.split("\n")
        for idx, line in enumerate(lines[:350]):
            l = line.strip()
            if any(k in l.lower() for k in ["báo cáo", "bảng cân đối", "tình hình tài chính", "b01", "b 01", "mẫu số", "b02", "b03"]):
                print(f"Line {idx}: {l}")

if __name__ == "__main__":
    main()
