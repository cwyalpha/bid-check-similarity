# 配置 JSON 参考

最小示例：

```json
{
  "groups": [
    {"name": "A公司", "files": ["D:/cases/A/投标文件.docx"]},
    {"name": "B公司", "files": ["D:/cases/B/投标文件.md"]}
  ],
  "exclude_files": ["D:/cases/招标文件.docx"],
  "keywords": ["某某科技有限公司", "re:1[3-9]\\d{9}"],
  "options": {
    "min_chars": 20,
    "min_words": 8,
    "similarity_threshold": 0.78,
    "exclude_threshold": 0.86,
    "sentence_delimiters": "。！？!?；;",
    "soft_delimiters": "，,、：:",
    "max_matches_per_pair": 600,
    "max_excluded_matches_per_pair": 200,
    "max_targets_per_unit": 20,
    "write_all_matches": false,
    "candidate_shared_ratio": 0.12,
    "exclude_candidates_per_unit": 80,
    "min_length_ratio": 0.55,
    "similarity_backend": "local_ngrams",
    "image_ahash_distance": 6,
    "legacy_conversion_timeout": 120,
    "soffice_path": ""
  }
}
```

字段说明：

- `groups`: 必填，至少 2 组；每组代表一家投标单位，可包含多个文件。
- `exclude_files`: 可选，招标文件、模板、统一格式要求等允许复用内容。
- `keywords`: 可选，普通文本按字面量匹配，`re:` 前缀按正则匹配。
- `min_chars`: 中文/混合短文本过滤阈值，低于该长度不参与文本相似度比对。
- `min_words`: 英文短文本过滤阈值，低于该词数不参与文本相似度比对。
- `similarity_threshold`: 跨组文本相似阈值，默认 `0.78`。
- `exclude_threshold`: 排除文件匹配阈值，默认 `0.86`。
- `sentence_delimiters`: 强分段符号。
- `soft_delimiters`: 长句辅助切分符号。
- `max_matches_per_pair`: 每个组对默认展示的异常相似片段上限，默认 `600`。
- `max_excluded_matches_per_pair`: 每个组对默认展示的已排除相似片段上限，默认 `200`。
- `max_targets_per_unit`: 单个文本片段最多保留多少个对侧相似目标，默认 `20`。
- `write_all_matches`: 是否额外写出全量 `all_matches.jsonl`，默认 `false`。
- `candidate_shared_ratio`: 候选召回所需共享 ngram 比例，默认 `0.12`。
- `exclude_candidates_per_unit`: 每个片段用于排除文件匹配的候选上限，默认 `80`。
- `min_length_ratio`: 两段文本长度比例预过滤，默认 `0.55`。
- `similarity_backend`: 相似度后端，当前只支持 `local_ngrams`；`embedding` 仅预留，尚未启用。
- `image_ahash_distance`: 图片近似重复 aHash 汉明距离。
- `legacy_conversion_timeout`: `.doc/.wps` 转换超时时间，单位秒。
- `soffice_path`: 可选，手动指定 LibreOffice `soffice` 可执行文件路径。

运行说明：

- 如果命令未指定 `--output`，报告默认写入当前工作目录下的 `outputs/run_时间戳`。
- 在 opencode 等 agent 中使用时，建议在项目根目录运行 CLI，这样报告会留在该项目文件夹内。
- 默认 `result.json` 只保存报告展示用的代表性 matches；统计里会保留总数、展示数和截断数。
- 如需全量相似明细，设置 `write_all_matches=true`，输出目录会额外生成 `all_matches.jsonl`。
