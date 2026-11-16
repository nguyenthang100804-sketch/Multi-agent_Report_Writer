# Danh mục Tài liệu Tham khảo, Mã nguồn Chuẩn & Bộ Dữ liệu Chính thống
**Dự án:** Multi-Agent Framework to Write Report from Documents  
**Nguyên tắc biên soạn:** 100% tài liệu, bài báo khoa học (arXiv/ACL/EMNLP/ICLR/NeurIPS), hướng dẫn kỹ thuật chính hãng và kho mã nguồn dưới đây đều là tài liệu thực tế, đã được xác thực mã định danh (`arXiv ID`, `GitHub URL`, tác giả, năm công bố).

---

## 1. Các Bài báo Khoa học Cốt lõi về Multi-Agent Viết Báo cáo Dài (Long-Form Report Generation)

Đây là nhóm tài liệu quan trọng nhất để thiết kế **`Outline & Planning Agent`**, **`Retrieval & Researcher Agent`**, **`Section Writer Agent`** và **`Lead / Editor Synthesis Agent`**.

### 1.1. STORM (Stanford University – NAACL 2024)
* **Tên bài báo:** *Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models*
* **Tác giả:** Yijia Shao, Yucheng Jiang, Theodore A. Kanell, Peter Xu, Omar Khattab, Monica S. Lam (Stanford University)
* **Mã định danh & Liên kết:** [arXiv:2402.14207](https://arxiv.org/abs/2402.14207) | [ACL Anthology (NAACL 2024)](https://aclanthology.org/2024.naacl-long.347/)
* **Giá trị áp dụng cho Project:**
  - Giải quyết "điểm nghẽn tiền soạn thảo" (pre-writing bottleneck): Trước khi viết báo cáo, Agent phải khảo sát sơ bộ kho tài liệu để khám phá các góc nhìn (perspectives) và đặt câu hỏi đa chiều để lập dàn ý (`Outline & Planning Agent`).
  - Quy trình viết từng mục (section-by-section) gắn chặt với trích dẫn nguồn thu thập được, sau đó mới tổng hợp toàn bài.

### 1.2. Co-STORM (Stanford University – EMNLP 2024)
* **Tên bài báo:** *Into the Unknown Unknowns: Engaged Human Learning through Participation in Language Model Agent Conversations*
* **Tác giả:** Yucheng Jiang, Yijia Shao, Dekun Ma, Sina J. Semnani, Monica S. Lam (Stanford University)
* **Mã định danh & Liên kết:** [arXiv:2408.15232](https://arxiv.org/abs/2408.15232)
* **Giá trị áp dụng cho Project:**
  - Bổ sung cơ chế điều phối giữa nhiều Agent chuyên gia (Expert Agents), điều phối viên (Moderator) và cơ chế **Human-in-the-Loop** cho phép người dùng can thiệp vào cấu trúc dàn ý/bản đồ khái niệm (Mind Map / Outline) trước và trong khi viết báo cáo.

### 1.3. LongWriter & AgentWrite (Tsinghua University & ZhipuAI – ICLR 2025)
* **Tên bài báo:** *LongWriter: Unleashing 10,000+ Word Generation from Long Context LLMs*
* **Tác giả:** Yushi Bai, Jiajie Zhang, Xin Lv, Linzhi Zheng, Siqi Zhu, Lei Hou, Yuxiao Dong, Jie Tang, Juanzi Li
* **Mã định danh & Liên kết:** [arXiv:2408.07055](https://arxiv.org/abs/2408.07055) | [GitHub: THUDM/LongWriter](https://github.com/THUDM/LongWriter)
* **Giá trị áp dụng cho Project:**
  - Chứng minh tại sao LLM dù có context đầu vào >100k tokens vẫn không thể viết báo cáo dài quá ~2,000 từ nếu chỉ gọi 1 lần.
  - Đề xuất kiến trúc **AgentWrite** (Divide-and-Conquer): Chia bài viết dài thành kế hoạch từng mục kèm phân bổ độ dài mục tiêu (target word count per section), viết từng phần rồi ghép nối đồng bộ.

### 1.4. PaperQA2 (FutureHouse – 2024)
* **Tên bài báo:** *Language agents achieve superhuman synthesis of scientific knowledge*
* **Tác giả:** Michael D. Skarlinski, Sam Cox, Jon M. Laurent, James D. Braza, Michaela Hinks, Michael J. Hammerling, Manvitha Ponnapati, Samuel G. Rodriques, Andrew D. White
* **Mã định danh & Liên kết:** [arXiv:2409.13740](https://arxiv.org/abs/2409.13740) | [GitHub: Future-House/paper-qa](https://github.com/Future-House/paper-qa)
* **Giá trị áp dụng cho Project:**
  - Thiết kế Agent chuyên đọc tài liệu PDF khoa học/kỹ thuật, chấm điểm mức độ liên quan của từng đoạn trích (Contextual Summarization & Evidence Scoring) và phát hiện mâu thuẫn giữa các tài liệu trước khi đưa vào bước viết tổng hợp.

---

## 2. Các Bài báo Khoa học về Kiểm chứng Trích dẫn, Chống Ảo giác & Vòng lặp Phản biện (Fact-Checking, Citations & Critique Loops)

Nhóm tài liệu này là cơ sở lý thuyết và thuật toán trực tiếp cho **`Fact-Checker & Critique Agent`** (Tuần 4) và vòng lặp điều kiện trên **LangGraph**.

### 2.1. ALCE – Chuẩn Đánh giá Sinh Văn bản Kèm Trích dẫn (Princeton University – EMNLP 2023)
* **Tên bài báo:** *Enabling Large Language Models to Generate Text with Citations*
* **Tác giả:** Tianyu Gao, Howard Yen, Jiatong Yu, Danqi Chen (Princeton University)
* **Mã định danh & Liên kết:** [arXiv:2305.14627](https://arxiv.org/abs/2305.14627) | [GitHub: princeton-nlp/ALCE](https://github.com/princeton-nlp/ALCE)
* **Giá trị áp dụng cho Project:**
  - Định nghĩa chuẩn mực cách gắn citation inline (dạng `[1]`, `[2]` hoặc `[Doc_X, p.Y]`) và bộ công thức đo **Citation Recall** (mệnh đề có được dẫn nguồn đầy đủ không) và **Citation Precision** (nguồn được trích dẫn có thực sự chứng minh cho mệnh đề đó không, sử dụng mô hình NLI / LLM Judge).

### 2.2. RARR – Tự động Kiểm chứng & Sửa chữa Sau khi Viết (Google Research – ACL 2023)
* **Tên bài báo:** *RARR: Researching and Revising What Language Models Say, Using Language Models*
* **Tác giả:** Luyu Gao, Zhuyun Dai, Panupong Pasupat, Anthony Chen, Arun Tejasvi Chaganty, Yicheng Fan, Vincent Zhao, Ni Lao, Hongrae Lee, Da-Cheng Juan, Kelvin Guu
* **Mã định danh & Liên kết:** [arXiv:2210.08726](https://arxiv.org/abs/2210.08726) | [ACL Anthology (ACL 2023)](https://aclanthology.org/2023.acl-long.910/)
* **Giá trị áp dụng cho Project:**
  - Cung cấp đúng mẫu thiết kế (design pattern) giữa `Section Writer Agent` và `Fact-Checker Agent`: Tách câu trong bản nháp $\rightarrow$ truy vấn lại kho bằng chứng $\rightarrow$ kiểm tra mức độ đồng thuận (Agreement Model) $\rightarrow$ chỉ chỉnh sửa những mệnh đề sai lệch trong khi giữ nguyên mạch văn của đoạn.

### 2.3. FActScore – Phân rã Mệnh đề Nguyên tử để Đo Độ Chính xác (UW / Meta AI / AI2 – EMNLP 2023)
* **Tên bài báo:** *FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation*
* **Tác giả:** Sewon Min, Kalpesh Krishna, Xinxi Lyu, Mike Lewis, Wen-tau Yih, Pang Wei Koh, Mohit Iyyer, Luke Zettlemoyer, Hannaneh Hajishirzi
* **Mã định danh & Liên kết:** [arXiv:2305.14251](https://arxiv.org/abs/2305.14251) | [GitHub: shmsw25/FActScore](https://github.com/shmsw25/FActScore)
* **Giá trị áp dụng cho Project:**
  - Thay vì chấm điểm cả đoạn văn một cách cảm tính, `Fact-Checker Agent` phải bóc tách đoạn văn thành các **Atomic Facts** (mệnh đề nguyên tử chứa đúng 1 thông tin/số liệu), sau đó tính tỷ lệ % các mệnh đề được hỗ trợ bởi `EvidenceChunk` để ra `groundedness_score`.

### 2.4. SAFE & LongFact (Google DeepMind – 2024)
* **Tên bài báo:** *Long-form factuality in large language models*
* **Tác giả:** Jerry Wei, Chengrun Yang, Xinying Song, Yifeng Lu, Nathan Hu, Jie Huang, Dustin Tran, Daiyi Peng, Ruibo Liu, Da Huang, Cosmo Du, Quoc V. Le
* **Mã định danh & Liên kết:** [arXiv:2403.18802](https://arxiv.org/abs/2403.18802) | [GitHub: google-deepmind/long-form-factuality](https://github.com/google-deepmind/long-form-factuality)
* **Giá trị áp dụng cho Project:**
  - Kiến trúc **SAFE (Search-Associated Factuality Evaluator)**: Sử dụng Agent đánh giá tự động từng fact trong văn bản dài với chi phí thấp hơn nhưng độ đồng thuận cao hơn con người.

### 2.5. Self-RAG & Corrective RAG (CRAG) – Luồng Tự Phản biện trong RAG
* **Self-RAG:** *Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection* — Akari Asai, Zeqiu Wu, Yizhong Wang, Avirup Sil, Hannaneh Hajishirzi (ICLR 2024) | [arXiv:2310.11511](https://arxiv.org/abs/2310.11511)
* **CRAG:** *Corrective Retrieval Augmented Generation* — Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling (2024) | [arXiv:2401.15884](https://arxiv.org/abs/2401.15884)
* **Reflexion:** *Reflexion: Language Agents with Verbal Reinforcement Learning* — Noah Shinn et al. (NeurIPS 2023) | [arXiv:2303.11366](https://arxiv.org/abs/2303.11366)
* **Giá trị áp dụng cho Project:**
  - Là nền tảng chuẩn cho các mẫu đồ thị LangGraph (`LangGraph Corrective RAG` & `LangGraph Self-RAG`):
    - Dùng tiêu chí của **CRAG** ở `Retrieval & Researcher Agent`: Đánh giá chất lượng chunks vừa tìm được (`Relevant` / `Ambiguous` / `Irrelevant`); nếu thiếu thông tin thì viết lại câu truy vấn (Query Rewriting) trước khi chuyển cho Writer.
    - Dùng tiêu chí của **Self-RAG** & **Reflexion** ở `Fact-Checker & Critique Agent`: Phân loại bản nháp thành `Fully Supported` / `Partially Supported` / `No Support` và sinh phản hồi bằng ngôn ngữ tự nhiên (`revision_instructions`) để Writer sửa ở vòng lặp tiếp theo.

---

## 3. Tài liệu Kỹ thuật về Document Parsing, Hybrid Search & RAG Evaluation

### 3.1. IBM Docling Technical Report (IBM Research – 2024)
* **Tên bài báo:** *Docling Technical Report*
* **Tác giả:** Deep Search Team, IBM Research (Nikolaos Livathinos, Christoph Auer, Maksym Lysak, et al.)
* **Mã định danh & Liên kết:** [arXiv:2408.09869](https://arxiv.org/abs/2408.09869) | [GitHub: DS4SD/docling](https://github.com/DS4SD/docling)
* **Giá trị áp dụng cho Project:**
  - Giải thích cơ chế nhận diện bố cục trang (**DocLayNet**) và cấu trúc bảng biểu (**TableFormer**) để chuyển PDF phức tạp sang Markdown/JSON mà không làm vỡ bảng số liệu.

### 3.2. BGE M3-Embedding (BAAI – 2024)
* **Tên bài báo:** *M3-Embedding: Multi-Linguality, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation*
* **Tác giả:** Jianlv Chen, Shitao Xiao, Peitian Zhang, Kun Luo, Defu Lian, Zheng Liu
* **Mã định danh & Liên kết:** [arXiv:2402.03216](https://arxiv.org/abs/2402.03216) | [HuggingFace: BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)
* **Giá trị áp dụng cho Project:**
  - Hỗ trợ hơn 100 ngôn ngữ (bao gồm tiếng Việt và tiếng Anh), context lên tới 8,192 tokens, và xuất đồng thời cả **Dense Vector** + **Sparse Lexical Weights (BM25-like)** để nạp trực tiếp vào **Qdrant Hybrid Search**.

### 3.3. RAGAS – Tự động Đánh giá Hệ thống RAG (EACL 2024)
* **Tên bài báo:** *Ragas: Automated Evaluation of Retrieval Augmented Generation*
* **Tác giả:** Shahul Es, Jithin James, Luis Espinosa-Anke, Steven Schockaert
* **Mã định danh & Liên kết:** [arXiv:2309.15217](https://arxiv.org/abs/2309.15217) | [GitHub: explodinggradients/ragas](https://github.com/explodinggradients/ragas)
* **Giá trị áp dụng cho Project:**
  - Cung cấp công thức toán học và thư viện Python dùng trực tiếp cho **Phase 5 (T5.1 - Benchmarking)** với các chỉ số `Faithfulness`, `Answer Relevance`, `Context Precision` và `Context Recall`.

---

## 4. Hướng dẫn Kỹ thuật Chính hãng & Kho Mã nguồn Tham chiếu (Official Docs & Reference Repos)

Đây là các tài liệu kỹ thuật thực chiến giúp rút ngắn thời gian code ở **Phase 2, 3, 4**:

| STT | Tên Tài liệu / Repository | Tổ chức phát hành | Liên kết chính thức | Mục đích tham khảo trong dự án |
| :-: | :--- | :--- | :--- | :--- |
| 1 | **Building Effective Agents** | **Anthropic** (Erik Schluntz & Barry Zhang, 12/2024) | [anthropic.com/research/building-effective-agents](https://www.anthropic.com/research/building-effective-agents) | Chuẩn hóa 3 design patterns cốt lõi mà dự án sử dụng: **Orchestrator-Workers** (Planner chia việc), **Parallelization / Sectioning** (viết song song các mục) và **Evaluator-Optimizer** (`Writer <-> Fact-Checker`). |
| 2 | **Open Deep Research (`open_deep_research`)** | **LangChain AI** | [github.com/langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research) | **Code mẫu tham chiếu số 1 cho dự án:** Viết hoàn toàn bằng **LangGraph**, minh họa cách dùng `StateGraph`, `Send()` API để chạy song song các nhánh viết từng mục báo cáo và tổng hợp kết quả. |
| 3 | **Stanford STORM (`knowledge-storm`)** | **Stanford OVAL Lab** | [github.com/stanford-oval/storm](https://github.com/stanford-oval/storm) | Tham khảo cách thiết kế prompt lập dàn ý đa chiều, quản lý cây mục lục và chuẩn hóa citation trong bài viết dài. |
| 4 | **GPT Researcher** | **Assaf Elovic / Tavily** | [github.com/assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | Tham khảo kiến trúc Multi-Agent `Planner -> Execution (Researcher) -> Publisher (Writer/Editor)` và cách xuất báo cáo sang PDF/DOCX/Markdown. |
| 5 | **LangGraph Official Tutorials: RAG & Multi-Agent Patterns** | **LangChain AI** | [langchain-ai.github.io/langgraph/tutorials/](https://langchain-ai.github.io/langgraph/tutorials/) | Tài liệu chính thức hướng dẫn cài đặt `Agentic RAG`, `Corrective RAG (CRAG)`, `Self-RAG`, `Map-Reduce Send API` và `Subgraphs` trên LangGraph. |

---

## 5. Các Bộ Dữ liệu Tài liệu Mẫu Chính thống (Dùng cho Task T1.2 & T5.1)

Để phục vụ **Task T1.2 (Chuẩn bị dữ liệu tài liệu mẫu cho RAG & Chunking)** và **Task T5.1 (Benchmarking chất lượng báo cáo)** mà không phải dùng dữ liệu giả định, bạn có thể lấy trực tiếp từ 4 bộ dữ liệu chuẩn quốc tế sau:

1. **FinanceBench (Báo cáo Tài chính Doanh nghiệp Thực tế – PDF phức tạp):**
   * **Bài báo:** *FinanceBench: A New Benchmark for Financial Question Answering* ([arXiv:2311.11944](https://arxiv.org/abs/2311.11944))
   * **Kho dữ liệu:** [github.com/patronus-ai/financebench](https://github.com/patronus-ai/financebench) | [HuggingFace: PatronusAI/financebench](https://huggingface.co/datasets/PatronusAI/financebench)
   * **Đặc điểm:** Bao gồm các báo cáo tài chính thực tế (SEC 10-K, 10-Q, Earnings Reports của 3M, Activision, Adobe, Amazon, Amcor...) ở định dạng **PDF nhiều trang, nhiều bảng biểu số liệu** kèm theo câu hỏi, câu trả lời chuẩn và **đoạn trích dẫn gốc kèm số trang (evidence string & page number)**. Rất lý tưởng để kiểm thử độ chính xác của `Document Parser Agent` và khả năng bắt lỗi sai số liệu của `Fact-Checker Agent`.

2. **MultiHop-RAG (Tổng hợp Thông tin Liên Tài liệu – Multi-Document Synthesis):**
   * **Bài báo:** *MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries* ([arXiv:2401.15391](https://arxiv.org/abs/2401.15391))
   * **Kho dữ liệu:** [github.com/yixuantt/MultiHop-RAG](https://github.com/yixuantt/MultiHop-RAG) | [HuggingFace: yixuantt/MultiHop-RAG](https://huggingface.co/datasets/yixuantt/MultiHop-RAG)
   * **Đặc điểm:** Tập hợp các bài báo thực tế yêu cầu hệ thống phải truy xuất và kết nối dẫn chứng nằm rải rác ở **2 đến 4 tài liệu khác nhau** mới viết được nhận định đúng. Rất phù hợp để đánh giá khả năng tổng hợp đa tài liệu của hệ thống.

3. **QASPER (Tập Bài báo Khoa học Chuyên sâu – Technical Reports):**
   * **Bài báo:** *A Dataset of Information-Seeking Questions and Answers Anchored in Research Papers* ([arXiv:2105.03011](https://arxiv.org/abs/2105.03011))
   * **Kho dữ liệu:** [HuggingFace: allenai/qasper](https://huggingface.co/datasets/allenai/qasper)
   * **Đặc điểm:** Gồm 1,585 bài báo nghiên cứu khoa học toàn văn chia theo cấu trúc Section/Paragraph rõ ràng, kèm theo các đoạn bằng chứng chuẩn (highlighted evidence) do chuyên gia đánh dấu.

4. **ALCE Benchmark Corpus (Đánh giá Độ Chính xác Trích dẫn):**
   * **Bài báo:** [arXiv:2305.14627](https://arxiv.org/abs/2305.14627)
   * **Kho dữ liệu:** [github.com/princeton-nlp/ALCE](https://github.com/princeton-nlp/ALCE)
   * **Đặc điểm:** Cung cấp sẵn script đánh giá tự động tỷ lệ trích dẫn đúng (`Citation Recall` & `Citation Precision`) bằng mô hình NLI (`TRUE` model).
