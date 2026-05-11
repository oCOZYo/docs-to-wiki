# Docs-to-Wiki

[![skills.sh](https://skills.sh/b/oCOZYo/docs-to-wiki)](https://skills.sh/oCOZYo/docs-to-wiki)

> Point it at a folder of documents — PDFs, slides, Word reports — and get a structured, searchable Obsidian wiki. Powered by PaddleOCR for scanned documents and complex layouts, with Claude Vision for diagrams and charts. Zero API key required.

[English](#english) | [中文](#中文)

---

## English

### What it does

Your desktop is full of documents — sales decks, audit reports, technical specs, scanned contracts — scattered across formats and folders. This skill collection turns that chaos into a structured Obsidian wiki with categorized pages, wikilink cross-references, and searchable source files.

**Core pipeline (docs-to-wiki):** point at a directory, and the orchestrator collects all documents, converts them in parallel, OCRs scanned PDFs, merges everything, then synthesizes a categorized wiki with LLM-generated pages.

**Three atomic converters** handle the format-level work:

- **pdf-to-md** — auto-detects native-text PDFs (instant via `pymupdf`) vs scanned/image PDFs. Scanned documents go through [PaddleOCR](https://aistudio.baidu.com/paddleocr), a state-of-the-art OCR engine with layout analysis — it handles multi-column text, tables, mixed Chinese/English, and complex page structures that traditional OCR tools choke on
- **docx-to-md** — lossless text + table extraction via `python-docx`. Embedded diagrams and screenshots are saved to disk and described by Claude Vision
- **pptx-to-md** — renders every slide as a high-fidelity PNG via LibreOffice. This preserves spatial relationships — flowchart arrows, side-by-side comparisons, four-quadrant charts, numbered callouts — that shape-text extraction (pandoc, markitdown) silently drops

All three converters use **agent mode** by default: scripts do deterministic extraction; the calling Claude Code agent describes images using its built-in Vision — no `ANTHROPIC_API_KEY` needed. For large jobs (>5 images), the agent spawns subagents to keep image bytes out of the main context. Tested on 8,430 slides without context overflow.

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

桌面堆满了文档 —— 销售 PPT、审计报告、技术方案、扫描合同 —— 格式各异、散落各处。这套 skill 集合把这堆杂乱的文件变成结构化的 Obsidian 知识库：分类页面、wikilink 交叉引用、可检索的源文件。

**核心流水线（docs-to-wiki）**：指向一个目录，编排器自动采集所有文档、并行转换、OCR 扫描件、合并输出，最后用 LLM 合成分门别类的 wiki 页面。

**三个原子转换器**处理格式级工作：

- **pdf-to-md** —— 自动区分原生文字 PDF（`pymupdf` 秒级提取）和扫描/图片 PDF。扫描件走 [PaddleOCR](https://aistudio.baidu.com/paddleocr) —— 业界领先的 OCR 引擎，带版面分析能力，能处理多栏排版、表格、中英混排、复杂页面结构，传统 OCR 工具搞不定的它都能搞定
- **docx-to-md** —— 通过 `python-docx` 无损提取文字和表格。嵌入的图表、截图保存到磁盘，由 Claude Vision 描述
- **pptx-to-md** —— 通过 LibreOffice 将每张幻灯片渲染为高清 PNG。保留流程图箭头方向、左右对比、四象限图表、编号标注等空间布局信息 —— pandoc、markitdown 等 shape-text 提取工具会静默丢失这些

三个转换器默认使用 **agent 模式**：脚本负责确定性提取；Claude Code agent 用自带的 Vision 能力描述图片 —— **不需要 ANTHROPIC_API_KEY**。大批量时（>5 张图）agent 自动 spawn subagent，图片字节不进入主上下文。实测 8430 张幻灯片无上下文溢出。

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
