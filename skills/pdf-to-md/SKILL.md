---
name: pdf-to-md
description: 将 PDF 文件批量转换为结构化 Markdown。自动识别原生文字 PDF（pymupdf 直接提取，秒级完成）和扫描/图像 PDF（PaddleOCR 云端识别）。也支持 JPG/PNG/BMP/TIFF/WEBP 图片文件。当用户提到"PDF转Markdown"、"扫描PDF"、"图像PDF"、"图片文档"、"OCR提取"、"处理一批PDF"、"文档转Markdown"、"文档转笔记"时，务必使用本 Skill。
compatibility: 此 Skill 必须安装在 ~/.cc-switch/skills/pdf-to-md/（脚本路径依赖此固定位置）。
---

# PDF / 图片 → Markdown

## 格式路由

| 输入 | 路径 | 说明 |
|------|------|------|
| PDF（原生文字，平均 >50 字符/页） | `pdf_to_md.py` (pymupdf) | 秒级完成，无 API 消耗 |
| PDF（扫描 / 图像） | `ocr_extract.py` (PaddleOCR 云端) | 自动识别后跳过快速路径 |
| 图片（JPG / PNG / BMP / TIFF / WEBP） | `ocr_extract.py` | 仅 PaddleOCR 路径 |

## 工作流

### Step 1：原生文字 PDF 快速提取

先对所有 PDF 跑快速提取——原生文字 PDF 直接出结果，扫描 PDF 自动跳过并打印 `scanned` 提示：

```bash
~/.venvs/paddleocr/bin/python \
  ~/.cc-switch/skills/pdf-to-md/scripts/pdf_to_md.py \
  --input "<source_dir_or_file>" \
  --output "<output_dir>"
```

输出每个文件的状态：
- `text (avg NNN ch/pg, N images)` — 已提取，结果在 `<output_dir>/<stem>.md`
- `scanned (avg N ch/pg)` — 跳过，进入 Step 2

可选参数：
- `--large-image-kb 30`：嵌入大图调用 Claude Vision 描述（需 `ANTHROPIC_API_KEY`）
- `--no-vision`：纯文字模式
- `--max-images 50`：单文档图片数上限

如果只有图片文件（非 PDF），跳过此步直接进 Step 2。

### Step 2：OCR（扫描 PDF + 图片）

```bash
export PADDLEOCR_TOKEN="your_token"
export PADDLEOCR_API_URL="https://xxxx.aistudio-app.com/layout-parsing"
python3 ~/.cc-switch/skills/pdf-to-md/scripts/ocr_extract.py \
  "<source_dir>" "<output_dir>"
```

OCR 输出结构：
- `per_page/`：逐页独立 MD（仅云端多页时生成）
- `merged/`：全文合并 MD，适合直接导入知识库

### Step 3：可选审查与调整

如果用户要求调整格式（修正识别错误、统一术语、优化标题层级），先读取 `references/optimization-prompt.md` 中的处理规范，再用 `Edit` 工具针对性修改。

## 环境

- `~/.venvs/paddleocr/bin/python`：含 `pymupdf`、可选 `anthropic`、`paddleocr`
- `PADDLEOCR_TOKEN` / `PADDLEOCR_API_URL`：云端 OCR 凭证（仅 Step 2 需要）
- `ANTHROPIC_API_KEY`：Step 1 中嵌入大图 Vision 描述时需要

## 注意事项

- 原生文字 PDF 走快速路径：无 API 消耗，秒级完成
- Token 含个人凭证，始终用环境变量传入，不要写在命令行
- 本地 MLX VLM 模式：`ocr_extract.py` 支持 `--server_url`，详见脚本 `--help`
