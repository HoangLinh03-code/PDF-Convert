"""S2: protect non-translatable spans with placeholders, then chunk the markdown."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"⟦P\d{4}⟧")

# Order matters: earlier patterns win over later ones.
_PATTERNS: list[re.Pattern] = [
    re.compile(r"!\[[^\]]*\]\([^)]*\)"),          # image links
    re.compile(r"```.*?```", re.DOTALL),           # fenced code
    re.compile(r"\$\$.*?\$\$", re.DOTALL),         # display math
    re.compile(r"</?[a-zA-Z][^>]*>"),              # HTML tags (tables etc.)
    re.compile(r"https?://[^\s)\]]+"),             # URLs (incl. inside md links)
    re.compile(r"`[^`\n]+`"),                      # inline code
    # inline math: opening $ not followed by a digit guards currency like $1,234.56
    re.compile(r"\$(?!\s*\d)[^$\n]+?(?<!\s)\$"),
]


def protect(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    counter = 0

    def repl(m: re.Match) -> str:
        nonlocal counter
        token = f"⟦P{counter:04d}⟧"
        counter += 1
        mapping[token] = m.group(0)
        return token

    for pattern in _PATTERNS:
        text = pattern.sub(repl, text)
    return text, mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    return PLACEHOLDER_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), text)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def split_blocks(md_text: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n{2,}", md_text) if b.strip()]


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return [p for p in parts if p]


def chunk_markdown(
    md_text: str, target_tokens: int = 1500, overlap_sentences: int = 2
) -> list[dict]:
    blocks = split_blocks(md_text)
    groups: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for block in blocks:
        block_tokens = estimate_tokens(block)
        if block_tokens > target_tokens * 1.5:
            # Oversized block (e.g. a big table): keep whole, as its own chunk.
            if current:
                groups.append(current)
                current, current_tokens = [], 0
            groups.append([block])
            continue
        if current and current_tokens + block_tokens > target_tokens:
            groups.append(current)
            current, current_tokens = [block], block_tokens
        else:
            current.append(block)
            current_tokens += block_tokens
    if current:
        groups.append(current)

    chunks = []
    prev_tail = ""
    for i, group in enumerate(groups):
        text = "\n\n".join(group)
        chunks.append({"id": f"chunk-{i:04d}", "overlap": prev_tail, "text": text})
        sentences = split_sentences(text)
        prev_tail = (
            " ".join(sentences[-overlap_sentences:]) if overlap_sentences else ""
        )
    return chunks


def run(work_dir: str | Path, cfg: dict) -> Path:
    work_dir = Path(work_dir)
    source_md = work_dir / "source.md"
    md_text = source_md.read_text(encoding="utf-8")

    protected, mapping = protect(md_text)
    (work_dir / "protected.md").write_text(protected, encoding="utf-8")
    (work_dir / "mapping.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    chunks = chunk_markdown(
        protected,
        cfg["chunk"]["target_tokens"],
        cfg["chunk"]["overlap_sentences"],
    )
    chunks_path = work_dir / "chunks.jsonl"
    with open(chunks_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return chunks_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)

    from common import load_config

    cfg = load_config(args.config)
    path = run(args.work_dir, cfg)
    print(path)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
