# Báo cáo cá nhân — Day 6

> **Họ và tên:** Phạm Quang Trường · **MSSV:** 2A202603378 · **Lớp:** L3A
> **Chủ đề:** Tài liệu kỹ thuật — *"Tìm hiểu kỹ thuật kiểm thử End-to-End và ứng dụng công cụ Selenium cho website thời trang IVY moda"*
> **Ngày chạy:** 2026-11-13 · Kết quả từ `starter/results/summary.json` + `starter/results/traces.json`.

---

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  Tài liệu kỹ thuật về kiểm thử phần mềm End-to-End và công cụ Selenium, nguồn `data/KTPM_N11.pdf` (Word→PDF, 71 trang vật lý). Đây là đồ án của chính học viên/nhóm nên được phép dùng cho mục đích học tập (ghi rõ tại `data/manifest.json`).
  **Quy tắc tính trang:** chỉ tính trang có nội dung hữu ích — trang vật lý **10..70** (tổng **61 trang nội dung**). Loại trang bìa/lời cảm ơn/mục lục/danh mục bảng-hình (trang 1..9) và trang tài liệu tham khảo (trang 71). Số trang in = trang vật lý − 1.

- **Chuẩn hóa, lỗi và giới hạn:**
  Đọc bằng `pypdf` với `extraction_mode="layout"` (khử gần hết khoảng trắng thừa do Word→PDF), sau đó `NFC` + gộp khoảng trắng, giữ dòng để chunk theo đoạn. Không trang nào rỗng; không cần OCR (text gốc, không scan). Một số khoảng trắng thừa trong từ còn sót lại được xử lý khi so khớp evidence bằng *de-spaced matching* (`evaluation._despace`). Hạn chế: các trang 28..32 và 37..41 chủ yếu là hình/bảng nên ít ký tự (33–419 ký tự/trang), vẫn giữ vì chứa chú thích có ý nghĩa.

- **Embedding model / vector store / metric / chi phí (đã chạy):**
  - **Embedding: local Sentence Transformers `paraphrase-multilingual-MiniLM-L12-v2`, 384 chiều** (sentence-transformers 6.3.0, torch 2.15.0+cpu). Lý do dùng local thay vì OpenAI: tài khoản OpenAI hết credit (lỗi HTTP 429 "You have no credits remaining") — đã ghi nhận và dùng phương án dự phòng theo `RULES.md`. Model là embedding thật, không phải vector mock; query/document dùng chung encoder (model đối xứng), chuẩn hóa L2.
  - **Vector store: Chroma 1.5.9 (persistent local, cosine `hnsw:space=cosine`), lưu tại `starter/chroma_data/`.** Lý do dùng Chroma thay pgvector: môi trường chạy không có Docker/PostgreSQL (`docker` không khả dụng). Search exact cosine; metadata filter qua `where`.
  - Chi phí API: **$0** (model local, không gọi API trả phí). Nếu dùng OpenAI `text-embedding-3-small` thì ước tính ~$0.0002 (token ≈ ký tự/4, giá $0.02/1M).
  - Mã vẫn hỗ trợ cả hai backend qua biến môi trường `EMBEDDING_BACKEND` (`openai`/`local`) và `STORE_BACKEND` (`pgvector`/`chroma`).

- **Metadata bắt buộc và trường lọc bổ sung:**
  - Bắt buộc: `document_id` (=`ktpm_e2e_selenium`), `source` (=`data/KTPM_N11.pdf`), `page` (trang vật lý PDF, 1-based).
  - Trường lọc bổ sung: **`section`** (`string`), 5 giá trị `mo_dau`, `chuong_1`, `chuong_2`, `chuong_3`, `ket_luan`; gán theo khoảng trang (kiểm chứng được). Lý do chọn: 3 chương phân biệt rõ, cho phép lọc truy vấn theo chương.
  - **Tính hữu dụng (không chỉ "đủ trường"):** `section` giúp *lọc phạm vi truy vấn* (khi câu hỏi chỉ quan tâm một chương) và *truy vết* (biết ngay chunk thuộc chương nào) — thực tế C lọc đúng 3/3 câu filter, loại bỏ chunk ngoài chương. **Hạn chế:** `section` chỉ có 5 giá trị (mức chương) nên *không* phân biệt được các mục con trong cùng một chương (vd nhiều test case khác nhau đều là `chuong_3`); muốn lọc mịn hơn cần thêm trường như `module_name`.

---

## Cấu hình và benchmark

