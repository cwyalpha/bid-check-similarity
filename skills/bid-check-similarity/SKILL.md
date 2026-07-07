---
name: bid-check-similarity
description: 离线标书和文件查重 Skill，支持按公司/投标单位分组比对 .docx/.doc/.wps/.md/.txt 文件。适用于需要检测投标文件相似文本、排除招标文件或模板内容、发现跨组关键词/正则异常，并在 Windows、macOS 或 Linux 上生成本地 HTML/JSON 报告的场景。
---

# bid-check-similarity

使用本 Skill 调用本地 `checksim` 引擎进行标书或通用文件查重。引擎完全离线运行：解析分组文档、过滤短文本后做相似度比对、应用可选排除文件、检测共享关键词/正则、检查重复图片，并输出 `report.html`、`ai_summary.json`、`result.json` 和按组对生成的 `compare_*.html`。完整结果默认全量写入 `result.json` 和 HTML 报告。

## 工作流程

1. 确认或推断输入分组。每组代表一家投标单位，可包含一个或多个 `.docx`、`.doc`、`.wps`、`.md`、`.txt` 文件。
2. 根据需要添加排除文件，例如招标文件、模板文件、统一格式要求等允许共享的内容。
3. 根据需要添加重要关键词或正则规则。正则规则必须以 `re:` 开头。
4. 生成 JSON 配置。字段结构和默认参数见本文“配置 JSON 参考”。
5. 调用内置 CLI。若用户未指定输出目录，优先在当前项目目录运行命令，让默认结果写入当前目录下的 `outputs/run_时间戳`：

```bash
python path/to/skill/scripts/run_check.py --config case.json --output outputs/run_001
```

6. 检测完成后先读取 `ai_summary.json`，再回复生成的 `report.html` 路径，并概述异常相似片段、已排除片段、关键词异常和旧格式转换限制。

## Agent 参数设置建议

- 如果用户给的是“一个上级目录，下面每个子目录是一家公司”，把每个直接子目录作为一个 `groups` 项，并递归收集支持文件。
- 如果用户一次给了多个投标文件，且明显一个文件对应一家公司，可以每个文件自动作为一个 `groups` 项；组名优先用文件名或父目录名。
- 如果用户给了招标文件、采购需求、模板、评分办法、统一格式要求，优先放入 `exclude_files`，避免共同引用招标内容被误判为异常。
- `min_chars` 默认 `10`；若目录、标题、编号噪声很多，可建议用户提高到 `15` 或 `20`。
- `similarity_threshold` 默认 `0.78`；想发现轻微改写可降到 `0.72` 到 `0.76`，想更严格可升到 `0.82` 以上。
- `exclude_threshold` 默认 `0.86`；通常应高于 `similarity_threshold`，避免过度排除。
- `sentence_delimiters` 默认 `。！？!?；;`；如文件中大量条款用冒号或换行表达，可询问用户是否追加 `：:`。
- 关键词建议由 Agent 主动整理：每家投标单位名称、简称、法人/负责人、项目经理、技术负责人、投标文件中出现的人员姓名、手机号、邮箱、统一社会信用代码、供应商专有产品名、售后机构名称等。
- 如果关键词可能有空格、括号或不同写法，优先使用 `re:` 正则。例如公司简称可写成 `re:晨星(信息|科技)?`，手机号可写成 `re:1[3-9]\d{9}`。
- 关键词命中规则是：同一关键词/正则出现在 2 个及以上公司/分组中，即视为异常；短文本过滤不会影响关键词检测。

## 平台说明

- 本 Skill 自带 `scripts/vendor/checksim` 核心代码副本；运行 `scripts/run_check.py` 时只使用 Skill 目录内文件，不依赖仓库根目录。
- `.docx`、`.md` 和 `.txt` 在 Windows、macOS 与 Linux 上直接解析；`.txt` 按纯文本处理，不做 Markdown 去格式。
- `.doc/.wps` 会先转换为临时 `.docx` 再解析，原始文件不会被修改。
- Windows 下按 WPS、Microsoft Office、LibreOffice 顺序尝试转换。
- macOS/Linux 下旧格式转换依赖 LibreOffice `soffice`。
- 如果旧格式转换不可用，明确报告错误，并提示用户安装 LibreOffice 或先手动另存为 `.docx`。
- 新 Python 环境需要先安装 `scripts/requirements.txt` 中的依赖。

