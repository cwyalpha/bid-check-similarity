from __future__ import annotations

import hashlib
import os
import re
import shutil
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from docx import Document
from PIL import Image

from .legacy import convert_legacy_to_docx
from .models import CheckOptions, DocumentData, DocumentImage, SUPPORTED_EXTENSIONS, TextUnit, normalize_path
from .text import english_word_count, is_comparable_text, make_ngrams, normalize_for_compare, split_blocks_to_units, visible_char_count


IMAGE_RE = re.compile(r"!\[[^\]]*]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
HTML_TAG_RE = re.compile(r"<[^>]+>")
LINK_RE = re.compile(r"\[([^\]]+)]\(([^)]+)\)")
EMPHASIS_RE = re.compile(r"(\*\*|__)(.*?)\1|(\*|_)([^*_`\n]+)\3|~~(.*?)~~")
ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)、]\s+")
UNORDERED_LIST_RE = re.compile(r"^\s*[-*+]\s+")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


Progress = Callable[[str], None]


def parse_file(
    path: str | Path,
    group_name: str,
    group_index: int,
    options: CheckOptions,
    progress: Progress | None = None,
) -> DocumentData:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"文件不存在: {resolved}")
    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"暂不支持的文件格式: {resolved.name}")
    if suffix == ".docx":
        return _parse_docx(resolved, group_name, group_index, options)
    if suffix in {".doc", ".wps"}:
        return _parse_legacy_word(resolved, group_name, group_index, options, progress)
    return _parse_markdown(resolved, group_name, group_index, options)