- **A / B / C (tham số cụ thể, khác biệt duy nhất B–C):**
  | Cấu hình | Chunk | Filter |
  |---|---|---|
  | **A** | `fixed_size`, size 500, overlap 50 | không lọc |
  | **B** | `by_paragraph`, max 700 (theo đoạn/heading) | không lọc |
  | **C** | `by_paragraph`, max 700 (giống B) | lọc `section` — chỉ khi câu hỏi có filter |
  A–B so sánh ảnh hưởng chunking; B–C chỉ khác filter (tách riêng ảnh hưởng metadata). Cùng corpus, model, metric, bộ câu hỏi.

- **Bộ câu hỏi (≥20), phân chia và kiểm chứng evidence:**
  `benchmark/benchmark.json`: **22 câu** — **16 dev / 6 test**, tách trước khi chạy. Gồm trực tiếp (14), diễn đạt lại (3), điều kiện/ngoại lệ (2) và **3 câu metadata filter** (2 dev + 1 test: `q20` lọc `chuong_1`, `q21` lọc `chuong_2`, `q22` lọc `chuong_3`).
  **Kiểm chứng evidence:** từng `evidence_quote` được xác minh là chuỗi con (de-spaced) của trang `gold_page` sau chuẩn hóa — 22/22 đạt. Gold không đưa vào query/filter; filter do người dùng/ngữ cảnh cung cấp trước truy xuất.

- **Tiêu chí chọn chiến lược (chốt trước khi xem test):**
  Ưu tiên **1) Evidence Hit@3** → **2) Grounding quality** → **3) tài nguyên** (số chunk/thời gian/chi phí). Không tinh chỉnh theo test.

---

## Kết quả

**Retrieval (đã chạy, số thật):**

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian ingest | Chi phí API |
|---|---|---|---|---|---|---|
| A | dev | 8/16 | 10/16 | 120 | 3.08s | $0 |
| A | test | 2/6 | 4/6 | 120 | (gộp) | $0 |
| B | dev | 7/16 | 13/16 | 103 | 2.48s | $0 |
| B | test | 1/6 | 5/6 | 103 | (gộp) | $0 |
| C | dev | 7/16 | 13/16 | 103 | 2.43s | $0 |
| C | test | 1/6 | 5/6 | 103 | (gộp) | $0 |

Thống kê chunk (thật): **A** 120 chunk, 46 923 ký tự (min 33, max 500, mean 391.0); **B/C** 103 chunk, 43 949 ký tự (min 8, max 700, mean 426.7). A có tổng ký tự cao hơn do overlap 50 tạo nội dung trùng lặp (~7%). Thời gian là embed+store trên CPU local (model đã tải).

**Audit thủ công (tác giả tự chấm — nguy cơ thiên lệch đã ghi nhận):**

| Strategy | Coherence TB /2 (n=10) | Metadata đủ & đúng (n/N) | Filter tuân thủ (n/N) | Grounding 0/1/2 + TB /2 (n=5 test) |
|---|---|---|---|---|
| A | 1.0 | 15/15 | 2/3 | 0×2, 1×0, 2×3 → **1.2** |
| B | 1.9 | 15/15 | 1/3 | 0×1, 1×0, 2×4 → **1.6** |
| C | 1.9 | 15/15 | **3/3** | 0×1, 1×0, 2×4 → **1.6** |

- **Coherence** (10 vị trí cố định = đầu trang 10..19): A cắt giữa ý tại biên 500 ký tự (ví dụ trang 10 cắt ngay giữa từ "công nghiệp ph…", trang 15/17/19 bắt đầu giữa câu) → đa số 1/2. B/C bám theo đoạn/heading nên tự hiểu được → 9/10 vị trí đạt 2/2; 1 vị trí (trang 19) bắt đầu giữa câu do chính PDF ngắt trang giữa câu (thuộc tính nguồn, không phải lỗi chunk). Lưu ý: B/C còn sinh chunk heading rất ngắn (14–40 ký tự).
- **Metadata** (5 câu test × top-3 = 15 bản ghi): `source`, `page`, `section` đều đúng/đủ → 15/15 cho cả ba chiến lược (gán section theo khoảng trang, kiểm chứng được).
- **Filter tuân thủ** (3 câu có filter): C đạt **3/3** (áp filter nên top-3 nằm đúng chương); A=2/3, B=1/3 vì không lọc nên lọt chunk ngoài chương (vd B `q20` trả về trang 11 thuộc `mo_dau`). Với câu không filter, C chạy không filter (đúng GUIDE).
- **Grounding** (5 câu test, thang 0–2): A yếu hơn (q19 thiếu bằng chứng ngôn ngữ Selenium vì chunk cố định tách nhầm phần; q16 không có bằng chứng). B/C tốt hơn: 4/5 câu đủ bằng chứng; q16 vẫn 0 vì tên riêng không có tín hiệu ngữ nghĩa.

