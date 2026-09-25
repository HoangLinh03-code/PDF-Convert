# pdf-translate

Pipeline dịch PDF kỹ thuật (AI / tài chính) Anh → Việt: PDF → MinerU (OCR/parse) → Markdown → LLM dịch → Markdown song ngữ + báo cáo QC.

Triển khai theo `implementation_plan.md` v1.1 (24/09/2026).

## Cài đặt

Yêu cầu Python 3.10–3.13.

```bash
python -m venv .venv
# Windows (Git Bash):
.venv/Scripts/python -m pip install -r requirements.txt
# Linux/macOS:
# .venv/bin/python -m pip install -r requirements.txt
```

Cài MinerU (bước nặng, tải thêm mô hình khi chạy lần đầu):

```bash
.venv/Scripts/python -m pip install mineru
mineru --help   # đối chiếu backend/flags của phiên bản đang cài
```

- Có GPU CUDA ≥ 8 GB: cài PyTorch bản phù hợp **trước** khi cài mineru (xem hướng dẫn của MinerU/PyTorch).
- Không GPU: dùng backend `pipeline` (mặc định trong `config.toml`, chạy được trên CPU).

Cấu hình khóa API:

```bash
cp .env.example .env   # rồi điền OPENAI_API_KEY
```

Hoặc chạy cục bộ bằng Ollama (không cần khóa): sửa `[llm]` trong `config.toml` → `base_url = "http://localhost:11434/v1"`, `model` = tên mô hình đã tải. **Tài liệu nhạy cảm: bắt buộc dùng Ollama cục bộ.**

## Cách chạy

```bash
# Thả PDF vào inbox/, rồi:
.venv/Scripts/python src/main.py

# Một file cụ thể, thử 3 trang đầu, lĩnh vực tài chính:
.venv/Scripts/python src/main.py inbox/report.pdf --pages 1-3 --domain finance

# Chỉ OCR, không dịch:
.venv/Scripts/python src/main.py --no-translate

# Chạy lại từ đầu (bỏ qua kết quả cũ):
.venv/Scripts/python src/main.py --force
```

Kết quả trong `output/<tên-file>/`:

| File              | Nội dung                                                              |
| ----------------- | ---------------------------------------------------------------------- |
| `translated.md` | Bản dịch tiếng Việt                                                |
| `bilingual.md`  | Song ngữ, xen kẽ đoạn gốc/dịch để đối chiếu                 |
| `qc_report.md`  | Báo cáo QC: số liệu, bảng, thuật ngữ, cấu trúc, nghi lỗi OCR |
| `run.json`      | Thời gian chạy, backend, mô hình, tóm tắt QC                     |

Tùy chọn khác: `--backend <tên>` (ghi đè backend MinerU), `--domain ai|finance`.

## Chạy lại từng bước

Mỗi module chạy độc lập được (đọc/ghi file trung gian trong `work/<tên-file>/`):

```bash
.venv/Scripts/python src/classify.py inbox/a.pdf
.venv/Scripts/python src/run_mineru.py inbox/a.pdf work/a --backend pipeline
.venv/Scripts/python src/preprocess.py work/a
.venv/Scripts/python src/translate.py work/a --domain finance
.venv/Scripts/python src/postprocess.py work/a output/a
.venv/Scripts/python src/qc.py work/a output/a
```

- Cache dịch nằm ở `work/<tên>/cache/` — **xóa thư mục này để dịch lại** (ví dụ sau khi đổi prompt/model). Kết quả có cờ `placeholder_mismatch` không được cache, sẽ tự dịch lại ở lần chạy sau.
- Thuật ngữ LLM không chắc chắn được gom vào `glossary/pending.csv` — duyệt định kỳ rồi gộp vào `ai.csv`/`finance.csv`.

## Kiểm thử

```bash
.venv/Scripts/python -m unittest discover -s tests
```

## Xử lý sự cố

| Triệu chứng                      | Cách xử lý                                                                                                                                    |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `mineru` báo lỗi tham số      | Flags thay đổi giữa phiên bản → chạy`mineru --help`, sửa `extra_args` trong `config.toml`                                          |
| Markdown rỗng / backend lỗi      | `run_mineru.py` tự thử `backend_fallback` nếu đã cấu hình; xem `work/<tên>/mineru.log`                                             |
| QC báo lệch số liệu            | Mở`qc_report.md` phần "Số thiếu/thừa"; thường do OCR sai số trong bảng → đối chiếu PDF gốc, cân nhắc backend VLM cho bản scan |
| Nhiều cờ`placeholder_mismatch` | Mô hình yếu hoặc nhiệt độ cao → giữ`temperature ≤ 0.2`, đổi model mạnh hơn, xóa cache rồi chạy lại                           |
| Chi phí API cao                   | Dùng`--pages` khi thử, bật cache (mặc định), cân nhắc model rẻ hơn hoặc Ollama                                                      |

## Trạng thái theo kế hoạch

- [X] Giai đoạn 0: môi trường, cấu trúc, config (trừ cài MinerU — do ngưỡng dùng quyết định GPU)
- [X] Giai đoạn 3: toàn bộ module S0–S5 + `main.py`, có test
- [ ] Giai đoạn 1: thu thập 10 PDF mẫu thật vào `samples/`, mở rộng glossary (hiện ~29 thuật ngữ/lĩnh vực)
- [ ] Giai đoạn 2: thử các backend MinerU trên mẫu, điền bảng quyết định + `backend_*` trong `config.toml`
- [ ] Giai đoạn 4–6: chuẩn hóa prompt trên đoạn khó, đánh giá cuối, vận hành
