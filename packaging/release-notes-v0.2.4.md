# v0.2.4

macOS 桌面版与示例文档版本。

## 主要更新

- 新增 `build_macos.sh`，可在 macOS 上构建 `.app` 并压缩为 release zip。
- macOS GUI 打开报告/输出目录时使用系统 `open` 命令。
- macOS 打包后的 Finder 启动场景默认把报告写到 `~/Documents/标书文件查重工具输出`，避免尝试写入系统根目录。
- CLI、GUI 和 Skill 加载配置时，相对文件路径改为按 `case.json` 所在目录解析，打包版和跨目录调用更稳定。
- 桌面入口在带命令行参数时可复用 CLI，便于对打包产物做自动化验收；双击无参数仍打开 GUI。
- README 增加 macOS 下载说明、示例案例、软件截图和报告截图位置。
- 示例 `sample_cases/demo_4_groups` 的关键词更新为 `晨星`、`凌云`、`北辰`、`青禾`。
- Skill 文档补充 macOS 平台说明；核心代码仍通过 `scripts/sync_skill_vendor.py` 同步到 Skill vendor。

## 验证

- `python scripts/sync_skill_vendor.py`
- `python -m compileall checksim tests scripts skills/bid-check-similarity`
- `python -m unittest discover -s tests -v`
- `python -m checksim.cli --config sample_cases/demo_4_groups/case.json --output sample_cases/demo_4_groups/outputs/run_v0.2.4_cli`
- `python skills/bid-check-similarity/scripts/run_check.py --config sample_cases/demo_4_groups/case.json --output sample_cases/demo_4_groups/outputs/run_v0.2.4_skill --quiet`
- `./build_macos.sh`
- macOS 桌面版使用 `sample_cases/demo_4_groups` 完成 4 家投标文件、1 个招标文件、4 个公司简称关键词的检测。

## 资产

- macOS Apple Silicon：`BidCheckSimilarity-v0.2.4-macOS-arm64.zip`
- Windows 单文件程序：`BidCheckSimilarity-v0.2.4-Windows-x64.exe`
