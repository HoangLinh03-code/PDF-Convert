import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from translate import (
    RateLimiter,
    glossary_subset,
    load_glossary,
    translate_chunk,
)

CFG = {"llm": {"model": "test-model", "temperature": 0, "qps": 0, "max_retries": 1}}
TEMPLATE = "GLOSSARY:\n{glossary_subset}\nOVERLAP: {overlap}\nCHUNK:\n{chunk}"


class FakeCompletions:
    def __init__(self, fn):
        self._fn = fn
        self.calls = 0

    def create(self, model, temperature, messages):
        self.calls += 1
        text = self._fn(messages[-1]["content"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
        )


class FakeClient:
    def __init__(self, fn):
        self.chat = SimpleNamespace(completions=FakeCompletions(fn))


GLOSSARY = [
    {"source": "fine-tuning", "target": "tinh chỉnh (fine-tuning)", "note": ""},
    {"source": "yield curve", "target": "đường cong lợi suất", "note": ""},
]


def make_chunk(text, overlap=""):
    return {"id": "chunk-0000", "overlap": overlap, "text": text}


class TestGlossary(unittest.TestCase):
    def test_subset_case_insensitive_and_plural(self):
        subset = glossary_subset(GLOSSARY, "Fine-Tuning is common. Yield curves slope.")
        sources = {e["source"] for e in subset}
        self.assertEqual(sources, {"fine-tuning", "yield curve"})

    def test_subset_empty(self):
        self.assertEqual(glossary_subset(GLOSSARY, "nothing relevant"), [])

    def test_load_real_glossary(self):
        root = Path(__file__).resolve().parent.parent
        entries = load_glossary(root / "glossary", "ai")
        self.assertGreaterEqual(len(entries), 20)
        self.assertTrue(all(e["source"] and e["target"] for e in entries))


class TestTranslateChunk(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def translate(self, fn, text, chunk_id="chunk-0000"):
        client = FakeClient(fn)
        chunk = make_chunk(text)
        chunk["id"] = chunk_id
        result = translate_chunk(
            client, CFG, TEMPLATE, GLOSSARY, chunk, self.cache_dir, RateLimiter(0)
        )
        return result, client.chat.completions.calls

    def test_placeholder_preserved_no_flag(self):
        (translation, flags, pending), calls = self.translate(
            lambda p: "Doanh thu ⟦P0000⟧ tăng.", "Revenue ⟦P0000⟧ grew."
        )
        self.assertEqual(translation, "Doanh thu ⟦P0000⟧ tăng.")
        self.assertEqual(flags, [])
        self.assertEqual(pending, [])
        self.assertEqual(calls, 1)

    def test_placeholder_mismatch_flagged_after_retries(self):
        (translation, flags, pending), calls = self.translate(
            lambda p: "Bản dịch bị mất token.", "Revenue ⟦P0000⟧ grew."
        )
        self.assertIn("placeholder_mismatch", flags)
        self.assertEqual(calls, 3)  # initial + 2 retries

    def test_term_extraction(self):
        (translation, flags, pending), _ = self.translate(
            lambda p: "Bản dịch xong.\nTERM?: stochastic gradient", "Some text."
        )
        self.assertEqual(translation, "Bản dịch xong.")
        self.assertEqual(pending, ["stochastic gradient"])

    def test_cache_hit_skips_llm(self):
        fn = lambda p: "Doanh thu tăng."
        client = FakeClient(fn)
        chunk = make_chunk("Revenue grew.")
        for _ in range(2):
            translation, flags, pending = translate_chunk(
                client, CFG, TEMPLATE, GLOSSARY, chunk, self.cache_dir, RateLimiter(0)
            )
        self.assertEqual(translation, "Doanh thu tăng.")
        self.assertEqual(client.chat.completions.calls, 1)  # second call served from cache

    def test_bad_response_not_cached(self):
        fn = lambda p: "mất token."
        self.translate(fn, "Revenue ⟦P0000⟧ grew.", chunk_id="c2")
        self.assertEqual(len(list(self.cache_dir.glob("*.txt"))), 0)


if __name__ == "__main__":
    unittest.main()
