"""S1: run MinerU on a PDF, normalize output to work/<name>/source.md + images/."""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MinerU v4 backend → tier mapping.
# The old "pipeline" / "vlm-transformers" names were removed in MinerU 4.x.
# Local server supports: flash  (CPU-based, fast)
# Remote service supports: basic | standard | advanced  (use --remote flag)
# ---------------------------------------------------------------------------
_BACKEND_TO_TIER: dict[str, str] = {
    "pipeline": "flash",
    "vlm-transformers": "flash",
    "vlm-sglang": "flash",
    "vlm-sglang-client": "flash",
    "hybrid": "flash",
    # Pass through valid tier names unchanged
    "flash": "flash",
    "basic": "basic",
    "standard": "standard",
    "advanced": "advanced",
}


def _mineru_exe() -> str:
    """Return the path to the mineru binary, preferring the active venv."""
    # Look for mineru next to the current python interpreter (covers venvs)
    python = Path(sys.executable)
    for scripts_dir in (python.parent, python.parent / "Scripts"):
        for name in ("mineru", "mineru.exe"):
            candidate = scripts_dir / name
            if candidate.is_file():
                return str(candidate)
    # Fall back to whatever is on PATH
    return "mineru"


def _ensure_server(exe: str) -> None:
    """Start the MinerU local server if it is not already running."""
    check = subprocess.run(
        [exe, "server", "start"],
        capture_output=True,
        text=True,
    )
    output = (check.stdout + check.stderr).strip()
    if "already running" in output.lower() or "started" in output.lower() or check.returncode == 0:
        if "started" in output.lower():
            logger.info("MinerU server started")
            time.sleep(2)  # brief pause for the server to be ready
        return
    logger.warning("MinerU server start returned code %d: %s", check.returncode, output)


def _find_images_dir(out_root: Path) -> Path | None:
    for d in sorted(out_root.rglob("images")):
        if d.is_dir() and any(d.iterdir()):
            return d
    return None


def run_mineru(
    pdf_path: str | Path,
    work_dir: str | Path,
    backend: str,
    fallback_backend: str | None = None,
    extra_args: str = "",
) -> Path:
    pdf_path = Path(pdf_path)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    log_path = work_dir / "mineru.log"

    exe = _mineru_exe()
    _ensure_server(exe)
    backends = [backend] + ([fallback_backend] if fallback_backend else [])
    md_path: Path | None = None
    out_dir: Path | None = None

    for b in backends:
        tier = _BACKEND_TO_TIER.get(b, "standard")
        out_dir = work_dir / f"mineru-{b}"
        out_dir.mkdir(parents=True, exist_ok=True)
        # MinerU v4 CLI: mineru parse <file> -o <output_path> --tier <tier>
        # -o receives the output *file* path (markdown); images land alongside it.
        out_md = out_dir / f"{pdf_path.stem}.md"
        cmd = [exe, "parse", str(pdf_path), "-o", str(out_md), "--tier", tier, "--force"]
        if extra_args:
            cmd += extra_args.split()
        logger.info("running: %s", " ".join(cmd))
        with open(log_path, "a", encoding="utf-8") as log:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            logger.warning("mineru backend %s exited with code %d", b, proc.returncode)
            continue
        # Accept either the exact output file or any .md produced under out_dir
        if out_md.is_file() and out_md.read_text(encoding="utf-8", errors="replace").strip():
            md_path = out_md
            break
        # Fallback: search the directory for any non-empty markdown
        candidates = sorted(out_dir.rglob("*.md"))
        for c in candidates:
            if c.read_text(encoding="utf-8", errors="replace").strip():
                md_path = c
                break
        if md_path:
            break
        logger.warning("mineru backend %s produced empty markdown", b)

    if md_path is None or out_dir is None:
        raise RuntimeError(f"MinerU failed for {pdf_path} (see {log_path})")

    source_md = work_dir / "source.md"
    shutil.copyfile(md_path, source_md)

    images_src = _find_images_dir(out_dir)
    if images_src:
        images_dst = work_dir / "images"
        if images_dst.exists():
            shutil.rmtree(images_dst)
        shutil.copytree(images_src, images_dst)

    return source_md


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("--backend", default="pipeline")
    parser.add_argument("--fallback", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    md = run_mineru(args.pdf, args.work_dir, args.backend, args.fallback)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