## 输出要求

- `report.html`：离线总览报告，CSS/JS 内嵌。
- `ai_summary.json`：给 AI/Agent 优先阅读的精简结果，包含统计、输出路径、组对摘要、代表性相似片段、关键词异常样例和图片重复样例。
- `compare_*.html`：两组文件左右对照页，支持高亮文本双向跳转。
- `result.json`：完整结构化结果，保存全量相似片段和统计，可能很长；只有需要追溯全部文本单元或全部匹配时再读取。

Agent 回复用户时，建议先读取 `ai_summary.json` 判断是否存在疑似重复，再把 `report.html` 和相关 `compare_*.html` 路径给用户。`ai_summary.json` 的 `evidence.similar_text.samples` 是异常相似片段样例，`evidence.excluded_text.samples` 是被排除文件解释覆盖的相似片段样例，`evidence.keyword_alerts` 是跨 2 组以上命中的关键词/正则异常。

## 配置 JSON 参考

最小示例：

```json
{
  "groups": [
    {"name": "A公司", "files": ["/project/cases/A/投标文件.docx"]},
    {"name": "B公司", "files": ["/project/cases/B/投标文件.md", "/project/cases/B/补充说明.txt"]}
  ],
  "exclude_files": ["/project/cases/招标文件.docx"],
  "keywords": ["某某科技有限公司", "re:1[3-9]\\d{9}"],
  "options": {
    "min_chars": 10,
    "min_words": 8,
    "similarity_threshold": 0.78,
    "exclude_threshold": 0.86,
    "sentence_delimiters": "。！？!?；;",
    "soft_delimiters": "，,、：:",
    "similarity_backend": "local_ngrams",
    "image_ahash_distance": 6,
    "legacy_conversion_timeout": 120,
    "soffice_path": ""
  }
}
```

字段说明：

- `groups`: 必填，至少 2 组；每组代表一家投标单位，可包含多个 `.docx/.doc/.wps/.md/.txt` 文件。
- `exclude_files`: 可选，招标文件、模板、统一格式要求等允许复用内容。
- `keywords`: 可选，普通文本按字面量匹配，`re:` 前缀按正则匹配。
- `min_chars`: 中文/混合短文本过滤阈值，低于该长度不参与文本相似度比对，默认 `10`。
- `min_words`: 英文短文本过滤阈值，低于该词数不参与文本相似度比对。
- `similarity_threshold`: 跨组文本相似阈值，默认 `0.78`。
- `exclude_threshold`: 排除文件匹配阈值，默认 `0.86`。
- `sentence_delimiters`: 强分段符号。
- `soft_delimiters`: 长句辅助切分符号。
- `similarity_backend`: 相似度后端，当前只支持 `local_ngrams`；`embedding` 仅预留，尚未启用。
- `image_ahash_distance`: 图片近似重复 aHash 汉明距离。
- `legacy_conversion_timeout`: `.doc/.wps` 转换超时时间，单位秒。
- `soffice_path`: 可选，手动指定 LibreOffice `soffice` 可执行文件路径。

运行说明：

- 如果命令未指定 `--output`，报告默认写入当前工作目录下的 `outputs/run_时间戳`。
- 在 opencode 等 agent 中使用时，建议在项目根目录运行 CLI，这样报告会留在该项目文件夹内。
- `result.json` 默认保存全量相似明细，不需要额外开启全量导出。

不要比较同一组内部文件。不要把短文本过滤用于关键词检测；关键词和正则必须基于全文检测。
不要选择 `similarity_backend="embedding"`；该接口目前仅预留，本版本只启用 `local_ngrams`。
