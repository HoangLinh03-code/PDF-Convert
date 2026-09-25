"""S5: QC between source.md and translated.md — numbers, tables, terms, structure, OCR."""
from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from translate import load_glossary

logger = logging.getLogger(__name__)

NUMBER_RE = re.compile(
    r"(?<![\w.,])\d{1,3}(?:,\d{3})+(?:\.\d+)?%?"   # EN grouped: 1,234.56
    r"|(?<![\w.,])\d{1,3}(?:\.\d{3})+(?:,\d+)?%?"  # VI grouped: 1.234,56
    r"|(?<![\w.,])\d+(?:[.,]\d+)?%?"               # plain: 42 / 1234.5 / 5%
)
PLACEHOLDER_RE = re.compile(r"⟦P\d{4}⟧")
_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
_IMAGE_RE = re.compile(r"!\[")
_GARBAGE_RE = re.compile(
    r"[^\w\s.,;:!?%$€£¥()\-/'\"<>|#*=`~^&+@\[\]{}—–«»“”‘’°§©®™•…×÷±∞≠≤≥→←↑↓]"
)


def normalize_number(token: str) -> tuple[Decimal, bool]:
    """Canonicalize EN/VI formats: 1,234.56 and 1.234,56 both -> Decimal('1234.56').

    Ambiguity rule: a single '.' is a decimal point, a single ',' followed by
    exactly 3 digits is a thousand separator, otherwise ',' is a decimal comma.
    """
    is_percent = token.endswith("%")
    t = token.rstrip("%").replace(" ", "").replace("\u00a0", "")
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        parts = t.split(",")
        if len(parts) > 2 or len(parts[-1]) == 3:
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
    elif "." in t and t.count(".") > 1:
        t = t.replace(".", "")
    try:
        return Decimal(t), is_percent
    except InvalidOperation:
        return Decimal(0), is_percent


def number_multiset(text: str) -> Counter:
    return Counter(normalize_number(m.group(0)) for m in NUMBER_RE.finditer(text))


def compare_numbers(source: str, translated: str) -> dict:
    src = number_multiset(source)
    tgt = number_multiset(translated)
    missing = src - tgt
    extra = tgt - src
    fmt = lambda counter: [
        {"value": str(value), "percent": is_pct, "count": count}
        for (value, is_pct), count in sorted(counter.items(), key=lambda kv: str(kv[0]))
    ]
    return {"missing": fmt(missing), "extra": fmt(extra)}


def md_table_shapes(text: str) -> list[tuple[int, int]]:
    shapes, rows = [], []
    for line in text.splitlines() + [""]:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            rows.append(s.strip("|").count("|") + 1)
        elif rows:
            shapes.append((len(rows), max(rows)))
            rows = []
    return shapes


def check_terms(source: str, translated: str, entries: list[dict]) -> list[dict]:
    missing = []
    for e in entries:
        src_pat = re.compile(rf"\b{re.escape(e['source'])}s?\b", re.IGNORECASE)
        if not src_pat.search(source):
            continue
        if e["target"].lower() == e["source"].lower():
            candidates = [e["source"]]
        else:
            candidates = [e["target"]]
            if "(" in e["target"]:
                candidates.append(e["target"].split("(")[0].strip())
        if not any(
            re.search(re.escape(c), translated, re.IGNORECASE)
            for c in candidates
            if c
        ):
            missing.append(e)
    return missing


def structure_counts(text: str) -> dict:
    return {
        "headings": len(_HEADING_RE.findall(text)),
        "images": len(_IMAGE_RE.findall(text)),
        "display_math": text.count("$$") // 2,
        "code_fences": text.count("```") // 2,
    }


def suspicious_lines(text: str, ratio: float = 0.35, min_len: int = 20) -> list[str]:
    flagged = []
    for line in text.splitlines():
        s = line.strip()
        if len(s) < min_len:
            continue
        non_space = [ch for ch in s if not ch.isspace()]
        weird = sum(1 for ch in non_space if _GARBAGE_RE.match(ch))
        if non_space and weird / len(non_space) > ratio:
            flagged.append(s[:120])
        if len(flagged) >= 20:
            break
    return flagged


def _term_pat(source: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(source)}s?\b", re.IGNORECASE)


