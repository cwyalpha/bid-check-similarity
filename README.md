# 标书/文件查重工具

本项目是一个本地离线运行的标书/文件查重工具，支持桌面 GUI、命令行 CLI 和 Agent Skill。它可以按公司/投标单位分组导入 `.docx`、`.doc`、`.wps`、`.md` 文件，检测跨组相似文本、共享关键词/正则、重复图片，并生成可在内网离线打开的 HTML 报告。

## 主要功能

- 多组投标文件两两查重，同一组内文件不会互相比对。
- 支持可选排除文件，例如招标文件、模板文件、统一格式要求。
- 支持重要关键词和 `re:` 正则规则；同一规则命中 2 个及以上公司组即提示异常。
- 支持短文本过滤、文本相似阈值、排除文件阈值、分段符号等参数设置。
- 支持快速/平衡/详细报告预设，默认控制每组对展示数量，避免大文件报告过慢。
- 支持 `.doc/.wps` 自动转换：Windows 下按 WPS、Microsoft Office、LibreOffice 顺序尝试，Linux/macOS 下使用 LibreOffice。
- 生成 `report.html`、`result.json`、可选 `all_matches.jsonl` 和按组对生成的 `compare_*.html` 左右对照页。
- HTML 报告的 CSS/JS 均内嵌，不依赖 CDN，适合内网离线使用。

## 桌面版

从 Release 页面下载单文件 Windows 程序：

```text
标书文件查重工具.exe
```

运行后按界面步骤操作：

1. 添加至少 2 个投标文件分组。
   - “添加文件组”：一次选择同一家公司的一批文件。
   - “按目录添加组”：选择一个公司目录，递归导入该公司文件。
   - “批量单文件成组”：一次选择多个文件，每个文件自动作为一个公司/分组。
   - “批量文件夹成组”：选择包含多个公司文件夹的上级目录，每个直接子文件夹及其子目录自动作为一个公司/分组。
2. 可选添加排除文件 B。
3. 可选填写关键词或正则规则。
4. 选择快速/平衡/详细报告预设，必要时展开高级参数调整结果上限、候选召回和全量 JSONL 导出。
5. 点击“开始检测”，完成后会自动打开 `report.html`。

## 命令行

推荐使用 Python 3.8+：

```powershell
python -m pip install -e .
python -m checksim.cli --config examples\case.example.json --output outputs\run_demo
```

不指定 `--output` 时，CLI 默认把结果写到当前工作目录的 `outputs/run_时间戳`，适合在 opencode 等 agent 的项目目录中直接运行。

也可以直接启动 GUI：

```powershell
python run_app.py
```

## Agent Skill 安装

本仓库包含 `bid-check-similarity` Skill。推荐通过 npx 安装到对应 agent 的 skills 目录：

```bash
npx github:cwyalpha/bid-check-similarity --target /path/to/agent/skills
```

如果环境变量中已经配置了 `AGENT_SKILLS_DIR`，也可以省略 `--target`：

```bash
AGENT_SKILLS_DIR=/path/to/agent/skills npx github:cwyalpha/bid-check-similarity
```

如果既不传 `--target`，也不设置 `AGENT_SKILLS_DIR`，安装器会默认写入当前命令行目录下的 `./skills`。

安装完成后，根据提示安装 Python 依赖：

```bash
python -m pip install -r /path/to/agent/skills/bid-check-similarity/scripts/requirements.txt
```

Skill 会调用同一套 `checksim` 核心代码和 CLI，适配 Windows 与 Linux。Windows 处理 `.doc/.wps` 时可使用 WPS/Office/LibreOffice；Linux 处理旧格式文件需要 LibreOffice `soffice`。

## 配置示例

```json
{
  "groups": [
    {
      "name": "A公司",
      "files": ["D:/cases/A公司/投标文件.docx"]
    },
    {
      "name": "B公司",
      "files": ["D:/cases/B公司/投标文件.md", "D:/cases/B公司/补充材料.wps"]
    }
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

短文本过滤只影响相似度比对，不影响关键词/正则检测。

## 报告说明

每次检测会生成：

- `report.html`：总览报告，包含统计、参数、两两比对、关键词异常、图片重复和明细。
- `compare_*.html`：两组文件左右对照页，支持点击高亮片段跳转到对侧对应片段。
- `result.json`：结构化结果，默认保存报告展示用的代表性相似片段和完整统计。
- `all_matches.jsonl`：仅当 `write_all_matches=true` 时生成，保存全量相似结果，适合后续脚本处理。

如果结果被截断，报告会显示“展示/总数/已截断”，并提示是否已生成全量 JSONL。左右对照页中，高亮颜色越深表示相似度越高；已排除片段颜色更淡。左右两栏可独立滚动，并支持“上一个/下一个高亮”导航。

## 开发与打包

运行测试：

```powershell
python -m unittest discover -s tests -v
```

性能 smoke 会临时生成 4 组 10 万字符级 Markdown 样本，不会提交大文本：

```powershell
python scripts\perf_smoke.py --mode cli --groups 4 --chars-per-file 100000
python scripts\perf_smoke.py --mode skill --groups 4 --chars-per-file 100000
```

构建 Windows 单文件 exe：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe_py38.ps1
```

输出文件：

```text
dist\标书文件查重工具.exe
```

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=cwyalpha/bid-check-similarity&type=Date)](https://star-history.com/#cwyalpha/bid-check-similarity&Date)
