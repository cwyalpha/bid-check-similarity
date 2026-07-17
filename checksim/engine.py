from __future__ import annotations

import json
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .keyword_rules import REGEX_PRESETS, normalize_regex_presets
from .models import (
    CheckOptions,
    DocumentData,
    ImageDuplicate,
    InputGroup,
    KeywordAlert,
    KeywordHit,
    MetadataAlert,
    MetadataHit,
    SimilarityMatch,
    TextUnit,
    normalize_path,
)
from .parsers import parse_file
from .text import make_snippet, similarity_score


Progress = Callable[[str], None]

_TEXT_RECALL_SHARED_RATIO = 0.12
_EXCLUDE_RECALL_LIMIT = 80
_TEXT_RECALL_LENGTH_FLOOR = 0.55

_METADATA_EXACT_RULES = (
    ("author", "作者", "高", "不同分组文档的作者元数据相同"),
    ("company", "公司", "高", "不同分组文档的公司元数据相同"),
    ("last_modified_by", "最后修改者", "中", "不同分组文档的最后修改者元数据相同"),
)
_METADATA_TIME_RULES = (
    ("created", "创建时间", "中", "不同分组文档的内部创建时间处于同一分钟"),
    ("modified", "修改时间", "中", "不同分组文档的内部修改时间处于同一分钟"),
)
_IGNORED_METADATA_VALUES = {
    "admin",
    "administrator",
    "default",
    "kingsoft office",
    "microsoft corporation",
    "microsoft office user",
    "n/a",
    "none",
    "python-docx",
    "unknown",
    "user",
    "wps office",
}
_IGNORED_METADATA_MINUTES = {"2013-12-23 23:15"}


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as fh:
        config = json.load(fh)
    return _resolve_config_paths(config, config_path.parent)


