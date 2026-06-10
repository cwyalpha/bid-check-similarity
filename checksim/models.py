from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {".docx", ".doc", ".wps", ".md"}


@dataclass
class CheckOptions:
    min_chars: int = 20
    min_words: int = 8
    similarity_threshold: float = 0.78
    exclude_threshold: float = 0.86
    sentence_delimiters: str = "。！？!?；;"
    soft_delimiters: str = "，,、：:"
    ngram_size: int = 3
    max_unit_chars: int = 420
    max_candidates_per_unit: int = 200
    max_ngram_postings: int = 300
    image_ahash_distance: int = 6
    legacy_conversion_timeout: int = 120
    soffice_path: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "CheckOptions":
        raw = raw or {}
        options = cls()
        for key in (
            "min_chars",
            "min_words",
            "similarity_threshold",
            "exclude_threshold",
            "sentence_delimiters",
            "soft_delimiters",
            "ngram_size",
            "max_unit_chars",
            "max_candidates_per_unit",
            "max_ngram_postings",
            "image_ahash_distance",
            "legacy_conversion_timeout",
            "soffice_path",
        ):
            if key in raw and raw[key] is not None:
                setattr(options, key, raw[key])
        options.validate()
        return options

    def validate(self) -> None:
        self.min_chars = max(1, int(self.min_chars))
        self.min_words = max(1, int(self.min_words))
        self.ngram_size = max(2, int(self.ngram_size))
        self.max_unit_chars = max(80, int(self.max_unit_chars))
        self.max_candidates_per_unit = max(20, int(self.max_candidates_per_unit))
        self.max_ngram_postings = max(50, int(self.max_ngram_postings))
        self.image_ahash_distance = max(0, int(self.image_ahash_distance))
        self.legacy_conversion_timeout = max(10, int(self.legacy_conversion_timeout))
        self.similarity_threshold = _clamp_float(self.similarity_threshold, 0.1, 1.0)
        self.exclude_threshold = _clamp_float(self.exclude_threshold, 0.1, 1.0)
        self.sentence_delimiters = str(self.sentence_delimiters or "。！？!?；;")
        self.soft_delimiters = str(self.soft_delimiters or "，,、：:")
        self.soffice_path = str(self.soffice_path or "").strip()

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_chars": self.min_chars,
            "min_words": self.min_words,
            "similarity_threshold": self.similarity_threshold,
            "exclude_threshold": self.exclude_threshold,
            "sentence_delimiters": self.sentence_delimiters,
            "soft_delimiters": self.soft_delimiters,
            "ngram_size": self.ngram_size,
            "max_unit_chars": self.max_unit_chars,
            "max_candidates_per_unit": self.max_candidates_per_unit,
            "max_ngram_postings": self.max_ngram_postings,
            "image_ahash_distance": self.image_ahash_distance,
            "legacy_conversion_timeout": self.legacy_conversion_timeout,
            "soffice_path": self.soffice_path,
        }


@dataclass
class InputGroup:
    name: str
    files: list[str]


@dataclass
class DocumentImage:
    image_id: str
    source: str
    sha256: str
    ahash: str | None
    size: int
    width: int | None = None
    height: int | None = None


@dataclass
class TextUnit:
    unit_id: str
    group_name: str
    group_index: int
    file_path: str
    file_name: str
    location: str
    text: str
    normalized: str
    char_count: int
    word_count: int
    comparable: bool
    ngrams: tuple[str, ...] = field(default_factory=tuple)

    def result_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "group_name": self.group_name,
            "group_index": self.group_index,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "location": self.location,
            "text": self.text,
            "normalized": self.normalized,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "comparable": self.comparable,
        }


@dataclass
class DocumentData:
    group_name: str
    group_index: int
    file_path: str
    file_name: str
    metadata: dict[str, Any]
    blocks: list[str]
    units: list[TextUnit]
    images: list[DocumentImage]

    @property
    def full_text(self) -> str:
        return "\n".join(self.blocks)


@dataclass
class SimilarityMatch:
    match_id: str
    unit_id_a: str
    unit_id_b: str
    group_a: str
    group_b: str
    file_a: str
    file_b: str
    location_a: str
    location_b: str
    text_a: str
    text_b: str
    similarity: float
    excluded: bool
    exclude_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "unit_id_a": self.unit_id_a,
            "unit_id_b": self.unit_id_b,
            "group_a": self.group_a,
            "group_b": self.group_b,
            "file_a": self.file_a,
            "file_b": self.file_b,
            "location_a": self.location_a,
            "location_b": self.location_b,
            "text_a": self.text_a,
            "text_b": self.text_b,
            "similarity": round(self.similarity, 4),
            "excluded": self.excluded,
            "exclude_reason": self.exclude_reason,
        }


@dataclass
class KeywordHit:
    keyword: str
    is_regex: bool
    group_name: str
    file_path: str
    file_name: str
    location: str
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "is_regex": self.is_regex,
            "group_name": self.group_name,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "location": self.location,
            "snippet": self.snippet,
        }


@dataclass
class KeywordAlert:
    keyword: str
    is_regex: bool
    groups: list[str]
    hits: list[KeywordHit]

    def to_dict(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "is_regex": self.is_regex,
            "groups": self.groups,
            "hits": [hit.to_dict() for hit in self.hits],
        }


@dataclass
class ImageDuplicate:
    kind: str
    distance: int
    images: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "distance": self.distance, "images": self.images}


def normalize_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return min(high, max(low, number))
