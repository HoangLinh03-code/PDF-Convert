"""S4: restore placeholders, assemble translated.md and bilingual.md, copy images."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from pathlib import Path

from preprocess import restore

logger = logging.getLogger(__name__)
import re, urllib.parse
IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")

def normalize_images(md: str) -> str:
    def repl(m: re.Match) -> str:
        alt, url = m.group(1), m.group(2)
        if url.startswith(("http://", "https://", "data:", "doc:")):
            return m.group(0)  # keep absolute / MinerU-locator URLs verbatim
        name = Path(urllib.parse.unquote(url)).name          # flatten to basename
        rel = "images/" + urllib.parse.quote(name)           # encode spaces etc.
        return f"![{alt}]({rel})"
    return IMG_RE.sub(repl, md)

def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run(work_dir: str | Path, output_dir: str | Path, cfg: dict) -> Path:
    work_dir = Path(work_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    mapping = json.loads((work_dir / "mapping.json").read_text(encoding="utf-8"))
    chunks = _read_jsonl(work_dir / "chunks.jsonl")
    translations = {r["id"]: r for r in _read_jsonl(work_dir / "translations.jsonl")}

    translated_parts: list[str] = []
    bilingual_parts: list[str] = []
    for chunk in chunks:
        rec = translations[chunk["id"]]
        src_restored = restore(chunk["text"], mapping)
        tgt_restored = restore(rec["translation"], mapping)
        translated_parts.append(normalize_images(tgt_restored))
        bilingual_parts.append(
            f"<!-- {chunk['id']} -->\n\n{src_restored}\n\n{tgt_restored}"
        )

    (output_dir / "translated.md").write_text(
        "\n\n".join(translated_parts) + "\n", encoding="utf-8"
    )
    if cfg["output"].get("bilingual", True):
        (output_dir / "bilingual.md").write_text(
            "\n\n---\n\n".join(bilingual_parts) + "\n", encoding="utf-8"
        )

    images_src = work_dir / "images"
    if images_src.is_dir():
        images_dst = output_dir / "images"
        if images_dst.exists():
            shutil.rmtree(images_dst)
        shutil.copytree(images_src, images_dst)

    if cfg["output"].get("pandoc_export"):
        pandoc = shutil.which("pandoc")
        if pandoc:
            subprocess.run(
                [pandoc, "translated.md", "-o", "translated.pdf"],
                cwd=output_dir, check=False,
            )
        else:
            logger.warning("pandoc_export enabled but pandoc not found on PATH")

    return output_dir


def main(argv: list[str] | None = None) -> int:
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)

    from common import load_config

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config(args.config)
    print(run(args.work_dir, args.output_dir, cfg))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
