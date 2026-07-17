## v0.2.7

本版本新增跨公司组的文档元数据碰撞预警，并同步更新桌面 GUI、命令行 CLI 和轻量 Agent Skill。

### 新增与改进

- 自动比较不同公司组文档的作者、公司、最后修改者及文档内部创建/修改时间。
- 作者或公司元数据相同标为高风险；最后修改者相同或时间处于同一分钟标为中风险。
- 仅比较不同公司组，并过滤 Administrator、Microsoft Office User、WPS/Office 厂商名等常见默认值，减少误报。
- DOCX 额外读取 Company 扩展属性，PDF 补充读取内部创建/修改时间。
- `report.html`、`result.json` 和 `ai_summary.json` 增加元数据预警数量、风险等级、碰撞值及具体文件定位。
- GUI 完成提示增加元数据预警数量。
- Agent Skill 同步使用共享核心实现，继续保持自包含、轻量且不内置 PDF/OCR。

### macOS 版本

- `BidCheckSimilarity-v0.2.7-macOS-arm64.zip`
- Apple Silicon 原生应用，包含 PDF 文本解析和扫描 PDF PP-OCRv6 medium OCR 能力。
- 应用包内部版本号与 Release 版本保持一致。

### Windows 版本

- Windows x64 安装包将在 Windows 环境后续构建并补充到本 Release。
