# v0.2.5

## 更新内容

- 新增 `.pdf` 输入支持，投标文件分组和排除文件均可使用 PDF。
- 可复制文本的 PDF 默认通过文本层直接解析，保持离线、轻量、跨平台。
- 扫描版 PDF 使用 PaddleOCR/PP-OCRv6 medium OCR，配置项为 `pdf_ocr_mode`、`pdf_ocr_lang`、`pdf_min_text_chars`、`pdf_ocr_engine`、`pdf_ocr_det_model`、`pdf_ocr_rec_model`。
- GUI 文件选择和源码 CLI 配置支持 PDF；Agent Skill 保持轻量，不包含 PDF/OCR 解析功能。

## 兼容性说明

- 桌面打包版默认内置 PP-OCRv6 medium ONNX 模型，可离线识别扫描版 PDF，不使用 PaddleOCR-VL。
- Skill 环境仍保持基础依赖轻量；如需 PDF/OCR，请使用桌面版或源码 CLI。

## 验证

- `python -m compileall run_app.py checksim tests scripts skills/bid-check-similarity`
- `python -m unittest discover -s tests -v`
- `python -m checksim.cli --config sample_cases/demo_4_groups/case.json --output sample_cases/demo_4_groups/outputs/run_v0.2.5_cli --quiet`
- `python skills/bid-check-similarity/scripts/run_check.py --config sample_cases/demo_4_groups/case.json --output sample_cases/demo_4_groups/outputs/run_v0.2.5_skill --quiet`
- Windows 单文件程序命令行运行 `sample_cases/demo_4_groups/case.json`。
- Windows 单文件程序命令行运行 PDF 文本层样例，确认 `pdf_extraction="text"` 并生成相似命中。
- Windows 单文件程序命令行运行扫描版 PDF 样例，强制 `pdf_ocr_mode="always"`，确认 `pdf_extraction="paddleocr"` 并生成相似命中。
- Windows 单文件程序 GUI 启动 smoke 测试通过。

## 发布资产

- Windows 单文件程序：`BidCheckSimilarity-v0.2.5-Windows-x64.exe`
- macOS 版本后续在 macOS 环境打包后再补充发布。
