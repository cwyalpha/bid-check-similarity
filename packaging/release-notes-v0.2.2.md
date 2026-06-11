# v0.2.2

Agent 复核体验增强版本。

## 主要更新

- 新增 `ai_summary.json` 输出，供 AI/Agent 优先阅读，避免直接读取过长的 `result.json`。
- `ai_summary.json` 包含统计摘要、输出文件路径、组对摘要、代表性相似片段、已排除片段样例、关键词异常样例和图片重复样例。
- `report.html` 的“运行与输出摘要”增加 `ai_summary.json`、`report.html` 和 `result.json` 路径，方便人工与 Agent 交叉复核。
- Skill 文档内联完整配置 JSON 参考，不再依赖单独的 `references/config-schema.md`。
- Skill 示例路径改为 Linux 风格 `/project/cases/...`，更适合 opencode 等 Agent 项目目录场景。
- README 增加 `ai_summary.json` 的用途说明，并保留 `result.json` 作为全量追溯文件。

## 验证

- `python -m compileall checksim tests scripts skills\bid-check-similarity`
- `python -m unittest discover -s tests -v`
- `python -m checksim.cli --config sample_cases\demo_4_groups\case.json --output outputs\run_ai_summary_cli_validation --quiet`
- `python skills\bid-check-similarity\scripts\run_check.py --config sample_cases\demo_4_groups\case.json --output outputs\run_ai_summary_skill_validation --quiet`
- `python -m checksim.cli --config sample_cases\demo_4_groups_long\case.json --output outputs\run_ai_summary_long_validation --quiet`
- `python scripts\perf_smoke.py --mode cli --groups 4 --chars-per-file 100000`
- `python scripts\perf_smoke.py --mode skill --groups 4 --chars-per-file 100000`
- `rg -n -I "https?://|cdn|<script src|<link" outputs\run_ai_summary_cli_validation outputs\run_ai_summary_skill_validation`

## 资产

- Windows 单文件程序：`BidCheckSimilarity-v0.2.2-Windows-x64.exe`
