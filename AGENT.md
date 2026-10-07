
# agent.md

Repo: pipeline dịch PDF Anh→Việt (AI/tài chính). PDF → MinerU → MD → LLM dịch → `translated.md`, `bilingual.md`, `qc_report.md`, `run.json`.

## Luồng

`classify → run_mineru → preprocess → translate → postprocess → qc` (đều trong `src/`, `main.py` chạy tất cả).
Trung gian: `work/<tên>/`. Kết quả: `output/<tên>/`. Cấu hình: `config.toml`, `.env`.

## Lệnh

- Chạy: `.venv/Scripts/python src/main.py [pdf] [--pages 1-3] [--domain ai|finance] [--no-translate] [--force] [--backend X]`
- Test: `.venv/Scripts/python -m unittest discover -s tests`
- Chạy lẻ bước: `src/<module>.py <work-dir> ...`

## Quy tắc tiết kiệm token

- Không đọc cả file lớn: dùng `grep`/`head`/`view_range`. Không đọc `work/`, `output/`, `cache/`, `.venv/`, `*.pdf`.
- Lỗi → đọc `work/<tên>/mineru.log` hoặc `qc_report.md` (đoạn liên quan), không đọc toàn bộ output.
- Thử nghiệm luôn dùng `--pages 1-3`; không dịch full khi chưa cần.
- Sửa nhỏ bằng str_replace; không viết lại cả file.
- Trả lời ngắn: kết quả + việc đã sửa, không lặp lại code/log.

## Ràng buộc

- Không đổi định dạng placeholder (công thức, bảng, số, mã) — lỗi `placeholder_mismatch` do đây.
- `temperature ≤ 0.2`. Đổi prompt/model → xóa `work/<tên>/cache/` rồi chạy lại.
- Tài liệu nhạy cảm: chỉ dùng Ollama cục bộ, không gọi API ngoài.
- Không commit `.env`, khóa API, PDF, `work/`, `output/`.
- Thuật ngữ không chắc → ghi `glossary/pending.csv`, không tự sửa `ai.csv`/`finance.csv`.
- `mineru` lỗi tham số → `mineru --help`, sửa `extra_args` trong `config.toml`.
- **Công thức thành ảnh** → dấu hiệu đang dùng tier `flash` (local CPU). Đổi sang `standard` trong `config.toml` để MinerU remote giữ LaTeX `$$..$$`.
- Tier `standard`/`advanced` cần cờ `--remote` (đã tự động thêm trong `run_mineru.py`); cần tài khoản mineru.net.
- Tier `flash` chỉ local CPU, không dùng GPU local được. GPU là server-side ở remote tiers.

## Xử lý lỗi nhanh

| Lỗi                           | Làm                                                 |
| ------------------------------ | ---------------------------------------------------- |
| MD rỗng                       | xem`mineru.log`, thử `backend_fallback`         |
| Lệch số liệu                | đối chiếu PDF gốc ở trang báo lỗi (OCR bảng) |
| Nhiều`placeholder_mismatch` | giảm temperature / model mạnh hơn / xóa cache    |

## Việc tồn đọng

Mẫu thật vào `samples/`, mở rộng glossary, chuẩn hóa prompt.
Backend hiện tại: `standard` (remote mineru.net API, giữ LaTeX, server-side GPU).
LLM: `gemini-2.5-flash` (cân bằng tốc độ/chất lượng); đổi sang `gemini-2.5-pro` nếu cần độ chính xác cao hơn.
