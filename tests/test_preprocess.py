import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from preprocess import chunk_markdown, protect, restore


class TestProtect(unittest.TestCase):
    def test_roundtrip_restores_original(self):
        text = (
            "See ![fig 1](images/fig1.png) for details.\n\n"
            "The formula $$E = mc^2$$ is famous, and $x^2 + y^2 = r^2$ inline.\n\n"
            "```\ncode_block = untouched()\n```\n\n"
            "Visit https://example.com/path?q=1 for more, or `inline_code`.\n\n"
            "<table><tr><td>cell</td></tr></table>"
        )
        protected, mapping = protect(text)
        self.assertNotIn("![fig 1]", protected)
        self.assertNotIn("E = mc^2", protected)
        self.assertNotIn("https://example.com", protected)
        self.assertEqual(restore(protected, mapping), text)

    def test_currency_is_not_treated_as_math(self):
        text = "Revenue was $1,234.56 million and cost $5.5 billion in 2024."
        protected, mapping = protect(text)
        self.assertEqual(protected, text)
        self.assertEqual(mapping, {})

    def test_mixed_currency_and_math(self):
        text = "The price $P_t$ exceeds $100 million."
        protected, mapping = protect(text)
        self.assertNotIn("$P_t$", protected)
        self.assertIn("$100 million", protected)
        self.assertEqual(restore(protected, mapping), text)


class TestChunk(unittest.TestCase):
    def test_splits_and_overlaps(self):
        paragraphs = [
            f"Paragraph {i}. " + "Some English sentence here. " * 20
            for i in range(12)
        ]
        md = "\n\n".join(paragraphs)
        chunks = chunk_markdown(md, target_tokens=300, overlap_sentences=1)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0]["overlap"], "")
        self.assertNotEqual(chunks[1]["overlap"], "")
        self.assertEqual([c["id"] for c in chunks], [f"chunk-{i:04d}" for i in range(len(chunks))])

    def test_oversized_block_kept_whole(self):
        big = "| a | b |\n|---|---|\n" + "\n".join("| 1 | 2 |" for _ in range(500))
        md = "Intro paragraph.\n\n" + big + "\n\nOutro paragraph."
        chunks = chunk_markdown(md, target_tokens=200, overlap_sentences=1)
        self.assertTrue(any(big in c["text"] for c in chunks))


if __name__ == "__main__":
    unittest.main()
