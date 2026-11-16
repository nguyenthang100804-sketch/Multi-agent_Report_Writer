"""
Script đếm số lượng token theo chuẩn Google Gemini cho bộ dữ liệu BCTC Top 100.
Tham khảo tài liệu chính thức:
https://ai.google.dev/gemini-api/docs/tokens?hl=vi

Hỗ trợ 2 chế độ đếm token chính thức của SDK `google-genai`:
1. `LocalTokenizer(model_name="gemini-2.5-flash").count_tokens(...)` (Mặc định):
   Sử dụng trực tiếp bộ tách từ SentencePiece chính thức của Gemini trên máy cục bộ,
   cho kết quả khớp 100% với tokenizer của model mà không tốn quota API.
2. `client.models.count_tokens(model="gemini-2.5-flash", contents=...)` (`--use-api`):
   Gọi trực tiếp endpoint `countTokens` của Gemini API (yêu cầu biến môi trường `GEMINI_API_KEY`).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import ssl
import tempfile
import urllib.request
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning)

# Cấu hình đường dẫn mặc định
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "raw_docs" / "top_100"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "token_statistics" / "raw_baseline_stats"
DEFAULT_MODEL = "gemini-2.5-flash"

# Cấu hình cache cho SentencePiece model của Gemini (phòng trường hợp lỗi SSL cert trên Windows)
_GEMMA3_SPIECE_URL = (
    "https://raw.githubusercontent.com/google/gemma_pytorch/"
    "014acb7ac4563a5f77c76d7ff98f31b568c16508/tokenizer/gemma3_cleaned_262144_v2.spiece.model"
)
_GEMMA3_SPIECE_SHA256 = "1299c11d7cf632ef3b4e11937501358ada021bbdf7c47638d13c0ee982f2e79c"


def ensure_local_tokenizer_model_cached() -> None:
    """Đảm bảo file SentencePiece tokenizer của Gemini đã được tải và xác thực SHA-256."""
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


class GeminiTokenCounter:
    """Bộ đếm token chuẩn Gemini theo tài liệu Google AI for Developers."""

    def __init__(self, model_name: str = DEFAULT_MODEL, use_api: bool = False) -> None:
        self.model_name = model_name
        self.use_api = use_api
        self._client = None
        self._local_tokenizer = None

        if self.use_api:
            from google import genai

            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "Chế độ --use-api yêu cầu biến môi trường GEMINI_API_KEY hoặc GOOGLE_API_KEY."
                )
            self._client = genai.Client(api_key=api_key)
        else:
            ensure_local_tokenizer_model_cached()
            from google.genai.local_tokenizer import LocalTokenizer

            self._local_tokenizer = LocalTokenizer(model_name=self.model_name)

    def count_tokens(self, text: str) -> int:
        """Đếm số lượng token của chuỗi văn bản theo chuẩn Gemini."""
        if not text:
            return 0
        if self.use_api and self._client is not None:
            response = self._client.models.count_tokens(
                model=self.model_name,
                contents=text,
            )
            return int(response.total_tokens)
        else:
            # Gọi trực tiếp thông qua LocalTokenizer của google-genai
            result = self._local_tokenizer.count_tokens(text)
            return int(result.total_tokens)


def collect_dataset_tokens(
    data_dir: Path,
    counter: GeminiTokenCounter,
) -> pd.DataFrame:
    """Duyệt toàn bộ thư mục top_100 và tính số token cho từng file .txt."""
    records: List[Dict] = []

    tickers = sorted([d.name for d in data_dir.iterdir() if d.is_dir()])
    total_tickers = len(tickers)
    print(f"Đang quét và đếm token cho {total_tickers} mã doanh nghiệp tại: {data_dir} ...")

    for idx, ticker in enumerate(tickers, start=1):
        ticker_dir = data_dir / ticker
        years = sorted([y.name for y in ticker_dir.iterdir() if y.is_dir()])
        for year in years:
            year_dir = ticker_dir / year
            txt_files = sorted(year_dir.glob("*.txt"))
            for txt_file in txt_files:
                content = txt_file.read_text(encoding="utf-8", errors="ignore")
                char_count = len(content)
                # Quy tắc ước lượng trong tài liệu Gemini: 1 token ~ 4 ký tự
                approx_tokens_4chars = round(char_count / 4)
                gemini_tokens = counter.count_tokens(content)

                is_giai_trinh = txt_file.name == "giai_trinh_lien_quan.txt"
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
                        "year": int(year),
                        "file_name": txt_file.name,
                        "relative_path": f"{ticker}/{year}/{txt_file.name}",
                        "is_giai_trinh": is_giai_trinh,
                        "doc_type": doc_type,
                        "char_count": char_count,
                        "approx_tokens_4chars": approx_tokens_4chars,
                        "gemini_tokens": gemini_tokens,
                    }
                )
        if idx % 20 == 0 or idx == total_tickers:
            print(f"  -> Đã xử lý {idx}/{total_tickers} công ty...")

    return pd.DataFrame(records)


def build_report_and_company_tables(df_files: pd.DataFrame):
    """
    Tổng hợp bảng dữ liệu cấp Báo cáo (Report-level) và cấp Công ty (Company-level).
    - Cấp File BCTC đơn lẻ: Tất cả các file .txt trừ `giai_trinh_lien_quan.txt` (405 files).
    - Cấp Báo cáo hoàn chỉnh (Merged POW 2025 p1+p2): Gộp p1 và p2 của POW/2025 thành 1 báo cáo (404 báo cáo).
    - Cấp Công ty (100 công ty): Tính tổng toàn bộ báo cáo các năm + giải trình liên quan nếu có.
    """
    df_bctc_files = df_files[~df_files["is_giai_trinh"]].copy().reset_index(drop=True)

    # Bảng báo cáo đã gộp POW 2025 p1 + p2 thành 1 báo cáo duy nhất
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
                        "char_count": int(row["char_count"] + p2_row["char_count"]),
                        "approx_tokens_4chars": int(
                            row["approx_tokens_4chars"] + p2_row["approx_tokens_4chars"]
                        ),
                        "gemini_tokens": int(row["gemini_tokens"] + p2_row["gemini_tokens"]),
                    }
                )
                continue
        merged_rows.append(row.to_dict())

    df_reports_merged = pd.DataFrame(merged_rows)

    # Bảng cấp Công ty (tính tất cả báo cáo các năm + giải trình liên quan nếu có)
    company_rows = []
    for ticker, grp in df_files.groupby("ticker", sort=True):
        bctc_grp = grp[~grp["is_giai_trinh"]]
        gt_grp = grp[grp["is_giai_trinh"]]

        # Số báo cáo chính (nếu gộp POW p1+p2)
        n_bctc_files = len(bctc_grp)
        n_reports = (
            n_bctc_files - 1
            if (ticker == "POW" and any("_p1_" in fn for fn in bctc_grp["file_name"]))
            else n_bctc_files
        )

        # Kiểm tra trường hợp chỉ lấy 4 báo cáo chính (loại bỏ Riengle dư khi đã có Hopnhat cùng năm ở NTP, NVB)
        primary_tokens = int(grp["gemini_tokens"].sum())
        if len(bctc_grp) > 4 and ticker in ("NTP", "NVB"):
            extra_riengle = bctc_grp[bctc_grp["doc_type"] == "BCTC_Riengle"]["gemini_tokens"].sum()
            primary_4reports_tokens = int(primary_tokens - extra_riengle)
        else:
            primary_4reports_tokens = primary_tokens

        company_rows.append(
            {
                "ticker": ticker,
                "num_bctc_files": n_bctc_files,
                "num_reports_merged": n_reports,
                "num_giai_trinh": len(gt_grp),
                "total_files": len(grp),
                "total_chars": int(grp["char_count"].sum()),
                "bctc_tokens": int(bctc_grp["gemini_tokens"].sum()),
                "giai_trinh_tokens": int(gt_grp["gemini_tokens"].sum()),
                "total_gemini_tokens": int(grp["gemini_tokens"].sum()),
                "total_4reports_strict_tokens": primary_4reports_tokens,
                "avg_tokens_per_year": float(grp["gemini_tokens"].sum()) / 4.0,
            }
        )

    df_companies = pd.DataFrame(company_rows)
    return df_bctc_files, df_reports_merged, df_companies


def plot_scatter_charts(
    df_bctc_files: pd.DataFrame,
    df_companies: pd.DataFrame,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Xuất 2 ảnh scatter plot mô tả phân phối số lượng token của các báo cáo và của các công ty."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["Segoe UI", "Arial", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    # =========================================================================
    # HÌNH 1: Scatter Plot phân phối số lượng token của các báo cáo (BCTC)
    # =========================================================================
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
            grp["gemini_tokens"],
            label=f"Năm {year} ({len(grp)} file)",
            color=year_palette.get(year, "#475569"),
            alpha=0.78,
            s=42,
            edgecolors="white",
            linewidth=0.5,
            zorder=3,
        )

    mean_rep = df_plot_rep["gemini_tokens"].mean()
    median_rep = df_plot_rep["gemini_tokens"].median()
    max_row = df_plot_rep.loc[df_plot_rep["gemini_tokens"].idxmax()]
    min_row = df_plot_rep.loc[df_plot_rep["gemini_tokens"].idxmin()]

    ax1.axhline(
        mean_rep,
        color="#dc2626",
        linestyle="--",
        linewidth=1.6,
        label=f"Trung bình (Mean): {mean_rep:,.0f} tokens",
        zorder=4,
    )
    ax1.axhline(
        median_rep,
        color="#0d9488",
        linestyle=":",
        linewidth=1.5,
        label=f"Trung vị (Median): {median_rep:,.0f} tokens",
        zorder=4,
    )

    # Đánh dấu điểm Max và Min
    ax1.scatter(
        [max_row["report_idx"], min_row["report_idx"]],
        [max_row["gemini_tokens"], min_row["gemini_tokens"]],
        color="#dc2626",
        s=95,
        zorder=5,
        edgecolors="black",
        linewidth=1.2,
    )
    ax1.annotate(
        f"MAX: {max_row['ticker']} ({max_row['year']})\n{max_row['gemini_tokens']:,} tokens",
        xy=(max_row["report_idx"], max_row["gemini_tokens"]),
        xytext=(max_row["report_idx"] - 55, max_row["gemini_tokens"] * 0.94),
        arrowprops=dict(arrowstyle="->", color="#dc2626", lw=1.2),
        fontsize=9,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="#fef2f2", ec="#dc2626", lw=0.8),
        zorder=6,
    )
    ax1.annotate(
        f"MIN: {min_row['ticker']} ({min_row['year']})\n{min_row['gemini_tokens']:,} tokens",
        xy=(min_row["report_idx"], min_row["gemini_tokens"]),
        xytext=(min(min_row["report_idx"] + 15, len(df_plot_rep) - 60), min_row["gemini_tokens"] + 25000),
        arrowprops=dict(arrowstyle="->", color="#1e293b", lw=1.2),
        fontsize=9,
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="#f8fafc", ec="#475569", lw=0.8),
        zorder=6,
    )

    ax1.set_title(
        f"Phân phối Số lượng Token Gemini của các Báo cáo Tài chính (N = {len(df_plot_rep)} files)",
        fontsize=14,
        fontweight="bold",
        pad=14,
    )
    ax1.set_xlabel("Chỉ số Báo cáo (Sắp xếp theo Mã Chứng khoán A → Z & Năm 2022 → 2025)", fontsize=11)
    ax1.set_ylabel("Số lượng Token (Gemini Tokenizer)", fontsize=11)
    ax1.set_ylim(10000, int(max_row["gemini_tokens"] * 1.12))
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax1.grid(True, linestyle="--", alpha=0.35, zorder=0)
    ax1.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.92, fontsize=9.5)

    report_plot_path = output_dir / "scatter_tokens_by_report.png"
    fig1.tight_layout()
    fig1.savefig(report_plot_path, dpi=200)
    plt.close(fig1)

    # =========================================================================
    # HÌNH 2: Scatter Plot phân phối tổng số lượng token của 100 công ty
    # =========================================================================
    fig2, ax2 = plt.subplots(figsize=(15, 7.5), dpi=200)

    df_plot_comp = df_companies.sort_values("ticker").reset_index(drop=True)
    df_plot_comp["comp_idx"] = np.arange(1, len(df_plot_comp) + 1)

    has_gt = df_plot_comp["num_giai_trinh"] > 0
    no_gt = ~has_gt

    ax2.scatter(
        df_plot_comp.loc[no_gt, "comp_idx"],
        df_plot_comp.loc[no_gt, "total_gemini_tokens"],
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
            df_plot_comp.loc[has_gt, "total_gemini_tokens"],
            label=f"Công ty có kèm Giải trình ({has_gt.sum()} công ty: IDC, MCH, SSH, VEA)",
            color="#f59e0b",
            marker="D",
            alpha=0.95,
            s=75,
            edgecolors="#78350f",
            linewidth=0.9,
            zorder=4,
        )

    mean_comp = df_plot_comp["total_gemini_tokens"].mean()
    median_comp = df_plot_comp["total_gemini_tokens"].median()
    max_comp = df_plot_comp.loc[df_plot_comp["total_gemini_tokens"].idxmax()]
    min_comp = df_plot_comp.loc[df_plot_comp["total_gemini_tokens"].idxmin()]

    ax2.axhline(
        mean_comp,
        color="#dc2626",
        linestyle="--",
        linewidth=1.6,
        label=f"Trung bình (Mean): {mean_comp:,.0f} tokens/công ty",
        zorder=4,
    )
    ax2.axhline(
        median_comp,
        color="#0d9488",
        linestyle=":",
        linewidth=1.5,
        label=f"Trung vị (Median): {median_comp:,.0f} tokens/công ty",
        zorder=4,
    )

    # Hiển thị nhãn mã chứng khoán cho Top 5 cao nhất và Top 3 thấp nhất
    top_high = df_plot_comp.nlargest(5, "total_gemini_tokens")
    top_low = df_plot_comp.nsmallest(3, "total_gemini_tokens")
    for _, r in pd.concat([top_high, top_low]).iterrows():
        ax2.annotate(
            f"{r['ticker']}\n({r['total_gemini_tokens']:,})",
            xy=(r["comp_idx"], r["total_gemini_tokens"]),
            xytext=(0, 8 if r["total_gemini_tokens"] >= mean_comp else -22),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            fontweight="bold",
            color="#991b1b" if r["total_gemini_tokens"] >= mean_comp else "#1e293b",
        )

    ax2.set_title(
        f"Phân phối Tổng số lượng Token Gemini theo Công ty (100 Công ty, Giai đoạn 2022–2025)",
        fontsize=14,
        fontweight="bold",
        pad=14,
    )
    ax2.set_xlabel("Chỉ số Công ty (1 → 100 theo thứ tự bảng chữ cái A → Z)", fontsize=11)
    ax2.set_ylabel("Tổng số Token của Công ty (4 năm + Giải trình nếu có)", fontsize=11)
    ax2.set_ylim(int(min_comp["total_gemini_tokens"] * 0.72), int(max_comp["total_gemini_tokens"] * 1.10))
    ax2.set_xticks(df_plot_comp["comp_idx"][::2])
    ax2.set_xticklabels(df_plot_comp["ticker"][::2], rotation=60, fontsize=8)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax2.grid(True, linestyle="--", alpha=0.35, zorder=0)
    ax2.legend(loc="upper left", frameon=True, facecolor="white", framealpha=0.92, fontsize=9.5)

    company_plot_path = output_dir / "scatter_tokens_by_company.png"
    fig2.tight_layout()
    fig2.savefig(company_plot_path, dpi=200)
    plt.close(fig2)

    return report_plot_path, company_plot_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Đếm số lượng token Gemini cho bộ dữ liệu BCTC top_100 và xuất biểu đồ Scatter Plot."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Đường dẫn tới thư mục top_100",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Đường dẫn thư mục xuất CSV và biểu đồ",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help="Tên model Gemini để tính token (mặc định: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Sử dụng Gemini API trực tuyến (client.models.count_tokens) thay vì LocalTokenizer",
    )
    args = parser.parse_args()

    counter = GeminiTokenCounter(model_name=args.model, use_api=args.use_api)
    df_files = collect_dataset_tokens(args.data_dir, counter)
    df_bctc_files, df_reports_merged, df_companies = build_report_and_company_tables(df_files)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    files_csv = args.output_dir / "token_stats_all_files.csv"
    reports_csv = args.output_dir / "token_stats_reports_merged.csv"
    companies_csv = args.output_dir / "token_stats_companies.csv"

    df_files.to_csv(files_csv, index=False, encoding="utf-8-sig")
    df_reports_merged.to_csv(reports_csv, index=False, encoding="utf-8-sig")
    df_companies.to_csv(companies_csv, index=False, encoding="utf-8-sig")

    report_plot, company_plot = plot_scatter_charts(df_bctc_files, df_companies, args.output_dir)

    # Thống kê chi tiết
    total_all_tokens = int(df_files["gemini_tokens"].sum())
    total_bctc_tokens = int(df_bctc_files["gemini_tokens"].sum())
    total_gt_tokens = int(df_files[df_files["is_giai_trinh"]]["gemini_tokens"].sum())

    avg_bctc_file = df_bctc_files["gemini_tokens"].mean()
    avg_bctc_merged = df_reports_merged["gemini_tokens"].mean()
    avg_company_all = df_companies["total_gemini_tokens"].mean()
    avg_company_strict4 = df_companies["total_4reports_strict_tokens"].mean()

    max_file_row = df_bctc_files.loc[df_bctc_files["gemini_tokens"].idxmax()]
    min_file_row = df_bctc_files.loc[df_bctc_files["gemini_tokens"].idxmin()]

    max_merged_row = df_reports_merged.loc[df_reports_merged["gemini_tokens"].idxmax()]
    min_merged_row = df_reports_merged.loc[df_reports_merged["gemini_tokens"].idxmin()]

    max_comp_row = df_companies.loc[df_companies["total_gemini_tokens"].idxmax()]
    min_comp_row = df_companies.loc[df_companies["total_gemini_tokens"].idxmin()]

    print("\n" + "=" * 78)
    print(f"KẾT QUẢ THỐNG KÊ TOKEN THEO CHUẨN GEMINI ({args.model})")
    print("=" * 78)
    print(f"1. SỐ TOKEN TRUNG BÌNH CỦA TOÀN BỘ CÁC BÁO CÁO:")
    print(f"   - Xét theo 405 file BCTC độc lập          : {avg_bctc_file:,.2f} tokens/file")
    print(f"   - Xét theo 404 báo cáo (gộp POW 2025 p1+p2): {avg_bctc_merged:,.2f} tokens/báo cáo")
    print(f"   - Trung vị (Median - 405 file BCTC)       : {df_bctc_files['gemini_tokens'].median():,.1f} tokens")
    print("-" * 78)
    print(f"2. SỐ TOKEN TRUNG BÌNH CỦA TOÀN BỘ CÁC CÔNG TY (100 CÔNG TY):")
    print(f"   - Tính toàn bộ báo cáo + giải trình đi kèm: {avg_company_all:,.2f} tokens/công ty")
    print(f"   - Nếu chỉ tính đúng 4 báo cáo chính/công ty: {avg_company_strict4:,.2f} tokens/công ty")
    print(f"   - Trung vị (Median - 100 công ty)         : {df_companies['total_gemini_tokens'].median():,.1f} tokens")
    print("-" * 78)
    print(f"3. TỔNG SỐ TOKEN & CỰC TRỊ (MAX / MIN):")
    print(f"   - Tổng số token toàn bộ dữ liệu (410 file): {total_all_tokens:,} tokens")
    print(f"     + Riêng 405 file BCTC                   : {total_bctc_tokens:,} tokens")
    print(f"     + Riêng 5 file giải trình liên quan     : {total_gt_tokens:,} tokens")
    print(f"     + (Tham khảo quy tắc 1 token ~ 4 ký tự) : {int(df_files['approx_tokens_4chars'].sum()):,} tokens")
    print(f"   - Báo cáo tốn NHIỀU token nhất (Max):")
    print(f"     + {max_file_row['relative_path']} -> {max_file_row['gemini_tokens']:,} tokens ({max_file_row['char_count']:,} ký tự)")
    print(f"   - Báo cáo tốn ÍT token nhất (Min):")
    print(f"     + Theo file đơn lẻ ({min_file_row['relative_path']}): {min_file_row['gemini_tokens']:,} tokens ({min_file_row['char_count']:,} ký tự)")
    print(f"     + Theo báo cáo hoàn chỉnh ({min_merged_row['relative_path']}): {min_merged_row['gemini_tokens']:,} tokens ({min_merged_row['char_count']:,} ký tự)")
    print(f"   - Công ty có tổng token NHIỀU nhất        : {max_comp_row['ticker']} ({max_comp_row['total_gemini_tokens']:,} tokens)")
    print(f"   - Công ty có tổng token ÍT nhất           : {min_comp_row['ticker']} ({min_comp_row['total_gemini_tokens']:,} tokens)")
    print("-" * 78)
    print(f"4. FILE KẾT QUẢ & BIỂU ĐỒ SCATTER PLOT ĐÃ XUẤT:")
    print(f"   - Biểu đồ Báo cáo : {report_plot}")
    print(f"   - Biểu đồ Công ty : {company_plot}")
    print(f"   - CSV Chi tiết    : {files_csv}")
    print(f"   - CSV Công ty     : {companies_csv}")
    print("=" * 78)


if __name__ == "__main__":
    main()
