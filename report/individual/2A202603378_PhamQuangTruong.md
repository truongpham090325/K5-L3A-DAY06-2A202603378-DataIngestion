# Báo cáo cá nhân — Day 6

> **Họ và tên:** Phạm Quang Trường · **MSSV:** 2A202603378 · **Lớp:** L3A
> **Chủ đề:** Tài liệu kỹ thuật — *"Tìm hiểu kỹ thuật kiểm thử End-to-End và ứng dụng công cụ Selenium cho website thời trang IVY moda"*
> **Trạng thái kết quả:** Các ô đánh dấu **`[chưa chạy]`** cần chạy pipeline rồi điền từ `starter/results/summary.json` và audit thủ công (xem mục *Cách điền kết quả* ở cuối).

---

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  Tài liệu kỹ thuật về kiểm thử phần mềm End-to-End và công cụ Selenium, nguồn `data/KTPM_N11.pdf` (Word→PDF, 71 trang vật lý). Đây là đồ án của chính học viên/nhóm nên được phép dùng cho mục đích học tập (ghi rõ tại `data/manifest.json`).
  **Quy tắc tính trang:** chỉ tính trang có nội dung hữu ích — trang vật lý **10..70** (tổng **61 trang nội dung**). Loại trang bìa/lời cảm ơn/mục lục/danh mục bảng-hình (trang 1..9) và trang tài liệu tham khảo (trang 71). Số trang in trong tài liệu = trang vật lý − 1.

- **Chuẩn hóa, lỗi và giới hạn:**
  Đọc bằng `pypdf` với `extraction_mode="layout"` (khử gần hết khoảng trắng thừa do Word→PDF), sau đó `NFC` + gộp khoảng trắng, giữ dòng để chunk theo đoạn. Không trang nào rỗng; không cần OCR (text gốc, không scan). Một số khoảng trắng thừa trong từ còn sót lại được xử lý khi so khớp evidence bằng *de-spaced matching* (`evaluation._despace`), không ảnh hưởng embedding. Hạn chế: các trang 28..32 và 37..41 chủ yếu là hình/bảng nên ít ký tự (33–419 ký tự/trang), vẫn giữ vì chứa chú thích hình/bảng có ý nghĩa.

- **Embedding model / vector store / metric / chi phí:**
  - Embedding: **OpenAI `text-embedding-3-small`**, 1536 chiều, batch 256, query/document dùng chung một `client.embeddings.create` (không fallback mock; thiếu `OPENAI_API_KEY` sẽ báo lỗi).
  - Vector store: **PostgreSQL 16 + pgvector** (image `pgvector/pgvector:0.8.7-pg16`, Docker Compose `starter/docker-compose.yml`), lưu bền vững qua volume, metric **cosine** (`embedding <=> query`). Search **exact** (full-scan), không dùng ANN index vì corpus nhỏ (~120 chunk) — ghi rõ để tránh nhiễu xấp xỉ.
  - Chi phí: list price $0.02/1M token (ước tính, xem bảng Kết quả).

- **Metadata bắt buộc và trường lọc bổ sung:**
  - Bắt buộc: `document_id` (=`ktpm_e2e_selenium`), `source` (=`data/KTPM_N11.pdf`), `page` (trang vật lý PDF, 1-based).
  - Trường lọc bổ sung: **`section`** (kiểu `string`), 5 giá trị `mo_dau`, `chuong_1`, `chuong_2`, `chuong_3`, `ket_luan`. Nguồn giá trị: cấu trúc chương của tài liệu, gán theo khoảng trang (kiểm chứng được). Lý do chọn: 3 chương có nội dung phân biệt rõ, cho phép thu hẹp phạm vi truy vấn theo chương.

---

## Cấu hình và benchmark

