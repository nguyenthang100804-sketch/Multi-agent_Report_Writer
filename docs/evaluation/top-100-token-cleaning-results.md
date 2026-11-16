# Báo cáo Kết quả Thực thi Pipeline Làm sạch Nội dung & Tính lại Token Gemini Top 100

**Dự án:** Multi-Agent Framework to Write Report from Documents  
**Bộ dữ liệu:** Báo cáo Tài chính Đã Kiểm toán Top 100 Doanh nghiệp Niêm yết (Giai đoạn 2022–2025)  
**Phạm vi:** 410 file văn bản trong `data/raw_docs/top_100` (405 file BCTC chính + 5 file giải trình liên quan)  
**Model Tokenizer:** `LocalTokenizer(model_name="gemini-2.5-flash")` từ SDK chính thức `google-genai` (SentencePiece vocab size = 262,144)  
**Script thực thi:** [`clean_and_recount_tokens.py`](../../src/ingestion/clean_and_recount_tokens.py)  
**Thư mục lưu trữ kết quả:** [`evaluation/token_statistics`](file:///C:/Research%20Dataset/Multi-agent_Report_Writer/evaluation/token_statistics)  
**Thư mục sao lưu an toàn dữ liệu gốc:** [`data/backup_data/raw_docs_top_100_backup`](../../data/backup_data/raw_docs_top_100_backup)  

---

## 1. Tóm tắt Kết quả Thực thi Cốt lõi (Executive Summary)

Pipeline làm sạch 5 tầng đã được triển khai và thực thi tự động, xử lý thành công **410/410 files (100%)** trong thời gian **30.5 giây**. Toàn bộ số liệu kế toán, thuyết minh tài chính và đánh dấu vị trí trang `[P.X]` đều được bảo toàn nguyên vẹn.

| Chỉ số Thống kê | Dữ liệu Gốc (Raw) | Sau Khi Làm sạch (Cleaned) | Mức Giảm Tuyệt đối | Tỷ lệ Giảm (%) |
| :--- | :---: | :---: | :---: | :---: |
| **Tổng số Token Toàn Bộ Dữ liệu (410 file)** | **29,031,422** | **23,090,302** | **-5,941,120** | **-20.46%** |
| **Số Token Trung bình / Báo cáo (405 file BCTC)** | **71,626.43** | **56,958.87** | **-14,667.57** | **-20.48%** |
| **Số Token Trung bình / Báo cáo (404 báo cáo gộp)** | **71,803.73** | **57,099.85** | **-14,703.87** | **-20.48%** |
| **Trung vị Token Báo cáo (Median)** | **67,614.0** | **56,657.0** | **-10,957.0** | **-16.21%** |
| **Số Token Trung bình / Công ty (100 công ty)** | **290,314.22** | **230,903.02** | **-59,411.20** | **-20.46%** |
| **Trung bình Công ty (Chuẩn 4 báo cáo chính)** | **288,574.62** | **229,626.38** | **-58,948.24** | **-20.43%** |
| **Báo cáo tốn nhiều token nhất (Max)** | `GVR/2025` (`208,938`) | `BVH/2024` (**`109,525`**) | **-99,413** | **Xóa bỏ triệt để ngoại lai >150k** |
| **Báo cáo tốn ít token nhất (Min)** | `PAP/2022` (`22,770`) | `PAP/2022` (**`17,684`**) | **-5,086** | **-22.34%** |
| **Công ty có tổng token lớn nhất** | `BVH` (`474,630`) | `BVH` (**`419,678`**) | **-54,952** | **-11.58%** |
| **Công ty có tổng token nhỏ nhất** | `PAP` (`104,834`) | `PAP` (**`88,991`**) | **-15,843** | **-15.11%** |

---

## 2. Các Kết quả Cụ thể theo Yêu cầu

### 2.1. Số Token Trung bình của Toàn bộ các Báo cáo
* **Xét theo 405 file BCTC độc lập:**
  * Giá trị trung bình mới: **`56,958.87 tokens/file`** (giảm `14,667.57 tokens`, tương đương **`-20.48%`** so với mức gốc `71,626.43 tokens/file`).
  * Trung vị mới: **`56,657.0 tokens`** (giảm so với mức gốc `67,614.0 tokens`).
* **Xét theo 404 báo cáo tài chính hoàn chỉnh (đã gộp POW 2025 p1 + p2):**
  * Giá trị trung bình mới: **`57,099.85 tokens/báo cáo`** (giảm `14,703.87 tokens`, tương đương **`-20.48%`** so với mức gốc `71,803.73 tokens/báo cáo`).

### 2.2. Số Token Trung bình của Toàn bộ 100 Công ty
* **Tính toàn bộ 4 năm + giải trình liên quan:**
  * Giá trị trung bình mới: **`230,903.02 tokens/công ty`** (giảm `59,411.20 tokens`, tương đương **`-20.46%`** so với mức gốc `290,314.22 tokens/công ty`).
  * Trung vị mới: **`229,602.0 tokens/công ty`** (giảm từ `279,274.0 tokens`).
* **Tính theo chuẩn 4 báo cáo chính/công ty:**
  * Giá trị trung bình mới: **`229,626.38 tokens/công ty`** (giảm từ `288,574.62 tokens`).
  * Trung bình mỗi năm tài chính của một công ty tiêu tốn khoảng **`57,406 tokens/năm`**.

### 2.3. Tổng số Token Toàn bộ Dữ liệu & Cực trị (Max / Min)
* **Tổng số token trên toàn bộ dữ liệu (410 files):**
  * Sau làm sạch: **`23,090,302 tokens`**.
  * So với số token gốc `29,031,422 tokens`, hệ thống đã tiết kiệm được **`5,941,120 tokens`** (**`-20.46%`**).
* **Báo cáo tốn nhiều token nhất (Max):**
  * Trước làm sạch: `GVR/2025` (`208,938 tokens`).
  * Sau làm sạch: **[`BVH/2024`](file:///C:/Research%20Dataset/Multi-agent_Report_Writer/data/raw_docs/top_100/BVH/2024/BVH_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt)** với **`109,525 tokens`** (nguyên bản là `125,394 tokens`, giảm `-12.66%`). Báo cáo này có độ dài thực tế 124 trang tiếng Việt đơn ngữ với hàng trăm bảng danh mục đầu tư bảo hiểm và chứng khoán chi tiết.
  * Toàn bộ nhóm 10 báo cáo "phình to" bất thường trước đây (`GVR`, `OCB`, `PVS`, `SSI`, `VHM`, `PVD`) đã được thu gọn thành công từ `150,000 – 208,000 tokens` xuống vùng an toàn `56,000 – 95,000 tokens`!
* **Báo cáo tốn ít token nhất (Min):**
  * File đơn lẻ: **[`PAP/2022`](../../data/raw_docs/top_100/PAP/2022/PAP_2022_BCTC_Kiemtoan_extracted.txt)** với **`17,684 tokens`** (gốc `22,770 tokens`, giảm `-22.34%`).
  * Báo cáo gộp hoàn chỉnh: **[`PAP/2022`](../../data/raw_docs/top_100/PAP/2022/PAP_2022_BCTC_Kiemtoan_extracted.txt)** với **`17,684 tokens`**.
* **Công ty tốn nhiều token nhất:**
  * **`BVH`** với **`419,678 tokens`** cho 4 năm (gốc `474,630 tokens`, giảm `-54,952 tokens`).
* **Công ty tốn ít token nhất:**
  * **`PAP`** với **`88,991 tokens`** cho 4 năm (gốc `104,834 tokens`, giảm `-15,843 tokens`).

---

## 3. Top 10 Báo cáo Giảm Token Ấn tượng Nhất

Nhờ việc loại bỏ phần dịch Tiếng Anh trùng lặp 1:1, bản USD phụ của `PVD`, và chuyển đổi thẻ bảng HTML sang Pipe Table:

| Hạng | Ticker / Năm | Đường dẫn Tệp | Token Gốc | Token Mới | Số Token Tiết kiệm | Tỷ lệ Giảm (%) | Ghi chú Tối ưu |
| :---: | :---: | :--- | ---: | ---: | ---: | :---: | :--- |
| **1** | `GVR/2025` | `GVR/2025/GVR_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `208,938` | `95,824` | **`-113,114`** | **-54.14%** | Khử 102 trang Tiếng Anh + nén bảng |
| **2** | `OCB/2025` | `OCB/2025/OCB_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `202,334` | `91,495` | **`-110,839`** | **-54.78%** | Khử 102 trang Tiếng Anh + khử 150 khối LaTeX |
| **3** | `PVS/2025` | `PVS/2025/PVS_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `189,132` | `85,473` | **`-103,659`** | **-54.81%** | Khử 73 trang Tiếng Anh + 145 câu lỗi QR Code |
| **4** | `PVS/2024` | `PVS/2024/PVS_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `187,084` | `85,092` | **`-101,992`** | **-54.52%** | Khử 95 trang Tiếng Anh + khử watermark e-office |
| **5** | `SSI/2024` | `SSI/2024/SSI_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `181,014` | `88,316` | **`-92,698`** | **-51.21%** | Khử 96 trang Tiếng Anh + lọc running headers |
| **6** | `PVD/2024` | `PVD/2024/PVD_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `146,481` | `56,147` | **`-90,334`** | **-61.67%** | Khử bản USD phụ + xóa chuỗi ô vuông viền trang |
| **7** | `PVD/2025` | `PVD/2025/PVD_2025_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `153,801` | `67,381` | **`-86,420`** | **-56.19%** | Khử bản USD phụ + xóa 549 khối LaTeX con dấu |
| **8** | `GVR/2024` | `GVR/2024/GVR_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `164,862` | `80,133` | **`-84,729`** | **-51.39%** | Khử 77 trang Tiếng Anh + nén bảng HTML |
| **9** | `GEE/2024` | `GEE/2024/GEE_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `139,749` | `55,935` | **`-83,814`** | **-59.97%** | Khử 59 trang Tiếng Anh + nén bảng HTML |
| **10** | `VHM/2024` | `VHM/2024/VHM_2024_BCTC_Kiemtoan_Hopnhat_extracted.txt` | `150,644` | `71,161` | **`-79,483`** | **-52.76%** | Khử 105 trang Tiếng Anh + nén bảng danh sách công ty con |

Ngay cả đối với các báo cáo chuẩn đơn ngữ (không có tiếng Anh trùng lặp như `FPT`, `VCB`, `HPG`, `NTP`), Pipeline Tầng 3 $\rightarrow$ 5 vẫn giúp giảm đều đặn từ **14% đến 22% số lượng token** nhờ việc loại bỏ các thẻ `<table><tr><td>` rườm rà, dòng trống thừa và các tiêu đề đầu/chân trang lặp lại.

---

## 4. Các Tệp Kết quả Đã Xuất trong `evaluation/token_statistics`

1. **2 Biểu đồ Scatter Plot Phân Phối Mới:**
   - [`scatter_tokens_by_report.png`](file:///C:/Research%20Dataset/Multi-agent_Report_Writer/evaluation/token_statistics/scatter_tokens_by_report.png): Mô tả phân phối số lượng token của 405 báo cáo sau khi làm sạch, phân chia màu theo năm (2022–2025), đường Mean, Median và đánh dấu 2 cực trị Max/Min mới.
   - [`scatter_tokens_by_company.png`](file:///C:/Research%20Dataset/Multi-agent_Report_Writer/evaluation/token_statistics/scatter_tokens_by_company.png): Mô tả tổng token của 100 công ty sau khi làm sạch, đường Mean, Median và nhãn mã chứng khoán rõ ràng.
2. **Các Bảng Dữ liệu Thống kê Chi tiết (CSV UTF-8 BOM):**
   - [`token_stats_all_files.csv`](file:///C:/Research%20Dataset/Multi-agent_Report_Writer/evaluation/token_statistics/token_stats_all_files.csv): Thống kê token và số ký tự mới cho toàn bộ 410 files.
   - [`token_stats_reports_merged.csv`](file:///C:/Research%20Dataset/Multi-agent_Report_Writer/evaluation/token_statistics/token_stats_reports_merged.csv): Thống kê cấp báo cáo hoàn chỉnh (đã gộp POW 2025 p1+p2).
   - [`token_stats_companies.csv`](file:///C:/Research%20Dataset/Multi-agent_Report_Writer/evaluation/token_statistics/token_stats_companies.csv): Thống kê tổng hợp cho từng công ty trong 100 mã cổ phiếu.
   - [`token_reduction_comparison.csv`](file:///C:/Research%20Dataset/Multi-agent_Report_Writer/evaluation/token_statistics/token_reduction_comparison.csv): Bảng so sánh chi tiết số token trước (Raw) và sau (Cleaned) cho từng file, số lượng token tiết kiệm được và tỷ lệ % giảm.
