from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Iterable


CJK_RE = re.compile(r"[\u3400-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")
VISIBLE_RE = re.compile(r"[\w\u3400-\u9fff]", re.UNICODE)


def normalize_for_compare(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()
    return "".join(VISIBLE_RE.findall(text))


def visible_char_count(text: str) -> int:
    return len(VISIBLE_RE.findall(unicodedata.normalize("NFKC", text or "")))


def english_word_count(text: str) -> int:
    return len(WORD_RE.findall(unicodedata.normalize("NFKC", text or "")))


def is_cjk_or_mixed(text: str) -> bool:
    return bool(CJK_RE.search(text or ""))


def is_comparable_text(text: str, min_chars: int, min_words: int) -> bool:
    if is_cjk_or_mixed(text):
        return visible_char_count(text) >= min_chars
    return english_word_count(text) >= min_words


def split_blocks_to_units(
    blocks: Iterable[str],
    max_unit_chars: int,
    sentence_delimiters: str = "。！？!?；;",
    soft_delimiters: str = "，,、：:",
) -> list[tuple[str, str]]:
    units: list[tuple[str, str]] = []
    for block_index, block in enumerate(blocks, start=1):
        cleaned = clean_text(block)
        if not cleaned:
            continue
        parts = _split_long_text(cleaned, max_unit_chars, sentence_delimiters, soft_delimiters)
        for part_index, part in enumerate(parts, start=1):
            if part:
                units.append((f"段{block_index}.{part_index}", part))
    return units


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_ngrams(normalized: str, n: int) -> tuple[str, ...]:
    if not normalized:
        return tuple()
    if len(normalized) <= n:
        return (normalized,)
    return tuple({normalized[i : i + n] for i in range(0, len(normalized) - n + 1)})


def similarity_score(a: str, b: str, grams_a: Iterable[str] | None = None, grams_b: Iterable[str] | None = None) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    set_a = set(grams_a or make_ngrams(a, 3))
    set_b = set(grams_b or make_ngrams(b, 3))
    if not set_a or not set_b:
        jaccard = 0.0
    else:
        jaccard = len(set_a & set_b) / len(set_a | set_b)
    seq_ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    return (0.62 * seq_ratio) + (0.38 * jaccard)


def highlight_common(left: str, right: str, min_equal: int = 4) -> tuple[str, str]:
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    left_parts: list[str] = []
    right_parts: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        left_text = _escape(left[i1:i2])
        right_text = _escape(right[j1:j2])
        if tag == "equal" and max(i2 - i1, j2 - j1) >= min_equal:
            left_parts.append(f"<mark>{left_text}</mark>")
            right_parts.append(f"<mark>{right_text}</mark>")
        else:
            left_parts.append(left_text)
            right_parts.append(right_text)
    return "".join(left_parts), "".join(right_parts)


def make_snippet(text: str, start: int, end: int, window: int = 50) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    prefix = "..." if left > 0 else ""
    suffix = "..." if right < len(text) else ""
    return prefix + text[left:right].replace("\n", " ") + suffix


def _split_long_text(text: str, max_unit_chars: int, sentence_delimiters: str, soft_delimiters: str) -> list[str]:
    rough = _split_after_delimiters(text, sentence_delimiters)
    if not rough:
        rough = [text]
    pieces: list[str] = []
    for part in rough:
        if visible_char_count(part) <= max_unit_chars:
            pieces.append(part)
            continue
        soft_parts = _split_after_delimiters(part, soft_delimiters)
        buffer = ""
        for soft in soft_parts:
            if not buffer:
                buffer = soft
            elif visible_char_count(buffer + soft) <= max_unit_chars:
                buffer += soft
            else:
                pieces.extend(_fixed_chunks(buffer, max_unit_chars))
                buffer = soft
        if buffer:
            pieces.extend(_fixed_chunks(buffer, max_unit_chars))
    return pieces


def _fixed_chunks(text: str, max_unit_chars: int) -> list[str]:
    if visible_char_count(text) <= max_unit_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for char in text:
        current += char
        if visible_char_count(current) >= max_unit_chars:
            chunks.append(current.strip())
            current = ""
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _merge_small_neighbors(parts: list[str], max_unit_chars: int) -> list[str]:
    merged: list[str] = []
    buffer = ""
    for part in parts:
        candidate = (buffer + part).strip() if buffer else part.strip()
        if not buffer:
            buffer = part.strip()
        elif visible_char_count(candidate) <= max_unit_chars:
            buffer = candidate
        else:
            merged.append(buffer)
            buffer = part.strip()
    if buffer:
        merged.append(buffer)
    return merged


def _split_after_delimiters(text: str, delimiters: str) -> list[str]:
    normalized_delimiters = set(unicodedata.normalize("NFKC", delimiters or ""))
    parts: list[str] = []
    buffer: list[str] = []
    for char in text:
        if char in "\r\n":
            current = "".join(buffer).strip()
            if current:
                parts.append(current)
            buffer = []
            continue
        buffer.append(char)
        if char in normalized_delimiters:
            current = "".join(buffer).strip()
            if current:
                parts.append(current)
            buffer = []
    current = "".join(buffer).strip()
    if current:
        parts.append(current)
    return parts


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
