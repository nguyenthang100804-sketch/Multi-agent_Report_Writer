"""
Pipeline Làm Sạch Nội Dung BCTC Top 100 & Tính Lại Số Lượng Token Gemini
========================================================================
Dự án: Multi-Agent Framework to Write Report from Documents
Mục tiêu:
  1. Thực thi Pipeline 5 tầng làm sạch nội dung cho toàn bộ 410 file trong data/raw_docs/top_100.
  2. Bảo toàn 100% độ chính xác số học kế toán, cấu trúc bảng biểu và khả năng truy vết trang [P.X].
  3. Tính toán lại số lượng token Gemini (gemini-2.5-flash) bằng LocalTokenizer chính thức.
  4. Xuất các bảng thống kê CSV chi tiết, file so sánh trước/sau làm sạch và 2 biểu đồ Scatter Plot chuẩn.

Pipeline 5 tầng:
  - Tầng 1: Khử Báo cáo Kép / Phần Tiếng Anh dịch nối tiếp & Bản USD phụ của PVD.
  - Tầng 2: Dọn Rác Ảo giác VLM (câu từ chối QR code, fake LaTeX con dấu, chuỗi ô vuông □, CJK loop).
  - Tầng 3: Khử Lặp Running Header/Footer & Watermark (dòng lặp >= 25% trang, watermark e-Office, nén [P.X]).
  - Tầng 4: Nén Bảng HTML sang Compact Pipe Table (loại bỏ tr/td rỗng, chuyển thẻ sang |, xóa dòng số cột).
  - Tầng 5: Nén Dòng Trống & Chuỗi Ký tự Dẫn dòng (chấm dẫn ...., gạch nối ----, gộp dòng trống).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import ssl
import sys
import tempfile
import time
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

# Đường dẫn dự án
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw_docs" / "top_100"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "token_statistics"
DEFAULT_BASELINE_CSV = DEFAULT_OUTPUT_DIR / "raw_baseline_stats" / "token_stats_all_files.csv"
DEFAULT_MODEL = "gemini-2.5-flash"

# Model SentencePiece cho Gemini
_GEMMA3_SPIECE_URL = (
    "https://raw.githubusercontent.com/google/gemma_pytorch/"
    "014acb7ac4563a5f77c76d7ff98f31b568c16508/tokenizer/gemma3_cleaned_262144_v2.spiece.model"
)
_GEMMA3_SPIECE_SHA256 = "1299c11d7cf632ef3b4e11937501358ada021bbdf7c47638d13c0ee982f2e79c"

# Danh mục 30 file báo cáo kép (bilingual VN-EN hoặc VND-USD) đã được xác minh trang cắt chính xác
BILINGUAL_AND_DUPLICATE_CUTS: Dict[Tuple[str, int], int] = {
    ("DIG", 2024): 59,
    ("DIG", 2025): 60,
    ("DPM", 2024): 51,
    ("GEE", 2024): 64,
    ("GVR", 2024): 78,
    ("GVR", 2025): 103,
    ("IDC", 2024): 68,
    ("KDC", 2024): 57,  # Trang 57 là EY boilerplate, trang 58 là bìa tiếng Anh
    ("MSR", 2022): 74,
    ("MSR", 2023): 78,
    ("MSR", 2025): 59,
    ("NLG", 2025): 65,
    ("OCB", 2024): 80,
    ("OCB", 2025): 105,
    ("PGV", 2025): 41,
    ("PNJ", 2025): 53,
    ("PVD", 2022): 53,  # Trang 52 phê duyệt BCTC chuyển đổi VND, trang 53 bắt đầu bản USD
    ("PVD", 2023): 54,  # Trang 53 phê duyệt BCTC chuyển đổi VND, trang 54 bắt đầu bản USD
    ("PVD", 2024): 54,  # Trang 53 phê duyệt BCTC chuyển đổi VND, trang 54 bắt đầu bản USD
    ("PVD", 2025): 58,  # Trang 57 phê duyệt BCTC chuyển đổi VND, trang 58 bắt đầu bản USD
    ("PVS", 2024): 96,
    ("PVS", 2025): 74,
    ("SAB", 2022): 76,
    ("SAB", 2023): 76,
    ("SAB", 2024): 75,
    ("SSI", 2024): 100,
    ("VHM", 2024): 105,  # Trang 105 là EY boilerplate, trang 106 là bìa tiếng Anh
    ("VHM", 2025): 113,
    ("VTP", 2024): 56,
    ("VTP", 2025): 55,
}


def ensure_local_tokenizer_cached() -> None:
    """Tải và lưu cache model SentencePiece của Gemini trên máy cục bộ."""
    model_dir = Path(tempfile.gettempdir()) / "vertexai_tokenizer_model"
    model_dir.mkdir(parents=True, exist_ok=True)
    filename = hashlib.sha1(_GEMMA3_SPIECE_URL.encode("utf-8")).hexdigest()
    model_path = model_dir / filename

    if model_path.exists():
        data = model_path.read_bytes()
        if hashlib.sha256(data).hexdigest() == _GEMMA3_SPIECE_SHA256:
            return

    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(_GEMMA3_SPIECE_URL, context=ctx) as resp:
        data = resp.read()
    actual_hash = hashlib.sha256(data).hexdigest()
    if actual_hash != _GEMMA3_SPIECE_SHA256:
        raise ValueError(f"SHA256 không khớp! Expected {_GEMMA3_SPIECE_SHA256}, got {actual_hash}")
    model_path.write_bytes(data)


# =============================================================================
# HÀM LÀM SẠCH VĂN BẢN (5 TẦNG)
# =============================================================================

def clean_report_content(text: str, ticker: str, year: int, is_giai_trinh: bool = False) -> str:
    """
    Thực thi 5 tầng làm sạch nội dung cho văn bản BCTC.
    Bảo toàn toàn bộ số liệu kế toán và đánh dấu số trang [P.X].
    """
    # -------------------------------------------------------------
    # TẦNG 1: Khử Báo cáo Kép / Phần Tiếng Anh trùng lặp
    # -------------------------------------------------------------
    if not is_giai_trinh:
        cut_page = BILINGUAL_AND_DUPLICATE_CUTS.get((ticker, year))
        chunks = re.split(r'(===== PAGE \d+ =====)', text)
        if cut_page is not None and len(chunks) > 1:
            retained = [chunks[0]]
            for i in range(1, len(chunks), 2):
                pnum = int(re.search(r'\d+', chunks[i]).group())
                if pnum < cut_page:
                    retained.append(chunks[i])
                    if i + 1 < len(chunks):
                        retained.append(chunks[i + 1])
            text = ''.join(retained)

    # -------------------------------------------------------------
    # TẦNG 2: Dọn Rác Ảo giác VLM & Nhiễu OCR
    # -------------------------------------------------------------
    # 1. Câu từ chối đọc QR/ảnh của VLM
    text = re.sub(
        r'The image (?:provided is a QR code|contains no text|does not contain any text)[^\n]*\n?',
        '',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'Therefore, no textual content can be extracted[^\n]*\n?',
        '',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'The OCR result \"[^\"]*\" is a hallucination[^\n]*\n?',
        '',
        text,
        flags=re.IGNORECASE,
    )

    # 2. Footnotes dạng mũ: \(^{(1)}\) -> (1), \( ^{(i)} \) -> (i)
    text = re.sub(r'\\\( ?\^\{?([\d\*\(\)a-zA-Z]+)\}? ?\\\)', r'(\1)', text)
    # Loại bỏ các biểu thức LaTeX ảo giác từ con dấu đỏ/chữ ký
    text = re.sub(r'\\\(.*?\\\)', '', text)
    text = re.sub(r'\\\[.*?\\\]', '', text)

    # 3. Chuỗi ô vuông viền trang
    text = re.sub(r'[□■▪▫◊○●\s]{4,}', ' ', text)

    # 4. Ký tự CJK & vòng lặp suy biến
    text = re.sub(r'[\u4e00-\u9fff]+', '', text)
    text = re.sub(r'(\(\d+\)\s*)+', '', text)

    # -------------------------------------------------------------
    # TẦNG 3: Khử Lặp Running Header/Footer & Watermark
    # -------------------------------------------------------------
    pages_raw = re.split(r'(===== PAGE \d+ =====)', text)
    if len(pages_raw) > 1:
        line_counts: Dict[str, int] = {}
        page_items = []
        for i in range(1, len(pages_raw), 2):
            marker = pages_raw[i]
            pnum = int(re.search(r'\d+', marker).group())
            pcontent = pages_raw[i + 1] if i + 1 < len(pages_raw) else ''

            outside_tbl = re.sub(r'<table.*?>.*?</table>', '', pcontent, flags=re.DOTALL | re.IGNORECASE)
            seen_in_page = set()
            for line in outside_tbl.split('\n'):
                line_str = line.strip()
                if len(line_str) >= 4 and not line_str.isdigit() and not line_str.startswith('====='):
                    seen_in_page.add(line_str)
            for l in seen_in_page:
                line_counts[l] = line_counts.get(l, 0) + 1
            page_items.append((pnum, pcontent))

        total_p = len(page_items)
        freq_threshold = max(5, int(total_p * 0.25)) if total_p >= 8 else 999
        repetitive_lines = {l for l, c in line_counts.items() if c >= freq_threshold}

        processed_pages = [pages_raw[0]]
        seen_first_time = set()
        for pnum, pcontent in page_items:
            new_marker = f'[P.{pnum}]\n'
            lines = pcontent.split('\n')
            new_lines = []
            in_table = False
            for line in lines:
                l_strip = line.strip()
                if '<table' in l_strip.lower():
                    in_table = True
                if in_table:
                    new_lines.append(line)
                    if '</table>' in l_strip.lower():
                        in_table = False
                    continue

                # Số trang in đơn lẻ dạng số: 45, 102
                if re.match(r'^\d{1,4}$', l_strip):
                    continue

                # Watermark e-office
                if 'eoffice' in l_strip.lower() or 'văn bản được tải lên hệ thống' in l_strip.lower():
                    continue

                # Dòng chỉ chứa dãy số thứ tự cột 1. 2. 3. 4.
                if re.match(r'^(?:\(?\d+\)?[\.\s]*){4,}$', l_strip):
                    continue

                if l_strip in repetitive_lines:
                    if l_strip not in seen_first_time:
                        seen_first_time.add(l_strip)
                        new_lines.append(line)
                    # Lược bỏ các lần lặp ở trang sau
                else:
                    new_lines.append(line)

            processed_pages.append(new_marker + '\n'.join(new_lines))
        text = '\n'.join(processed_pages)
    else:
        text = re.sub(r'===== PAGE (\d+) =====', r'[P.\1]', text)

    # -------------------------------------------------------------
    # TẦNG 4: Nén Bảng HTML sang Compact Pipe Table
    # -------------------------------------------------------------
    def compact_table(match: re.Match) -> str:
        tbl_html = match.group(0)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl_html, flags=re.DOTALL | re.IGNORECASE)
        pipe_rows = []
        for r in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, flags=re.DOTALL | re.IGNORECASE)
            cleaned_cells = []
            for c in cells:
                c_clean = re.sub(r'<[^>]+>', '', c)
                c_clean = html.unescape(c_clean).strip()
                c_clean = re.sub(r'\s+', ' ', c_clean)
                cleaned_cells.append(c_clean)

            # Cắt bỏ các ô rỗng ở cuối dòng
            while cleaned_cells and not cleaned_cells[-1]:
                cleaned_cells.pop()

            # Nếu cả dòng rỗng -> bỏ qua
            if not cleaned_cells or all(c == '' for c in cleaned_cells):
                continue

            # Bỏ dòng số thứ tự cột: (1) | (2) | (3) | (4)
            if all(re.match(r'^\(?\d+\)?$', c) for c in cleaned_cells if c):
                if len(cleaned_cells) >= 3:
                    continue

            pipe_rows.append(' | '.join(cleaned_cells))

        if not pipe_rows:
            return ''
        return '\n' + '\n'.join(pipe_rows) + '\n'

    text = re.sub(r'<table[^>]*>.*?</table>', compact_table, text, flags=re.DOTALL | re.IGNORECASE)

    # -------------------------------------------------------------
    # TẦNG 5: Nén Dòng Trống & Chuỗi Ký tự Dẫn dòng
    # -------------------------------------------------------------
    text = re.sub(r'\.{4,}', ' ', text)
    text = re.sub(r'-{4,}', ' ', text)
    clean_lines = [l.strip() for l in text.split('\n')]
    final_lines = []
    last_empty = False
    for l in clean_lines:
        if not l:
            if not last_empty:
                final_lines.append('')
                last_empty = True
        else:
            final_lines.append(l)
            last_empty = False

    return '\n'.join(final_lines).strip() + '\n'


# =============================================================================
# BỘ ĐẾM TOKEN & XỬ LÝ DỮ LIỆU
# =============================================================================

class PipelineExecutor:
    """Điều phối toàn bộ quá trình làm sạch và tính toán token mới."""

    def __init__(self, data_dir: Path, output_dir: Path, model_name: str = DEFAULT_MODEL, workers: int = 4) -> None:
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.model_name = model_name
        self.workers = workers
        ensure_local_tokenizer_cached()
        from google.genai.local_tokenizer import LocalTokenizer

        self.tokenizer = LocalTokenizer(model_name=self.model_name)

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return int(self.tokenizer.count_tokens(text).total_tokens)

    def process_and_clean_all(self, baseline_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Duyệt qua tất cả 410 file, làm sạch nội dung tại chỗ (in-place) trong data/raw_docs/top_100,
        và tính toán lại token mới.
        """
        records: List[Dict] = []
        tickers = sorted([d.name for d in self.data_dir.iterdir() if d.is_dir()])
        all_file_tasks = []

        for ticker in tickers:
            ticker_dir = self.data_dir / ticker
            years = sorted([y.name for y in ticker_dir.iterdir() if y.is_dir()])
            for year in years:
                year_dir = ticker_dir / year
                txt_files = sorted(year_dir.glob("*.txt"))
                for txt_file in txt_files:
                    is_giai_trinh = txt_file.name == "giai_trinh_lien_quan.txt"
                    all_file_tasks.append((ticker, int(year), txt_file, is_giai_trinh))

        total_files = len(all_file_tasks)
        print(f"Bắt đầu làm sạch và tính lại token cho {total_files} files tại: {self.data_dir}")

        baseline_map = {}
        if baseline_df is not None:
            for _, r in baseline_df.iterrows():
                baseline_map[r["relative_path"]] = {
                    "raw_chars": r["char_count"],
                    "raw_tokens": r["gemini_tokens"],
                }

        t0 = time.time()
        for idx, (ticker, year, txt_file, is_giai_trinh) in enumerate(all_file_tasks, start=1):
            raw_content = txt_file.read_text(encoding="utf-8", errors="ignore")
            raw_chars = len(raw_content)

            # Thực thi pipeline 5 tầng
            cleaned_content = clean_report_content(raw_content, ticker, year, is_giai_trinh=is_giai_trinh)
            cleaned_chars = len(cleaned_content)

            # Ghi đè file sạch vào vị trí chính thức
            txt_file.write_text(cleaned_content, encoding="utf-8")

            # Đếm token mới
            clean_tokens = self.count_tokens(cleaned_content)
            approx_clean_tokens = round(cleaned_chars / 4)

            # Lấy baseline nếu có
            rel_path = f"{ticker}/{year}/{txt_file.name}"
            base_info = baseline_map.get(rel_path, {})
            raw_tokens = base_info.get("raw_tokens", clean_tokens)
            tokens_saved = raw_tokens - clean_tokens
            pct_token_reduction = (tokens_saved / raw_tokens * 100.0) if raw_tokens > 0 else 0.0

            if is_giai_trinh:
                doc_type = "GiaiTrinh"
            elif "_Hopnhat_p1_" in txt_file.name or "_Hopnhat_p2_" in txt_file.name:
                doc_type = "BCTC_Hopnhat_Part"
            elif "_Hopnhat_" in txt_file.name:
                doc_type = "BCTC_Hopnhat"
            elif "_Riengle_" in txt_file.name:
                doc_type = "BCTC_Riengle"
            else:
                doc_type = "BCTC_Kiemtoan"

            records.append(
                {
                    "ticker": ticker,
                    "year": year,
                    "file_name": txt_file.name,
                    "relative_path": rel_path,
                    "is_giai_trinh": is_giai_trinh,
                    "doc_type": doc_type,
                    "raw_char_count": raw_chars,
                    "clean_char_count": cleaned_chars,
                    "char_reduction_pct": round((raw_chars - cleaned_chars) / raw_chars * 100.0, 2),
                    "raw_gemini_tokens": raw_tokens,
                    "clean_gemini_tokens": clean_tokens,
                    "tokens_saved": tokens_saved,
                    "token_reduction_pct": round(pct_token_reduction, 2),
                    "approx_clean_tokens_4chars": approx_clean_tokens,
                }
            )

            if idx % 50 == 0 or idx == total_files:
                elapsed = time.time() - t0
                print(f"  -> Đã làm sạch & tính lại token: {idx}/{total_files} files ({elapsed:.1f}s)")

        return pd.DataFrame(records)


