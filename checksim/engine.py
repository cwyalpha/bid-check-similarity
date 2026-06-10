from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .models import (
    CheckOptions,
    DocumentData,
    ImageDuplicate,
    InputGroup,
    KeywordAlert,
    KeywordHit,
    SimilarityMatch,
    TextUnit,
    normalize_path,
)
from .parsers import parse_file
from .text import make_snippet, similarity_score


Progress = Callable[[str], None]


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).expanduser().open("r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_config(config: dict[str, Any]) -> tuple[list[InputGroup], list[str], list[str], CheckOptions]:
    groups: list[InputGroup] = []
    for index, raw_group in enumerate(config.get("groups") or [], start=1):
        name = str(raw_group.get("name") or f"公司{index}").strip()
        files = [normalize_path(file) for file in raw_group.get("files") or []]
        if files:
            groups.append(InputGroup(name=name, files=files))
    if len(groups) < 2:
        raise ValueError("至少需要导入 2 组投标文件。")
    exclude_files = [normalize_path(file) for file in config.get("exclude_files") or []]
    keywords = [str(item).strip() for item in config.get("keywords") or [] if str(item).strip()]
    options = CheckOptions.from_dict(config.get("options") or {})
    return groups, exclude_files, keywords, options


def run_check(
    config: dict[str, Any],
    output_dir: str | Path | None = None,
    progress: Progress | None = None,
) -> dict[str, Any]:
    progress = progress or (lambda message: None)
    groups, exclude_files, keywords, options = normalize_config(config)

    progress("正在解析投标文件...")
    documents = _parse_group_documents(groups, options, progress)

    progress("正在解析排除文件...")
    exclude_documents = _parse_exclude_documents(exclude_files, options, progress)

    progress("正在建立文本索引并计算相似片段...")
    matches = _find_similarity_matches(documents, exclude_documents, options)

    progress("正在检测重要关键词和正则...")
    keyword_alerts, keyword_errors = _detect_keyword_alerts(documents, keywords)

    progress("正在检测图片重复...")
    image_duplicates = _detect_image_duplicates(documents, options)

    result = _build_result(
        groups=groups,
        exclude_files=exclude_files,
        keywords=keywords,
        options=options,
        documents=documents,
        exclude_documents=exclude_documents,
        matches=matches,
        keyword_alerts=keyword_alerts,
        keyword_errors=keyword_errors,
        image_duplicates=image_duplicates,
    )

    if output_dir:
        from .report import write_report_bundle

        progress("正在生成离线 HTML 报告...")
        paths = write_report_bundle(result, output_dir)
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
            min_shared = max(2, int(min(len(unit.ngrams), len(candidate.ngrams)) * 0.12))
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
            if len(postings) > self.options.max_ngram_postings:
                continue
            for index in postings:
                if index <= current_index:
                    continue
                counts[index] += 1
        ranked = counts.most_common(self.options.max_candidates_per_unit)
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
            if len(postings) > self.options.max_ngram_postings:
                continue
            for index in postings:
                counts[index] += 1
        best_score = 0.0
        best_unit: TextUnit | None = None
        for index, _shared in counts.most_common(80):
            candidate = self.units[index]
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


def _detect_keyword_alerts(documents: list[DocumentData], keywords: list[str]) -> tuple[list[KeywordAlert], list[str]]:
    import re

    alerts: list[KeywordAlert] = []
    errors: list[str] = []
    for keyword in keywords:
        is_regex = keyword.startswith("re:")
        pattern_text = keyword[3:] if is_regex else re.escape(keyword)
        try:
            pattern = re.compile(pattern_text, flags=re.IGNORECASE)
        except re.error as exc:
            errors.append(f"{keyword}: {exc}")
            continue
        hits: list[KeywordHit] = []
        for doc in documents:
            full_text = doc.full_text
            for hit_index, match in enumerate(pattern.finditer(full_text), start=1):
                if hit_index > 100:
                    break
                hits.append(
                    KeywordHit(
                        keyword=keyword,
                        is_regex=is_regex,
                        group_name=doc.group_name,
                        file_path=doc.file_path,
                        file_name=doc.file_name,
                        location=f"命中{hit_index}",
                        snippet=make_snippet(full_text, match.start(), match.end()),
                    )
                )
        groups = sorted({hit.group_name for hit in hits})
        if len(groups) >= 2:
            alerts.append(KeywordAlert(keyword=keyword, is_regex=is_regex, groups=groups, hits=hits))
    return alerts, errors


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
    options: CheckOptions,
    documents: list[DocumentData],
    exclude_documents: list[DocumentData],
    matches: list[SimilarityMatch],
    keyword_alerts: list[KeywordAlert],
    keyword_errors: list[str],
    image_duplicates: list[ImageDuplicate],
) -> dict[str, Any]:
    summaries = _pair_summaries(matches, groups)
    comparable_units = sum(1 for doc in documents for unit in doc.units if unit.comparable)
    total_units = sum(len(doc.units) for doc in documents)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": {
            "groups": [{"name": group.name, "files": group.files} for group in groups],
            "exclude_files": exclude_files,
            "keywords": keywords,
        },
        "options": options.to_dict(),
        "stats": {
            "group_count": len(groups),
            "document_count": len(documents),
            "exclude_document_count": len(exclude_documents),
            "unit_count": total_units,
            "comparable_unit_count": comparable_units,
            "short_filtered_unit_count": total_units - comparable_units,
            "similar_match_count": sum(1 for match in matches if not match.excluded),
            "excluded_match_count": sum(1 for match in matches if match.excluded),
            "keyword_alert_count": len(keyword_alerts),
            "image_duplicate_count": len(image_duplicates),
        },
        "documents": [_document_summary(doc) for doc in documents],
        "exclude_documents": [_document_summary(doc) for doc in exclude_documents],
        "pair_summaries": summaries,
        "matches": [match.to_dict() for match in matches],
        "keyword_alerts": [alert.to_dict() for alert in keyword_alerts],
        "keyword_errors": keyword_errors,
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
        pair_map[(match.group_a, match.group_b)].append(match)

    summaries: list[dict[str, Any]] = []
    group_names = [group.name for group in groups]
    for left_index, left in enumerate(group_names):
        for right in group_names[left_index + 1 :]:
            pair_matches = pair_map.get((left, right), [])
            active = [match for match in pair_matches if not match.excluded]
            excluded = [match for match in pair_matches if match.excluded]
            scores = [match.similarity for match in active]
            summaries.append(
                {
                    "group_a": left,
                    "group_b": right,
                    "match_count": len(active),
                    "excluded_count": len(excluded),
                    "max_similarity": round(max(scores), 4) if scores else 0,
                    "avg_similarity": round(sum(scores) / len(scores), 4) if scores else 0,
                    "files": sorted({Path(match.file_a).name for match in active} | {Path(match.file_b).name for match in active}),
                }
            )
    summaries.sort(key=lambda item: (-item["match_count"], -item["max_similarity"], item["group_a"], item["group_b"]))
    return summaries
