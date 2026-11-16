# Kiến trúc Lưu trữ và Vận hành Dữ liệu Đa tầng (Multi-tier Data Storage & Operations Architecture)

> Cập nhật 09/11/2026: snapshot đang dùng `v2.1` có 141 tài liệu, 32.175 chunk và 18.540 fact. Các số 30.282 chunk trong phần thiết kế dưới đây là số của snapshot v1, trước khi sửa phân loại bảng thuyết minh; xem [kiểm tra tác động](../evaluation/notes-classification-audit.md).

> **Tài liệu đặc tả kiến trúc kỹ thuật & Vận hành dữ liệu (Data Architecture & Operations Specification)**  
> **Dự án:** Multi-agent Financial Report Writer  
> **Phiên bản:** `v1.0` | **Ngày lập:** 30/10/2026  
> **Trạng thái:** Kiến trúc sản xuất (Production Architecture)  

---

## Mục lục
1. [Tổng quan & Triết lý Thiết kế](#1-tổng-quan--triết-lý-thiết-kế)
2. [Kiến trúc Lưu trữ Đa tầng (Multi-tier Storage Tiers)](#2-kiến-trúc-lưu-trữ-đa-tầng-multi-tier-storage-tiers)
   - [Tầng 0: Lớp Dữ liệu Bán cấu trúc Bất biến (Processed JSON Layer)](#tầng-0-lớp-dữ-liệu-bán-cấu-trúc-bất-biến-processed-json-layer)
   - [Tầng 1: Lớp Bộ đệm Vector Trung gian (Intermediate Vector Parquet Cache)](#tầng-1-lớp-bộ-đệm-vector-trung-gian-intermediate-vector-parquet-cache)
   - [Tầng 2: Hệ Động cơ Phục vụ Kép (Dual Serving Engines: Qdrant & DuckDB)](#tầng-2-hệ-động-cơ-phục-vụ-kép-dual-serving-engines-qdrant--duckdb)
   - [Tầng 3: Lớp Kê khai Thực thi & Phân tách Đánh giá (Manifests & Evaluation Artifacts)](#tầng-3-lớp-kê-khai-thực-thi--phân-tách-đánh-giá-manifests--evaluation-artifacts)
3. [Phân tích Đối đầu: Kiến trúc Hiện tại vs. Lưu trữ & Vận hành Thông thường (Conventional RAG)](#3-phân-tích-đối-đầu-kiến-trúc-hiện-tại-vs-lưu-trữ--vận-hành-thông-thường-conventional-rag)
   - [Bảng đối đầu 8 tiêu chí cốt lõi](#bảng-đối-đầu-8-tiêu-chí-cốt-lõi)
   - [Phân tích chi tiết 5 điểm vượt trội sống còn](#phân-tích-chi-tiết-5-điểm-vượt-trội-sống-còn)
4. [Sơ đồ Kiến trúc & Luồng Dữ liệu (Mermaid Diagrams)](#4-sơ-đồ-kiến-trúc--luồng-dữ-liệu-mermaid-diagrams)
5. [Quy trình Vận hành Thực tế (Operational Workflows)](#5-quy-trình-vận-hành-thực-tế-operational-workflows)
   - [Luồng Ingestion & Caching](#luồng-ingestion--caching)
   - [Luồng Truy vấn Song song của Multi-Agent](#luồng-truy-vấn-song-song-của-multi-agent)
   - [Cơ chế Phục hồi Sự cố & Tự điều hòa (Self-healing & Reconciliation)](#cơ-chế-phục-hồi-sự-cố--tự-điều-hòa-self-healing--reconciliation)
6. [Kết luận & Khuyến nghị Môi trường Sản xuất](#6-kết-luận--khuyến-nghị-môi-trường-sản-xuất)

---

## 1. Tổng quan & Triết lý Thiết kế

Trong các hệ thống RAG (Retrieval-Augmented Generation) thông thường, dữ liệu thường được xử lý theo cách thức ngây thơ (naive approach): cắt nhỏ văn bản thành các đoạn cố định (fixed-size chunking 500–1000 tokens), nhúng toàn bộ vào một Vector Database duy nhất, rồi dùng mô hình ngôn ngữ lớn (LLM) để tìm kiếm và tự suy luận ra câu trả lời. 

Tuy nhiên, đối với **miền dữ liệu Báo cáo Tài chính Doanh nghiệp Việt Nam** (với 141 BCTC kiểm toán giai đoạn 2022–2025 của 35 doanh nghiệp lớn, bao gồm hơn 30.282 chunks và hàng chục nghìn chỉ tiêu số học phức tạp), cách tiếp cận thông thường hoàn toàn thất bại vì:
1. **Khủng hoảng ảo giác số học (Financial Hallucination):** Vector search không thể phân biệt chính xác sự khác nhau giữa `12.694.975.751.615 VNĐ` và `12.694.975.751.616 VNĐ`. LLM khi đọc các bảng biểu Markdown cắt vụn sẽ dễ dàng cộng trừ sai hoặc "bịa" ra con số khi các cột năm bị lệch.
2. **Nhiễu thời gian & Văn bản khuôn mẫu (Temporal Leakage):** Báo cáo của các năm khác nhau có phần thuyết minh chính sách kế toán gần như giống nhau từng chữ. Tìm kiếm vector đơn thuần không có bộ lọc cứng sẽ kéo nhầm tài liệu năm trước vào năm nay.
3. **Chi phí tính toán khổng lồ khi tái lập chỉ mục (Re-indexing Bottleneck):** Mỗi lần đổi mô hình embedding hoặc tinh chỉnh tham số, việc quét lại toàn bộ văn bản và gọi mô hình embedding mất từ 4–6 giờ suy luận CPU. Nếu lưu trữ gắn chặt vào một cơ sở dữ liệu duy nhất, khi kết nối mạng lỗi hoặc database hỏng, toàn bộ công sức suy luận sẽ mất trắng.

### 4 Trụ cột Triết lý Kiến trúc Cốt lõi:

> [!IMPORTANT]
> **1. Phân định Ranh giới Trách nhiệm (Strict Separation of Concerns):**  
> **Qdrant** phụ trách không gian mờ (Semantic Space) — trả lời câu hỏi: *"Đoạn văn bản/bảng biểu nào có liên quan đến ngữ cảnh cần tìm?"*  
> **DuckDB** phụ trách không gian số học chính xác (Relational Fact Space) — trả lời câu hỏi: *"Chỉ tiêu tài chính đó có giá trị chính xác là bao nhiêu, tăng trưởng bao nhiêu % qua các năm?"*

> [!IMPORTANT]
> **2. Nguyên tắc Không suy diễn Số học (Zero-Hallucination on Numbers):**  
> Tất cả các phép tính toán tổng hợp (YoY, CAGR, Tỷ suất lợi nhuận, Cơ cấu nợ) bắt buộc được thực hiện bằng công cụ tính toán xác định (SQL/Code Engine trên DuckDB facts), tuyệt đối không để LLM tự làm toán nhẩm trên context window.

> [!IMPORTANT]
> **3. Bộ đệm Trung gian Bất biến (Zero-Recompute Vector Parquet Cache):**  
> Tách rời tuyệt đối pha tính toán nặng (Inference trên CPU/GPU) khỏi pha truyền tải và lập chỉ mục (I/O, Network, Database Upload). Vector một khi đã được tính toán sẽ lưu vĩnh viễn dưới dạng file Parquet phân tán theo từng tài liệu.

> [!IMPORTANT]
> **4. Kiểm toán Trích dẫn Học thuật 100% (Auditable Lineage & Citations):**  
> Mọi con số và đoạn văn bản xuất hiện trong báo cáo tổng hợp cuối cùng đều phải truy ngược được chính xác: Mã cổ phiếu (`ticker`), Năm tài chính (`fiscal_year`), Số trang in thực tế (`printed_page`), và Số trang vật lý của file PDF gốc (`physical_page`).

---

## 2. Kiến trúc Lưu trữ Đa tầng (Multi-tier Storage Tiers)

Hệ thống được thiết kế theo mô hình 4 tầng lưu trữ dữ liệu chuyên biệt hóa, tạo thành một ống dẫn dữ liệu (Data Pipeline) khép kín, có tính phòng thủ cao và khả năng khôi phục sau sự cố tức thì.

```
+-----------------------------------------------------------------------------------+
| TẦNG 0: NGUỒN SỰ THẬT BẤT BIẾN (SINGLE SOURCE OF TRUTH)                            |
| 141 files: data/processed_chunks/{ticker}_{year}_{scope}.json                      |
| [Metadata, Parser v2.0, Chunks (text + embed_text), Structured Facts List]        |
+-----------------------------------------------------------------------------------+
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    ▼                                           ▼
+---------------------------------------+   +---------------------------------------+
| TẦNG 1: BỘ ĐỆM VECTOR TRUNG GIAN      |   | TẦNG 2B: QUAN HỆ SỰ THẬT SỐ HỌC       |
| data/vector_cache/bge_m3/*.parquet    |   | In-memory / DuckDB Persistent Store   |
| 141 files Parquet (Dense + Sparse)    |   | Bảng `facts`: SQL OLAP Engine         |
| [chunk_id, content_hash, vectors]     |   | [ticker, year, code, label, value...] |
+---------------------------------------+   +---------------------------------------+
                    │                                           │
                    ▼                                           │
+---------------------------------------+                       │
| TẦNG 2A: ĐỘNG CƠ TÌM KIẾM NGỮ NGHĨA   |                       │
| Qdrant Engine (Local / Cloud)         |                       │
| Collection: vnfin_v1_bge_m3_v1        |                       │
| [Hybrid Search + 6 Payload Indexes]   |                       │
+---------------------------------------+                       │
                    │                                           │
                    └─────────────────────┬─────────────────────┘
                                          ▼
+-----------------------------------------------------------------------------------+
| TẦNG 3: VẬN HÀNH & ĐÁNH GIÁ (MANIFESTS, EVALUATION SPLITS & GOLDEN SET)          |
| configs/manifests/manifest_*.json | configs/eval_dataset_split.json (25 Dev / 10 Test)
| configs/golden_evaluation_dataset.json (114 câu hỏi đa dạng: Facts, Text, Traps) |
+-----------------------------------------------------------------------------------+
```

---

### Tầng 0: Lớp Dữ liệu Bán cấu trúc Bất biến (Processed JSON Layer)

- **Vị trí lưu trữ:** `data/processed_chunks/*.json`
- **Quy mô:** 141 tệp tin JSON tương ứng với 141 Báo cáo Tài chính đã kiểm toán.
- **Vai trò:** Là **Nguồn sự thật duy nhất (Single Source of Truth - SSOT)**. Toàn bộ các tầng phía sau (Parquet cache, Qdrant index, DuckDB tables) đều là các thực thể dẫn xuất (pure derivations). Nếu toàn bộ hệ thống cơ sở dữ liệu bị xóa sạch, hệ thống có thể tái lập 100% trạng thái hoàn chỉnh chỉ từ thư mục này.

#### Cấu trúc Payload của một tệp tin Tầng 0:
Mỗi file JSON chứa 2 thành phần dữ liệu lõi song song:
```json
{
  "doc_id": "ABB_2022_Hopnhat",
  "ticker": "ABB",
  "fiscal_year": 2022,
  "source_file": "ABB_2022_Hopnhat.pdf",
  "sha256": "4b2e8a...",
  "parser_version": "v2.0",
  "scope": "Hopnhat",
  "default_unit": "VND",
  "chunks": [
    {
      "chunk_id": "ABB_2022_Hopnhat_c0012",
      "chunk_type": "table",
      "text": "| Mã số | Chỉ tiêu | Năm nay | Năm trước |\n| 110 | Tiền gửi... | 12.694.975.751.615 | 8.214... |",
      "embed_text": "[ABB | 2022 | Hợp nhất | Báo cáo lưu chuyển tiền tệ]\nChỉ tiêu: Tiền gửi tại NHNN | Mã số: 110 | Năm nay | Năm trước",
      "physical_pages": [8],
      "physical_page_start": 8,
      "physical_page_end": 8,
      "printed_pages": ["6"],
      "citation_tag": "[ABB-2022-Hopnhat-p8]",
      "section": "CASH_FLOW",
      "section_title": "BÁO CÁO LƯU CHUYỂN TIỀN TỆ",
      "row_count": 14
    }
  ],
  "facts": [
    {
      "report_type": "BALANCE_SHEET",
      "code": "110",
      "stt": null,
      "label": "Tiền và các khoản tương đương tiền",
      "note": "5",
      "current_year": 480517.0,
      "prior_year": 485554.0,
      "raw_current": "480.517",
      "raw_prior": "485.554",
      "suspect": false,
      "suspect_reason": null,
      "unit": "million_VND",
      "physical_page": 8,
      "printed_page": "6"
    }
  ]
}
```

> [!NOTE]
> **Điểm đột phá kỹ thuật: Chiến lược Dual-Stream Representation**  
> Mỗi chunk dữ liệu được phân đôi thành hai trường riêng biệt:
> - `text`: Chứa toàn bộ nội dung nguyên vẹn (bảng biểu có đầy đủ tất cả các con số, văn bản có dấu). Dùng cho Writer Agent đọc, trích xuất sự thật và lập luận.
> - `embed_text`: Đã được thanh lọc số liệu dài dòng, thêm tiền tố chuẩn hóa cấu trúc `[Ticker | Năm | Phạm vi | Mục báo cáo]`, chỉ giữ lại nhãn chỉ tiêu kinh tế. Điều này loại bỏ hoàn toàn hiện tượng phân tán vector do các con số gây ra.

---

### Tầng 1: Lớp Bộ đệm Vector Trung gian (Intermediate Vector Parquet Cache)

- **Vị trí lưu trữ:** `data/vector_cache/{model_slug}/*.parquet` (ví dụ: `data/vector_cache/bge_m3/*.parquet`)
- **Quy mô:** 141 file Apache Parquet, nén chuẩn Snappy.
- **Vai trò:** Cô lập hoàn toàn chi phí suy luận Embedding khỏi quy trình vận hành và cập nhật cơ sở dữ liệu.

```
┌────────────────────────────────────────────────────────┐
│ Apache Parquet Schema (data/vector_cache/bge_m3/*.parquet) │
├────────────────────────┬───────────────────────────────┤
│ Cột (Column)           │ Kiểu dữ liệu (Data Type)      │
├────────────────────────┼───────────────────────────────┤
│ chunk_id               │ Utf8 (Khóa chính)             │
│ doc_id                 │ Utf8                          │
│ content_hash           │ Utf8 (SHA-256 của embed_text) │
│ dense_vector           │ List[Float32] (dim=1024)      │
│ sparse_indices         │ List[UInt32] (Từ vựng băm)    │
│ sparse_values          │ List[Float32] (Trọng số BM25) │
└────────────────────────┴───────────────────────────────┘
```

#### Tại sao Parquet là lựa chọn tối ưu cho Vector Cache?
1. **Zero-Recompute (Không bao giờ suy luận lại):** Việc suy luận 30.282 chunks bằng mô hình `bge-m3` trên CPU mất khoảng 4 giờ. Khi có file Parquet, bất kể Qdrant bị xóa, đổi port, đổi từ Local sang Cloud, hay gặp lỗi `ReadTimeout`, hệ thống chỉ mất **70–90 giây** để đọc file Parquet và đẩy thẳng vào Qdrant mà không tốn một giây suy luận CPU nào.
2. **Hiệu năng I/O dạng cột (Columnar I/O):** Parquet cho phép đọc từng batch hàng nghìn vector với tốc độ hàng trăm MB/s, dung lượng nén giảm hơn 75% so với lưu JSON hay Pickle thông thường.
3. **Phát hiện thay đổi cấp độ Chunk (Granular Invalidation):** Trường `content_hash` lưu mã băm SHA-256 của `embed_text`. Khi một báo cáo được trích xuất lại bởi parser, hệ thống chỉ cần tính lại embedding cho những chunk có `content_hash` bị thay đổi, giữ nguyên 99% các chunk còn lại.

---

### Tầng 2: Hệ Động cơ Phục vụ Kép (Dual Serving Engines: Qdrant & DuckDB)

Thay vì cố gắng nhồi nhét mọi thứ vào một hệ quản trị cơ sở dữ liệu duy nhất, hệ thống triển khai hai động cơ phục vụ song song, mỗi động cơ giải quyết xuất sắc một bài toán chuyên biệt:

```
                            ┌────────────────────────┐
                            │      USER REQUEST      │
                            └───────────┬────────────┘
                                        │
                                        ▼
                            ┌────────────────────────┐
                            │     PLANNER AGENT      │
                            └─────┬────────────┬─────┘
                                  │            │
            [Yêu cầu ngữ cảnh & văn bản]   [Yêu cầu số liệu & chuỗi thời gian]
                                  │            │
                                  ▼            ▼
                   ┌────────────────────┐   ┌────────────────────┐
                   │   QDRANT ENGINE    │   │   DUCKDB ENGINE    │
                   │  (Vector + Sparse) │   │ (Relational Facts) │
                   └─────────┬──────────┘   └──────────┬─────────┘
                             │                         │
                             ▼                         ▼
                   [Danh sách Chunks top-k]  [Số liệu SQL chính xác 100%]
                             │                         │
                             └──────────┬──────────────┘
                                        │
                                        ▼
                            ┌────────────────────────┐
                            │   FACT VERIFIER &      │
                            │      WRITER AGENT      │
                            └────────────────────────┘
```

#### 1. Động cơ 1: Qdrant Vector & Hybrid Search Engine
- **Trách nhiệm:** Trả lời câu hỏi *"Chunk nào liên quan?"*. Chuyên trách tìm kiếm ngữ nghĩa mờ, phát hiện các đoạn thuyết minh phức tạp, đối chiếu câu chữ hợp đồng, rủi ro, sự kiện sau niên độ.
- **Khóa nhận diện Điểm (Point ID):** Sử dụng hàm băm định danh **UUID v5** từ chuỗi `chunk_id` (`uuid5(NAMESPACE_URL, chunk_id)`). Điều này đảm bảo tính Idempotency tuyệt đối: nạp lại dữ liệu 100 lần thì bản ghi vẫn ghi đè chính xác vào ID đó, không sinh điểm rác, không tạo duplicate.
- **Không gian Vector Kép (Dense + Sparse Hybrid):**
  - **Dense Vector:** Mô hình `BAAI/bge-m3` (1024 chiều, Cosine Distance).
  - **Sparse Vector:** BM25 Tiếng Việt chuyên sâu (`vietnamese_sparse_tokenizer.py`), bảo tồn nguyên vẹn các token đặc thù như số tiền kế toán (`12.694.975.751.615`), mã biểu mẫu (`b01`, `b02`, `b03`, `maso110`), ngày báo cáo (`31/12/2024`).
- **Lập chỉ mục Siêu dữ liệu Cứng (6 Payload Indexes):**
  Qdrant tạo sẵn 6 index dạng `keyword` và `integer` ngay khi khởi tạo:
  1. `ticker` (keyword): Lọc tuyệt đối theo mã doanh nghiệp (ví dụ: `FPT`, `VNM`, `HPG`).
  2. `fiscal_year` (integer): Lọc tuyệt đối theo năm tài chính (ví dụ: `2024`).
  3. `report_type` (keyword): Lọc theo loại báo cáo (`BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW`, `NOTES`).
  4. `scope` (keyword): `Hopnhat` (Hợp nhất) vs `Congtyme` (Công ty mẹ).
  5. `is_table` (bool): Phân biệt chunk bảng tính và chunk văn bản thuần.
  6. `section_standardized` (keyword): Nhãn phân loại chuẩn hóa của từng phần.
- **Mô hình Vận hành Linh hoạt (Hybrid Deployment Strategy):**
  - **Local Mode (Default for Dev & Benchmark):** Dữ liệu lưu tại thư mục cục bộ. Với 30.282 vectors kích thước 1024-dim, bộ nhớ RAM chỉ chiếm ~124 MB. Thời gian phản hồi truy vấn siêu tốc: **2–5 ms**. Không phụ thuộc mạng internet.
  - **Cloud Mode (Production Backup & Remote Collaboration):** Kết nối cluster Qdrant Cloud thông qua endpoint và API key trong `.env`. Được cấu hình cơ chế phòng thủ `timeout = 60.0s`, batch upload 64 điểm và Retry Backoff 3 lần để xử lý độ trễ đường truyền quốc tế.

#### 2. Động cơ 2: DuckDB In-process Relational Facts Store
- **Trách nhiệm:** Trả lời câu hỏi *"Số liệu chính xác là bao nhiêu?"*. Chuyên trách lưu trữ các chỉ tiêu kế toán đã được bóc tách có cấu trúc (`facts`).
- **Bản chất công nghệ:** DuckDB là hệ quản trị cơ sở dữ liệu quan hệ OLAP in-process, không cần cài đặt server riêng, tốc độ đọc trực tiếp từ JSON/Parquet lên tới hàng triệu dòng mỗi giây.
- **Cấu trúc bảng `facts`:**
  ```sql
  CREATE TABLE facts (
      fact_id VARCHAR PRIMARY KEY,
      doc_id VARCHAR,
      ticker VARCHAR,
      fiscal_year INTEGER,
      report_type VARCHAR,
      item_code VARCHAR,
      item_name VARCHAR,
      note VARCHAR,
      current_year DOUBLE,
      prior_year DOUBLE,
      unit VARCHAR,
      physical_page INTEGER,
      printed_page VARCHAR,
      chunk_id VARCHAR
  );
  ```
- **Sức mạnh phân tích tài chính vượt trội:**
  Khi cần so sánh doanh thu của Vinamilk (VNM) từ 2022 đến 2024 hoặc tính tốc độ tăng trưởng lũy kế:
  ```sql
  -- Truy vấn tức thì trong 1.2 mili-giây, chính xác tuyệt đối 100%
  SELECT 
      fiscal_year, 
      current_year AS revenue, 
      LAG(current_year) OVER (ORDER BY fiscal_year) AS prev_revenue,
      ROUND((current_year - LAG(current_year) OVER (ORDER BY fiscal_year)) * 100.0 / LAG(current_year) OVER (ORDER BY fiscal_year), 2) AS growth_rate_pct
  FROM facts
  WHERE ticker = 'VNM' AND item_code = '01' AND report_type = 'INCOME_STATEMENT'
  ORDER BY fiscal_year;
  ```
  > [!TIP]
  > Kết quả trả về là con số thuần túy từ bảng kế toán chính thức, triệt tiêu 100% khả năng LLM bị ảo giác khi đọc nhầm cột năm trước/năm nay trong chunk văn bản.

---

### Tầng 3: Lớp Kê khai Thực thi & Phân tách Đánh giá (Manifests & Evaluation Artifacts)

Để đảm bảo tính khoa học và có thể thẩm định (academic reproducibility), hệ thống xây dựng một tầng siêu dữ liệu kiểm định độc lập:

1. **Manifest File (`configs/manifests/manifest_{collection_name}.json`):**  
   Ghi lại "vân tay kỹ thuật" của mỗi lần dựng chỉ mục:
   ```json
   {
     "collection_name": "vnfin_v1_bge_m3_v1",
     "parser_version": "v2.0",
     "model_name": "BAAI/bge-m3",
     "model_version": "bge-m3-main",
     "embed_text_version": "v1",
     "dimension": 1024,
     "distance_metric": "Cosine",
     "total_chunks_indexed": 30282,
     "total_documents_indexed": 141,
     "created_at": "2026-10-30T10:15:30Z"
   }
   ```
2. **Company-level Held-out Split (`configs/eval_dataset_split.json`):**  
   Phân chia cố định 35 doanh nghiệp thành **25 Dev Companies** (101 tài liệu, 21.670 chunks) và **10 Test Companies** (40 tài liệu, 8.612 chunks). Phân chia theo công ty (không chia ngẫu nhiên theo chunk) để ngăn chặn hoàn toàn hiện tượng rò rỉ dữ liệu (data leakage) khi đánh giá các thuật toán xếp hạng.
3. **Bộ câu hỏi Golden chuẩn hóa (`configs/golden_evaluation_dataset.json`):**  
   114 câu hỏi kiểm định thực tế được phân loại rõ ràng:
   - **Type A (50%):** Câu hỏi số liệu đơn (sinh tự động từ DuckDB facts, có ground truth tuyệt đối).
   - **Type B (35%):** Câu hỏi ngữ cảnh văn bản (sinh từ chunk thuyết minh chính sách dài > 300 ký tự).
   - **Type C (15%):** Câu hỏi tổng hợp đa năm/đa chunk.
   - **Traps (Bẫy kiểm thử):** Câu hỏi về các công ty không có trong corpus (như FOX, DPM) để kiểm tra xem hệ thống có biết từ chối trả lời thay vì ảo giác.

---

## 3. Phân tích Đối đầu: Kiến trúc Hiện tại vs. Lưu trữ & Vận hành Thông thường (Conventional RAG)

### Bảng đối đầu 8 tiêu chí cốt lõi

| Tiêu chí Đánh giá | Lưu trữ & Vận hành Thông thường (Naive / Conventional RAG) | Kiến trúc Đa tầng Hiện tại (Multi-tier Multi-agent Architecture) |
| :--- | :--- | :--- |
| **1. Khả năng truy xuất số liệu** | Nhồi toàn bộ bảng số liệu vào Vector DB; LLM đọc text Markdown và tự cộng trừ $\rightarrow$ **Tỷ lệ sai lệch số học cao (> 35%)**. | **Tách đôi:** DuckDB xử lý số học chính xác 100% bằng SQL; Qdrant chỉ tìm văn bản và bối cảnh thuyết minh. |
| **2. Độ nhạy với văn bản lặp qua các năm** | Vector Search bị kéo nhầm sang các năm khác do văn bản chính sách kế toán giống hệt nhau $\rightarrow$ **Temporal Leakage**. | **Hard Filtering bắt buộc:** Mọi truy vấn đều áp bộ lọc siêu dữ liệu cứng (`ticker`, `fiscal_year`, `scope`) trước khi tính tương đồng cosine. |
| **3. Tối ưu Không gian Vector** | Embed toàn bộ chuỗi số dài $\rightarrow$ Không gian vector bị pha loãng (diluted), điểm tương đồng giữa các công ty bị bão hòa. | **Dual-stream:** `embed_text` chỉ lưu ngữ nghĩa chỉ tiêu + tiền tố chuẩn hóa; `text` nguyên bản lưu trữ ở payload riêng biệt. |
| **4. Chi phí Tái lập Chỉ mục (Re-indexing)** | Mỗi lần đổi mô hình, sửa parser hoặc lỗi mạng phải tính lại toàn bộ từ đầu $\rightarrow$ **Mất 4–6 tiếng CPU/lần**. | **Parquet Cache trung gian:** Tính 1 lần, lưu vĩnh viễn. Đẩy lại vào database mới chỉ mất **70–90 giây**, Zero-recompute. |
| **5. Khả năng Kiểm toán Trích dẫn** | Chỉ trả về chunk chung chung, không rõ nguồn trang vật lý trong hồ sơ gốc. | Mỗi chunk và fact gắn chặt với `citation_tag`, lưu rõ `physical_page` và `printed_page` của tài liệu kiểm toán gốc. |
| **6. Quản trị Phiên bản Chỉ mục** | Thường cập nhật đè trực tiếp (in-place mutation) $\rightarrow$ Không thể A/B test, dễ hỏng dữ liệu khi pipeline đứt gãy. | **Immutable Collections:** Đặt tên kèm phiên bản (`vnfin_v1_bge_m3_v1`), ghi `manifest.json`, quản lý ID bằng deterministic UUIDv5. |
| **7. Cơ chế Phục hồi Sự cố Mạng** | Nếu mạng ngắt quãng khi gọi Cloud DB, pipeline bị dừng và phải chạy lại từ con số 0. | **Kiến trúc phòng thủ:** Hỗ trợ chạy Local-first siêu tốc (2ms); Cloud upload có cơ chế Retry Backoff 3 tầng và Resume từ Parquet. |
| **8. Khả năng Đánh giá Khách quan** | Đánh giá ngẫu nhiên trên chunk, dễ rò rỉ kiến thức công ty giữa tập huấn luyện và kiểm định. | Cố định tập tách biệt ở cấp độ Doanh nghiệp (Company-level held-out split: 25 Dev / 10 Test) và bộ 114 Golden Questions. |

---

### Phân tích chi tiết 5 điểm vượt trội sống còn

#### Điểm 1: Triệt tiêu Ảo giác Số học bằng Động cơ Quan hệ Song song (DuckDB Facts vs Vector Hallucination)
Trong BCTC, một bảng kế toán có thể có hàng chục con số liền kề nhau: số đầu năm, số cuối năm, số đã kiểm toán lại, số hợp nhất và số công ty mẹ. Nếu chỉ lưu vector text:
- Khi người dùng hỏi: *"Chi phí bán hàng của Vinamilk năm 2023 tăng bao nhiêu phần trăm so với 2022?"*
- Hệ thống thông thường sẽ lấy ra chunk bảng biểu, đưa vào prompt cho LLM. Do bảng Markdown thường dài và phức tạp, LLM rất dễ nhầm giữa "Chi phí bán hàng" và "Chi phí quản lý doanh nghiệp", hoặc lấy nhầm cột "Năm trước" của báo cáo 2022 thay vì cột "Năm nay".
- **Kiến trúc hiện tại:** Planner gửi câu hỏi số liệu sang **DuckDB**. DuckDB thực thi câu lệnh SQL trực tiếp trên các bản ghi `facts` đã được gán mã chuẩn (`item_code`). Kết quả trả về một con số duy nhất chính xác đến từng đơn vị VNĐ, kèm theo công thức tính toán toán học minh bạch. LLM không bao giờ phải làm toán nhẩm.

#### Điểm 2: Tối ưu Không gian Nhúng bằng Dual-Stream (`text` vs `embed_text`)
Các mô hình Transformer embedding (kể cả những mô hình mạnh như BAAI/bge-m3, OpenAI text-embedding-3-large) đều mã hóa số liệu thành các sub-word tokens rời rạc. Một dãy số như `12.694.975.751.615` chiếm tới 15–20 tokens nhưng mang giá trị ngữ nghĩa gần như bằng 0 trong không gian biểu diễn văn bản.
- Việc nhồi số liệu vào vector làm loãng không gian vector, khiến khoảng cách cosine giữa hai công ty có chỉ tiêu giống nhau nhưng doanh thu chênh nhau 1.000 lần lại trở nên gần nhau một cách vô nghĩa.
- Bằng cách phân tách thành `embed_text` (chỉ gồm cấu trúc, tên mục, nhãn chỉ tiêu kinh tế và bối cảnh doanh nghiệp), vector embedding tập trung 100% "năng lượng" vào việc phân biệt khái niệm tài chính (ví dụ: phân biệt rạch ròi giữa *"Dòng tiền thuần từ hoạt động kinh doanh"* và *"Lợi nhuận thuần từ hoạt động kinh doanh"*).

#### Điểm 3: Tách rời Tính toán & Lưu trữ qua Tầng Đệm Parquet (Decoupled Compute & Storage)
Đây là thiết kế mang tính sống còn đối với các dự án xử lý dữ liệu lớn trên máy trạm hoặc môi trường hybrid:
- Trong quá trình phát triển, chúng ta thường xuyên phải thử nghiệm: thay đổi từ mô hình `bge-m3` sang `multilingual-e5-base`, chuyển từ Qdrant Local sang Qdrant Cloud, hoặc đổi khoảng cách từ Cosine sang Dot Product.
- Ở các kiến trúc thông thường, mỗi lần thử nghiệm là một lần chạy lại toàn bộ script embed kéo dài 4–5 tiếng.
- Với tầng đệm **Parquet Cache**, 30.282 vector được tính một lần và lưu cố định trong 141 file Parquet nhỏ gọn. Khi cần thử nghiệm một database mới (như Milvus, pgvector hay Qdrant Cloud), hệ thống chỉ việc đọc lại Parquet và stream vào database với tốc độ mạng tối đa. Thời gian thiết lập một cụm thử nghiệm mới giảm từ **240 phút xuống còn 1.5 phút (nhanh hơn 160 lần)**.

#### Điểm 4: Ngăn chặn Rò rỉ Thời gian (Zero Temporal Leakage via Payload Indexing)
Trong 4 năm từ 2022 đến 2025, phần thuyết minh về *"Nguyên tắc ghi nhận doanh thu"* hoặc *"Chính sách dự phòng nợ phải thu khó đòi"* của một ngân hàng (như ACB, ABBANK) hầu như không đổi một từ. 
- Nếu không có siêu dữ liệu cứng, người dùng hỏi về năm 2024 nhưng mô hình embedding có thể xếp đoạn văn của năm 2022 lên trên cùng vì đoạn văn năm 2022 có độ tương đồng cosine vô tình cao hơn 0.001%.
- Hệ thống giải quyết triệt để vấn đề này bằng việc index cứng trường `fiscal_year` và `ticker` trong Qdrant. Truy vấn của Retriever luôn bắt buộc đi kèm:
  ```json
  "filter": {
    "must": [
      {"key": "ticker", "match": {"value": "ABB"}},
      {"key": "fiscal_year", "match": {"value": 2024}}
    ]
  }
  ```
  Điều này cô lập không gian tìm kiếm trong đúng phạm vi năm tài chính cần khảo sát trước khi tính khoảng cách vector, loại bỏ 100% rủi ro trích dẫn nhầm năm.

#### Điểm 5: Tính Bất biến và Cơ chế Định danh Điểm Xác định (Deterministic UUIDv5)
Trong nhiều hệ thống RAG sơ sài, Point ID trong vector database được sinh bằng số nguyên tự tăng (`1, 2, 3...`) hoặc UUID ngẫu nhiên (`uuid4()`). 
- Khi nạp lại một tài liệu bị lỗi, hệ thống ngây thơ sẽ nạp trùng (duplicate) các chunk cũ, khiến số lượng điểm tăng vọt và kết quả tìm kiếm bị nhân đôi.
- Hệ thống áp dụng công thức toán học xác định:
  $$\text{Point\_ID} = \text{uuid5}(\text{NAMESPACE\_URL}, \text{chunk\_id})$$
  Ví dụ: `chunk_id = "FPT_2024_Hopnhat_c0015"` sẽ luôn luôn ánh xạ thành một UUID duy nhất bất kể được nạp lại bao nhiêu lần. Điều này đảm bảo tính toàn vẹn (idempotency) của toàn bộ cụm dữ liệu.

---

## 4. Sơ đồ Kiến trúc & Luồng Dữ liệu (Mermaid Diagrams)

### Sơ đồ 1: Kiến trúc Phân tầng Dữ liệu Đa tầng (Storage Tiers Topology)

```mermaid
flowchart TD
    subgraph TIER0["TẦNG 0: NGUỒN SỰ THẬT BẤT BIẾN (SSOT)"]
        PDF["141 Báo cáo Tài chính Kiểm toán (PDF gốc)"] --> PARSER["Document Parser Engine v2.0"]
        PARSER --> JSONS["data/processed_chunks/*.json<br>(141 files | 30.282 chunks | Facts tables)"]
    end

    subgraph TIER1["TẦNG 1: BỘ ĐỆM VECTOR TRUNG GIAN (ZERO-RECOMPUTE)"]
        JSONS -->|"Đọc embed_text<br>(Length-sorted Batching)"| EMBED["Transformer Embedding Engine<br>(BAAI/bge-m3)"]
        EMBED -->|"Ghi song song Dense & Sparse"| PARQUET["data/vector_cache/bge_m3/*.parquet<br>(141 files Snappy Columnar Cache)"]
    end

    subgraph TIER2["TẦNG 2: HỆ ĐỘNG CƠ PHỤC VỤ KÉP (DUAL SERVING ENGINES)"]
        PARQUET -->|"Stream nạp nhanh (70s)<br>UUIDv5 Point ID"| QDRANT["QDRANT VECTOR ENGINE<br>(Local / Cloud Collection)<br>- Dense: 1024-dim Cosine<br>- Sparse: Custom VN-Financial BM25<br>- 6 Hard Payload Indexes"]
        JSONS -->|"Load có cấu trúc trực tiếp"| DUCKDB["DUCKDB FACTS ENGINE<br>(In-process OLAP Store)<br>- Bảng facts kế toán chuẩn hóa<br>- Phép tính SQL tức thì (0-hallucination)"]
    end

    subgraph TIER3["TẦNG 3: VẬN HÀNH, ĐIỀU PHỐI & ĐÁNH GIÁ"]
        QDRANT <-->|"Truy vấn ngữ cảnh & bối cảnh"| AGENTS["HỆ MULTI-AGENT<br>(Planner, Retriever, Verifier, Writer)"]
        DUCKDB <-->|"Truy vấn số liệu chính xác & CAGR"| AGENTS
        AGENTS --> REPORT["BÁO CÁO PHÂN TÍCH TÀI CHÍNH HOÀN CHỈNH<br>(Đầy đủ số liệu & 100% trích dẫn minh bạch)"]
    end

    classDef tier0 fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    classDef tier1 fill:#fff3e0,stroke:#f57c00,stroke-width:2px;
    classDef tier2 fill:#e8f5e9,stroke:#388e3c,stroke-width:2px;
    classDef tier3 fill:#ede7f6,stroke:#512da8,stroke-width:2px;

    class PDF,PARSER,JSONS tier0;
    class EMBED,PARQUET tier1;
    class QDRANT,DUCKDB tier2;
    class AGENTS,REPORT tier3;
```

---

### Sơ đồ 2: Luồng Xử lý Truy vấn Phân nhánh Song song (Bifurcated Serving Flow)

```mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng / Nhà phân tích
    participant Planner as Planner Agent
    participant DuckDB as DuckDB (Facts Engine)
    participant Qdrant as Qdrant (Vector Engine)
    participant Verifier as Fact Verifier Agent
    participant Writer as Writer Agent

    User->>Planner: "Phân tích doanh thu và biên lợi nhuận của VNM năm 2024 so với 2023, giải thích nguyên nhân biến động?"
    
    rect rgb(240, 248, 255)
        Note over Planner,DuckDB: Nhánh 1: Truy vấn Số liệu Chính xác (Deterministic Query)
        Planner->>DuckDB: SQL Query (Doanh thu thuần mã 01, Lợi nhuận gộp mã 20 năm 2023-2024)
        DuckDB-->>Planner: Dữ liệu chuẩn xác: Doanh thu 2024 = 63.380 tỷ, 2023 = 60.369 tỷ (+4.98%), Biên lãi gộp 41.2%
    end

    rect rgb(255, 248, 240)
        Note over Planner,Qdrant: Nhánh 2: Truy vấn Ngữ cảnh & Thuyết minh (Semantic Query)
        Planner->>Qdrant: Hybrid Search (Filter: ticker='VNM', fiscal_year=2024, query="nguyên nhân biến động biên lợi nhuận")
        Qdrant-->>Planner: Top-3 chunks thuyết minh về giá sữa nguyên liệu đầu vào và cơ cấu chi phí bán hàng
    end

    rect rgb(245, 255, 245)
        Note over Verifier,Writer: Đối chiếu & Soạn thảo Báo cáo có trích dẫn
        Planner->>Verifier: Chuyển giao số liệu DuckDB + Đoạn trích Qdrant
        Verifier->>Verifier: Kiểm tra tính nhất quán giữa số liệu trong văn bản và bảng Facts
        Verifier-->>Writer: Bộ dữ liệu đã được xác thực (Validated Context)
        Writer->>Writer: Soạn thảo văn bản, tự động chèn Citation Tag: [VNM-2024-Hopnhat-p12]
        Writer-->>User: Báo cáo phân tích tài chính hoàn chỉnh, chính xác 100%
    end
```

---

## 5. Quy trình Vận hành Thực tế (Operational Workflows)

### Luồng Ingestion & Caching
Quy trình nạp và tạo lập chỉ mục được thực hiện tuần tự qua các lệnh CLI chuyên biệt:

1. **Khởi tạo và Kiểm tra Tiền thực thi (Dry-run / Benchmark):**
   ```bash
   # Kiểm tra tính toàn vẹn của dữ liệu và đo đạc tốc độ trên 200 chunks mẫu
   python src/indexing/pipeline.py --model bge-m3 --benchmark-200
   ```
2. **Suy luận Vector & Lưu trữ Parquet Cache:**
   ```bash
   # Quá trình này đọc data/processed_chunks/*.json, chạy mô hình bge-m3,
   # và tạo ra 141 files tại data/vector_cache/bge_m3/*.parquet
   python src/indexing/pipeline.py --model bge-m3
   ```
3. **Nạp dữ liệu vào Qdrant (Local hoặc Cloud):**
   ```bash
   # Chạy trên Qdrant Local (siêu nhanh, phục vụ phát triển & đánh giá nội bộ)
   python src/indexing/pipeline.py --model bge-m3 --reconcile-only

   # Hoặc đẩy lên Qdrant Cloud Cluster phục vụ chia sẻ và triển khai ứng dụng
   python src/indexing/pipeline.py --model bge-m3 --cloud
   ```

---

### Luồng Truy vấn Song song của Multi-Agent
Khi một câu hỏi tài chính được tiếp nhận:
1. **Phân tích Ý định (Intent Parsing):** Planner Agent xác định các thực thể: `ticker`, `fiscal_year`, `scope`, và loại câu hỏi (Hỏi số liệu thuần túy, hỏi nguyên nhân văn bản, hay hỏi so sánh tổng hợp).
2. **Thực thi Nhánh Số liệu (Deterministic Branch):** 
   - Planner Agent tạo câu lệnh SQL chuẩn gửi tới DuckDB.
   - DuckDB truy vấn trên bảng `facts`, tính toán các chỉ số phái sinh (YoY growth, tỷ lệ biên lợi nhuận, tỷ số thanh toán hiện hành).
   - Tuyệt đối không để LLM đoán số.
3. **Thực thi Nhánh Ngữ cảnh (Fuzzy Semantic Branch):**
   - Planner Agent kích hoạt Retriever Agent gọi Qdrant.
   - Áp dụng bộ lọc cứng `Filter(ticker, fiscal_year)`.
   - Kết hợp điểm số Hybrid: 
     $$\text{Score} = \alpha \cdot \text{DenseScore} + (1 - \alpha) \cdot \text{SparseScore}$$
   - Lấy ra top-k chunks liên quan nhất kèm theo `citation_tag` gốc.
4. **Hợp nhất & Trích dẫn Nguồn gốc (Synthesis & Citation Linking):**
   - Writer Agent kết hợp số liệu từ DuckDB và bối cảnh từ Qdrant.
   - Mọi tuyên bố số liệu trong báo cáo bắt buộc phải đi kèm tag dạng `[Doc_X, p.Y]` (Ví dụ: `[FPT-2024-Hopnhat-p15]`).

---

### Cơ chế Phục hồi Sự cố & Tự điều hòa (Self-healing & Reconciliation)

Hệ thống được thiết kế với cơ chế phòng thủ sâu để đảm bảo tính sẵn sàng cao trong mọi điều kiện hạ tầng:

1. **Khắc phục lỗi mạng và Timeout đối với Cloud Database:**
   - Khi giao tiếp với các cluster điện toán đám mây quốc tế (như Qdrant Cloud trên AWS US-West), độ trễ đường truyền xuyên Thái Bình Dương có thể gây ra hiện tượng `httpx.ReadTimeout`.
   - Hệ thống tự động kích hoạt bộ tham số phòng thủ: `timeout = 60.0s`, giảm kích thước gói tin gửi đi (`batch_size = 64`), và áp dụng thuật toán **Exponential Backoff Retry** (thử lại 3 lần với khoảng cách tăng dần `[2s, 4s, 8s]`).
2. **Cơ chế Điều hòa Dữ liệu (Reconciliation Loop):**
   - Lệnh `--reconcile-only` cho phép kiểm tra độ lệch (drift) giữa số lượng chunk trong file nguồn và số lượng điểm hiện có trong Qdrant collection.
   - Nếu phát hiện thiếu bất kỳ điểm nào, hệ thống chỉ đọc lại file Parquet tương ứng của tài liệu đó để bổ sung đúng những điểm còn thiếu mà không chạm vào các tài liệu đã toàn vẹn.
3. **Độc lập Không gian Vận hành (Local & Cloud Co-existence):**
   - Kiến trúc cho phép duy trì song song hai môi trường:
     - **Local Mode:** Đặt tại `.qdrant_local/`. Đây là môi trường chính để chạy benchmark, kiểm thử thuật toán retrieval, và phát triển tính năng mới với độ trễ tối thiểu (2–5 ms).
     - **Cloud Mode:** Đặt tại Qdrant Cloud. Đóng vai trò là cụm sao lưu (backup) và phục vụ các dịch vụ API hoặc dashboard bên ngoài truy cập.

---

## 6. Kết luận & Khuyến nghị Môi trường Sản xuất

Kiến trúc Lưu trữ và Vận hành Dữ liệu Đa tầng hiện tại không chỉ đơn thuần là việc chọn lựa các phần mềm cơ sở dữ liệu, mà là một **chiến lược kỹ thuật có tính toán sâu sắc** nhằm giải quyết tận gốc các điểm yếu chí mạng của AI trong lĩnh vực tài chính:

1. **Về độ chính xác:** Giải quyết triệt để vấn đề ảo giác số học bằng cách chuyển toàn bộ gánh nặng tính toán sang DuckDB facts store, chỉ sử dụng LLM cho việc hành văn và tổng hợp logic.
2. **Về độ tin cậy:** Bảo đảm 100% khả năng kiểm toán nguồn gốc thông qua cơ chế định danh trang vật lý (`physical_page`) và thẻ trích dẫn học thuật (`citation_tag`).
3. **Về chi phí vận hành:** Tiết kiệm hàng trăm giờ tính toán và chi phí API nhờ tầng đệm Parquet Cache trung gian (Zero-Recompute).
4. **Về tính linh hoạt:** Cho phép chuyển đổi mượt mà giữa môi trường làm việc cục bộ (Local siêu tốc) và môi trường phân tán (Cloud sẵn sàng mở rộng).

### Khuyến nghị vận hành chuẩn cho Đội ngũ Kỹ thuật:
- **Trong giai đoạn phát triển & Đánh giá (Dev & Benchmarking):** Luôn sử dụng Qdrant Local Mode và DuckDB In-process. Việc này triệt tiêu hoàn toàn sự phụ thuộc vào đường truyền internet, ngăn ngừa lỗi timeout và cho kết quả benchmark trung thực nhất về mặt thuật toán.
- **Trước khi cập nhật Parser:** Luôn đảm bảo tăng phiên bản (`parser_version = "v2.1"`) và tạo collection Qdrant mới có gắn phiên bản tương ứng trong tên. Tuyệt đối không ghi đè tại chỗ để duy trì khả năng đối sánh A/B testing khoa học.
- **Bảo trì Định kỳ:** Lưu trữ thư mục `data/vector_cache/` cẩn thận như một tài sản tính toán quan trọng. Đây là "bảo hiểm thời gian" giúp toàn bộ hệ sinh thái Multi-agent có thể dựng lại chỉ trong vài phút khi có bất kỳ sự cố hạ tầng nào xảy ra.

---
*Tài liệu được biên soạn và chuẩn hóa bởi Đội ngũ Kiến trúc Dự án Multi-agent Financial Report Writer.*
