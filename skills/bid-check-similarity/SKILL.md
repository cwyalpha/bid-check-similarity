---
name: bid-check-similarity
description: 离线标书和文件查重 Skill，支持按公司/投标单位分组比对 .docx/.doc/.wps/.md/.txt 文件。适用于需要检测投标文件相似文本、排除招标文件或模板内容、发现跨组关键词/正则异常，并在 Windows 或 Linux 上生成本地 HTML/JSON 报告的场景。
---

# bid-check-similarity

使用本 Skill 调用本地 `checksim` 引擎进行标书或通用文件查重。引擎完全离线运行：解析分组文档、过滤短文本后做相似度比对、应用可选排除文件、检测共享关键词/正则、检查重复图片，并输出 `report.html`、`result.json` 和按组对生成的 `compare_*.html`。结果默认全量写入 `result.json` 和 HTML 报告。

## 工作流程

1. 确认或推断输入分组。每组代表一家投标单位，可包含一个或多个 `.docx`、`.doc`、`.wps`、`.md`、`.txt` 文件。
2. 根据需要添加排除文件，例如招标文件、模板文件、统一格式要求等允许共享的内容。
3. 根据需要添加重要关键词或正则规则。正则规则必须以 `re:` 开头。
4. 生成 JSON 配置。字段结构和默认参数见 `references/config-schema.md`。
5. 调用内置 CLI。若用户未指定输出目录，优先在当前项目目录运行命令，让默认结果写入当前目录下的 `outputs/run_时间戳`：

```bash
python path/to/skill/scripts/run_check.py --config case.json --output outputs/run_001
```

6. 回复时优先给出生成的 `report.html` 路径，再概述异常相似片段、已排除片段、关键词异常和旧格式转换限制。

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

- `.docx`、`.md` 和 `.txt` 在 Windows 与 Linux 上直接解析；`.txt` 按纯文本处理，不做 Markdown 去格式。
- `.doc/.wps` 会先转换为临时 `.docx` 再解析，原始文件不会被修改。
- Windows 下按 WPS、Microsoft Office、LibreOffice 顺序尝试转换。
- Linux 下旧格式转换依赖 LibreOffice `soffice`。
- 如果旧格式转换不可用，明确报告错误，并提示用户安装 LibreOffice 或先手动另存为 `.docx`。
- 新 Python 环境需要先安装 `scripts/requirements.txt` 中的依赖。

## 输出要求

- `report.html`：离线总览报告，CSS/JS 内嵌。
- `compare_*.html`：两组文件左右对照页，支持高亮文本双向跳转。
- `result.json`：完整结构化结果，保存全量相似片段和统计。

不要比较同一组内部文件。不要把短文本过滤用于关键词检测；关键词和正则必须基于全文检测。
不要选择 `similarity_backend="embedding"`；该接口目前仅预留，本版本只启用 `local_ngrams`。