def build_aggregated_tables(df_files: pd.DataFrame):
    """
    Xây dựng bảng tổng hợp cấp Báo cáo (Merged POW) và cấp Công ty (100 công ty).
    """
    df_bctc_files = df_files[~df_files["is_giai_trinh"]].copy().reset_index(drop=True)

    # Bảng Merged BCTC (gộp POW 2025 p1+p2)
    merged_rows = []
    skip_indices = set()
    for i, row in df_bctc_files.iterrows():
        if i in skip_indices:
            continue
        if row["ticker"] == "POW" and row["year"] == 2025 and "_p1_" in row["file_name"]:
            p2_matches = df_bctc_files[
                (df_bctc_files["ticker"] == "POW")
                & (df_bctc_files["year"] == 2025)
                & (df_bctc_files["file_name"].str.contains("_p2_"))
            ]
            if not p2_matches.empty:
                p2_idx = p2_matches.index[0]
                p2_row = p2_matches.iloc[0]
                skip_indices.add(p2_idx)
                merged_rows.append(
                    {
                        "ticker": "POW",
                        "year": 2025,
                        "file_name": "POW_2025_BCTC_Kiemtoan_Hopnhat_p1+p2_extracted.txt",
                        "relative_path": "POW/2025/POW_2025_BCTC_Kiemtoan_Hopnhat_p1+p2_extracted.txt",
                        "is_giai_trinh": False,
                        "doc_type": "BCTC_Hopnhat",
                        "raw_char_count": int(row["raw_char_count"] + p2_row["raw_char_count"]),
                        "clean_char_count": int(row["clean_char_count"] + p2_row["clean_char_count"]),
                        "char_reduction_pct": round(
                            (
                                (row["raw_char_count"] + p2_row["raw_char_count"])
                                - (row["clean_char_count"] + p2_row["clean_char_count"])
                            )
                            / (row["raw_char_count"] + p2_row["raw_char_count"])
                            * 100.0,
                            2,
                        ),
                        "raw_gemini_tokens": int(row["raw_gemini_tokens"] + p2_row["raw_gemini_tokens"]),
                        "clean_gemini_tokens": int(row["clean_gemini_tokens"] + p2_row["clean_gemini_tokens"]),
                        "tokens_saved": int(row["tokens_saved"] + p2_row["tokens_saved"]),
                        "token_reduction_pct": round(
                            (row["tokens_saved"] + p2_row["tokens_saved"])
                            / (row["raw_gemini_tokens"] + p2_row["raw_gemini_tokens"])
                            * 100.0,
                            2,
                        ),
                        "approx_clean_tokens_4chars": int(
                            row["approx_clean_tokens_4chars"] + p2_row["approx_clean_tokens_4chars"]
                        ),
                    }
                )
                continue
        merged_rows.append(row.to_dict())

    df_reports_merged = pd.DataFrame(merged_rows)

    # Bảng Cấp Công Ty (100 công ty)
    company_rows = []
    for ticker, grp in df_files.groupby("ticker", sort=True):
        bctc_grp = grp[~grp["is_giai_trinh"]]
        gt_grp = grp[grp["is_giai_trinh"]]

        n_bctc_files = len(bctc_grp)
        n_reports = (
            n_bctc_files - 1
            if (ticker == "POW" and any("_p1_" in fn for fn in bctc_grp["file_name"]))
            else n_bctc_files
        )

        total_clean_tokens = int(grp["clean_gemini_tokens"].sum())
        total_raw_tokens = int(grp["raw_gemini_tokens"].sum())
        tokens_saved = total_raw_tokens - total_clean_tokens
        pct_saved = (tokens_saved / total_raw_tokens * 100.0) if total_raw_tokens > 0 else 0.0

        # Phân biệt trường hợp NTP, NVB nếu chỉ tính đúng 4 báo cáo chính
        if len(bctc_grp) > 4 and ticker in ("NTP", "NVB"):
            extra_riengle = bctc_grp[bctc_grp["doc_type"] == "BCTC_Riengle"]["clean_gemini_tokens"].sum()
            primary_4reports_tokens = int(total_clean_tokens - extra_riengle)
        else:
            primary_4reports_tokens = total_clean_tokens

        company_rows.append(
            {
                "ticker": ticker,
                "num_bctc_files": n_bctc_files,
                "num_reports_merged": n_reports,
                "num_giai_trinh": len(gt_grp),
                "total_files": len(grp),
                "raw_total_chars": int(grp["raw_char_count"].sum()),
                "clean_total_chars": int(grp["clean_char_count"].sum()),
                "raw_total_tokens": total_raw_tokens,
                "clean_bctc_tokens": int(bctc_grp["clean_gemini_tokens"].sum()),
                "clean_giai_trinh_tokens": int(gt_grp["clean_gemini_tokens"].sum()),
                "clean_total_tokens": total_clean_tokens,
                "total_tokens_saved": tokens_saved,
                "token_reduction_pct": round(pct_saved, 2),
                "clean_4reports_strict_tokens": primary_4reports_tokens,
                "clean_avg_tokens_per_year": float(total_clean_tokens) / 4.0,
            }
        )

    df_companies = pd.DataFrame(company_rows)
    return df_bctc_files, df_reports_merged, df_companies


