# v0.1.0

首个公开版本，发布者：cwyalpha。

## Highlights

- Windows 单文件桌面程序：`标书文件查重工具.exe`。
- 支持 `.docx/.doc/.wps/.md` 分组查重。
- Windows 下旧格式文件按 WPS、Microsoft Office、LibreOffice 顺序转换；Linux/macOS 下使用 LibreOffice。
- 支持招标文件/模板文件排除、关键词/正则异常检测、图片重复检测。
- 输出离线 `report.html`、`result.json` 和左右对照 `compare_*.html`。
- 内置 Codex Skill：`bid-check-similarity`，可通过 npx 从 GitHub 安装。

## Skill Install

```bash
npx github:cwyalpha/bid-check-similarity
```

安装后按提示安装 Python 依赖，并使用 Skill 调用同一套 `checksim` CLI。
