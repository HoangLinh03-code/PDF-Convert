# PDF Translate & Viewer

Công cụ chuyển đổi, dịch và xem tài liệu PDF dạng Markdown. Sử dụng MinerU để chuyển đổi PDF sang Markdown, Gemini để dịch sang tiếng Việt, và trình xem Markdown để hiển thị kết quả dưới dạng web đẹp mắt.

Dự án hỗ trợ người Việt nghiên cứu tài liệu học thuật, bài báo kỹ thuật nước ngoài dạng PDF khi khả năng tiếng Anh còn hạn chế.

## Tính năng

- **Chuyển đổi PDF → Markdown**: Sử dụng MinerU (OCR) để trích xuất văn bản, hình ảnh, bảng biểu, công thức toán từ PDF
- **Dịch thuật thông minh**: Dịch sang tiếng Việt với Gemini, giữ nguyên thuật ngữ chuyên ngành nhờ glossary
- **Kiểm soát chất lượng**: Tự động kiểm tra số liệu, bảng biểu, thuật ngữ sau khi dịch
- **Trình xem Markdown**: Hiển thị Markdown đẹp mắt trong trình duyệt với hỗ trợ toán học, code highlighting, mục lục
- **Song ngữ**: Tạo bản song ngữ Anh-Việt để đối chiếu

## Cài đặt

### Yêu cầu
- Python 3.10–3.13
- MinerU (công cụ OCR)
- API key Gemini hoặc Ollama (chạy cục bộ)

### Các bước cài đặt

```bash
# 1. Tạo virtual environment
python -m venv .venv

# 2. Kích hoạt virtual environment
# Windows (Git Bash):
.venv/Scripts/python -m pip install -r requirements.txt
# Linux/macOS:
# .venv/bin/python -m pip install -r requirements.txt

# 3. Cài MinerU (tải mô hình khi chạy lần đầu)
.venv/Scripts/python -m pip install mineru
mineru --help   # kiểm tra backend/flags

# 4. Cấu hình API key
cp .env.example .env
# Mở .env và điền OPENAI_API_KEY (hoặc sử dụng Ollama cục bộ)
```

**Lưu ý GPU:**
- Có GPU CUDA ≥ 8 GB: cài PyTorch bản phù hợp **trước** khi cài mineru
- Không GPU: dùng backend `pipeline` (mặc định, chạy trên CPU)

**Chạy cục bộ với Ollama** (cho tài liệu nhạy cảm):
- Sửa `[llm]` trong `config.toml`: `base_url = "http://localhost:11434/v1"`
- Đặt `model` = tên mô hình đã tải

## Sử dụng

### 1. Dịch PDF

```bash
# Thả PDF vào thư mục inbox/, rồi chạy:
.venv/Scripts/python src/main.py

# Dịch một file cụ thể, thử 3 trang đầu:
.venv/Scripts/python src/main.py inbox/report.pdf --pages 1-3

# Chỉ định lĩnh vực (ai hoặc finance):
.venv/Scripts/python src/main.py inbox/paper.pdf --domain ai

# Chỉ OCR, không dịch:
.venv/Scripts/python src/main.py --no-translate

# Chạy lại từ đầu (bỏ qua cache):
.venv/Scripts/python src/main.py --force
```

**Kết quả** trong `output/<tên-file>/`:
- `translated.md` — Bản dịch tiếng Việt
- `bilingual.md` — Song ngữ Anh-Việt (xen kẽ đoạn gốc/dịch)
- `qc_report.md` — Báo cáo kiểm tra chất lượng
- `images/` — Hình ảnh trích xuất từ PDF
- `run.json` — Thông tin chạy (thời gian, backend, model)

### 2. Xem Markdown

Trình xem hiển thị Markdown đẹp mắt trong trình duyệt với hỗ trợ toán học (KaTeX), code highlighting, bảng biểu, và mục lục.

