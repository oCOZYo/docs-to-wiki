# Docs-to-Wiki

[![skills.sh](https://skills.sh/b/oCOZYo/docs-to-wiki)](https://skills.sh/oCOZYo/docs-to-wiki)

> Four Claude Code skills that convert PDF, DOCX, PPTX to structured Markdown — and synthesize them into an Obsidian wiki. No API key required.

[English](#english) | [中文](#中文)

---

## English

### What it does

- **docs-to-wiki** (orchestrator) — takes a folder of mixed documents, runs the three converters below in parallel, OCRs scanned PDFs, then synthesizes a categorized Obsidian wiki with wikilink cross-references
- **pdf-to-md** — auto-detects native-text PDFs (instant via `pymupdf`) vs scanned PDFs (PaddleOCR). Extracts large images to disk as `![](...)` placeholders
- **docx-to-md** — lossless text + table extraction via `python-docx`. Embedded images saved to disk as placeholders
- **pptx-to-md** — renders every slide as a PNG via LibreOffice, preserving spatial layouts (flowcharts, side-by-side comparisons, charts) that shape-text extraction silently drops

All three converters use **agent mode** by default: scripts do deterministic extraction; the calling Claude Code agent describes images using its built-in Vision — no `ANTHROPIC_API_KEY` needed. For large jobs (>5 images), the agent spawns subagents to keep image bytes out of the main context.

### Install

```bash
npx skills add oCOZYo/docs-to-wiki
```

Installs all four skills. Add `-g` for global install, or `--skill pdf-to-md` to install just one.

### Quick Start

**Single document conversion:**
- *"Convert this PDF to Markdown"* → `pdf-to-md`
- *"Extract this Word doc"* → `docx-to-md`
- *"Turn these slides into notes"* → `pptx-to-md`

**Full knowledge base:**
- *"Build a wiki from the docs in ./corpus/"* → `docs-to-wiki` orchestrates the complete pipeline

### Skills

| Skill | Input | Method |
|-------|-------|--------|
| [docs-to-wiki](skills/docs-to-wiki/) | Directory of mixed docs | Collect → Convert → OCR → Merge → Synthesize wiki |
| [pdf-to-md](skills/pdf-to-md/) | PDF, JPG, PNG, BMP, TIFF, WEBP | `pymupdf` direct + PaddleOCR fallback |
| [docx-to-md](skills/docx-to-md/) | DOCX | `python-docx` + extracted images |
| [pptx-to-md](skills/pptx-to-md/) | PPTX, PPSX | LibreOffice → per-slide PNG |

### Setup

```bash
# Python dependencies
pip install pymupdf python-docx requests pyyaml

# PaddleOCR — only for scanned PDFs (free tier available)
export PADDLEOCR_TOKEN="your_token"
export PADDLEOCR_API_URL="https://xxxx.aistudio-app.com/layout-parsing"
# Sign up: https://aistudio.baidu.com/paddleocr

# LibreOffice — only for pptx-to-md
# macOS:  brew install --cask libreoffice
# Linux:  apt install libreoffice
```

For backend automation outside Claude Code, pass `--api-key` to any script.

### License

MIT

---

## 中文

### 功能概述

- **docs-to-wiki**（编排器）—— 读取一个文档目录，并行调用下面三个转换器，OCR 扫描 PDF，最后合成一个带 wikilink 交叉引用的 Obsidian 知识库
- **pdf-to-md** —— 自动识别原生文字 PDF（`pymupdf` 秒级提取）和扫描 PDF（PaddleOCR）。大图提取到磁盘，以 `![](...)` 占位符嵌入 Markdown
- **docx-to-md** —— 通过 `python-docx` 无损提取文字和表格。嵌入图片保存到磁盘作为占位符
- **pptx-to-md** —— 通过 LibreOffice 将每张幻灯片渲染为 PNG，保留流程图、左右对比、图表等空间布局信息

三个转换器默认使用 **agent 模式**：脚本负责确定性提取；Claude Code agent 用自带的 Vision 能力描述图片 —— **不需要 ANTHROPIC_API_KEY**。大批量时（>5 张图）agent 自动 spawn subagent，图片字节不进入主上下文。

### 安装

```bash
npx skills add oCOZYo/docs-to-wiki
```

安装全部四个 skill。加 `-g` 装到用户全局目录，`--skill pdf-to-md` 只装一个。

### 快速开始

**单文档转换：**
- *"把这个 PDF 转成 Markdown"* → `pdf-to-md`
- *"提取这个 Word 文档"* → `docx-to-md`
- *"把这些幻灯片转成笔记"* → `pptx-to-md`

**批量建知识库：**
- *"把 ./corpus/ 里的文档建成 wiki"* → `docs-to-wiki` 编排完整流水线

### Skills 列表

| Skill | 输入格式 | 方法 |
|-------|----------|------|
| [docs-to-wiki](skills/docs-to-wiki/) | 混合文档目录 | 采集 → 转换 → OCR → 合并 → 合成 wiki |
| [pdf-to-md](skills/pdf-to-md/) | PDF, JPG, PNG, BMP, TIFF, WEBP | `pymupdf` 直提 + PaddleOCR 兜底 |
| [docx-to-md](skills/docx-to-md/) | DOCX | `python-docx` + 提取嵌入图 |
| [pptx-to-md](skills/pptx-to-md/) | PPTX, PPSX | LibreOffice → 逐页 PNG |

### 配置

```bash
# Python 依赖
pip install pymupdf python-docx requests pyyaml

# PaddleOCR —— 仅扫描 PDF 需要（有免费额度）
export PADDLEOCR_TOKEN="your_token"
export PADDLEOCR_API_URL="https://xxxx.aistudio-app.com/layout-parsing"
# 注册：https://aistudio.baidu.com/paddleocr

# LibreOffice —— 仅 pptx-to-md 需要
# macOS:  brew install --cask libreoffice
# Linux:  apt install libreoffice
```

如果要在 Claude Code 外做后台自动化，给脚本加 `--api-key` 参数即可。

### License

MIT