def _resolve_config_paths(config: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    resolved = dict(config)
    groups: list[dict[str, Any]] = []
    for raw_group in config.get("groups") or []:
        group = dict(raw_group)
        group["files"] = [_resolve_config_path(file, base_dir) for file in group.get("files") or []]
        groups.append(group)
    resolved["groups"] = groups
    resolved["exclude_files"] = [_resolve_config_path(file, base_dir) for file in config.get("exclude_files") or []]
    return resolved


def _resolve_config_path(value: object, base_dir: Path) -> str:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    return str((base_dir / path).resolve())


def normalize_config(
    config: dict[str, Any],
) -> tuple[list[InputGroup], list[str], list[str], list[str], dict[str, bool], CheckOptions]:
    groups: list[InputGroup] = []
    for index, raw_group in enumerate(config.get("groups") or [], start=1):
        name = str(raw_group.get("name") or f"公司{index}").strip()
        files = [normalize_path(file) for file in raw_group.get("files") or []]
        if files:
            groups.append(InputGroup(name=name, files=files))
    if len(groups) < 2:
        raise ValueError("至少需要导入 2 组投标文件。")
    exclude_files = [normalize_path(file) for file in config.get("exclude_files") or []]
    keywords: list[str] = []
    regex_keywords: list[str] = []
    for item in config.get("keywords") or []:
        value = str(item).strip()
        if not value:
            continue
        if value.startswith("re:"):
            pattern = value[3:].strip()
            if pattern:
                regex_keywords.append(pattern)
        else:
            keywords.append(value)
    for item in config.get("regex_keywords") or []:
        value = str(item).strip()
        if value.startswith("re:"):
            value = value[3:].strip()
        if value:
            regex_keywords.append(value)
    regex_keywords = list(dict.fromkeys(regex_keywords))
    regex_presets = normalize_regex_presets(config.get("regex_presets"))
    options = CheckOptions.from_dict(config.get("options") or {})
    return groups, exclude_files, keywords, regex_keywords, regex_presets, options


def run_check(
    config: dict[str, Any],
    output_dir: str | Path | None = None,
    progress: Progress | None = None,
) -> dict[str, Any]:
    progress = progress or (lambda message: None)
    run_started = time.perf_counter()
    stage_seconds: dict[str, float] = {}
    groups, exclude_files, keywords, regex_keywords, regex_presets, options = normalize_config(config)

    progress("正在解析投标文件...")
    stage_started = time.perf_counter()
    documents = _parse_group_documents(groups, options, progress)
    stage_seconds["parse_documents"] = round(time.perf_counter() - stage_started, 3)
    progress(f"投标文件解析完成，用时 {stage_seconds['parse_documents']:.3f} 秒。")

    progress("正在解析排除文件...")
    stage_started = time.perf_counter()
    exclude_documents = _parse_exclude_documents(exclude_files, options, progress)
    stage_seconds["parse_excludes"] = round(time.perf_counter() - stage_started, 3)
    progress(f"排除文件解析完成，用时 {stage_seconds['parse_excludes']:.3f} 秒。")

    progress("正在建立文本索引并计算相似片段...")
    stage_started = time.perf_counter()
    matches = _find_similarity_matches(documents, exclude_documents, options)
    stage_seconds["similarity"] = round(time.perf_counter() - stage_started, 3)
    progress(f"相似片段计算完成，用时 {stage_seconds['similarity']:.3f} 秒。")

    progress("正在检测重要关键词和正则...")
    stage_started = time.perf_counter()
    keyword_alerts, keyword_errors = _detect_keyword_alerts(
        documents,
        keywords,
        regex_keywords,
        regex_presets,
    )
    stage_seconds["keywords"] = round(time.perf_counter() - stage_started, 3)

    progress("正在检测文档元数据碰撞...")
    stage_started = time.perf_counter()
    metadata_alerts = _detect_metadata_alerts(documents)
    stage_seconds["metadata"] = round(time.perf_counter() - stage_started, 3)

    progress("正在检测图片重复...")
    stage_started = time.perf_counter()
    image_duplicates = _detect_image_duplicates(documents, options)
    stage_seconds["images"] = round(time.perf_counter() - stage_started, 3)

    result = _build_result(
        groups=groups,
        exclude_files=exclude_files,
        keywords=keywords,
        regex_keywords=regex_keywords,
        regex_presets=regex_presets,
        options=options,
        documents=documents,
        exclude_documents=exclude_documents,
        matches=matches,
        keyword_alerts=keyword_alerts,
        keyword_errors=keyword_errors,
        metadata_alerts=metadata_alerts,
        image_duplicates=image_duplicates,
    )
    result["performance"] = {
        "stage_seconds": stage_seconds,
        "engine_seconds": round(time.perf_counter() - run_started, 3),
    }

    if output_dir:
        from .report import write_report_bundle

        progress("正在生成离线 HTML 报告...")
        paths = write_report_bundle(result, output_dir)
        result["performance"]["engine_seconds"] = round(time.perf_counter() - run_started, 3)
        result["output_files"] = paths
    progress("完成。")
    return result


def _parse_group_documents(groups: list[InputGroup], options: CheckOptions, progress: Progress) -> list[DocumentData]:
    documents: list[DocumentData] = []
    for group_index, group in enumerate(groups):
        for file in group.files:
            progress(f"解析 {group.name}: {Path(file).name}")
            documents.append(parse_file(file, group.name, group_index, options, progress))
    return documents


def _parse_exclude_documents(files: list[str], options: CheckOptions, progress: Progress) -> list[DocumentData]:
    documents: list[DocumentData] = []
    for file in files:
        progress(f"解析排除文件: {Path(file).name}")
        documents.append(parse_file(file, "排除文件", -1, options, progress))
    return documents


def _find_similarity_matches(
    documents: list[DocumentData],
    exclude_documents: list[DocumentData],
    options: CheckOptions,
) -> list[SimilarityMatch]:
    units = [unit for doc in documents for unit in doc.units if unit.comparable and unit.normalized]
    units.sort(key=lambda item: (item.group_index, item.file_path, item.location))
    index = _NgramIndex(units, options)
    exclude_index = _ExcludeIndex([unit for doc in exclude_documents for unit in doc.units if unit.comparable], options)
    matches: list[SimilarityMatch] = []
    seen: set[tuple[str, str]] = set()

    for unit in units:
        candidates = index.candidates_for(unit)
        for candidate, shared in candidates:
            if candidate.group_index == unit.group_index:
                continue
            key = tuple(sorted((unit.unit_id, candidate.unit_id)))
            if key in seen:
                continue
            seen.add(key)
            if not _length_ratio_ok(unit.normalized, candidate.normalized, _TEXT_RECALL_LENGTH_FLOOR):
                continue
            min_shared = max(2, int(min(len(unit.ngrams), len(candidate.ngrams)) * _TEXT_RECALL_SHARED_RATIO))
            if shared < min_shared:
                continue
            score = similarity_score(unit.normalized, candidate.normalized, unit.ngrams, candidate.ngrams)
            if score < options.similarity_threshold:
                continue
            left, right = _ordered_pair(unit, candidate)
            left_excluded = exclude_index.best_match(left)
            right_excluded = exclude_index.best_match(right)
            excluded = left_excluded["matched"] and right_excluded["matched"]
            reason = None
            if excluded:
                reason = (
                    f"两侧均匹配排除文件: {left_excluded['file_name']}({left_excluded['score']:.2f}), "
                    f"{right_excluded['file_name']}({right_excluded['score']:.2f})"
                )
            matches.append(
                SimilarityMatch(
                    match_id=f"M{len(matches) + 1:05d}",
                    unit_id_a=left.unit_id,
                    unit_id_b=right.unit_id,
                    group_a=left.group_name,
                    group_b=right.group_name,
                    file_a=left.file_path,
                    file_b=right.file_path,
                    location_a=left.location,
                    location_b=right.location,
                    text_a=left.text,
                    text_b=right.text,
                    similarity=score,
                    excluded=excluded,
                    exclude_reason=reason,
                )
            )
    matches.sort(key=lambda item: (item.excluded, -item.similarity, item.group_a, item.group_b))
    return matches


def _ordered_pair(a: TextUnit, b: TextUnit) -> tuple[TextUnit, TextUnit]:
    if (a.group_index, a.file_path, a.location) <= (b.group_index, b.file_path, b.location):
        return a, b
    return b, a


class _NgramIndex:
    def __init__(self, units: list[TextUnit], options: CheckOptions) -> None:
        self.units = units
        self.options = options
        self.positions = {unit.unit_id: index for index, unit in enumerate(units)}
        postings: dict[str, list[int]] = defaultdict(list)
        exact: dict[str, list[int]] = defaultdict(list)
        for index, unit in enumerate(units):
            exact[unit.normalized].append(index)
            for gram in unit.ngrams:
                postings[gram].append(index)
        self.postings = postings
        self.exact = exact

    def candidates_for(self, unit: TextUnit) -> list[tuple[TextUnit, int]]:
        current_index = self.positions[unit.unit_id]
        counts: Counter[int] = Counter()
        for index in self.exact.get(unit.normalized, []):
            if index > current_index:
                counts[index] += max(len(unit.ngrams), 1)
        for gram in unit.ngrams:
            postings = self.postings.get(gram) or []
            if self.options.max_ngram_postings and len(postings) > self.options.max_ngram_postings:
                continue
            for index in postings:
                if index <= current_index:
                    continue
                counts[index] += 1
        ranked = counts.most_common(self.options.max_candidates_per_unit or None)
        return [(self.units[index], shared) for index, shared in ranked]


class _ExcludeIndex:
    def __init__(self, units: list[TextUnit], options: CheckOptions) -> None:
        self.units = [unit for unit in units if unit.normalized and unit.ngrams]
        self.options = options
        self.cache: dict[str, dict[str, Any]] = {}
        postings: dict[str, list[int]] = defaultdict(list)
        exact: dict[str, list[int]] = defaultdict(list)
        for index, unit in enumerate(self.units):
            exact[unit.normalized].append(index)
            for gram in unit.ngrams:
                postings[gram].append(index)
        self.postings = postings
        self.exact = exact

    def best_match(self, unit: TextUnit) -> dict[str, Any]:
        if unit.unit_id in self.cache:
            return self.cache[unit.unit_id]
        if not self.units:
            result = {"matched": False, "score": 0.0, "file_name": ""}
            self.cache[unit.unit_id] = result
            return result
        exact_matches = self.exact.get(unit.normalized, [])
        if exact_matches:
            best_unit = self.units[exact_matches[0]]
            result = {"matched": True, "score": 1.0, "file_name": best_unit.file_name}
            self.cache[unit.unit_id] = result
            return result
        counts: Counter[int] = Counter()
        for gram in unit.ngrams:
            postings = self.postings.get(gram) or []
            if self.options.max_ngram_postings and len(postings) > self.options.max_ngram_postings:
                continue
            for index in postings:
                counts[index] += 1
        best_score = 0.0
        best_unit: TextUnit | None = None
        for index, _shared in counts.most_common(_EXCLUDE_RECALL_LIMIT):
            candidate = self.units[index]
            if not _length_ratio_ok(unit.normalized, candidate.normalized, _TEXT_RECALL_LENGTH_FLOOR):
                continue
            score = similarity_score(unit.normalized, candidate.normalized, unit.ngrams, candidate.ngrams)
            if score > best_score:
                best_score = score
                best_unit = candidate
        result = {
            "matched": best_score >= self.options.exclude_threshold,
            "score": best_score,
            "file_name": best_unit.file_name if best_unit else "",
        }
        self.cache[unit.unit_id] = result
        return result


def _detect_keyword_alerts(
    documents: list[DocumentData],
    keywords: list[str],
    regex_keywords: list[str] | None = None,
    regex_presets: dict[str, bool] | None = None,
) -> tuple[list[KeywordAlert], list[str]]:
    import re

    alerts: list[KeywordAlert] = []
    errors: list[str] = []
    rules: list[tuple[str, str, bool]] = []
    for keyword in keywords:
        if keyword.startswith("re:"):
            rules.append((keyword, keyword[3:], True))
        else:
            rules.append((keyword, re.escape(keyword), False))
    for regex_keyword in regex_keywords or []:
        pattern_text = regex_keyword[3:] if regex_keyword.startswith("re:") else regex_keyword
        rules.append((pattern_text, pattern_text, True))
    enabled_presets = normalize_regex_presets(regex_presets)
    for preset_key, enabled in enabled_presets.items():
        if enabled:
            preset = REGEX_PRESETS[preset_key]
            rules.append((f"{preset.label}（预设）", preset.pattern, True))

    seen_rules: set[tuple[str, bool]] = set()
    for keyword, pattern_text, is_regex in rules:
        rule_key = (pattern_text, is_regex)
        if rule_key in seen_rules:
            continue
        seen_rules.add(rule_key)
        try:
            pattern = re.compile(pattern_text, flags=re.IGNORECASE)
        except re.error as exc:
            errors.append(f"{keyword}: {exc}")
            continue
        hits_by_value: dict[str, list[KeywordHit]] = defaultdict(list)
        display_values: dict[str, str] = {}
        for doc in documents:
            full_text = doc.full_text
            for hit_index, match in enumerate(pattern.finditer(full_text), start=1):
                matched_text = match.group(0)
                if not matched_text.strip():
                    continue
                canonical_value = matched_text if is_regex else keyword.casefold()
                display_values.setdefault(canonical_value, matched_text)
                hits_by_value[canonical_value].append(
                    KeywordHit(
                        keyword=keyword,
                        is_regex=is_regex,
                        group_name=doc.group_name,
                        file_path=doc.file_path,
                        file_name=doc.file_name,
                        location=f"命中{hit_index}",
                        snippet=make_snippet(full_text, match.start(), match.end()),
                        matched_text=matched_text,
                        pattern=pattern_text,
                    )
                )
        for canonical_value, hits in hits_by_value.items():
            groups = sorted({hit.group_name for hit in hits})
            if len(groups) >= 2:
                alerts.append(
                    KeywordAlert(
                        keyword=keyword,
                        is_regex=is_regex,
                        groups=groups,
                        hits=hits,
                        matched_text=display_values[canonical_value],
                        pattern=pattern_text,
                    )
                )
    return alerts, errors


def _detect_metadata_alerts(documents: list[DocumentData]) -> list[MetadataAlert]:
    alerts: list[MetadataAlert] = []
    for field, label, level, reason in _METADATA_EXACT_RULES:
        alerts.extend(_metadata_value_alerts(documents, field, label, level, reason))
    for field, label, level, reason in _METADATA_TIME_RULES:
        alerts.extend(_metadata_time_alerts(documents, field, label, level, reason))
    return sorted(alerts, key=lambda item: (0 if item.level == "高" else 1, item.label, item.value))


def _metadata_value_alerts(
    documents: list[DocumentData],
    field: str,
    label: str,
    level: str,
    reason: str,
) -> list[MetadataAlert]:
    hits_by_value: dict[str, list[MetadataHit]] = defaultdict(list)
    display_values: dict[str, str] = {}
    for doc in documents:
        raw_value = str(doc.metadata.get(field) or "").strip()
        normalized = _normalize_metadata_value(raw_value)
        if not normalized or normalized in _IGNORED_METADATA_VALUES:
            continue
        display_values.setdefault(normalized, raw_value[:200])
        hits_by_value[normalized].append(_metadata_hit(doc, raw_value[:200]))
    return _metadata_alerts_from_hits(field, label, level, reason, hits_by_value, display_values)


def _metadata_time_alerts(
    documents: list[DocumentData],
    field: str,
    label: str,
    level: str,
    reason: str,
) -> list[MetadataAlert]:
    hits_by_value: dict[str, list[MetadataHit]] = defaultdict(list)
    display_values: dict[str, str] = {}
    for doc in documents:
        raw_value = str(doc.metadata.get(field) or "").strip()
        minute_key = _metadata_minute_key(raw_value)
        if not minute_key or minute_key in _IGNORED_METADATA_MINUTES:
            continue
        display_values[minute_key] = f"{minute_key}（同一分钟）"
        hits_by_value[minute_key].append(_metadata_hit(doc, raw_value[:200]))
    return _metadata_alerts_from_hits(field, label, level, reason, hits_by_value, display_values)


def _metadata_alerts_from_hits(
    field: str,
    label: str,
    level: str,
    reason: str,
    hits_by_value: dict[str, list[MetadataHit]],
    display_values: dict[str, str],
) -> list[MetadataAlert]:
    alerts: list[MetadataAlert] = []
    for normalized, hits in hits_by_value.items():
        groups = sorted({hit.group_name for hit in hits})
        if len(groups) < 2:
            continue
        alerts.append(
            MetadataAlert(
                field=field,
                label=label,
                level=level,
                value=display_values[normalized],
                groups=groups,
                hits=hits,
                reason=reason,
            )
        )
    return alerts


def _metadata_hit(doc: DocumentData, value: str) -> MetadataHit:
    return MetadataHit(
        group_name=doc.group_name,
        file_path=doc.file_path,
        file_name=doc.file_name,
        value=value,
    )


def _normalize_metadata_value(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


def _metadata_minute_key(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if text.startswith("D:"):
        digits = "".join(character for character in text[2:] if character.isdigit())
        if len(digits) >= 12:
            return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]} {digits[8:10]}:{digits[10:12]}"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return parsed.strftime("%Y-%m-%d %H:%M")


def _detect_image_duplicates(documents: list[DocumentData], options: CheckOptions) -> list[ImageDuplicate]:
    image_items: list[dict[str, Any]] = []
    for doc in documents:
        for image in doc.images:
            image_items.append(
                {
                    "group_name": doc.group_name,
                    "file_path": doc.file_path,
                    "file_name": doc.file_name,
                    "image_id": image.image_id,
                    "source": image.source,
                    "sha256": image.sha256,
                    "ahash": image.ahash,
                    "size": image.size,
                    "width": image.width,
                    "height": image.height,
                }
            )

    duplicates: list[ImageDuplicate] = []
    by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in image_items:
        by_sha[item["sha256"]].append(item)
    for items in by_sha.values():
        if len({item["group_name"] for item in items}) >= 2:
            duplicates.append(ImageDuplicate(kind="sha256", distance=0, images=items))

    exact_pairs = {tuple(sorted((a["image_id"], b["image_id"]))) for dup in duplicates for a in dup.images for b in dup.images if a is not b}
    for index, left in enumerate(image_items):
        if not left.get("ahash"):
            continue
        for right in image_items[index + 1 :]:
            if left["group_name"] == right["group_name"] or not right.get("ahash"):
                continue
            key = tuple(sorted((left["image_id"], right["image_id"])))
            if key in exact_pairs:
                continue
            distance = _hamming_hex(left["ahash"], right["ahash"])
            if distance <= options.image_ahash_distance:
                duplicates.append(ImageDuplicate(kind="ahash", distance=distance, images=[left, right]))
    return duplicates


def _hamming_hex(left: str, right: str) -> int:
    try:
        return _bit_count_compat(int(left, 16) ^ int(right, 16))
    except ValueError:
        return 64


def _bit_count_compat(value: int) -> int:
    bit_count = getattr(value, "bit_count", None)
    if bit_count is not None:
        return bit_count()
    return bin(value).count("1")


def _build_result(
    groups: list[InputGroup],
    exclude_files: list[str],
    keywords: list[str],
    regex_keywords: list[str],
    regex_presets: dict[str, bool],
    options: CheckOptions,
    documents: list[DocumentData],
    exclude_documents: list[DocumentData],
    matches: list[SimilarityMatch],
    keyword_alerts: list[KeywordAlert],
    keyword_errors: list[str],
    metadata_alerts: list[MetadataAlert],
    image_duplicates: list[ImageDuplicate],
) -> dict[str, Any]:
    summaries = _pair_summaries(matches, groups)
    comparable_units = sum(1 for doc in documents for unit in doc.units if unit.comparable)
    total_units = sum(len(doc.units) for doc in documents)
    total_similar = sum(1 for match in matches if not match.excluded)
    total_excluded = sum(1 for match in matches if match.excluded)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": {
            "groups": [{"name": group.name, "files": group.files} for group in groups],
            "exclude_files": exclude_files,
            "keywords": keywords,
            "regex_keywords": regex_keywords,
            "regex_presets": regex_presets,
        },
        "options": options.to_dict(),
        "stats": {
            "group_count": len(groups),
            "document_count": len(documents),
            "exclude_document_count": len(exclude_documents),
            "unit_count": total_units,
            "comparable_unit_count": comparable_units,
            "short_filtered_unit_count": total_units - comparable_units,
            "similar_match_count": total_similar,
            "excluded_match_count": total_excluded,
            "total_similar_match_count": total_similar,
            "total_excluded_match_count": total_excluded,
            "displayed_similar_match_count": total_similar,
            "displayed_excluded_match_count": total_excluded,
            "truncated_similar_match_count": 0,
            "truncated_excluded_match_count": 0,
            "match_truncated": False,
            "keyword_alert_count": len(keyword_alerts),
            "metadata_alert_count": len(metadata_alerts),
            "image_duplicate_count": len(image_duplicates),
        },
        "documents": [_document_summary(doc) for doc in documents],
        "exclude_documents": [_document_summary(doc) for doc in exclude_documents],
        "pair_summaries": summaries,
        "matches": [match.to_dict() for match in matches],
        "keyword_alerts": [alert.to_dict() for alert in keyword_alerts],
        "keyword_errors": keyword_errors,
        "metadata_alerts": [alert.to_dict() for alert in metadata_alerts],
        "image_duplicates": [duplicate.to_dict() for duplicate in image_duplicates],
    }


