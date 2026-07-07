#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache PP-OCRv6 models for bundled desktop builds.")
    parser.add_argument("--output", default="packaging/ocr_models", help="Directory copied into the app bundle.")
    parser.add_argument("--det-model", default="PP-OCRv6_medium_det")
    parser.add_argument("--rec-model", default="PP-OCRv6_medium_rec")
    parser.add_argument("--engine", default="onnxruntime")
    args = parser.parse_args()

    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    expected = [_cache_name(args.det_model, args.engine), _cache_name(args.rec_model, args.engine)]
    if all((output / name / "inference.onnx").exists() for name in expected):
        print(f"PP-OCR models already cached in {output}")
        return 0

    from paddleocr import PaddleOCR

    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "hf")
    PaddleOCR(
        lang="ch",
        ocr_version="PP-OCRv6",
        text_detection_model_name=args.det_model,
        text_recognition_model_name=args.rec_model,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        engine=args.engine,
    )

    source_root = Path.home() / ".paddlex" / "official_models"
    for name in expected:
        source = source_root / name
        if not (source / "inference.onnx").exists():
            raise SystemExit(f"Expected PaddleOCR model cache not found: {source}")
        target = output / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "*.lock"))
        print(f"Cached {source} -> {target}")
    return 0


def _cache_name(model_name: str, engine: str) -> str:
    if engine == "onnxruntime" and not model_name.endswith("_onnx"):
        return f"{model_name}_onnx"
    return model_name


if __name__ == "__main__":
    raise SystemExit(main())
