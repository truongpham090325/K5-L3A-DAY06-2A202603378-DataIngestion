# README — Báo cáo & tái lập kết quả (Day 06)

Hướng dẫn setup, chạy và đường dẫn dữ liệu để người chấm tái lập kết quả trong
`individual/2A202603378_PhamQuangTruong.md`.

## 1. Yêu cầu

- Python 3.11–3.14.
- Các gói trong `starter/requirements.txt` (psycopg, pypdf, python-dotenv).
- Tùy backend:
  - **Local (đã dùng để sinh kết quả):** `sentence-transformers` (kéo theo `torch`) và `chromadb`.
  - **OpenAI + pgvector (tùy chọn):** `openai` và Docker Desktop (PostgreSQL + pgvector).

## 2. Cài đặt

```bash
cd starter
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# Backend đã dùng (local embedding + Chroma, không cần Docker/API key):
python -m pip install sentence-transformers chromadb

# Backend thay thế (OpenAI + pgvector):
python -m pip install openai
docker compose -p day6_student_starter up -d --wait
```

Cấu hình biến môi trường (`.env` tại `starter/` hoặc thư mục gốc repo):

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `EMBEDDING_BACKEND` | `local` hoặc `openai` | `openai` |
| `EMBEDDING_MODEL` | tên model embedding | `text-embedding-3-small` |
| `STORE_BACKEND` | `chroma` hoặc `pgvector` | `pgvector` |
| `OPENAI_API_KEY` | key khi dùng backend `openai` | — |
| `DATABASE_URL` | URL PostgreSQL khi dùng `pgvector` | `postgresql://day6:...@127.0.0.1:55433/day6_lab` |
| `CHROMA_DIR` | thư mục lưu Chroma | `starter/chroma_data` |

## 3. Chạy pipeline

```bash
cd starter

# Cách 1 — local + Chroma (đã dùng để ra kết quả trong báo cáo):
$env:EMBEDDING_BACKEND='local'
$env:EMBEDDING_MODEL='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
$env:STORE_BACKEND='chroma'
python -m src.run

# Cách 2 — OpenAI + pgvector (cần Docker + credit OpenAI):
$env:EMBEDDING_BACKEND='openai'
$env:STORE_BACKEND='pgvector'
python -m src.run
```

Pipeline nạp corpus, build 3 cấu hình A/B/C, embed, lưu vector, chạy 22 câu hỏi
top-3 rồi ghi trace + chỉ số.

## 4. Đường dẫn dữ liệu

| Thành phần | Đường dẫn |
|---|---|
| Corpus (PDF gốc) | `data/KTPM_N11.pdf` |
| Manifest corpus (nguồn/quyền/trang/char) | `data/manifest.json` |
| Benchmark (22 câu + gold evidence) | `benchmark/benchmark.json` |
| Code pipeline | `starter/src/` (`ingestion`, `chunking`, `embeddings`, `store`, `evaluation`, `run`) |
| Trace top-3 (chạy thật) | `starter/results/traces.json` |
| Chỉ số gộp + thống kê (chạy thật) | `starter/results/summary.json` |
| Nhãn audit thủ công (coherence/grounding/metadata/filter) | `starter/results/manual_audit.json` |
| Dữ liệu vector Chroma (local) | `starter/chroma_data/` (đã gitignore) |
| Nhật ký thí nghiệm A/B/C | `artifacts/experiment_log.csv` |
| Báo cáo cá nhân | `report/individual/2A202603378_PhamQuangTruong.md` |

## 5. Ghi chú tái lập

- Kết quả trong báo cáo được sinh bằng **local embedding
  `paraphrase-multilingual-MiniLM-L12-v2` (384 dims) + Chroma (cosine)**, do tài
  khoản OpenAI hết credit (429) và môi trường không có Docker — đây là phương án
  dự phòng hợp lệ theo `RULES.md`, đã ghi rõ trong báo cáo.
- Kết quả truy xuất (Hit@1/Hit@3) là **định lượng tự động**, tái lập được bằng
  `python -m src.run`; các nhãn coherence/metadata/grounding là **audit thủ công**
  của tác giả (đã ghi cách chọn mẫu trong báo cáo).