# =============================================================================
# VẼ VÀ XUẤT 2 BIỂU ĐỒ SCATTER PLOT MỚI
# =============================================================================

def plot_updated_scatter_charts(
    df_bctc_files: pd.DataFrame,
    df_companies: pd.DataFrame,
    output_dir: Path,
) -> Tuple[Path, Path]:
    """Xuất 2 ảnh scatter plot mô tả phân phối số lượng token đã làm sạch."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["Segoe UI", "Arial", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    # -------------------------------------------------------------------------
    # HÌNH 1: Scatter Plot Báo cáo đã làm sạch
    # -------------------------------------------------------------------------
    fig1, ax1 = plt.subplots(figsize=(14, 7), dpi=200)
    year_palette = {
        2022: "#2563eb",  # Xanh dương
        2023: "#16a34a",  # Xanh lá
        2024: "#ea580c",  # Cam
        2025: "#9333ea",  # Tím
    }

    df_plot_rep = df_bctc_files.sort_values(["ticker", "year", "file_name"]).reset_index(drop=True)
    df_plot_rep["report_idx"] = np.arange(1, len(df_plot_rep) + 1)

    for year, grp in df_plot_rep.groupby("year"):
        ax1.scatter(
            grp["report_idx"],
            grp["clean_gemini_tokens"],
            label=f"Năm {year} ({len(grp)} file)",
            color=year_palette.get(year, "#475569"),
            alpha=0.78,
            s=42,
            edgecolors="white",
            linewidth=0.5,
            zorder=3,
        )

    mean_rep = df_plot_rep["clean_gemini_tokens"].mean()
    median_rep = df_plot_rep["clean_gemini_tokens"].median()
    max_row = df_plot_rep.loc[df_plot_rep["clean_gemini_tokens"].idxmax()]
    min_row = df_plot_rep.loc[df_plot_rep["clean_gemini_tokens"].idxmin()]

    ax1.axhline(
        mean_rep,
        color="#dc2626",
        linestyle="--",
        linewidth=1.6,
        label=f"Trung bình mới: {mean_rep:,.0f} tokens (Gốc: 71,626)",
        zorder=4,
    )
    ax1.axhline(
        median_rep,
        color="#0d9488",
        linestyle=":",
        linewidth=1.5,
        label=f"Trung vị mới: {median_rep:,.0f} tokens (Gốc: 68,140)",
        zorder=4,
    )

    # Đánh dấu Max & Min
    ax1.scatter(
        [max_row["report_idx"], min_row["report_idx"]],
        [max_row["clean_gemini_tokens"], min_row["clean_gemini_tokens"]],
        color="#dc2626",
        s=95,
        zorder=5,
        edgecolors="black",
        linewidth=1.2,
    )
    ax1.annotate(
        f"MAX MỚI: {max_row['ticker']} ({max_row['year']})\n{max_row['clean_gemini_tokens']:,} tokens (Gốc: {max_row['raw_gemini_tokens']:,})",
        xy=(max_row["report_idx"], max_row["clean_gemini_tokens"]),
        xytext=(max_row["report_idx"] - 65, max_row["clean_gemini_tokens"] * 0.92),
        arrowprops=dict(arrowstyle="->", color="#dc2626", lw=1.2),
        fontsize=9,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="#fef2f2", ec="#dc2626", lw=0.8),
        zorder=6,
    )
    ax1.annotate(
        f"MIN MỚI: {min_row['ticker']} ({min_row['year']})\n{min_row['clean_gemini_tokens']:,} tokens",
        xy=(min_row["report_idx"], min_row["clean_gemini_tokens"]),
        xytext=(min(min_row["report_idx"] + 15, len(df_plot_rep) - 60), min_row["clean_gemini_tokens"] + 18000),
        arrowprops=dict(arrowstyle="->", color="#1e293b", lw=1.2),
        fontsize=9,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="#f8fafc", ec="#475569", lw=0.8),
        zorder=6,
    )

    ax1.set_title(
        f"Phân phối Số lượng Token Gemini SAU KHI LÀM SẠCH (N = {len(df_plot_rep)} Báo cáo Tài chính)",
        fontsize=14,
        fontweight="bold",
        pad=14,
    )
    ax1.set_xlabel("Chỉ số Báo cáo (Sắp xếp theo Mã Chứng khoán A → Z & Năm 2022 → 2025)", fontsize=11)
    ax1.set_ylabel("Số lượng Token (Cleaned Gemini Tokens)", fontsize=11)
    ax1.set_ylim(8000, int(max_row["clean_gemini_tokens"] * 1.15))
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax1.grid(True, linestyle="--", alpha=0.35, zorder=0)
    ax1.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.92, fontsize=9.5)

    rep_plot_path = output_dir / "scatter_tokens_by_report.png"
    fig1.tight_layout()
    fig1.savefig(rep_plot_path, dpi=200)
    plt.close(fig1)

    # -------------------------------------------------------------------------
    # HÌNH 2: Scatter Plot Công ty đã làm sạch
    # -------------------------------------------------------------------------
    fig2, ax2 = plt.subplots(figsize=(15, 7.5), dpi=200)
    df_plot_comp = df_companies.sort_values("ticker").reset_index(drop=True)
    df_plot_comp["comp_idx"] = np.arange(1, len(df_plot_comp) + 1)

    has_gt = df_plot_comp["num_giai_trinh"] > 0
    no_gt = ~has_gt

    ax2.scatter(
        df_plot_comp.loc[no_gt, "comp_idx"],
        df_plot_comp.loc[no_gt, "clean_total_tokens"],
        label=f"Công ty chỉ có BCTC ({no_gt.sum()} công ty)",
        color="#0284c7",
        alpha=0.82,
        s=55,
        edgecolors="white",
        linewidth=0.6,
        zorder=3,
    )
    if has_gt.any():
        ax2.scatter(
            df_plot_comp.loc[has_gt, "comp_idx"],
            df_plot_comp.loc[has_gt, "clean_total_tokens"],
            label=f"Công ty có kèm Giải trình ({has_gt.sum()} công ty: IDC, MCH, SSH, VEA)",
            color="#f59e0b",
            marker="D",
            alpha=0.95,
            s=75,
            edgecolors="#78350f",
            linewidth=0.9,
            zorder=4,
        )

    mean_comp = df_plot_comp["clean_total_tokens"].mean()
    median_comp = df_plot_comp["clean_total_tokens"].median()
    max_comp = df_plot_comp.loc[df_plot_comp["clean_total_tokens"].idxmax()]
    min_comp = df_plot_comp.loc[df_plot_comp["clean_total_tokens"].idxmin()]

    ax2.axhline(
        mean_comp,
        color="#dc2626",
        linestyle="--",
        linewidth=1.6,
        label=f"Trung bình mới: {mean_comp:,.0f} tokens/công ty (Gốc: 290,314)",
        zorder=4,
    )
    ax2.axhline(
        median_comp,
        color="#0d9488",
        linestyle=":",
        linewidth=1.5,
        label=f"Trung vị mới: {median_comp:,.0f} tokens/công ty (Gốc: 279,726)",
        zorder=4,
    )

    top_high = df_plot_comp.nlargest(5, "clean_total_tokens")
    top_low = df_plot_comp.nsmallest(3, "clean_total_tokens")
    for _, r in pd.concat([top_high, top_low]).iterrows():
        ax2.annotate(
            f"{r['ticker']}\n({r['clean_total_tokens']:,})",
            xy=(r["comp_idx"], r["clean_total_tokens"]),
            xytext=(0, 8 if r["clean_total_tokens"] >= mean_comp else -22),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            fontweight="bold",
            color="#991b1b" if r["clean_total_tokens"] >= mean_comp else "#1e293b",
        )

    ax2.set_title(
        f"Phân phối Tổng số lượng Token Gemini SAU KHI LÀM SẠCH (100 Công ty, 2022–2025)",
        fontsize=14,
        fontweight="bold",
        pad=14,
    )
    ax2.set_xlabel("Chỉ số Công ty (1 → 100 theo thứ tự bảng chữ cái A → Z)", fontsize=11)
    ax2.set_ylabel("Tổng Token Sau Làm Sạch (4 năm + Giải trình)", fontsize=11)
    ax2.set_ylim(int(min_comp["clean_total_tokens"] * 0.72), int(max_comp["clean_total_tokens"] * 1.10))
    ax2.set_xticks(df_plot_comp["comp_idx"][::2])
    ax2.set_xticklabels(df_plot_comp["ticker"][::2], rotation=60, fontsize=8)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax2.grid(True, linestyle="--", alpha=0.35, zorder=0)
    ax2.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.92, fontsize=9.5)

    comp_plot_path = output_dir / "scatter_tokens_by_company.png"
    fig2.tight_layout()
    fig2.savefig(comp_plot_path, dpi=200)
    plt.close(fig2)

    return rep_plot_path, comp_plot_path


# =============================================================================
# HÀM CHÍNH (MAIN)
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Thực thi pipeline làm sạch 5 tầng và tính lại token Gemini cho bộ dữ liệu BCTC Top 100."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Đường dẫn thư mục chứa 100 công ty (mặc định: data/raw_docs/top_100)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Đường dẫn thư mục xuất kết quả (mặc định: evaluation/token_statistics)",
    )
    parser.add_argument(
        "--baseline-csv",
        type=Path,
        default=DEFAULT_BASELINE_CSV,
        help="Đường dẫn file CSV thống kê gốc để đối chiếu Before/After",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help="Tên model Gemini để tính token (mặc định: gemini-2.5-flash)",
    )
    args = parser.parse_args()

    baseline_df = None
    if args.baseline_csv.exists():
        baseline_df = pd.read_csv(args.baseline_csv)
        print(f"Đã nạp dữ liệu gốc từ: {args.baseline_csv} ({len(baseline_df)} bản ghi)")

    executor = PipelineExecutor(args.data_dir, args.output_dir, model_name=args.model)
    df_files = executor.process_and_clean_all(baseline_df)
    df_bctc_files, df_reports_merged, df_companies = build_aggregated_tables(df_files)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    files_csv = args.output_dir / "token_stats_all_files.csv"
    reports_csv = args.output_dir / "token_stats_reports_merged.csv"
    companies_csv = args.output_dir / "token_stats_companies.csv"
    comparison_csv = args.output_dir / "token_reduction_comparison.csv"

    # Lưu định dạng chuẩn tương thích với script trước đó
    df_files_standard = df_files.rename(
        columns={
            "clean_char_count": "char_count",
            "clean_gemini_tokens": "gemini_tokens",
            "approx_clean_tokens_4chars": "approx_tokens_4chars",
        }
    )
    df_files_standard.to_csv(files_csv, index=False, encoding="utf-8-sig")

    df_reports_standard = df_reports_merged.rename(
        columns={
            "clean_char_count": "char_count",
            "clean_gemini_tokens": "gemini_tokens",
            "approx_clean_tokens_4chars": "approx_tokens_4chars",
        }
    )
    df_reports_standard.to_csv(reports_csv, index=False, encoding="utf-8-sig")

    df_companies_standard = df_companies.rename(
        columns={
            "clean_total_chars": "total_chars",
            "clean_bctc_tokens": "bctc_tokens",
            "clean_giai_trinh_tokens": "giai_trinh_tokens",
            "clean_total_tokens": "total_gemini_tokens",
            "clean_4reports_strict_tokens": "total_4reports_strict_tokens",
            "clean_avg_tokens_per_year": "avg_tokens_per_year",
        }
    )
    df_companies_standard.to_csv(companies_csv, index=False, encoding="utf-8-sig")

    # Bảng so sánh chi tiết Before / After
    df_files.to_csv(comparison_csv, index=False, encoding="utf-8-sig")

    # Xuất 2 biểu đồ phân phối mới
    report_plot, company_plot = plot_updated_scatter_charts(df_bctc_files, df_companies, args.output_dir)

    # Thống kê tổng hợp
    raw_total_tokens = int(df_files["raw_gemini_tokens"].sum())
    clean_total_tokens = int(df_files["clean_gemini_tokens"].sum())
    total_tokens_saved = raw_total_tokens - clean_total_tokens
    pct_total_reduction = (total_tokens_saved / raw_total_tokens * 100.0) if raw_total_tokens > 0 else 0.0

    raw_avg_bctc = df_bctc_files["raw_gemini_tokens"].mean()
    clean_avg_bctc = df_bctc_files["clean_gemini_tokens"].mean()

    raw_avg_merged = df_reports_merged["raw_gemini_tokens"].mean()
    clean_avg_merged = df_reports_merged["clean_gemini_tokens"].mean()

    raw_avg_comp = df_companies["raw_total_tokens"].mean()
    clean_avg_comp = df_companies["clean_total_tokens"].mean()

    max_file_row = df_bctc_files.loc[df_bctc_files["clean_gemini_tokens"].idxmax()]
    min_file_row = df_bctc_files.loc[df_bctc_files["clean_gemini_tokens"].idxmin()]

    max_comp_row = df_companies.loc[df_companies["clean_total_tokens"].idxmax()]
    min_comp_row = df_companies.loc[df_companies["clean_total_tokens"].idxmin()]

    print("\n" + "=" * 82)
    print("KẾT QUẢ THỰC THI PIPELINE LÀM SẠCH VÀ TÍNH LẠI TOKEN GEMINI (gemini-2.5-flash)")
    print("=" * 82)
    print(f"1. SỐ TOKEN TRUNG BÌNH CỦA TOÀN BỘ CÁC BÁO CÁO:")
    print(f"   - Theo 405 file BCTC độc lập           : {clean_avg_bctc:,.2f} tokens/file (Gốc: {raw_avg_bctc:,.2f} -> Giảm {raw_avg_bctc - clean_avg_bctc:,.2f} tokens / -{(raw_avg_bctc - clean_avg_bctc)/raw_avg_bctc*100:.2f}%)")
    print(f"   - Theo 404 báo cáo (gộp POW p1+p2)     : {clean_avg_merged:,.2f} tokens/báo cáo (Gốc: {raw_avg_merged:,.2f} -> Giảm {raw_avg_merged - clean_avg_merged:,.2f} tokens / -{(raw_avg_merged - clean_avg_merged)/raw_avg_merged*100:.2f}%)")
    print(f"   - Trung vị (Median - 405 file BCTC)    : {df_bctc_files['clean_gemini_tokens'].median():,.1f} tokens (Gốc: {df_bctc_files['raw_gemini_tokens'].median():,.1f})")
    print("-" * 82)
    print(f"2. SỐ TOKEN TRUNG BÌNH CỦA TOÀN BỘ CÁC CÔNG TY (100 CÔNG TY):")
    print(f"   - Toàn bộ báo cáo + giải trình đi kèm  : {clean_avg_comp:,.2f} tokens/công ty (Gốc: {raw_avg_comp:,.2f} -> Giảm {raw_avg_comp - clean_avg_comp:,.2f} tokens / -{(raw_avg_comp - clean_avg_comp)/raw_avg_comp*100:.2f}%)")
    print(f"   - Chỉ tính đúng 4 báo cáo chính/công ty: {df_companies['clean_4reports_strict_tokens'].mean():,.2f} tokens/công ty")
    print(f"   - Trung vị (Median - 100 công ty)      : {df_companies['clean_total_tokens'].median():,.1f} tokens (Gốc: {df_companies['raw_total_tokens'].median():,.1f})")
    print("-" * 82)
    print(f"3. TỔNG SỐ TOKEN & CỰC TRỊ (MAX / MIN):")
    print(f"   - TỔNG SỐ TOKEN TRÊN TOÀN BỘ DỮ LIỆU   : {clean_total_tokens:,} tokens")
    print(f"     + Số token gốc trước khi làm sạch    : {raw_total_tokens:,} tokens")
    print(f"     + TỔNG SỐ TOKEN ĐÃ TIẾT KIỆM ĐƯỢC    : {total_tokens_saved:,} tokens (GIẢM {pct_total_reduction:.2f}%)")
    print(f"   - Báo cáo tốn NHIỀU token nhất (Max):")
    print(f"     + {max_file_row['relative_path']} -> {max_file_row['clean_gemini_tokens']:,} tokens (Gốc: {max_file_row['raw_gemini_tokens']:,} | Giảm -{max_file_row['token_reduction_pct']}%)")
    print(f"   - Báo cáo tốn ÍT token nhất (Min):")
    print(f"     + {min_file_row['relative_path']} -> {min_file_row['clean_gemini_tokens']:,} tokens (Gốc: {min_file_row['raw_gemini_tokens']:,} | Giảm -{min_file_row['token_reduction_pct']}%)")
    print(f"   - Công ty có tổng token NHIỀU nhất     : {max_comp_row['ticker']} ({max_comp_row['clean_total_tokens']:,} tokens | Gốc: {max_comp_row['raw_total_tokens']:,})")
    print(f"   - Công ty có tổng token ÍT nhất        : {min_comp_row['ticker']} ({min_comp_row['clean_total_tokens']:,} tokens | Gốc: {min_comp_row['raw_total_tokens']:,})")
    print("-" * 82)
    print(f"4. FILE ĐÃ XUẤT TẠI THƯ MỤC C:\\Research Dataset\\Multi-agent_Report_Writer\\evaluation\\token_statistics:")
    print(f"   - {report_plot.name}")
    print(f"   - {company_plot.name}")
    print(f"   - {files_csv.name}")
    print(f"   - {reports_csv.name}")
    print(f"   - {companies_csv.name}")
    print(f"   - {comparison_csv.name}")
    print("=" * 82)


if __name__ == "__main__":
    main()