**Đường dẫn trace và nhãn:** trace top-3 đầy đủ tại `starter/results/traces.json` (câu, ID chunk, text, score, metadata, cờ hit, filter-compliance); chỉ số gộp tại `starter/results/summary.json`; nhãn thủ công chi tiết (coherence từng vị trí, grounding từng câu, filter từng câu) tại `starter/results/manual_audit.json`. Cách chọn mẫu: coherence theo 10 trang đầu đã sắp xếp; metadata/grounding trên 5 câu test.

**Nạp lại không trùng:** `upsert` xóa theo `(strategy, document_id)` rồi chèn lại nên idempotent — pipeline đã chạy lại 3 lần, số chunk luôn ổn định (A=120, B=C=103) và kết quả Hit@1/Hit@3 giữ nguyên, không nhân đôi. Khi tài liệu đổi (chunk boundary thay đổi), chunk cũ được xóa tự động.

**Đối chiếu 5 tiêu chí (BENCHMARK.md):** ① Retrieval accuracy → bảng Hit@1/Hit@3 dev+test; ② Chunk coherence → nhãn 10 vị trí (1.0/1.9/1.9); ③ Metadata usefulness → 15/15 + filter tuân thủ + giải thích hữu dụng & hạn chế; ④ Grounding quality → nhãn 5 câu test (1.2/1.6/1.6); ⑤ Data strategy impact → so sánh A–B và B–C kèm đánh đổi.

---

## Phân tích và kết luận

- **So sánh A–B (chunking):** B tăng Evidence Hit@3 rõ rệt so với A (**dev 10/16 → 13/16**, **test 4/6 → 5/6**), dù Hit@1 hơi giảm (8→7 dev). A cắt ngang ý tại biên cố định nên evidence hay bị tách khỏi đoạn vàng (coherence 1.0 vs 1.9), dẫn đến nhiều miss hơn (A miss 8 câu, B/C miss 4 câu). → Chunk theo đoạn/heading **tốt hơn** cho corpus này.
- **So sánh B–C (filter):** Hit@3 giữ nguyên (13/16, 5/6) vì gold đã nằm trong top-3 của B; nhưng C cải thiện **độ chính xác/grounding**: top-3 tuân thủ filter 3/3 (B chỉ 1/3), loại bỏ chunk ngoài chương (vd `q20`, `q22`). Lợi ích của filter nằm ở việc thu hẹp phạm vi và tăng độ tin cậy, không nhất thiết tăng Hit@3 trên corpus nhỏ.
- **2 ví dụ sai:**
  1. `q16` (test, gold trang 56) *"Ai là người tạo test case Tìm kiếm sản phẩm?"* — cả 3 chiến lược miss: tên riêng "Phạm Quang Trường" không có tín hiệu ngữ nghĩa; query chỉ còn từ chung "tạo test case/tìm kiếm" nên xếp các mục test-case khác lên trên.
  2. `q12` (dev, gold trang 25) *"Selenium là công cụ gì?"* — B/C miss vì trang 26 chứa câu gần trùng ("Selenium là bộ kiểm thử tự động miễn phí…") xếp hạng cao hơn; đây là bằng chứng gần-trùng lặp khiến gold theo trang bị "đánh bại" bởi trang tương đương.
- **Chiến lược chọn:** theo tiêu chí đã chốt (Hit@3 → grounding → tài nguyên), chọn **C** — Hit@3 ngang B nhưng grounding/metadata và khả năng lọc tốt hơn (filter 3/3), chi phí/time tương đương B. Đánh đổi: C phụ thuộc giá trị `section` được gán đúng và chỉ lọc khi người dùng cung cấp filter.
- **Hạn chế:** corpus một tài liệu, bộ test nhỏ (22 câu, 6 test) nên không suy rộng; nhãn coherence/grounding do tác giả tự chấm (thiên lệch); đo thời gian trên CPU local có nhiễu; mô hình embedding đa ngữ nhỏ (384 dims) có thể yếu hơn mô hình lớn; khoảng trắng thừa của PDF chỉ khắc phục ở khâu so khớp evidence.
- **Nếu làm lại/mở rộng:** thêm hybrid BM25 + dense (giữ nguyên chunk/filter), bổ sung `alt_pages` cho bằng chứng gần-trùng (vd `q12`), dùng nhiều tài liệu để lọc theo `document_type`/`version`, thử chunk đa tầng để tránh chunk heading quá ngắn.
