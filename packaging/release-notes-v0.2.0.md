# v0.2.0

大文件友好和报告复核增强版本。

## 主要更新

- 新增报告结果限流：默认每个组对展示 600 条异常相似、200 条已排除相似，避免 10 万字级样本生成过大的 HTML/JSON。
- 新增全量导出：设置 `write_all_matches=true` 后额外生成 `all_matches.jsonl`。
- 新增高级算法参数：候选共享 ngram 比例、排除候选上限、最小长度比例和相似度后端字段。
- 总报告增加展示/总数/已截断提示、运行耗时摘要、组对搜索和相似度区间筛选。
- 左右对照页继续支持高亮跳转，并提示仅标注报告保留的代表性命中。
- GUI 新增快速/平衡/详细预设、高级参数折叠区、配置保存/加载、历史报告打开目录/复制路径/删除记录。
- Skill 和 CLI 共享同一核心代码，文档同步新增截断和全量 JSONL 说明。
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
