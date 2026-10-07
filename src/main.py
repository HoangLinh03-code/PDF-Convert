"""Pipeline orchestrator: inbox/*.pdf -> classify -> MinerU -> preprocess -> translate -> postprocess -> QC."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path

import pymupdf as fitz

import classify as classify_mod
import postprocess
import preprocess
import qc
import run_mineru as mineru_mod
import translate as translate_mod
from common import ROOT, ensure_dir, load_config, load_dotenv

logger = logging.getLogger("main")


def slice_pdf(src: Path, dest: Path, pages_spec: str) -> Path:
    """Extract 1-based inclusive page range, e.g. '1-3' or '5'."""
    start_s, _, end_s = pages_spec.partition("-")
    start = int(start_s) - 1
    end = int(end_s) if end_s else start + 1
    with fitz.open(src) as doc:
        end = min(end, doc.page_count)
        if start < 0 or start >= end:
            raise ValueError(f"invalid --pages {pages_spec!r} for {doc.page_count}-page PDF")
        with fitz.open() as new:
            new.insert_pdf(doc, from_page=start, to_page=end - 1)
            new.save(dest)
    return dest


def process_pdf(pdf_path: Path, cfg: dict, args: argparse.Namespace) -> dict:
    name = pdf_path.stem
    work_dir = ensure_dir(ROOT / cfg["general"]["work"] / name)
    output_dir = ensure_dir(ROOT / cfg["general"]["output"] / name)
    durations: dict[str, float] = {}

    src_pdf = pdf_path
    if args.pages:
        src_pdf = slice_pdf(pdf_path, work_dir / "sliced.pdf", args.pages)

    t0 = time.monotonic()
    c = cfg["classify"]
    classification = classify_mod.classify_pdf(
        src_pdf,
        c["min_chars_per_page"],
        c["scanned_ratio_threshold"],
        c["born_digital_ratio_threshold"],
    )
    backend = args.backend or classify_mod.backend_for(classification, cfg)
    durations["classify"] = time.monotonic() - t0
    logger.info("[%s] classified=%s -> backend=%s", name, classification, backend)

    t0 = time.monotonic()
    mineru_mod.run_mineru(
        src_pdf,
        work_dir,
        backend,
        cfg["mineru"].get("backend_fallback") or None,
        cfg["mineru"].get("extra_args", ""),
        restart_server=cfg["mineru"].get("restart_server", False),
    )
    durations["mineru"] = time.monotonic() - t0

    t0 = time.monotonic()
    preprocess.run(work_dir, cfg)
    durations["preprocess"] = time.monotonic() - t0

    domain = args.domain or cfg["general"]["domain"]
    result: dict = {
        "pdf": pdf_path.name,
        "classification": classification,
        "backend": backend,
        "domain": domain,
    }

    if args.no_translate:
        shutil.copyfile(work_dir / "source.md", output_dir / "source.md")
        images = work_dir / "images"
        if images.is_dir():
            dst = output_dir / "images"
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(images, dst)
        logger.info("[%s] --no-translate: OCR output copied to %s", name, output_dir)
    else:
        t0 = time.monotonic()
        translate_mod.run(work_dir, cfg, domain, force=args.force)
        durations["translate"] = time.monotonic() - t0

        t0 = time.monotonic()
        postprocess.run(work_dir, output_dir, cfg)
        durations["postprocess"] = time.monotonic() - t0

        t0 = time.monotonic()
        summary = qc.run(work_dir, output_dir, cfg, domain)
        durations["qc"] = time.monotonic() - t0
        result["qc"] = summary

    result["model"] = cfg["llm"]["model"]
    result["durations_sec"] = {k: round(v, 1) for k, v in durations.items()}
    (output_dir / "run.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="?", type=Path, help="single PDF; default: scan inbox/")
    parser.add_argument("--backend", default=None, help="override MinerU backend")
    parser.add_argument("--domain", choices=["ai", "finance"], default=None)
    parser.add_argument("--pages", default=None, help="1-based inclusive range, e.g. 1-3")
    parser.add_argument("--force", action="store_true", help="re-run even if output exists")
    parser.add_argument("--no-translate", action="store_true", help="OCR only")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    load_dotenv()
    cfg = load_config(args.config)

    if args.pdf:
        pdfs = [args.pdf]
    else:
        inbox = ROOT / cfg["general"]["inbox"]
        pdfs = sorted(inbox.glob("*.pdf"))
        if not pdfs:
            logger.warning("no PDFs found in %s", inbox)
            return 0

    failures = 0
    processed = 0
    for pdf in pdfs:
        if not args.force and not args.no_translate:
            done_marker = ROOT / cfg["general"]["output"] / pdf.stem / "translated.md"
            if done_marker.exists():
                logger.info("[%s] already translated, skipping (use --force)", pdf.stem)
                continue
        try:
            result = process_pdf(pdf, cfg, args)
            processed += 1
            qc_summary = result.get("qc")
            if (
                qc_summary
                and not qc_summary["numbers_ok"]
                and cfg["qc"]["fail_on_number_mismatch"]
            ):
                failures += 1
        except Exception:
            logger.exception("[%s] pipeline failed", pdf.stem)
            failures += 1

    logger.info("done: %d processed, %d failure(s)", processed, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
