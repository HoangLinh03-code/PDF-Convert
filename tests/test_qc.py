import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from qc import (
    check_terms,
    compare_numbers,
    md_table_shapes,
    normalize_number,
    number_multiset,
)


class TestNormalizeNumber(unittest.TestCase):
    def n(self, token):
        return normalize_number(token)[0]

    def test_en_grouped(self):
        self.assertEqual(self.n("1,234.56"), Decimal("1234.56"))

    def test_vi_grouped(self):
        self.assertEqual(self.n("1.234,56"), Decimal("1234.56"))

    def test_comma_thousand(self):
        self.assertEqual(self.n("1,234"), Decimal("1234"))

    def test_comma_decimal(self):
        self.assertEqual(self.n("1,5"), Decimal("1.5"))

    def test_multi_dot_vi_thousand(self):
        self.assertEqual(self.n("1.234.567"), Decimal("1234567"))

    def test_percent_flag(self):
        value, is_pct = normalize_number("5%")
        self.assertEqual(value, Decimal("5"))
        self.assertTrue(is_pct)

    def test_percent_not_equal_plain(self):
        src = number_multiset("growth of 5%")
        tgt = number_multiset("tăng trưởng 5")
        self.assertNotEqual(src, tgt)


class TestCompareNumbers(unittest.TestCase):
    def test_identical_multisets(self):
        src = "Revenue was $1,234.5 million, up 5% from 1,000 in 2023."
        tgt = "Doanh thu 1,234.5 triệu đô la, tăng 5% so với 1,000 năm 2023."
        result = compare_numbers(src, tgt)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["extra"], [])

    def test_missing_number_detected(self):
        src = "Revenue 1,234.5 and cost 678."
        tgt = "Doanh thu 1,234.5."
        result = compare_numbers(src, tgt)
        values = [item["value"] for item in result["missing"]]
        self.assertIn("678", values)

    def test_extra_number_detected(self):
        src = "Revenue 100."
        tgt = "Doanh thu 100 từ 200."
        result = compare_numbers(src, tgt)
        values = [item["value"] for item in result["extra"]]
        self.assertIn("200", values)

    def test_vi_format_matches_en(self):
        src = "The figure is 1,234.56."
        tgt = "Con số là 1.234,56."
        result = compare_numbers(src, tgt)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["extra"], [])


class TestTables(unittest.TestCase):
    def test_shapes(self):
        md = (
            "| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n\n"
            "text\n\n"
            "| x | y |\n|---|---|\n| 4 | 5 |\n| 6 | 7 |\n"
        )
        self.assertEqual(md_table_shapes(md), [(3, 3), (4, 2)])


class TestTerms(unittest.TestCase):
    ENTRIES = [
        {"source": "yield curve", "target": "đường cong lợi suất", "note": ""},
        {"source": "transformer", "target": "transformer", "note": "giữ nguyên"},
        {"source": "fine-tuning", "target": "tinh chỉnh (fine-tuning)", "note": ""},
    ]

    def test_term_present(self):
        src = "The yield curve inverted. Transformer models and fine-tuning."
        tgt = "Đường cong lợi suất đảo ngược. Các mô hình transformer và tinh chỉnh."
        self.assertEqual(check_terms(src, tgt, self.ENTRIES), [])

    def test_term_missing(self):
        src = "The yield curve inverted."
        tgt = "Đường cong lợi nhuận đảo ngược."
        missing = check_terms(src, tgt, self.ENTRIES)
        self.assertEqual([e["source"] for e in missing], ["yield curve"])

    def test_term_not_in_source_ignored(self):
        src = "Nothing relevant here."
        tgt = "Không có gì liên quan."
        self.assertEqual(check_terms(src, tgt, self.ENTRIES), [])


if __name__ == "__main__":
    unittest.main()
