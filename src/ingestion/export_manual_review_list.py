"""
Script trích xuất danh sách các lỗi và ô nghi ngờ (suspect/failed identities)
cần rà soát thủ công (Manual Review) từ thư mục data/processed_chunks.
Xuất kết quả ra file Excel (.xlsx) và file CSV (.csv) với cột cuối cùng 'gia_tri_sua' để trống.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


def export_manual_review_items(
    processed_dir: Path,
    output_excel: Path,
    output_csv: Path,
) -> None:
    json_files = sorted(
        f for f in processed_dir.glob("*.json")
        if not f.name.startswith("_")
    )

    rows: List[Dict[str, Any]] = []

    for fpath in json_files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[Cảnh báo] Lỗi khi đọc {fpath.name}: {e}")
            continue

        doc_id = data.get("doc_id", fpath.stem)
        ticker = data.get("ticker", "")
        fiscal_year = data.get("fiscal_year", "")
        scope = data.get("scope", "")
        default_unit = data.get("default_unit", "")
        quality = data.get("quality", {})
        gating_status = quality.get("gating_status", "")

        # 1. Thu thập các ô số liệu bị đánh dấu suspect=True
        suspect_cells = quality.get("suspect_cells", [])
        for item in suspect_cells:
            rows.append({
                "stt": len(rows) + 1,
                "doc_id": doc_id,
                "ma_ck": ticker,
                "nam": fiscal_year,
                "pham_vi": scope,
                "trang_pdf": item.get("physical_page", ""),
                "loai_loi": "SUSPECT_CELL (Số liệu lẫn chữ / lỗi con dấu / định dạng)",
                "loai_bao_cao": item.get("report_type", ""),
                "ma_so": item.get("code") or "",
                "ten_chi_tieu": item.get("label", ""),
                "cot_du_lieu": item.get("column", ""),
                "chuoi_goc_raw": str(item.get("raw", "")),
                "don_vi_tinh": default_unit,
                "ly_do_chi_tiet": item.get("reason", ""),
                "gia_tri_sua": "",  # Cột cuối cùng để trống cho người dùng điền
            })

        # 2. Thu thập các đẳng thức kế toán bị lệch (identity checks failed)
        identity_checks = quality.get("identity_checks", [])
        for chk in identity_checks:
            if not chk.get("passed", True):
                diff_val = chk.get("diff")
                diff_str = f"{diff_val:,.2f}" if diff_val is not None else ""
                lhs_val = chk.get("lhs_value")
                lhs_str = f"{lhs_val:,.2f}" if lhs_val is not None else ""
                rhs_val = chk.get("rhs_value")
                rhs_str = f"{rhs_val:,.2f}" if rhs_val is not None else ""
                
                rows.append({
                    "stt": len(rows) + 1,
                    "doc_id": doc_id,
                    "ma_ck": ticker,
                    "nam": fiscal_year,
                    "pham_vi": scope,
                    "trang_pdf": "",
                    "loai_loi": "FAILED_IDENTITY (Lệch đẳng thức kế toán)",
                    "loai_bao_cao": chk.get("report_type", ""),
                    "ma_so": chk.get("check_name", ""),
                    "ten_chi_tieu": f"Công thức: {chk.get('formula', '')}",
                    "cot_du_lieu": chk.get("period", ""),
                    "chuoi_goc_raw": f"Vế trái (LHS)={lhs_str} | Vế phải (RHS)={rhs_str} | Lệch={diff_str}",
                    "don_vi_tinh": default_unit,
                    "ly_do_chi_tiet": f"Đẳng thức {chk.get('check_name')} không khớp. Quy ước: {chk.get('sign_convention', '')}",
                    "gia_tri_sua": "",  # Cột cuối cùng để trống cho người dùng điền
                })

        # 3. Thu thập trường hợp không trích xuất được bảng (NO_CHECKABLE_TABLES)
        if quality.get("identity_status") == "NO_CHECKABLE_TABLES" and not suspect_cells:
            for reason in quality.get("gating_reasons", []):
                rows.append({
                    "stt": len(rows) + 1,
                    "doc_id": doc_id,
                    "ma_ck": ticker,
                    "nam": fiscal_year,
                    "pham_vi": scope,
                    "trang_pdf": "",
                    "loai_loi": "MISSING_STATEMENT_TABLE (Không tìm thấy bảng BCTC chính)",
                    "loai_bao_cao": "",
                    "ma_so": "",
                    "ten_chi_tieu": "",
                    "cot_du_lieu": "",
                    "chuoi_goc_raw": "",
                    "don_vi_tinh": default_unit,
                    "ly_do_chi_tiet": reason,
                    "gia_tri_sua": "",  # Cột cuối cùng để trống cho người dùng điền
                })

    df = pd.DataFrame(rows)

    # Đảm bảo thư mục lưu trữ tồn tại
    output_excel.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    # Xuất file CSV (UTF-8 with BOM để mở trực tiếp trong Excel tiếng Việt không bị lỗi font)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    # Xuất file Excel định dạng đẹp
    try:
        with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Danh_sach_can_sua", index=False)
            ws = writer.sheets["Danh_sach_can_sua"]
            
            # Căn chỉnh độ rộng cột tự động
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 50)
            
            # Đặt độ rộng riêng cho cột sửa cuối cùng
            ws.column_dimensions["O"].width = 25
    except Exception as e:
        print(f"[Cảnh báo] Lỗi khi tạo file Excel: {e}")

    print("=" * 80)
    print("HOÀN THÀNH TRÍCH XUẤT DANH SÁCH MANUAL REVIEW")
    print("=" * 80)
    print(f"- Tổng số mục lỗi / nghi ngờ cần rà soát: {len(df)}")
    if not df.empty:
        type_counts = df["loai_loi"].value_counts().to_dict()
        for k, v in type_counts.items():
            print(f"  + {k}: {v} mục")
    print(f"- File Excel đã lưu: {output_excel}")
    print(f"- File CSV đã lưu:   {output_csv}")
    print("=" * 80)


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    default_proc_dir = project_root / "data" / "processed_chunks"
    default_excel = project_root / "evaluation" / "token_statistics" / "danh_sach_loi_manual_review.xlsx"
    default_csv = project_root / "evaluation" / "token_statistics" / "danh_sach_loi_manual_review.csv"

    parser = argparse.ArgumentParser(
        description="Xuất danh sách các lỗi và ô suspect cần chỉnh sửa manual."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=default_proc_dir,
        help="Thư mục chứa các file JSON processed (mặc định: data/processed_chunks)",
    )
    parser.add_argument(
        "--output-excel",
        type=Path,
        default=default_excel,
        help="Đường dẫn lưu file Excel (mặc định: evaluation/token_statistics/danh_sach_loi_manual_review.xlsx)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=default_csv,
        help="Đường dẫn lưu file CSV (mặc định: evaluation/token_statistics/danh_sach_loi_manual_review.csv)",
    )

    args = parser.parse_args()
    export_manual_review_items(args.input_dir, args.output_excel, args.output_csv)


if __name__ == "__main__":
    main()