def run(
    work_dir: str | Path,
    output_dir: str | Path,
    cfg: dict,
    domain: str | None = None,
) -> dict:
    from common import ROOT

    work_dir = Path(work_dir)
    output_dir = Path(output_dir)
    name = work_dir.name
    source = (work_dir / "source.md").read_text(encoding="utf-8")
    translated = (output_dir / "translated.md").read_text(encoding="utf-8")

    numbers = compare_numbers(source, translated)
    missing_count = sum(item["count"] for item in numbers["missing"])
    extra_count = sum(item["count"] for item in numbers["extra"])
    numbers_ok = missing_count == 0 and extra_count == 0

    src_tables = md_table_shapes(source)
    tgt_tables = md_table_shapes(translated)
    src_html = len(re.findall(r"<table\b", source, re.I))
    tgt_html = len(re.findall(r"<table\b", translated, re.I))
    tables_ok = src_tables == tgt_tables and src_html == tgt_html

    domain = domain or cfg["general"]["domain"]
    entries = load_glossary(ROOT / "glossary", domain)
    present_terms = [e for e in entries if _term_pat(e["source"]).search(source)]
    missing_terms = check_terms(source, translated, present_terms)
    terms_total = len(present_terms)
    terms_ok_count = terms_total - len(missing_terms)

    src_struct = structure_counts(source)
    tgt_struct = structure_counts(translated)
    structure_ok = src_struct == tgt_struct

    leftover = PLACEHOLDER_RE.findall(translated)

    translation_flags = []
    translations_path = work_dir / "translations.jsonl"
    if translations_path.exists():
        for line in translations_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                for flag in rec.get("flags", []):
                    translation_flags.append(f"{rec['id']}: {flag}")

    ocr_flags = suspicious_lines(source)

    lines = []
    lines.append(f"# QC Report: {name}\n")
    lines.append("## Tóm tắt\n")
    number_status = "OK" if numbers_ok else f"LỆCH — thiếu {missing_count}, thừa {extra_count}"
    lines.append(f"- **Số liệu:** {number_status}")
    table_status = "OK" if tables_ok else f"LỆCH — md {len(src_tables)}→{len(tgt_tables)}, html {src_html}→{tgt_html}"
    lines.append(f"- **Bảng:** {table_status}")
    term_status = "OK" if not missing_terms else f"thiếu {len(missing_terms)}"
    lines.append(f"- **Thuật ngữ:** {terms_ok_count}/{terms_total} — {term_status}")
    struct_status = "OK" if structure_ok else f"LỆCH — {src_struct} → {tgt_struct}"
    lines.append(f"- **Cấu trúc:** {struct_status}")
    lines.append(f"- **Placeholder còn sót:** {len(leftover)}")
    lines.append(f"- **Cờ dịch:** {len(translation_flags)}")
    lines.append(f"- **Dòng nghi lỗi OCR (nguồn):** {len(ocr_flags)}")

    lines.append("\n## Chi tiết\n")
    if not numbers_ok:
        lines.append("### Số thiếu trong bản dịch\n")
        for item in numbers["missing"][:50]:
            pct = "%" if item["percent"] else ""
            lines.append(f"- `{item['value']}{pct}` × {item['count']}")
        lines.append("\n### Số thừa trong bản dịch\n")
        for item in numbers["extra"][:50]:
            pct = "%" if item["percent"] else ""
            lines.append(f"- `{item['value']}{pct}` × {item['count']}")
        lines.append("")
    if not tables_ok:
        lines.append("### Cấu trúc bảng\n")
        lines.append(f"- Nguồn (rows, cols): {src_tables}")
        lines.append(f"- Dịch  (rows, cols): {tgt_tables}\n")
    if missing_terms:
        lines.append("### Thuật ngữ thiếu trong bản dịch\n")
        for e in missing_terms:
            lines.append(f"- `{e['source']}` → kỳ vọng `{e['target']}`")
        lines.append("")
    if translation_flags:
        lines.append("### Cờ từ bước dịch\n")
        for flag in translation_flags:
            lines.append(f"- {flag}")
        lines.append("")
    if ocr_flags:
        lines.append("### Dòng nghi lỗi OCR (kiểm tra lại bản gốc)\n")
        for line in ocr_flags:
            lines.append(f"- `{line}`")
        lines.append("")

    report_path = output_dir / "qc_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("QC report written to %s", report_path)

    return {
        "numbers_ok": numbers_ok,
        "missing_numbers": missing_count,
        "extra_numbers": extra_count,
        "tables_ok": tables_ok,
        "terms_total": terms_total,
        "terms_missing": len(missing_terms),
        "structure_ok": structure_ok,
        "leftover_placeholders": len(leftover),
        "translation_flags": translation_flags,
        "ocr_suspicious_lines": len(ocr_flags),
    }


def main(argv: list[str] | None = None) -> int:
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--domain", choices=["ai", "finance"], default=None)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)

    from common import load_config

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config(args.config)
    summary = run(args.work_dir, args.output_dir, cfg, args.domain)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["numbers_ok"] and cfg["qc"]["fail_on_number_mismatch"]:
        return 1
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