def _parse_legacy_word(
    path: Path,
    group_name: str,
    group_index: int,
    options: CheckOptions,
    progress: Progress | None,
) -> DocumentData:
    converted_path, temp_dir = convert_legacy_to_docx(
        path,
        log=progress,
        soffice_path=options.soffice_path or None,
        timeout=options.legacy_conversion_timeout,
    )
    try:
        return _parse_docx(converted_path, group_name, group_index, options, source_path=path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _parse_docx(
    path: Path,
    group_name: str,
    group_index: int,
    options: CheckOptions,
    source_path: Path | None = None,
) -> DocumentData:
    display_path = source_path or path
    document = Document(str(path))
    blocks: list[str] = []
    for para in document.paragraphs:
        text = para.text.strip()
        if text:
            blocks.append(text)
    for table_index, table in enumerate(document.tables, start=1):
        for row_index, row in enumerate(table.rows, start=1):
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append(f"表{table_index} 行{row_index}: " + " | ".join(cells))

    metadata = _docx_metadata(document, display_path)
    if source_path is not None:
        metadata["converted_from"] = source_path.suffix.lower()
        metadata["converted_via"] = "docx"
    images = _docx_images(document, display_path)
    units = _build_units(display_path, group_name, group_index, blocks, options)
    return DocumentData(group_name, group_index, normalize_path(display_path), display_path.name, metadata, blocks, units, images)


def _parse_markdown(path: Path, group_name: str, group_index: int, options: CheckOptions) -> DocumentData:
    raw = _read_text(path)
    images = _markdown_images(raw, path)
    text = _strip_markdown(raw)
    blocks = [line.strip() for line in re.split(r"\n{1,}", text) if line.strip()]
    metadata = _file_metadata(path)
    units = _build_units(path, group_name, group_index, blocks, options)
    return DocumentData(group_name, group_index, normalize_path(path), path.name, metadata, blocks, units, images)


def _build_units(path: Path, group_name: str, group_index: int, blocks: list[str], options: CheckOptions) -> list[TextUnit]:
    units: list[TextUnit] = []
    for index, (location, text) in enumerate(
        split_blocks_to_units(blocks, options.max_unit_chars, options.sentence_delimiters, options.soft_delimiters),
        start=1,
    ):
        normalized = normalize_for_compare(text)
        comparable = is_comparable_text(text, options.min_chars, options.min_words)
        unit_id = _unit_id(path, group_name, location, index, normalized)
        ngrams = make_ngrams(normalized, options.ngram_size) if comparable else tuple()
        units.append(
            TextUnit(
                unit_id=unit_id,
                group_name=group_name,
                group_index=group_index,
                file_path=normalize_path(path),
                file_name=path.name,
                location=location,
                text=text,
                normalized=normalized,
                char_count=visible_char_count(text),
                word_count=english_word_count(text),
                comparable=comparable,
                ngrams=ngrams,
            )
        )
    return units


def _docx_metadata(document: Document, path: Path) -> dict[str, Any]:
    props = document.core_properties
    metadata = _file_metadata(path)
    metadata.update(
        {
            "author": props.author or "",
            "last_modified_by": props.last_modified_by or "",
            "created": _date_value(props.created),
            "modified": _date_value(props.modified),
            "revision": props.revision,
            "title": props.title or "",
            "subject": props.subject or "",
        }
    )
    return metadata


def _file_metadata(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": normalize_path(path),
        "name": path.name,
        "size": stat.st_size,
        "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _docx_images(document: Document, path: Path) -> list[DocumentImage]:
    images: list[DocumentImage] = []
    seen: set[str] = set()
    for rel_index, rel in enumerate(document.part.rels.values(), start=1):
        if "image" not in rel.reltype:
            continue
        blob = rel.target_part.blob
        sha = hashlib.sha256(blob).hexdigest()
        if sha in seen:
            continue
        seen.add(sha)
        info = _image_info(blob)
        images.append(
            DocumentImage(
                image_id=f"{path.name}:image{rel_index}",
                source=normalize_path(path),
                sha256=sha,
                ahash=info["ahash"],
                size=len(blob),
                width=info["width"],
                height=info["height"],
            )
        )
    return images


def _markdown_images(raw: str, path: Path) -> list[DocumentImage]:
    images: list[DocumentImage] = []
    for index, match in enumerate(IMAGE_RE.finditer(raw), start=1):
        target = unquote(match.group(1).strip("<>"))
        parsed = urlparse(target)
        if parsed.scheme in {"http", "https", "data"}:
            continue
        image_path = (path.parent / target).resolve()
        if not image_path.exists() or not image_path.is_file():
            continue
        blob = image_path.read_bytes()
        info = _image_info(blob)
        images.append(
            DocumentImage(
                image_id=f"{path.name}:md-image{index}",
                source=normalize_path(image_path),
                sha256=hashlib.sha256(blob).hexdigest(),
                ahash=info["ahash"],
                size=len(blob),
                width=info["width"],
                height=info["height"],
            )
        )
    return images


def _image_info(blob: bytes) -> dict[str, Any]:
    try:
        with Image.open(BytesIO(blob)) as image:
            width, height = image.size
            gray = image.convert("L").resize((8, 8))
            pixels = list(gray.getdata())
            avg = sum(pixels) / len(pixels)
            bits = "".join("1" if pixel >= avg else "0" for pixel in pixels)
            ahash = f"{int(bits, 2):016x}"
            return {"width": width, "height": height, "ahash": ahash}
    except Exception:
        return {"width": None, "height": None, "ahash": None}


def _strip_markdown(raw: str) -> str:
    text = FENCED_CODE_RE.sub("\n", raw)
    text = INLINE_CODE_RE.sub(" ", text)
    text = IMAGE_RE.sub(" ", text)
    text = LINK_RE.sub(r"\1", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = _strip_markdown_emphasis(text)

    lines: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned or TABLE_SEPARATOR_RE.match(cleaned):
            lines.append("")
            continue
        cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", cleaned)
        cleaned = re.sub(r"\s+#{1,6}\s*$", "", cleaned)
        cleaned = re.sub(r"^\s*>\s?", "", cleaned)
        cleaned = ORDERED_LIST_RE.sub("", cleaned)
        cleaned = UNORDERED_LIST_RE.sub("", cleaned)
        cleaned = cleaned.replace("|", " ")
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        lines.append(cleaned)
    return "\n".join(lines)


def _strip_markdown_emphasis(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        for group_index in (2, 4, 5):
            value = match.group(group_index)
            if value is not None:
                return value
        return ""

    previous = None
    current = text
    while previous != current:
        previous = current
        current = EMPHASIS_RE.sub(replace, current)
    return current


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _date_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat(timespec="seconds")
    return str(value)


def _unit_id(path: Path, group_name: str, location: str, index: int, normalized: str) -> str:
    payload = f"{group_name}|{path}|{location}|{index}|{normalized[:80]}".encode("utf-8", errors="ignore")
    return hashlib.sha1(payload).hexdigest()[:16]
