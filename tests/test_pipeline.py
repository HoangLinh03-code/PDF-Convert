import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import postprocess
import preprocess
import qc
import translate

SOURCE_MD = """# Financial Report 2024

Revenue was $1,234.5 million, up 5% from 1,000 in 2023. The yield curve inverted.

| Item | 2024 | 2023 |
|---|---|---|
| Revenue | 1,234.5 | 1,000 |
| Cost | 678 | 700 |

See ![revenue chart](images/chart.png) for the trend. Operating expenses reached $100 million.

The formula $$r = R^2$$ summarizes fit quality.
"""


class FakeCompletions:
    REPLACEMENTS = [
        (r"yield curve", "đường cong lợi suất"),
        (r"operating expenses", "chi phí hoạt động"),
        (r"revenue", "doanh thu"),
    ]

    def create(self, model, temperature, messages):
        prompt = messages[-1]["content"]
        chunk = prompt.split("Văn bản cần dịch:\n", 1)[1]
        for pattern, repl in self.REPLACEMENTS:
            chunk = re.sub(pattern, repl, chunk, flags=re.IGNORECASE)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=chunk))]
        )


class FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


class TestPipeline(unittest.TestCase):
    def test_preprocess_translate_postprocess_qc(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "work" / "sample"
            out = Path(td) / "out" / "sample"
            work.mkdir(parents=True)
            (work / "source.md").write_text(SOURCE_MD, encoding="utf-8")
            images = work / "images"
            images.mkdir()
            (images / "chart.png").write_bytes(b"\x89PNG fake")

            cfg = {
                "general": {"domain": "finance"},
                "chunk": {"target_tokens": 400, "overlap_sentences": 1},
                "llm": {"model": "m", "temperature": 0, "qps": 0, "max_retries": 1},
                "output": {"bilingual": True, "pandoc_export": False},
                "qc": {"fail_on_number_mismatch": True},
            }

            preprocess.run(work, cfg)
            self.assertTrue((work / "chunks.jsonl").exists())

            translate.run(work, cfg, "finance", client=FakeClient())
            self.assertTrue((work / "translations.jsonl").exists())

            postprocess.run(work, out, cfg)
            translated = (out / "translated.md").read_text(encoding="utf-8")
            bilingual = (out / "bilingual.md").read_text(encoding="utf-8")

            self.assertNotIn("⟦P", translated)
            self.assertIn("![revenue chart](images/chart.png)", translated)
            self.assertIn("$$r = R^2$$", translated)
            self.assertTrue((out / "images" / "chart.png").exists())
            self.assertIn("<!-- chunk-", bilingual)

            summary = qc.run(work, out, cfg, "finance")
            self.assertTrue(summary["numbers_ok"], summary)
            self.assertTrue(summary["tables_ok"], summary)
            self.assertEqual(summary["leftover_placeholders"], 0)
            self.assertEqual(summary["translation_flags"], [])
            self.assertTrue((out / "qc_report.md").exists())
            self.assertEqual(summary["terms_missing"], 0)


if __name__ == "__main__":
    unittest.main()