- **A / B / C (tham số cụ thể, khác biệt duy nhất B–C):**
  | Cấu hình | Chunk | Filter |
  |---|---|---|
  | **A** | `fixed_size`, size 500, overlap 50 | không lọc |
  | **B** | `by_paragraph`, max 700 (theo đoạn/heading) | không lọc |
  | **C** | `by_paragraph`, max 700 (giống B) | lọc `section` — **chỉ** áp dụng khi câu hỏi cung cấp filter |
  A–B so sánh ảnh hưởng của chunking; B–C chỉ khác filter nên tách được ảnh hưởng của metadata. Cùng corpus, cùng model, cùng metric, cùng bộ câu hỏi cho cả ba.

- **Bộ câu hỏi (≥20), phân chia và cách kiểm chứng evidence:**
  `benchmark/benchmark.json` gồm **22 câu** — **16 dev / 6 test**, tách trước khi chạy. Gồm câu trực tiếp (14), diễn đạt lại (3), điều kiện/ngoại lệ (2) và **3 câu metadata filter** (2 dev + 1 test: `q20` lọc `chuong_1`, `q21` lọc `chuong_2`, `q22` lọc `chuong_3`).
  **Kiểm chứng evidence:** từng `evidence_quote` được xác minh là chuỗi con (sau khi bỏ khoảng trắng) của trang `gold_page` trong văn bản đã chuẩn hóa — toàn bộ 22/22 đạt. Gold không bị đưa vào query/filter; filter do người dùng/ngữ cảnh cung cấp trước khi truy xuất.

- **Tiêu chí chọn chiến lược (chốt trước khi xem test):**
  Ưu tiên **1) Evidence Hit@3**, rồi **2) Grounding quality**, rồi **3) tài nguyên** (số chunk / thời gian / chi phí). Khi nhiều mục tiêu xung đột, Hit@3 được ưu tiên trước; không tinh chỉnh theo test (test chỉ dùng để đánh giá sau khi đã cố định cấu hình).

---

## Kết quả

> **Trạng thái:** số liệu *chunk count*, *chi phí ước tính* và thống kê độ dài chunk là **số thật** (đo trực tiếp từ corpus bằng đúng code chunking). Các ô `[chưa chạy]` (Hit@1/Hit@3, thời gian, nhãn thủ công) cần chạy `python -m src.run` với Docker + `OPENAI_API_KEY` rồi điền.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí (ước tính) |
|---|---|---|---|---|---|---|
| A | dev | `[chưa chạy]` | `[chưa chạy]` | 120 | `[chưa chạy]` | ~$0.000235 |
| A | test | `[chưa chạy]` | `[chưa chạy]` | 120 | `[chưa chạy]` | (đã gộp) |
| B | dev | `[chưa chạy]` | `[chưa chạy]` | 103 | `[chưa chạy]` | ~$0.000220 |
| B | test | `[chưa chạy]` | `[chưa chạy]` | 103 | `[chưa chạy]` | (đã gộp) |
| C | dev | `[chưa chạy]` | `[chưa chạy]` | 103 | `[chưa chạy]` | ~$0.000220 |
| C | test | `[chưa chạy]` | `[chưa chạy]` | 103 | `[chưa chạy]` | (đã gộp) |

Thống kê chunk (đo thật từ corpus): **A** 120 chunk, tổng 46 923 ký tự (min 33, max 500, mean 391.0); **B/C** 103 chunk, tổng 43 949 ký tự (min 8, max 700, mean 426.7). A có tổng ký tự cao hơn do overlap 50 tạo nội dung trùng lặp (~7%). Chi phí là ước tính theo list price, dựa trên token ≈ ký tự/4.

