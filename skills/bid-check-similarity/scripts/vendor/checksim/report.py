from __future__ import annotations

import json
import time
from html import escape
from pathlib import Path
from typing import Any

from .text import highlight_common


def write_report_bundle(result: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    started = time.perf_counter()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "result.json"
    report_path = output / "report.html"
    ai_summary_path = output / "ai_summary.json"
    compare_pages = _write_compare_pages(result, output)
    paths = {
        "result_json": str(result_path),
        "ai_summary_json": str(ai_summary_path),
        "report_html": str(report_path),
        "output_dir": str(output),
        "compare_pages": compare_pages,
        "match_truncated": bool(result.get("stats", {}).get("match_truncated")),
    }
    result["output_files"] = paths
    result.setdefault("performance", {}).setdefault("stage_seconds", {})["report"] = round(time.perf_counter() - started, 3)
    ai_summary = build_ai_summary(result)
    ai_summary_path.write_text(json.dumps(ai_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["ai_summary_json_bytes"] = ai_summary_path.stat().st_size
    report_path.write_text(render_report(result), encoding="utf-8")
    paths["report_html_bytes"] = report_path.stat().st_size
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["result_json_bytes"] = result_path.stat().st_size
    result["output_files"] = paths
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def build_ai_summary(result: dict[str, Any]) -> dict[str, Any]:
    matches = result.get("matches", [])
    active_matches = [match for match in matches if not match.get("excluded")]
    excluded_matches = [match for match in matches if match.get("excluded")]
    return {
        "schema": "checksim.ai_summary.v1",
        "purpose": "供 AI/Agent 快速判断是否存在疑似重复、共享关键词、元数据碰撞或重复图片；完整结果见 result.json，人工复核见 report.html 和 compare_*.html。",
        "generated_at": result.get("generated_at", ""),
        "stats": _ai_stats(result),
        "output_files": _ai_output_files(result),
        "options": result.get("options", {}),
        "pair_summaries": _ai_pair_summaries(result),
        "evidence": {
            "similar_text": _ai_match_samples(active_matches, result, per_pair_limit=20, total_limit=160),
            "excluded_text": _ai_match_samples(excluded_matches, result, per_pair_limit=8, total_limit=80),
            "keyword_alerts": _ai_keyword_alerts(result),
            "metadata_alerts": _ai_metadata_alerts(result),
            "image_duplicates": _ai_image_duplicates(result),
        },
        "limits": {
            "similar_text_per_pair": 20,
            "similar_text_total": 160,
            "excluded_text_per_pair": 8,
            "excluded_text_total": 80,
            "keyword_hits_per_rule": 10,
            "metadata_hits_per_alert": 10,
            "image_duplicate_groups": 30,
            "text_chars_per_side": 320,
        },
    }


def _ai_stats(result: dict[str, Any]) -> dict[str, Any]:
    stats = result.get("stats", {})
    return {
        "group_count": stats.get("group_count", 0),
        "document_count": stats.get("document_count", 0),
        "exclude_document_count": stats.get("exclude_document_count", 0),
        "unit_count": stats.get("unit_count", 0),
        "comparable_unit_count": stats.get("comparable_unit_count", 0),
        "short_filtered_unit_count": stats.get("short_filtered_unit_count", 0),
        "similar_match_count": stats.get("similar_match_count", 0),
        "excluded_match_count": stats.get("excluded_match_count", 0),
        "keyword_alert_count": stats.get("keyword_alert_count", 0),
        "metadata_alert_count": stats.get("metadata_alert_count", 0),
        "image_duplicate_count": stats.get("image_duplicate_count", 0),
        "has_abnormal_similarity": bool(stats.get("similar_match_count", 0)),
        "has_keyword_alerts": bool(stats.get("keyword_alert_count", 0)),
        "has_metadata_alerts": bool(stats.get("metadata_alert_count", 0)),
        "has_image_duplicates": bool(stats.get("image_duplicate_count", 0)),
    }


def _ai_output_files(result: dict[str, Any]) -> dict[str, Any]:
    output_files = result.get("output_files", {})
    return {
        "report_html": output_files.get("report_html", ""),
        "ai_summary_json": output_files.get("ai_summary_json", ""),
        "result_json": output_files.get("result_json", ""),
        "output_dir": output_files.get("output_dir", ""),
        "compare_pages": [
            {
                "group_a": page.get("group_a", ""),
                "group_b": page.get("group_b", ""),
                "path": page.get("path", ""),
                "file_name": page.get("file_name", ""),
                "match_count": page.get("match_count", 0),
                "excluded_count": page.get("excluded_count", 0),
            }
            for page in output_files.get("compare_pages", [])
        ],
    }


def _ai_pair_summaries(result: dict[str, Any]) -> list[dict[str, Any]]:
    compare_map = {
        (page.get("group_a"), page.get("group_b")): page
        for page in result.get("output_files", {}).get("compare_pages", [])
    }
    summaries = []
    for item in result.get("pair_summaries", []):
        page = compare_map.get((item.get("group_a"), item.get("group_b")), {})
        summaries.append(
            {
                "group_a": item.get("group_a", ""),
                "group_b": item.get("group_b", ""),
                "similar_match_count": item.get("match_count", 0),
                "excluded_match_count": item.get("excluded_count", 0),
                "max_similarity": item.get("max_similarity", 0),
                "avg_similarity": item.get("avg_similarity", 0),
                "compare_page": page.get("path", ""),
            }
        )
    return summaries


def _ai_match_samples(
    matches: list[dict[str, Any]],
    result: dict[str, Any],
    per_pair_limit: int,
    total_limit: int,
) -> dict[str, Any]:
    compare_map = {
        (page.get("group_a"), page.get("group_b")): page.get("path", "")
        for page in result.get("output_files", {}).get("compare_pages", [])
    }
    sorted_matches = sorted(matches, key=lambda item: (-float(item.get("similarity", 0) or 0), item.get("match_id", "")))
    pair_counts: dict[tuple[str, str], int] = {}
    samples: list[dict[str, Any]] = []
    omitted_by_pair: dict[str, int] = {}
    for match in sorted_matches:
        pair = (match.get("group_a", ""), match.get("group_b", ""))
        pair_label = f"{pair[0]} VS {pair[1]}"
        current_count = pair_counts.get(pair, 0)
        if len(samples) >= total_limit or current_count >= per_pair_limit:
            omitted_by_pair[pair_label] = omitted_by_pair.get(pair_label, 0) + 1
            continue
        pair_counts[pair] = current_count + 1
        samples.append(
            {
                "match_id": match.get("match_id", ""),
                "group_a": match.get("group_a", ""),
                "group_b": match.get("group_b", ""),
                "file_a": Path(match.get("file_a", "")).name,
                "file_b": Path(match.get("file_b", "")).name,
                "location_a": match.get("location_a", ""),
                "location_b": match.get("location_b", ""),
                "similarity": match.get("similarity", 0),
                "excluded": bool(match.get("excluded")),
                "exclude_reason": match.get("exclude_reason") or "",
                "text_a": _shorten_ai_text(match.get("text_a", "")),
                "text_b": _shorten_ai_text(match.get("text_b", "")),
                "compare_page": compare_map.get(pair, ""),
            }
        )
    return {
        "total_count": len(matches),
        "sample_count": len(samples),
        "omitted_count": max(0, len(matches) - len(samples)),
        "omitted_by_pair": omitted_by_pair,
        "samples": samples,
    }


def _ai_keyword_alerts(result: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for alert in result.get("keyword_alerts", []):
        hits = alert.get("hits", [])
        alerts.append(
            {
                "keyword": alert.get("keyword", ""),
                "is_regex": bool(alert.get("is_regex")),
                "pattern": alert.get("pattern", ""),
                "matched_text": alert.get("matched_text", ""),
                "groups": alert.get("groups", []),
                "hit_count": len(hits),
                "sample_hits": [
                    {
                        "group_name": hit.get("group_name", ""),
                        "file_name": hit.get("file_name", ""),
                        "location": hit.get("location", ""),
                        "matched_text": hit.get("matched_text", ""),
                        "snippet": _shorten_ai_text(hit.get("snippet", ""), 220),
                    }
                    for hit in hits[:10]
                ],
                "omitted_hit_count": max(0, len(hits) - 10),
            }
        )
    return alerts


def _ai_metadata_alerts(result: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = []
    for alert in result.get("metadata_alerts", []):
        hits = alert.get("hits", [])
        alerts.append(
            {
                "field": alert.get("field", ""),
                "label": alert.get("label", ""),
                "level": alert.get("level", ""),
                "value": alert.get("value", ""),
                "groups": alert.get("groups", []),
                "reason": alert.get("reason", ""),
                "hit_count": len(hits),
                "sample_hits": [
                    {
                        "group_name": hit.get("group_name", ""),
                        "file_name": hit.get("file_name", ""),
                        "value": hit.get("value", ""),
                    }
                    for hit in hits[:10]
                ],
                "omitted_hit_count": max(0, len(hits) - 10),
            }
        )
    return alerts


def _ai_image_duplicates(result: dict[str, Any]) -> dict[str, Any]:
    duplicates = result.get("image_duplicates", [])
    samples = []
    for duplicate in duplicates[:30]:
        samples.append(
            {
                "kind": duplicate.get("kind", ""),
                "distance": duplicate.get("distance", 0),
                "images": [
                    {
                        "group_name": image.get("group_name", ""),
                        "file_name": image.get("file_name", ""),
                        "image_id": image.get("image_id", ""),
                        "source": image.get("source", ""),
                    }
                    for image in duplicate.get("images", [])
                ],
            }
        )
    return {
        "total_count": len(duplicates),
        "sample_count": len(samples),
        "omitted_count": max(0, len(duplicates) - len(samples)),
        "samples": samples,
    }


def _shorten_ai_text(value: Any, limit: int = 320) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    head = max(1, limit // 2 - 8)
    tail = max(1, limit - head - 5)
    return text[:head] + " ... " + text[-tail:]


def render_report(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>文件查重报告</title>",
            f"<style>{_css()}</style>",
            "</head>",
            "<body>",
            _header(result),
            '<main class="page">',
            _stats(result),
            _run_summary(result),
            _options(result),
            _pair_summary(result),
            _keyword_section(result),
            _metadata_section(result),
            _image_section(result),
            _match_details(result),
            "</main>",
            f"<script>{_js()}</script>",
            "</body>",
            "</html>",
        ]
    )


def _header(result: dict[str, Any]) -> str:
    stats = result.get("stats", {})
    total = stats.get("similar_match_count", 0)
    return f"""
<header class="hero">
  <div>
    <h1>文件查重报告</h1>
    <p>生成时间：{escape(result.get("generated_at", ""))}</p>
  </div>
  <div class="hero-score">
    <strong>{total}</strong>
    <span>异常片段</span>
  </div>
</header>
"""


def _stats(result: dict[str, Any]) -> str:
    stats = result.get("stats", {})
    items = [
        ("投标组数", stats.get("group_count", 0)),
        ("投标文件", stats.get("document_count", 0)),
        ("可比片段", stats.get("comparable_unit_count", 0)),
        ("短文本过滤", stats.get("short_filtered_unit_count", 0)),
        ("异常片段", stats.get("similar_match_count", 0)),
        ("已排除片段", stats.get("excluded_match_count", 0)),
        ("关键词异常", stats.get("keyword_alert_count", 0)),
        ("元数据预警", stats.get("metadata_alert_count", 0)),
        ("图片重复", stats.get("image_duplicate_count", 0)),
    ]
    cards = "".join(f'<div class="stat"><b>{escape(str(value))}</b><span>{escape(label)}</span></div>' for label, value in items)
    return f'<section class="stats">{cards}</section>'


def _run_summary(result: dict[str, Any]) -> str:
    stats = result.get("stats", {})
    performance = result.get("performance", {})
    stage = performance.get("stage_seconds", {})
    output_files = result.get("output_files", {})
    rows = [
        ("总耗时", f"{performance.get('engine_seconds', 0)} 秒"),
        ("解析投标文件", f"{stage.get('parse_documents', 0)} 秒"),
        ("相似度计算", f"{stage.get('similarity', 0)} 秒"),
        ("元数据检测", f"{stage.get('metadata', 0)} 秒"),
        ("报告生成", f"{stage.get('report', 0)} 秒"),
        ("总览报告", output_files.get("report_html", "")),
        ("AI 精简结果", output_files.get("ai_summary_json", "")),
        ("完整 JSON", output_files.get("result_json", "")),
    ]
    body = "".join(f"<tr><th>{escape(str(name))}</th><td>{escape(str(value))}</td></tr>" for name, value in rows)
    return f"""
<section class="panel">
  <h2>运行与输出摘要</h2>
  <table class="meta-table"><tbody>{body}</tbody></table>
</section>
"""


def _options(result: dict[str, Any]) -> str:
    options = result.get("options", {})
    rows = [
        ("中文/混合短文本过滤", f"少于 {options.get('min_chars')} 个可见字符不参与相似度比对"),
        ("英文短文本过滤", f"少于 {options.get('min_words')} 个英文词不参与相似度比对"),
        ("文本相似阈值", options.get("similarity_threshold")),
        ("排除文件阈值", options.get("exclude_threshold")),
        ("强分段符号", options.get("sentence_delimiters")),
        ("长句辅助切分符号", options.get("soft_delimiters")),
        ("图片近似阈值", f"aHash 汉明距离 <= {options.get('image_ahash_distance')}"),
        ("相似度后端", options.get("similarity_backend")),
    ]
    body = "".join(f"<tr><th>{escape(str(name))}</th><td>{escape(str(value))}</td></tr>" for name, value in rows)
    return f"""
<section class="panel">
  <h2>检测参数</h2>
  <table class="meta-table"><tbody>{body}</tbody></table>
</section>
"""


def _pair_summary(result: dict[str, Any]) -> str:
    rows = []
    compare_links = {
        (page.get("group_a"), page.get("group_b")): page.get("file_name")
        for page in result.get("output_files", {}).get("compare_pages", [])
    }
    for index, item in enumerate(result.get("pair_summaries", []), start=1):
        pair_id = _pair_id(item["group_a"], item["group_b"])
        compare_file = compare_links.get((item["group_a"], item["group_b"]))
        compare_link = f" | <a href='{escape(str(compare_file))}'>左右对照</a>" if compare_file else ""
        rows.append(
            f"<tr data-active='{item.get('total_match_count', item['match_count'])}' "
            f"data-excluded='{item.get('total_excluded_count', item['excluded_count'])}' "
            f"data-max-sim='{float(item.get('max_similarity', 0) or 0):.4f}'>"
            f"<td>{index}</td>"
            f"<td>{escape(item['group_a'])}</td>"
            f"<td>{escape(item['group_b'])}</td>"
            f"<td class='num danger'>{item['match_count']}</td>"
            f"<td class='num muted'>{item['excluded_count']}</td>"
            f"<td class='num'>{_percent(item['max_similarity'])}</td>"
            f"<td class='num'>{_percent(item['avg_similarity'])}</td>"
            f"<td><a href='#{pair_id}'>查看明细</a>{compare_link}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='8' class='empty'>未发现超过阈值的跨组相似片段。</td></tr>"
    return f"""
<section class="panel">
  <div class="panel-title">
    <h2>两两比对总览</h2>
    <div class="filters">
      <input id="pairFilter" type="search" placeholder="搜索公司/分组">
      <input id="minSimFilter" type="number" min="0" max="100" step="1" placeholder="最低%">
      <input id="maxSimFilter" type="number" min="0" max="100" step="1" placeholder="最高%">
      <label class="toggle"><input type="checkbox" id="pairIncludeExcluded"> 总览包含仅已排除</label>
      <label class="toggle"><input type="checkbox" id="showExcluded"> 明细显示已排除</label>
    </div>
  </div>
  <table id="pairSummaryTable">
    <thead><tr><th>序号</th><th>组1</th><th>组2</th><th>异常片段</th><th>已排除片段</th><th>最高相似度</th><th>平均相似度</th><th>操作</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</section>
"""


def _keyword_section(result: dict[str, Any]) -> str:
    alerts = result.get("keyword_alerts", [])
    rows = []
    for index, alert in enumerate(alerts, start=1):
        hits = alert.get("hits", [])
        samples = "<br>".join(
            f"{escape(hit.get('group_name', ''))} / {escape(hit.get('file_name', ''))}: {escape(hit.get('snippet', ''))}"
            for hit in hits[:5]
        )
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{escape(alert.get('keyword', ''))}</td>"
            f"<td>{'正则' if alert.get('is_regex') else '关键词'}</td>"
            f"<td class='snippet'>{escape(alert.get('matched_text', ''))}</td>"
            f"<td>{escape(', '.join(alert.get('groups', [])))}</td>"
            f"<td>{len(hits)}</td>"
            f"<td class='snippet'>{samples}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='7' class='empty'>未发现跨 2 组以上的重要关键词或正则同值异常。</td></tr>"
    errors = result.get("keyword_errors") or []
    error_html = ""
    if errors:
        error_html = "<p class='warn'>正则错误：" + "；".join(escape(error) for error in errors) + "</p>"
    return f"""
<section class="panel">
  <h2>重要关键词与正则异常</h2>
  <p class="muted">普通关键词跨组出现即预警；正则规则仅在同一个实际匹配内容跨 2 个及以上分组出现时预警。</p>
  {error_html}
  <table>
    <thead><tr><th>序号</th><th>规则</th><th>类型</th><th>重复内容</th><th>命中组</th><th>命中数</th><th>样例</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</section>
"""


def _metadata_section(result: dict[str, Any]) -> str:
    rows = []
    for index, alert in enumerate(result.get("metadata_alerts", []), start=1):
        hits = alert.get("hits", [])
        documents = "<br>".join(
            f"{escape(hit.get('group_name', ''))} / {escape(hit.get('file_name', ''))}: {escape(hit.get('value', ''))}"
            for hit in hits[:8]
        )
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td><strong>{escape(alert.get('level', ''))}</strong></td>"
            f"<td>{escape(alert.get('label', ''))}</td>"
            f"<td class='snippet'>{escape(alert.get('value', ''))}</td>"
            f"<td>{escape(', '.join(alert.get('groups', [])))}</td>"
            f"<td class='snippet'>{documents}</td>"
            f"<td>{escape(alert.get('reason', ''))}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='7' class='empty'>未发现跨组文档元数据碰撞。</td></tr>"
    return f"""
<section class="panel">
  <h2>文档元数据碰撞预警</h2>
  <p class="muted">比较不同分组文档的作者、公司、最后修改者及文档内部创建/修改时间；通用 Office/WPS 默认值会被忽略。此项仅用于风险提示，需结合正文和原始文件人工复核。</p>
  <table>
    <thead><tr><th>序号</th><th>风险</th><th>字段</th><th>碰撞值</th><th>涉及组</th><th>文档</th><th>说明</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</section>
"""


def _image_section(result: dict[str, Any]) -> str:
    rows = []
    for index, duplicate in enumerate(result.get("image_duplicates", []), start=1):
        images = duplicate.get("images", [])
        detail = "<br>".join(
            f"{escape(image.get('group_name', ''))} / {escape(image.get('file_name', ''))} / {escape(image.get('image_id', ''))}"
            for image in images
        )
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{escape(duplicate.get('kind', ''))}</td>"
            f"<td>{duplicate.get('distance', 0)}</td>"
            f"<td>{detail}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='4' class='empty'>未发现跨组重复图片。</td></tr>"
    return f"""
<section class="panel">
  <h2>图片重复</h2>
  <table>
    <thead><tr><th>序号</th><th>类型</th><th>距离</th><th>图片位置</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</section>
"""


def _match_details(result: dict[str, Any]) -> str:
    matches = result.get("matches", [])
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for match in matches:
        by_pair.setdefault((match["group_a"], match["group_b"]), []).append(match)
    sections = []
    for summary in result.get("pair_summaries", []):
        pair = (summary["group_a"], summary["group_b"])
        pair_matches = by_pair.get(pair, [])
        sections.append(
            f"<section class='panel detail' id='{_pair_id(*pair)}'>"
            f"<h2>{escape(pair[0])} VS {escape(pair[1])}</h2>"
            + _match_cards(pair_matches)
            + "</section>"
        )
    return "\n".join(sections)


def _match_cards(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return "<p class='empty'>该组组合未发现相似片段。</p>"
    cards = []
    for match in matches:
        left, right = highlight_common(match.get("text_a", ""), match.get("text_b", ""))
        excluded_class = " excluded" if match.get("excluded") else ""
        reason = f"<p class='reason'>{escape(match.get('exclude_reason') or '')}</p>" if match.get("excluded") else ""
        status_badge = "<em>已排除</em>" if match.get("excluded") else '<em class="risk">异常</em>'
        cards.append(
            f"<article class='match-card{excluded_class}'>"
            "<div class='match-head'>"
            f"<span>{escape(match.get('match_id', ''))}</span>"
            f"<b>{_percent(match.get('similarity', 0))}</b>"
            f"{status_badge}"
            "</div>"
            f"{reason}"
            "<div class='compare'>"
            "<div>"
            f"<h3>{escape(Path(match.get('file_a', '')).name)} · {escape(match.get('location_a', ''))}</h3>"
            f"<p>{left}</p>"
            "</div>"
            "<div>"
            f"<h3>{escape(Path(match.get('file_b', '')).name)} · {escape(match.get('location_b', ''))}</h3>"
            f"<p>{right}</p>"
            "</div>"
            "</div>"
            "</article>"
        )
    return "\n".join(cards)


def _write_compare_pages(result: dict[str, Any], output: Path) -> list[dict[str, Any]]:
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for match in result.get("matches", []):
        by_pair.setdefault((match["group_a"], match["group_b"]), []).append(match)

    pages: list[dict[str, Any]] = []
    used_names: set[str] = set()
    for summary in result.get("pair_summaries", []):
        pair = (summary["group_a"], summary["group_b"])
        pair_matches = by_pair.get(pair, [])
        if not pair_matches:
            continue
        file_name = _unique_compare_filename(pair[0], pair[1], used_names)
        page_path = output / file_name
        page_path.write_text(render_compare_page(result, pair[0], pair[1], pair_matches), encoding="utf-8")
        pages.append(
            {
                "group_a": pair[0],
                "group_b": pair[1],
                "file_name": file_name,
                "path": str(page_path),
                "match_count": sum(1 for match in pair_matches if not match.get("excluded")),
                "excluded_count": sum(1 for match in pair_matches if match.get("excluded")),
            }
        )
    return pages


def render_compare_page(result: dict[str, Any], group_a: str, group_b: str, matches: list[dict[str, Any]]) -> str:
    documents = result.get("documents", [])
    left_docs = [doc for doc in documents if doc.get("group_name") == group_a]
    right_docs = [doc for doc in documents if doc.get("group_name") == group_b]
    left_annotations, right_annotations = _compare_annotations(matches)
    title = f"{group_a} VS {group_b}"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(title)} 左右对照</title>",
            f"<style>{_compare_css()}</style>",
            "</head>",
            "<body>",
            "<header class='compare-top'>",
            "<div>",
            f"<h1>{escape(title)}</h1>",
            f"<p>异常相似 {sum(1 for match in matches if not match.get('excluded'))} 处，已排除 {sum(1 for match in matches if match.get('excluded'))} 处</p>",
            "</div>",
            "<a href='report.html'>返回总报告</a>",
            "</header>",
            "<main class='compare-layout'>",
            _compare_side("left", group_a, left_docs, left_annotations),
            _compare_side("right", group_b, right_docs, right_annotations),
            "</main>",
            f"<script>{_compare_js()}</script>",
            "</body>",
            "</html>",
        ]
    )


def _compare_annotations(matches: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    left: dict[str, list[dict[str, Any]]] = {}
    right: dict[str, list[dict[str, Any]]] = {}
    for match in matches:
        left_ref = {
            "target_id": f"right-{match.get('unit_id_b')}",
            "similarity": float(match.get("similarity", 0) or 0),
            "excluded": bool(match.get("excluded")),
            "match_id": match.get("match_id", ""),
        }
        right_ref = {
            "target_id": f"left-{match.get('unit_id_a')}",
            "similarity": float(match.get("similarity", 0) or 0),
            "excluded": bool(match.get("excluded")),
            "match_id": match.get("match_id", ""),
        }
        left.setdefault(str(match.get("unit_id_a")), []).append(left_ref)
        right.setdefault(str(match.get("unit_id_b")), []).append(right_ref)
    return left, right


def _compare_side(side: str, group_name: str, documents: list[dict[str, Any]], annotations: dict[str, list[dict[str, Any]]]) -> str:
    all_units = [unit for doc in documents for unit in doc.get("units", [])]
    unit_positions = {unit.get("unit_id"): index for index, unit in enumerate(all_units)}
    markers = _compare_markers(side, all_units, unit_positions, annotations)
    docs_html = []
    for doc in documents:
        units = doc.get("units", [])
        unit_html = "".join(_compare_unit(side, unit, annotations.get(unit.get("unit_id"), [])) for unit in units)
        empty_unit_html = '<p class="empty-unit">无可展示文本</p>'
        docs_html.append(
            "<article class='file-block'>"
            f"<h3>{escape(doc.get('file_name', ''))}</h3>"
            f"{unit_html or empty_unit_html}"
            "</article>"
        )
    return (
        f"<section class='compare-side {side}' data-side='{side}'>"
        "<div class='side-toolbar'>"
        f"<h2>{escape(group_name)}</h2>"
        "<div class='nav-buttons'>"
        f"<button type='button' data-nav='prev' data-side='{side}'>上一个高亮</button>"
        f"<button type='button' data-nav='next' data-side='{side}'>下一个高亮</button>"
        f"<label><input type='checkbox' data-include-excluded='{side}'> 包含已排除</label>"
        "</div>"
        "</div>"
        "<div class='scroll-shell'>"
        f"<div class='marker-rail' aria-hidden='true'>{markers}</div>"
        f"<div class='doc-stream' id='stream-{side}'>"
        f"{''.join(docs_html)}"
        "</div>"
        "</div>"
        "</section>"
    )


def _compare_unit(side: str, unit: dict[str, Any], refs: list[dict[str, Any]]) -> str:
    unit_id = str(unit.get("unit_id", ""))
    dom_id = f"{side}-{unit_id}"
    text = escape(str(unit.get("text", "")))
    location = escape(str(unit.get("location", "")))
    comparable_class = "" if unit.get("comparable") else " short-unit"
    if not refs:
        return f"<p id='{dom_id}' class='unit{comparable_class}'><span class='loc'>{location}</span>{text}</p>"

    refs = sorted(refs, key=lambda item: (item["excluded"], -item["similarity"], item["target_id"]))
    active_refs = [ref for ref in refs if not ref["excluded"]]
    all_excluded = not active_refs
    score = max(ref["similarity"] for ref in refs)
    alpha = _similarity_alpha(score, all_excluded)
    targets = ",".join(escape(ref["target_id"]) for ref in refs)
    match_ids = "、".join(escape(str(ref["match_id"])) for ref in refs)
    badge = f"<span class='hit-badge'>{len(refs)}</span>" if len(refs) > 1 else ""
    excluded_label = "<span class='excluded-label'>已排除</span>" if all_excluded else ""
    return (
        f"<p id='{dom_id}' class='unit hit {'hit-excluded' if all_excluded else 'hit-active'}{comparable_class}' "
        f"data-side='{side}' data-unit-id='{escape(unit_id)}' data-targets='{targets}' data-cycle='0' data-excluded='{'1' if all_excluded else '0'}' "
        f"style='--alpha:{alpha:.3f}; --edge:{min(0.95, alpha + 0.25):.3f}' title='{match_ids}'>"
        f"<span class='loc'>{location}</span>{badge}{excluded_label}<span class='score'>{_percent(score)}</span>{text}"
        "</p>"
    )


def _compare_markers(
    side: str,
    units: list[dict[str, Any]],
    positions: dict[Any, int],
    annotations: dict[str, list[dict[str, Any]]],
) -> str:
    total = max(1, len(units) - 1)
    markers = []
    for unit_id, refs in annotations.items():
        if unit_id not in positions:
            continue
        score = max(float(ref["similarity"]) for ref in refs)
        all_excluded = all(bool(ref["excluded"]) for ref in refs)
        top = 0 if total == 0 else positions[unit_id] / total * 100
        alpha = _similarity_alpha(score, all_excluded)
        markers.append(
            f"<button type='button' class='marker {'marker-excluded' if all_excluded else 'marker-active'}' "
            f"data-target='{side}-{escape(unit_id)}' style='top:{top:.2f}%; --alpha:{alpha:.3f}' title='{_percent(score)}'></button>"
        )
    return "".join(markers)


def _similarity_alpha(score: float, excluded: bool) -> float:
    score = max(0.0, min(1.0, score))
    if excluded:
        return 0.14 + score * 0.16
    return 0.18 + score * 0.36


def _unique_compare_filename(group_a: str, group_b: str, used: set[str]) -> str:
    base = _safe_filename(f"compare_{group_a}__{group_b}")[:120] or "compare"
    name = base + ".html"
    counter = 2
    while name in used:
        name = f"{base}_{counter}.html"
        counter += 1
    used.add(name)
    return name


def _safe_filename(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value.strip())
    safe = "_".join(part for part in safe.split("_") if part)
    return safe


def _compare_css() -> str:
    return """
:root { color-scheme: light; --bg:#f5f7fb; --panel:#fff; --text:#1d2433; --muted:#697386; --line:#d8dee9; --active:#d92d20; --excluded:#667085; }
* { box-sizing:border-box; }
body { margin:0; font:14px/1.65 "Microsoft YaHei", "Segoe UI", Arial, sans-serif; color:var(--text); background:var(--bg); overflow:hidden; }
.compare-top { height:76px; display:flex; justify-content:space-between; align-items:center; gap:20px; padding:12px 20px; background:#133b5c; color:white; }
.compare-top h1 { margin:0; font-size:20px; letter-spacing:0; }
.compare-top p { margin:2px 0 0; color:#dbe7f4; }
.compare-top a { color:white; border:1px solid rgba(255,255,255,.42); border-radius:6px; padding:6px 12px; text-decoration:none; }
.compare-layout { display:grid; grid-template-columns:1fr 1fr; gap:12px; height:calc(100vh - 76px); padding:12px; }
.compare-side { min-width:0; display:flex; flex-direction:column; background:var(--panel); border:1px solid var(--line); border-radius:8px; overflow:hidden; }
.side-toolbar { min-height:58px; display:flex; justify-content:space-between; align-items:center; gap:12px; padding:10px 12px; border-bottom:1px solid var(--line); background:#f7f9fc; }
.side-toolbar h2 { margin:0; font-size:16px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.nav-buttons { display:flex; align-items:center; gap:6px; flex-wrap:wrap; justify-content:flex-end; }
button { font:inherit; border:1px solid #b8c2d1; background:white; border-radius:6px; padding:4px 9px; cursor:pointer; }
button:hover { border-color:#7c8da6; background:#f8fafc; }
label { color:var(--muted); user-select:none; white-space:nowrap; }
.scroll-shell { position:relative; flex:1; min-height:0; display:flex; }
.marker-rail { position:relative; flex:0 0 16px; margin:10px 0 10px 8px; border-radius:999px; background:#eef2f7; border:1px solid #d9e1ec; }
.marker { position:absolute; left:2px; width:10px; height:7px; margin-top:-3px; border:0; border-radius:999px; padding:0; opacity:.95; }
.marker-active { background:rgba(217,45,32,var(--alpha)); }
.marker-excluded { background:rgba(102,112,133,var(--alpha)); }
.doc-stream { flex:1; min-width:0; overflow-y:auto; padding:12px 14px 32px; scroll-behavior:smooth; }
.file-block { border:1px solid var(--line); border-radius:8px; margin:0 0 12px; overflow:hidden; background:white; }
.file-block h3 { margin:0; padding:8px 10px; font-size:13px; color:#3a4557; background:#f0f3f8; border-bottom:1px solid var(--line); }
.unit { position:relative; margin:0; padding:9px 10px 9px 82px; border-bottom:1px solid #edf1f6; white-space:pre-wrap; word-break:break-word; transition:box-shadow .18s, outline-color .18s; }
.unit:last-child { border-bottom:0; }
.unit.short-unit { color:#6b7280; }
.loc { position:absolute; left:10px; top:9px; width:58px; color:#8a94a6; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.hit { cursor:pointer; border-left:4px solid rgba(217,45,32,var(--edge)); }
.hit-active { background:rgba(217,45,32,var(--alpha)); }
.hit-excluded { background:rgba(102,112,133,var(--alpha)); border-left-color:rgba(102,112,133,var(--edge)); }
.hit-badge, .score, .excluded-label { display:inline-block; margin-right:6px; padding:0 6px; border-radius:999px; font-size:12px; line-height:1.6; background:rgba(255,255,255,.72); color:#344054; }
.score { color:#7a271a; }
.hit-excluded .score { color:#344054; }
.excluded-label { color:#475467; }
.flash { outline:3px solid #1570ef; outline-offset:-3px; box-shadow:0 0 0 4px rgba(21,112,239,.18) inset; }
.empty-unit { margin:0; padding:14px; color:var(--muted); }
@media (max-width: 920px) {
  body { overflow:auto; }
  .compare-layout { grid-template-columns:1fr; height:auto; }
  .compare-side { height:70vh; }
}
@media print {
  body { overflow:auto; background:white; }
  .compare-top { position:static; color:#111; background:white; border-bottom:1px solid var(--line); }
  .compare-top a, .nav-buttons, .marker-rail { display:none; }
  .compare-layout { display:block; height:auto; }
  .compare-side { margin-bottom:14px; break-inside:avoid; }
  .doc-stream { overflow:visible; }
}
"""


def _compare_js() -> str:
    return """
const navState = { left: -1, right: -1 };

function streamFor(side) {
  return document.getElementById('stream-' + side);
}

function scrollToElement(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const stream = el.closest('.doc-stream');
  if (!stream) return;
  const er = el.getBoundingClientRect();
  const sr = stream.getBoundingClientRect();
  const top = stream.scrollTop + (er.top - sr.top) - (stream.clientHeight / 2) + (el.offsetHeight / 2);
  stream.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
  el.classList.remove('flash');
  void el.offsetWidth;
  el.classList.add('flash');
  window.setTimeout(() => el.classList.remove('flash'), 950);
}

function hitElements(side, includeExcluded) {
  const stream = streamFor(side);
  if (!stream) return [];
  const selector = includeExcluded ? '.hit' : '.hit:not(.hit-excluded)';
  return Array.from(stream.querySelectorAll(selector));
}

function setNavStateFromId(side, id) {
  const include = document.querySelector(`[data-include-excluded="${side}"]`)?.checked || false;
  const hits = hitElements(side, include);
  const idx = hits.findIndex((el) => el.id === id);
  if (idx >= 0) navState[side] = idx;
}

document.addEventListener('click', (event) => {
  const marker = event.target.closest('.marker');
  if (marker) {
    const target = marker.dataset.target;
    if (target) {
      scrollToElement(target);
      setNavStateFromId(target.startsWith('left-') ? 'left' : 'right', target);
    }
    return;
  }

  const nav = event.target.closest('[data-nav]');
  if (nav) {
    const side = nav.dataset.side;
    const include = document.querySelector(`[data-include-excluded="${side}"]`)?.checked || false;
    const hits = hitElements(side, include);
    if (!hits.length) return;
    const delta = nav.dataset.nav === 'prev' ? -1 : 1;
    navState[side] = (navState[side] + delta + hits.length) % hits.length;
    scrollToElement(hits[navState[side]].id);
    return;
  }

  const hit = event.target.closest('.hit');
  if (!hit) return;
  const targets = (hit.dataset.targets || '').split(',').filter(Boolean);
  if (!targets.length) return;
  const index = Number(hit.dataset.cycle || '0') % targets.length;
  hit.dataset.cycle = String(index + 1);
  scrollToElement(targets[index]);
  setNavStateFromId(hit.dataset.side || '', hit.id);
});

document.addEventListener('change', (event) => {
  const checkbox = event.target.closest('[data-include-excluded]');
  if (checkbox) {
    navState[checkbox.dataset.includeExcluded] = -1;
  }
});
"""


def _pair_id(left: str, right: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in f"{left}-{right}")
    return "pair-" + safe.strip("-")


def _percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _css() -> str:
    return """
:root { color-scheme: light; --bg:#f5f7fb; --panel:#fff; --text:#1d2433; --muted:#697386; --line:#d8dee9; --accent:#0f8f72; --danger:#c92a2a; --mark:#fff3a3; }
* { box-sizing: border-box; }
body { margin:0; font:14px/1.6 "Microsoft YaHei", "Segoe UI", Arial, sans-serif; color:var(--text); background:var(--bg); }
.hero { display:flex; justify-content:space-between; align-items:center; padding:28px 36px; background:#133b5c; color:white; }
.hero h1 { margin:0 0 4px; font-size:28px; letter-spacing:0; }
.hero p { margin:0; color:#dbe7f4; }
.hero-score { min-width:150px; padding:12px 18px; border:1px solid rgba(255,255,255,.24); border-radius:8px; text-align:center; }
.hero-score strong { display:block; font-size:34px; line-height:1.1; }
.hero-score span { color:#dbe7f4; }
.page { width:min(1240px, calc(100% - 32px)); margin:20px auto 48px; }
.stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:16px; }
.stat { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }
.stat b { display:block; font-size:22px; }
.stat span { color:var(--muted); }
.panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; margin-bottom:16px; box-shadow:0 1px 2px rgba(20, 30, 50, .04); }
.panel-title { display:flex; justify-content:space-between; gap:16px; align-items:center; }
.filters { display:flex; align-items:center; gap:12px; flex-wrap:wrap; justify-content:flex-end; }
.filters input[type=search] { border:1px solid var(--line); border-radius:6px; padding:6px 8px; min-width:180px; }
.filters input[type=number] { border:1px solid var(--line); border-radius:6px; padding:6px 8px; width:82px; }
h2 { margin:0 0 12px; font-size:18px; }
h3 { margin:0 0 8px; font-size:13px; color:var(--muted); }
table { width:100%; border-collapse:collapse; table-layout:fixed; }
th, td { border:1px solid var(--line); padding:9px 10px; vertical-align:top; word-break:break-word; }
th { background:#f0f3f8; color:#3a4557; }
.meta-table th { width:240px; text-align:left; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
.danger { color:var(--danger); font-weight:700; }
.muted { color:var(--muted); }
.empty { color:var(--muted); text-align:center; padding:24px; }
.warn { color:var(--danger); }
a { color:#0969da; text-decoration:none; }
a:hover { text-decoration:underline; }
.toggle { color:var(--muted); user-select:none; }
.match-card { border:1px solid var(--line); border-radius:8px; margin:12px 0; overflow:hidden; }
.match-card.excluded { display:none; opacity:.72; }
body.show-excluded .match-card.excluded { display:block; }
.match-head { display:flex; align-items:center; gap:12px; padding:10px 12px; background:#f6f8fb; border-bottom:1px solid var(--line); }
.match-head b { margin-left:auto; color:var(--danger); }
.match-head em { font-style:normal; color:white; background:var(--muted); border-radius:999px; padding:2px 8px; }
.match-head em.risk { background:var(--danger); }
.reason { margin:10px 12px 0; color:var(--muted); }
.compare { display:grid; grid-template-columns:1fr 1fr; gap:0; }
.compare > div { padding:12px; min-width:0; }
.compare > div:first-child { border-right:1px solid var(--line); }
.compare p { margin:0; white-space:pre-wrap; }
mark { background:var(--mark); color:#8a4b00; padding:0 1px; }
.snippet { font-size:13px; }
@media (max-width: 900px) {
  .stats { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .hero { display:block; }
  .hero-score { margin-top:14px; }
  .compare { grid-template-columns:1fr; }
  .compare > div:first-child { border-right:0; border-bottom:1px solid var(--line); }
}
@media print {
  body { background:white; }
  .panel, .stat { box-shadow:none; break-inside:avoid; }
  .toggle { display:none; }
}
"""


def _js() -> str:
    return """
document.getElementById('showExcluded')?.addEventListener('change', function () {
  document.body.classList.toggle('show-excluded', this.checked);
});

function applyPairFilters() {
  const needle = document.getElementById('pairFilter')?.value.trim().toLowerCase() || '';
  const includeExcluded = document.getElementById('pairIncludeExcluded')?.checked || false;
  const minValue = Number(document.getElementById('minSimFilter')?.value || '');
  const maxValue = Number(document.getElementById('maxSimFilter')?.value || '');
  const hasMin = !Number.isNaN(minValue) && document.getElementById('minSimFilter')?.value !== '';
  const hasMax = !Number.isNaN(maxValue) && document.getElementById('maxSimFilter')?.value !== '';
  document.querySelectorAll('#pairSummaryTable tbody tr').forEach((row) => {
    const active = Number(row.dataset.active || '0');
    const excluded = Number(row.dataset.excluded || '0');
    const maxSim = Number(row.dataset.maxSim || '0') * 100;
    let visible = true;
    if (needle && !row.textContent.toLowerCase().includes(needle)) visible = false;
    if (!includeExcluded && active <= 0) visible = false;
    if (includeExcluded && active <= 0 && excluded <= 0) visible = false;
    if (hasMin && maxSim < minValue) visible = false;
    if (hasMax && maxSim > maxValue) visible = false;
    row.style.display = visible ? '' : 'none';
  });
}

['pairFilter', 'pairIncludeExcluded', 'minSimFilter', 'maxSimFilter'].forEach((id) => {
  const el = document.getElementById(id);
  if (el) {
    el.addEventListener('input', applyPairFilters);
    el.addEventListener('change', applyPairFilters);
  }
});
applyPairFilters();
"""
