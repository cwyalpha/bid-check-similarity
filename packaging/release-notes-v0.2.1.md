# v0.2.1

全量查重和输入格式增强版本。

## 主要更新

- 移除报告展示限流和相关配置项，`report.html` 与 `result.json` 默认输出全量相似结果。
- 中文/混合短文本过滤默认值从 `20` 调整为 `10`。
- GUI 参数项右侧增加 `?` 帮助按钮，说明每个参数的含义和建议取值。
- 新增 `.txt` 输入支持，txt 按纯文本解析，不做 Markdown 去格式处理。
- Skill 增强中文操作指导，说明 Agent 如何根据目录结构自动分组、如何设置关键词/正则，以及如何建议用户补充公司名称、法人、人员姓名、手机号等异常关键词。
- README、示例配置和 Skill schema 同步移除已废弃参数。

## 验证

- `python -m unittest discover -s tests -v`
- `python -m checksim.cli --config sample_cases\demo_4_groups\case.json --output outputs\run_demo_validation --quiet`
- `python skills\bid-check-similarity\scripts\run_check.py --config sample_cases\demo_4_groups\case.json --output outputs\run_skill_validation --quiet`
- `python -m checksim.cli --config sample_cases\demo_4_groups_long\case.json --output outputs\run_long_validation --quiet`
- `python scripts\perf_smoke.py --mode cli --groups 4 --chars-per-file 100000`
- `python scripts\perf_smoke.py --mode skill --groups 4 --chars-per-file 100000`

## 资产

- Windows 单文件程序：`BidCheckSimilarity-v0.2.1-Windows-x64.exe`
