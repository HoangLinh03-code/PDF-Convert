"""S3: translate protected chunks with an LLM — glossary-constrained, cached, verified."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import time
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"⟦P\d{4}⟧")
TERM_RE = re.compile(r"^TERM\?:\s*(.+?)\s*$", re.MULTILINE)


def load_glossary(glossary_dir: str | Path, domain: str) -> list[dict]:
    entries = []
    path = Path(glossary_dir) / f"{domain}.csv"
    if not path.exists():
        logger.warning("glossary not found: %s", path)
        return entries
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("source") and row.get("target"):
                entries.append(
                    {
                        "source": row["source"].strip(),
                        "target": row["target"].strip(),
                        "note": (row.get("note") or "").strip(),
                    }
                )
    return entries


def glossary_subset(entries: list[dict], text: str) -> list[dict]:
    subset = []
    for e in entries:
        pattern = re.compile(rf"\b{re.escape(e['source'])}s?\b", re.IGNORECASE)
        if pattern.search(text):
            subset.append(e)
    return subset


def format_glossary(subset: list[dict]) -> str:
    if not subset:
        return "(không có thuật ngữ nào trong đoạn này)"
    lines = []
    for e in subset:
        line = f"- {e['source']} → {e['target']}"
        if e["note"]:
            line += f"  ({e['note']})"
        lines.append(line)
    return "\n".join(lines)


class RateLimiter:
    def __init__(self, qps: float):
        self.min_interval = 1.0 / qps if qps > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


# ---------------------------------------------------------------------------
# Gemini client wrapper — mirrors the OpenAI SDK interface used by call_llm()
# so the rest of the module needs no changes.
# ---------------------------------------------------------------------------
class _GeminiChoice:
    def __init__(self, text: str):
        self.message = type("_Msg", (), {"content": text})()


class _GeminiResponse:
    def __init__(self, text: str):
        self.choices = [_GeminiChoice(text)]


class _GeminiCompletions:
    def __init__(self, genai_client, model: str):
        self._client = genai_client
        self._model = model

    def create(self, model: str, temperature: float, messages: list, **_):
        from google.genai import types as gtypes

        # Combine all user messages into a single prompt string
        prompt = "\n".join(m["content"] for m in messages if m.get("role") == "user")
        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=gtypes.GenerateContentConfig(temperature=temperature),
        )
        return _GeminiResponse(response.text)


class _GeminiChat:
    def __init__(self, genai_client, model: str):
        self.completions = _GeminiCompletions(genai_client, model)


class GeminiClient:
    """Thin wrapper around google-genai that looks like an OpenAI client."""

    def __init__(self, api_key: str, model: str):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.chat = _GeminiChat(self._client, model)


def make_client(cfg: dict):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. Add it to your .env file."
        )
    return GeminiClient(api_key=api_key, model=cfg["llm"]["model"])


def call_llm(client, model: str, temperature: float, prompt: str, max_retries: int) -> str:
    delay = 1.0
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.choices[0].message.content
            if content and content.strip():
                return content.strip()
            raise ValueError("empty response from LLM")
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            logger.warning("LLM call failed (%s), retrying in %.1fs", e, delay)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def _cache_key(model: str, prompt: str) -> str:
    return hashlib.sha256(f"{model}\n{prompt}".encode("utf-8")).hexdigest()


def translate_chunk(
    client,
    cfg: dict,
    template: str,
    glossary_entries: list[dict],
    chunk: dict,
    cache_dir: Path,
    limiter: RateLimiter,
) -> tuple[str, list[str], list[str]]:
    """Returns (translation, flags, pending_terms)."""
    model = cfg["llm"]["model"]
    subset = glossary_subset(glossary_entries, chunk["text"])
    prompt = template.format(
        glossary_subset=format_glossary(subset),
        overlap=chunk.get("overlap", ""),
        chunk=chunk["text"],
    )

    cache_path = cache_dir / f"{_cache_key(model, prompt)}.txt"
    raw: str | None = None
    if cache_path.exists():
        raw = cache_path.read_text(encoding="utf-8")
    else:
        expected = Counter(PLACEHOLDER_RE.findall(chunk["text"]))
        attempt_prompt = prompt
        for retry in range(3):  # initial + up to 2 re-translations
            limiter.wait()
            candidate = call_llm(
                client, model, cfg["llm"]["temperature"], attempt_prompt,
                cfg["llm"]["max_retries"],
            )
            if Counter(PLACEHOLDER_RE.findall(candidate)) == expected:
                raw = candidate
                cache_path.write_text(raw, encoding="utf-8")
                break
            logger.warning(
                "%s: placeholder mismatch (attempt %d), re-translating",
                chunk["id"], retry + 1,
            )
            attempt_prompt = (
                prompt
                + "\n\nLưu ý: lần trước bạn đã làm mất hoặc thêm token ⟦P....⟧."
                " Giữ nguyên số lượng và nội dung các token đó."
            )
            raw = candidate

    flags: list[str] = []
    if Counter(PLACEHOLDER_RE.findall(raw)) != Counter(
        PLACEHOLDER_RE.findall(chunk["text"])
    ):
        flags.append("placeholder_mismatch")

    pending_terms = TERM_RE.findall(raw)
    translation = TERM_RE.sub("", raw).rstrip()
    return translation, flags, pending_terms


def append_pending(glossary_dir: Path, domain: str, terms: list[str]) -> None:
    if not terms:
        return
    pending_path = Path(glossary_dir) / "pending.csv"
    existing: set[str] = set()
    if pending_path.exists():
        with open(pending_path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("term"):
                    existing.add(row["term"].strip().lower())
    new_terms = [t for t in dict.fromkeys(terms) if t.lower() not in existing]
    if not new_terms:
        return
    write_header = not pending_path.exists()
    with open(pending_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["term", "domain", "note"])
        for t in new_terms:
            writer.writerow([t, domain, ""])
    logger.info("added %d pending term(s) to %s", len(new_terms), pending_path)


def run(
    work_dir: str | Path,
    cfg: dict,
    domain: str,
    force: bool = False,
    client=None,
) -> Path:
    from common import ROOT, ensure_dir, load_dotenv

    work_dir = Path(work_dir)
    cache_dir = ensure_dir(work_dir / "cache")
    chunks_path = work_dir / "chunks.jsonl"
    translations_path = work_dir / "translations.jsonl"

    chunks = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    done: dict[str, dict] = {}
    if translations_path.exists() and not force:
        for line in translations_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["id"]] = rec

    template_path = ROOT / "prompts" / f"translate_{domain}.txt"
    template = template_path.read_text(encoding="utf-8")
    glossary_dir = ROOT / "glossary"
    glossary_entries = load_glossary(glossary_dir, domain)

    if client is None:
        load_dotenv()
        client = make_client(cfg)
    limiter = RateLimiter(cfg["llm"]["qps"])

    all_pending: list[str] = []
    with open(translations_path, "w", encoding="utf-8") as out:
        for chunk in chunks:
            if chunk["id"] in done:
                rec = done[chunk["id"]]
                all_pending.extend(rec.get("pending_terms", []))
            else:
                translation, flags, pending = translate_chunk(
                    client, cfg, template, glossary_entries, chunk, cache_dir, limiter
                )
                rec = {
                    "id": chunk["id"],
                    "translation": translation,
                    "flags": flags,
                    "pending_terms": pending,
                }
                all_pending.extend(pending)
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")

    append_pending(glossary_dir, domain, all_pending)
    return translations_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--domain", choices=["ai", "finance"], default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)

    from common import load_config

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config(args.config)
    domain = args.domain or cfg["general"]["domain"]
    path = run(args.work_dir, cfg, domain, force=args.force)
    print(path)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
