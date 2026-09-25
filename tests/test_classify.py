import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pymupdf as fitz

from classify import classify_pdf


def make_pdf(path: Path, pages: list[str]) -> None:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


LONG_TEXT = "This page contains a substantial amount of English text. " * 5


class TestClassify(unittest.TestCase):
    def test_born_digital(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "born.pdf"
            make_pdf(pdf, [LONG_TEXT] * 5)
            self.assertEqual(classify_pdf(pdf), "born-digital")

    def test_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "scan.pdf"
            make_pdf(pdf, ["", "", "", "", ""])
            self.assertEqual(classify_pdf(pdf), "scanned")

    def test_hybrid(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "hybrid.pdf"
            make_pdf(pdf, [LONG_TEXT, LONG_TEXT, LONG_TEXT, "", ""])
            self.assertEqual(classify_pdf(pdf), "hybrid")

    def test_borderline_born_digital(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "border.pdf"
            make_pdf(pdf, [LONG_TEXT] * 19 + [""])
            self.assertEqual(classify_pdf(pdf), "born-digital")


if __name__ == "__main__":
    unittest.main()
