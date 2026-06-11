# v0.2.3

Skill 自包含修复版本。

## 主要更新

- Skill 目录新增 `scripts/vendor/checksim` 内置核心代码副本。
- `scripts/run_check.py` 只加载 Skill 目录内的 vendor 包，不再回退引用仓库根目录。
- `scripts/install-skill.js` 改为直接复制完整 Skill 目录，并校验内置核心代码存在。
- 新增 `scripts/sync_skill_vendor.py`，开发时可把仓库核心代码同步到 Skill 内置副本。
- 新增回归测试：复制 Skill 到临时目录后独立运行查重，验证不依赖外部源码。
- README 和 Skill 文档补充自包含说明。

## 验证

- `python scripts\sync_skill_vendor.py`
- `python -m compileall checksim tests scripts skills\bid-check-similarity`
- `python -m unittest discover -s tests -v`
- `python skills\bid-check-similarity\scripts\run_check.py --config sample_cases\demo_4_groups\case.json --output outputs\run_self_contained_skill_validation --quiet`
- `node scripts\install-skill.js --target <temp-dir>`
- `npm pack --dry-run`

## 资产

- Windows 单文件程序：`BidCheckSimilarity-v0.2.3-Windows-x64.exe`
