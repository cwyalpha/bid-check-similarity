# v0.2.0

大文件友好和报告复核增强版本。

注：本版本曾尝试通过报告结果限流控制大文件输出体积；后续版本已改为默认全量输出。

## 主要更新

- 曾新增报告结果规模控制能力，避免 10 万字级样本生成过大的 HTML/JSON。
- 曾新增高级算法参数和相似度后端字段。
- 总报告增加运行耗时摘要、组对搜索和相似度区间筛选。
- 左右对照页继续支持高亮跳转。
- GUI 新增配置保存/加载、历史报告打开目录/复制路径/删除记录。
- Skill 和 CLI 共享同一核心代码，文档同步更新。
- 新增 `scripts/perf_smoke.py`，可临时生成 4 组 10 万字符级样本进行 CLI/Skill 性能测试。

## 验证

- `python -m unittest discover -s tests -v`
- `python -m checksim.cli --config sample_cases\demo_4_groups\case.json --output outputs\run_demo_validation --quiet`
- `python skills\bid-check-similarity\scripts\run_check.py --config sample_cases\demo_4_groups\case.json --output outputs\run_skill_validation --quiet`
- `python -m checksim.cli --config sample_cases\demo_4_groups_long\case.json --output outputs\run_long_validation --quiet`
- `python scripts\perf_smoke.py --mode cli --groups 4 --chars-per-file 100000`
- `python scripts\perf_smoke.py --mode skill --groups 4 --chars-per-file 100000`

## 资产

- Windows 单文件程序：`BidCheckSimilarity-v0.2.0-Windows-x64.exe`