| Strategy | Coherence TB /2 (n) | Metadata đủ & đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) + TB /2 |
|---|---|---|---|---|
| A | `[chưa chạy]` | `[chưa chạy]` | `[chưa chạy]` | `[chưa chạy]` |
| B | `[chưa chạy]` | `[chưa chạy]` | `[chưa chạy]` | `[chưa chạy]` |
| C | `[chưa chạy]` | `[chưa chạy]` | `[chưa chạy]` | `[chưa chạy]` |

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- Trace top-3 đầy đủ (câu, ID chunk, text, score, metadata, cờ hit, filter-compliance): `starter/results/traces.json`.
- Chỉ số gộp: `starter/results/summary.json`.
- **Coherence:** chọn **10 vị trí cố định trước khi xem điểm** = 10 trang nội dung đầu (trang vật lý 10..19); chấm chunk bao phủ đầu mỗi trang, thang 0–2 (0=cắt giữa ý/thiếu chủ thể, 1=hiểu một phần, 2=tự hiểu được và giữ trọn ý).
- **Metadata:** trên 5 câu test × top-3 = 15 bản ghi, kiểm tra `source`, `page`, `section` đúng/đủ so với nguồn; với 3 câu filter, kiểm tra top-3 của C tuân thủ filter.
- **Grounding:** 5 câu test, chấm top-3 thang 0–2 (0=không có bằng chứng, 1=thiếu điều kiện/ngữ cảnh, 2=đủ để trả lời và truy nguồn).
- Người chấm là chính tác giả → có nguy cơ thiên lệch (đã ghi nhận, không dùng LLM judge).

---

## Phân tích và kết luận

- **So sánh A–B và B–C (phần đo được trước khi chạy):** A tạo 120 chunk (mean 391, đều đặn nhưng cắt theo ký tự nên có thể cắt ngang ý); B tạo 103 chunk (mean 427, bám theo đoạn/heading nên giữ trọn ý tốt hơn nhưng xuất hiện chunk rất ngắn — min 8 ký tự — thường là heading hoặc mảnh bảng). B–C giống hệt về chunk (103), chỉ khác việc C thêm filter `section` khi câu hỏi cung cấp filter. → Kết luận định lượng về Hit@3/grounding sẽ điền sau khi chạy.
- **2 ví dụ sai (ID câu + nguồn):** `[chưa chạy]` — xác định từ `traces.json` bằng cách tìm trace có `evidence_hit@3 == false`, ghi ID câu + `gold_page` + chunk thực tế trả về (page/section).
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:** theo tiêu chí đã chốt (Hit@3 → grounding → tài nguyên). `[điền kết luận sau khi chạy]` — dự kiến khung: nếu B/C có Hit@3 ≥ A, ưu tiên B; chọn C khi ứng dụng cần lọc theo chương.
- **Hạn chế:** corpus một tài liệu (61 trang), bộ test nhỏ (22 câu) nên không suy rộng; nhãn thủ công do tác giả tự chấm (thiên lệch); thời gian/chi phí là ước tính; khoảng trắng thừa của PDF chỉ được khắc phục ở khâu so khớp evidence, không tái tạo hoàn hảo từ gốc.
- **Nếu làm lại/mở rộng:** thêm hybrid BM25 + dense (giữ nguyên chunk/filter), dùng nhiều tài liệu kỹ thuật khác nhau, thử chunk đa tầng (heading + leaf), và bổ sung câu filter theo `document_type`/`version` khi có nhiều nguồn.

---

### Cách điền kết quả (để hoàn thiện các ô `[chưa chạy]`)

```bash
cd starter
python -m pip install -r requirements.txt          # cần thêm openai (venv chưa có)
# bật Docker Desktop rồi:
docker compose -p day6_student_starter up -d --wait
python -m src.run                                   # cần OPENAI_API_KEY trong .env
```

1. Điền bảng Kết quả từ `starter/results/summary.json` (mục `metrics`, gồm `hit@1`, `evidence_hit@3` dạng `n/N`).
2. Chạy audit thủ công theo *cách chọn mẫu* ở trên, điền bảng Coherence/Metadata/Filter/Grounding.
3. Ghi 2 ví dụ sai từ `traces.json` và điền kết luận cuối.
