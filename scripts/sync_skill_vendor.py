#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "checksim"
    target = repo_root / "skills" / "bid-check-similarity" / "scripts" / "vendor" / "checksim"
    if not source.is_dir():
        raise SystemExit(f"checksim source not found: {source}")

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
    _strip_skill_pdf_support(target)
    print(f"Synced {source} -> {target}")
    return 0


def _strip_skill_pdf_support(target: Path) -> None:
    """Keep the Skill lightweight: no PDF extension, pypdf, or PaddleOCR code."""
    models = target / "models.py"
    parsers = target / "parsers.py"
    _write_skill_models(models)
    _write_skill_parsers(parsers)


def _write_skill_models(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("import os\n", "")
    text = _remove_block(text, "\ndef _env_flag", "\n\nSUPPORTED_EXTENSIONS")
    text = text.replace(
        'SUPPORTED_EXTENSIONS = {".docx", ".doc", ".wps", ".pdf", ".md", ".txt"}\n'
        'if _env_flag("CHECKSIM_DISABLE_PDF"):\n'
        '    SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS - {".pdf"}\n',
        'SUPPORTED_EXTENSIONS = {".docx", ".doc", ".wps", ".md", ".txt"}\n',
    )
    for line in (
        '    pdf_ocr_mode: str = "auto"\n',
        '    pdf_ocr_lang: str = "ch"\n',
        "    pdf_min_text_chars: int = 20\n",
        '    pdf_ocr_engine: str = "onnxruntime"\n',
        '    pdf_ocr_det_model: str = "PP-OCRv6_medium_det"\n',
        '    pdf_ocr_rec_model: str = "PP-OCRv6_medium_rec"\n',
        '            "pdf_ocr_mode",\n',
        '            "pdf_ocr_lang",\n',
        '            "pdf_min_text_chars",\n',
        '            "pdf_ocr_engine",\n',
        '            "pdf_ocr_det_model",\n',
        '            "pdf_ocr_rec_model",\n',
        "        self.pdf_min_text_chars = max(0, int(self.pdf_min_text_chars))\n",
        '            "pdf_ocr_mode": self.pdf_ocr_mode,\n',
        '            "pdf_ocr_lang": self.pdf_ocr_lang,\n',
        '            "pdf_min_text_chars": self.pdf_min_text_chars,\n',
        '            "pdf_ocr_engine": self.pdf_ocr_engine,\n',
        '            "pdf_ocr_det_model": self.pdf_ocr_det_model,\n',
        '            "pdf_ocr_rec_model": self.pdf_ocr_rec_model,\n',
    ):
        text = text.replace(line, "")
    text = _remove_block(text, "        self.pdf_ocr_mode =", "\n    def to_dict")
    text = text.replace("\n    def to_dict", "\n\n    def to_dict")
    path.write_text(text, encoding="utf-8")


def _write_skill_parsers(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for line in ("import os\n", "import sys\n", "import time\n"):
        text = text.replace(line, "")
    text = text.replace(
        '    if suffix == ".pdf":\n'
        "        return _parse_pdf(resolved, group_name, group_index, options, progress)\n",
        "",
    )
    text = _remove_block(text, "\ndef _parse_pdf(", "\ndef _build_units(")
    text = text.replace("\ndef _build_units(", "\n\ndef _build_units(")
    path.write_text(text, encoding="utf-8")


def _remove_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        return text
    end = text.find(end_marker, start)
    if end == -1:
        raise RuntimeError(f"Unable to find end marker after {start_marker!r}")
    return text[:start] + text[end:]


if __name__ == "__main__":
    raise SystemExit(main())
