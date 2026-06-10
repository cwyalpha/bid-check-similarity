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
- `image_ahash_distance`: 图片近似重复 aHash 汉明距离。
- `legacy_conversion_timeout`: `.doc/.wps` 转换超时时间，单位秒。
- `soffice_path`: 可选，手动指定 LibreOffice `soffice` 可执行文件路径。

运行说明：

- 如果命令未指定 `--output`，报告默认写入当前工作目录下的 `outputs/run_时间戳`。
- 在 opencode 等 agent 中使用时，建议在项目根目录运行 CLI，这样报告会留在该项目文件夹内。
