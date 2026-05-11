# Doc-to-MD Skills

[![skills.sh](https://skills.sh/b/oCOZYo/doc-to-md-skills)](https://skills.sh/oCOZYo/doc-to-md-skills)

> Three skills that convert PDF, DOCX, PPTX to Markdown — preserving diagrams, charts, and visual layouts that text-only converters lose.

[English](#english) | [中文](#中文)

---

## English

### Why these skills

Most document-to-Markdown tools either drop images entirely or OCR everything (slow, noisy, loses structure). These skills are different:

- **Auto-routes by content type** — text PDFs extract instantly via `pymupdf` (seconds, zero API cost); only scanned PDFs go through OCR
- **Vision-LLM for visual content** — embedded diagrams, flowcharts, and slide layouts are described by Claude Vision *at their original position* in the document. Text-only extractors like `markitdown` or `pandoc` silently drop this information
- **Per-slide PPTX rendering** — every slide is rendered as a PNG and described in full, preserving spatial relationships (left/right comparisons, arrow directions, four-quadrant diagrams) that shape-text extraction can't capture
- **Cost controls built in** — `--large-image-kb` skips logos/icons, `--max-images` / `--max-slides` cap per-file Vision calls

Tested on a 326-document corpus (270 PPTX + 37 PDF + 18 DOCX = 8,430 slides), all converted with Haiku Vision in ~100 minutes.

### Install

```bash
npx skills add oCOZYo/doc-to-md-skills
```

Installs all three skills into the current project's `.agents/skills/`. Add `-g` to install globally for the current user, or `--skill pdf-to-md` to install just one.

### Setup

#### 1. Python environment

```bash
python3 -m venv ~/.venvs/doc-to-md
source ~/.venvs/doc-to-md/bin/activate
pip install pymupdf python-docx anthropic requests
```

#### 2. Claude Vision (required for `docx-to-md`, `pptx-to-md`, and image-rich PDFs)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Get your key at https://console.anthropic.com/settings/keys

#### 3. PaddleOCR (only needed for scanned PDFs)

Native-text PDFs are handled by `pymupdf` and don't need OCR. Only scanned PDFs (image-based, no text layer) trigger this path.

```bash
export PADDLEOCR_TOKEN="your_token"
export PADDLEOCR_API_URL="https://xxxx.aistudio-app.com/layout-parsing"
```

Sign up and provision an inference endpoint at https://aistudio.baidu.com/paddleocr — free tier available. After creating an endpoint, copy the URL and access token from your AI Studio dashboard.

#### 4. LibreOffice (only needed for `pptx-to-md`)

```bash
# macOS
brew install --cask libreoffice

# Debian/Ubuntu
apt install libreoffice
```

Required to convert PPTX → PDF before rendering each slide.

### Usage

The skills activate automatically when you ask Claude Code to convert documents:

- *"Convert this PDF to Markdown"* → `pdf-to-md`
- *"Extract this Word doc"* → `docx-to-md`
- *"Turn these slides into notes"* → `pptx-to-md`

Or run the scripts directly:

```bash
# PDF: auto-detect text vs scanned, send large images to Vision
python skills/pdf-to-md/scripts/pdf_to_md.py \
  --input docs/ --output out/ \
  --large-image-kb 30 --model claude-haiku-4-5

# DOCX: extract text + tables, describe embedded images
python skills/docx-to-md/scripts/docx_to_md.py \
  --input report.docx --output out/ \
  --large-image-kb 30 --model claude-haiku-4-5

# PPTX: render each slide as PNG, describe via Vision
python skills/pptx-to-md/scripts/pptx_to_md.py \
  --input deck.pptx --output out/ \
  --dpi 150 --concurrent 5 --model claude-haiku-4-5
```

### Skills

| Skill | Input | Method | Optional deps |
|-------|-------|--------|---------------|
| [pdf-to-md](skills/pdf-to-md/) | PDF, JPG, PNG, BMP, TIFF, WEBP | `pymupdf` direct + PaddleOCR fallback | PaddleOCR for scanned PDFs |
| [docx-to-md](skills/docx-to-md/) | DOCX | `python-docx` + Claude Vision | — |
| [pptx-to-md](skills/pptx-to-md/) | PPTX, PPSX | LibreOffice → PNG → Claude Vision | LibreOffice |

### License

MIT

---

## 中文

### 为什么用这套 skills

市面上的文档转 Markdown 工具，要么完全丢弃图片，要么对所有内容做 OCR（慢、噪音大、丢失结构）。这套 skills 不一样：

- **按内容类型自动分流** —— 原生文字 PDF 用 `pymupdf` 秒级提取，零 API 消耗；只有扫描 PDF 才走 OCR
- **用 Vision LLM 处理视觉内容** —— 嵌入的架构图、流程图、PPT 布局由 Claude Vision 描述，**保留在原文位置**。`markitdown` / `pandoc` 这类纯文本提取器会静默丢弃这部分信息
- **PPTX 逐张幻灯片渲染** —— 每张幻灯片渲染成 PNG 后完整描述，保留 shape-text 提取拿不到的空间关系（左右对比、箭头方向、四象限图表）
- **内置费用控制** —— `--large-image-kb` 跳过 logo/图标，`--max-images` / `--max-slides` 限制单文件 Vision 调用数

实测：326 个文档（270 PPTX + 37 PDF + 18 DOCX = 8430 张幻灯片），用 Haiku Vision 约 100 分钟跑完。

### 安装

```bash
npx skills add oCOZYo/doc-to-md-skills
```

安装全部 3 个 skill 到当前项目的 `.agents/skills/`。加 `-g` 装到用户全局目录，或 `--skill pdf-to-md` 只装一个。

### 配置

#### 1. Python 环境

```bash
python3 -m venv ~/.venvs/doc-to-md
source ~/.venvs/doc-to-md/bin/activate
pip install pymupdf python-docx anthropic requests
```

#### 2. Claude Vision（`docx-to-md`、`pptx-to-md`、含图 PDF 必需）

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

在 https://console.anthropic.com/settings/keys 申请。

#### 3. PaddleOCR（仅扫描 PDF 需要）

原生文字 PDF 由 `pymupdf` 直接处理，不需要 OCR。只有扫描 PDF（图像形式、无文字层）会触发 OCR 路径。

```bash
export PADDLEOCR_TOKEN="your_token"
export PADDLEOCR_API_URL="https://xxxx.aistudio-app.com/layout-parsing"
```

在 https://aistudio.baidu.com/paddleocr 注册并部署一个推理服务（有免费额度）。部署完成后从 AI Studio 控制台拿到端点 URL 和访问 token。

#### 4. LibreOffice（仅 `pptx-to-md` 需要）

```bash
# macOS
brew install --cask libreoffice

# Debian/Ubuntu
apt install libreoffice
```

用于在渲染每张幻灯片前将 PPTX 转为 PDF。

### 使用

在 Claude Code 里直接用自然语言触发：

- *"把这个 PDF 转成 Markdown"* → `pdf-to-md`
- *"提取这个 Word 文档"* → `docx-to-md`
- *"把这些幻灯片转成笔记"* → `pptx-to-md`

或直接调脚本：

```bash
# PDF：自动判断文字/扫描，大图发 Vision
python skills/pdf-to-md/scripts/pdf_to_md.py \
  --input docs/ --output out/ \
  --large-image-kb 30 --model claude-haiku-4-5

# DOCX：提取文字+表格，嵌入大图发 Vision
python skills/docx-to-md/scripts/docx_to_md.py \
  --input report.docx --output out/ \
  --large-image-kb 30 --model claude-haiku-4-5

# PPTX：每张幻灯片渲染为 PNG 后由 Vision 描述
python skills/pptx-to-md/scripts/pptx_to_md.py \
  --input deck.pptx --output out/ \
  --dpi 150 --concurrent 5 --model claude-haiku-4-5
```

### Skill 列表

| Skill | 输入格式 | 方法 | 可选依赖 |
|-------|----------|------|----------|
| [pdf-to-md](skills/pdf-to-md/) | PDF, JPG, PNG, BMP, TIFF, WEBP | `pymupdf` 直接提取 + PaddleOCR 兜底 | PaddleOCR（扫描 PDF）|
| [docx-to-md](skills/docx-to-md/) | DOCX | `python-docx` + Claude Vision | — |
| [pptx-to-md](skills/pptx-to-md/) | PPTX, PPSX | LibreOffice → PNG → Claude Vision | LibreOffice |

### License

MIT