```bash
# Xem một file Markdown:
.venv/Scripts/python src/viewer.py output/<tên-file>/translated.md

# Chỉ định port:
.venv/Scripts/python src/viewer.py output/<tên-file>/translated.md --port 8080
```

**Tính năng trình xem:**
- Giao diện đẹp với gradient, shadow, hiệu ứng hover
- Hỗ trợ LaTeX (KaTeX) cho công thức toán
- Code highlighting cho nhiều ngôn ngữ
- Mục lục tự động từ headings
- Dark/Light theme
- Responsive trên mobile
- Justified text với hyphenation

## Chạy từng bước riêng lẻ

Mỗi module có thể chạy độc lập (đọc/ghi file trung gian trong `work/<tên-file>/`):

```bash
# 1. Phân loại PDF (born-digital/scanned/hybrid)
.venv/Scripts/python src/classify.py inbox/a.pdf

# 2. Chạy MinerU OCR
.venv/Scripts/python src/run_mineru.py inbox/a.pdf work/a --backend pipeline

# 3. Tiền xử lý (chia đoạn, bảo vệ placeholder)
.venv/Scripts/python src/preprocess.py work/a

# 4. Dịch
.venv/Scripts/python src/translate.py work/a --domain ai

# 5. Hậu xử lý (phục hồi placeholder, tạo file cuối)
.venv/Scripts/python src/postprocess.py work/a output/a

# 6. Kiểm tra chất lượng
.venv/Scripts/python src/qc.py work/a output/a
```

## Cấu hình

Chỉnh sửa `config.toml`:

```toml
[general]
domain = "ai"  # ai hoặc finance

[mineru]
backend_born_digital = "pipeline"
backend_scanned = "vlm"

[llm]
base_url = "https://api.openai.com/v1"
model = "gpt-4"
temperature = 0.1

[chunk]
target_tokens = 1500
```

## Glossary

Thuật ngữ chuyên ngành nằm trong `glossary/`:
- `ai.csv` — Thuật ngữ AI/ML
- `finance.csv` — Thuật ngữ tài chính
- `pending.csv` — Thuật ngữ LLM đề xuất, chờ duyệt

Định dạng: `source,target,note`

## Kiểm thử

```bash
.venv/Scripts/python -m unittest discover -s tests
```

## Xử lý sự cố

| Vấn đề | Giải pháp |
|--------|-----------|
| `mineru` lỗi tham số | Chạy `mineru --help`, cập nhật `extra_args` trong `config.toml` |
| Markdown rỗng | Xem `work/<tên>/mineru.log`, thử backend khác |
| QC báo lệch số | Mở `qc_report.md`, đối chiếu PDF gốc |
| Nhiều lỗi placeholder | Giảm `temperature ≤ 0.2`, đổi model mạnh hơn, xóa cache |
| Chi phí API cao | Dùng `--pages` khi thử, dùng Ollama cục bộ |

## Cấu trúc thư mục

```
pdf-translate/
├── inbox/              # PDF đầu vào
├── output/             # Kết quả (translated.md, bilingual.md, images/)
├── work/               # File trung gian, cache
├── glossary/           # Thuật ngữ chuyên ngành
├── prompts/            # Prompt template cho LLM
├── src/
│   ├── main.py         # Điều phối pipeline
│   ├── classify.py     # Phân loại PDF
│   ├── run_mineru.py   # OCR với MinerU
│   ├── preprocess.py   # Tiền xử lý Markdown
│   ├── translate.py    # Dịch với LLM
│   ├── postprocess.py  # Hậu xử lý
│   ├── qc.py           # Kiểm tra chất lượng
│   ├── viewer.py       # Trình xem Markdown
│   └── common.py       # Hàm tiện ích
└── tests/              # Unit tests
```

## License

MIT

## Đóng góp

Mọi đóng góp đều được chào đón! Hãy tạo issue hoặc pull request.