def _document_summary(doc: DocumentData) -> dict[str, Any]:
    return {
        "group_name": doc.group_name,
        "file_path": doc.file_path,
        "file_name": doc.file_name,
        "metadata": doc.metadata,
        "units": [unit.result_dict() for unit in doc.units],
        "unit_count": len(doc.units),
        "comparable_unit_count": sum(1 for unit in doc.units if unit.comparable),
        "short_filtered_unit_count": sum(1 for unit in doc.units if not unit.comparable),
        "image_count": len(doc.images),
    }


def _pair_summaries(matches: list[SimilarityMatch], groups: list[InputGroup]) -> list[dict[str, Any]]:
    pair_map: dict[tuple[str, str], list[SimilarityMatch]] = defaultdict(list)
    for match in matches:
        pair_map[_pair_key(match.group_a, match.group_b)].append(match)

    summaries: list[dict[str, Any]] = []
    group_names = [group.name for group in groups]
    for left_index, left in enumerate(group_names):
        for right in group_names[left_index + 1 :]:
            pair_key = _pair_key(left, right)
            pair_matches = pair_map.get(pair_key, [])
            active = [match for match in pair_matches if not match.excluded]
            excluded = [match for match in pair_matches if match.excluded]
            scores = [match.similarity for match in active]
            summaries.append(
                {
                    "group_a": left,
                    "group_b": right,
                    "match_count": len(active),
                    "excluded_count": len(excluded),
                    "total_match_count": len(active),
                    "total_excluded_count": len(excluded),
                    "displayed_match_count": len(active),
                    "displayed_excluded_count": len(excluded),
                    "truncated_match_count": 0,
                    "truncated_excluded_count": 0,
                    "truncated": False,
                    "max_similarity": round(max(scores), 4) if scores else 0,
                    "avg_similarity": round(sum(scores) / len(scores), 4) if scores else 0,
                    "files": sorted({Path(match.file_a).name for match in active} | {Path(match.file_b).name for match in active}),
                }
            )
    summaries.sort(key=lambda item: (-item["match_count"], -item["max_similarity"], item["group_a"], item["group_b"]))
    return summaries


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _length_ratio_ok(left: str, right: str, min_ratio: float) -> bool:
    if min_ratio <= 0:
        return True
    left_len = len(left)
    right_len = len(right)
    if not left_len or not right_len:
        return False
    return min(left_len, right_len) / max(left_len, right_len) >= min_ratio
