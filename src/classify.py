"""S0: classify a PDF as born-digital | scanned | hybrid from per-page text length."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf as fitz


def classify_pdf(
    pdf_path: str | Path,
    min_chars_per_page: int = 50,
    scanned_ratio_threshold: float = 0.9,
    born_digital_ratio_threshold: float = 0.1,
) -> str:
    with fitz.open(pdf_path) as doc:
        if doc.page_count == 0:
            raise ValueError(f"{pdf_path}: PDF has no pages")
        scan_pages = sum(
            1 for page in doc if len(page.get_text().strip()) < min_chars_per_page
        )
        ratio = scan_pages / doc.page_count
    if ratio > scanned_ratio_threshold:
        return "scanned"
    if ratio < born_digital_ratio_threshold:
        return "born-digital"
    return "hybrid"


def backend_for(classification: str, cfg: dict) -> str:
    m = cfg["mineru"]
    if classification == "scanned":
        return m["backend_scanned"]
    return m["backend_born_digital"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)

    from common import load_config

    cfg = load_config(args.config)
    c = cfg["classify"]
    result = classify_pdf(
        args.pdf,
        c["min_chars_per_page"],
        c["scanned_ratio_threshold"],
        c["born_digital_ratio_threshold"],
    )
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
