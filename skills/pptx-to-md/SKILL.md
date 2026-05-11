---
name: pptx-to-md
description: 将 PPTX/PPSX 演示文稿批量转换为结构化 Markdown。每张幻灯片渲染为 PNG 由 Claude Vision 描述完整内容——保留流程图、架构图、对比布局、数据表格、视觉层级关系等通过文字提取会丢失的信息。当用户提到"PPTX转Markdown"、"PPT转笔记"、"演示文稿提取"、"幻灯片转md"、"PPT转Markdown"时，务必使用本 Skill。
compatibility: 此 Skill 必须安装在 ~/.cc-switch/skills/pptx-to-md/（脚本路径依赖此固定位置）。
---

# PPTX → Markdown

PPTX 中信息往往通过视觉布局（左右对比、流程图箭头、图表）呈现——单纯文字提取（如 `markitdown`）会丢失大量结构。本 Skill 将每张幻灯片渲染成 PNG 后由 Claude Vision 描述完整内容，能保留视觉关系。

## 流程

```
PPTX → PDF (LibreOffice) → 每页 PNG (pymupdf 150dpi) → Vision 描述 → 合并 .md
```

## 工作流

```bash
export ANTHROPIC_API_KEY="..."
~/.venvs/paddleocr/bin/python \
  ~/.cc-switch/skills/pptx-to-md/scripts/pptx_to_md.py \
  --input "<pptx_or_dir>" \
  --output "<output_dir>" \
  --dpi 150 \
  --concurrent 5 \
  --model claude-haiku-4-5-20251001
```

输出：`<output_dir>/<stem>.md`，每张幻灯片对应一段 `## Slide N`。

## 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--dpi` | 150 | 幻灯片渲染分辨率。文字为主用 100；密集图表用 200 |
| `--concurrent` | 5 | 单文件内并行 Vision 调用数，触发限流可调低 |
| `--max-slides` | 200 | 单文件幻灯片数上限（费用保护） |
| `--workers` | 2 | 并行处理文件数（脚本目前序列执行，保留以备后续） |
| `--model` | `claude-haiku-4-5-20251001` | Haiku 快/便宜；`claude-sonnet-4-6` 描述更细 |

## 环境

- `~/.venvs/paddleocr/bin/python`：含 `pymupdf`、`anthropic`
- LibreOffice（命令 `soffice`，macOS 通过 brew 或 LibreOffice.app 提供）
- `ANTHROPIC_API_KEY`

## 注意事项

- LibreOffice 在 macOS 下 `--convert-to png` 只导出第一张幻灯片，因此本 Skill 走 PDF→PNG 路径
- LibreOffice profile 隔离（`-env:UserInstallation`）已内建，并行运行时不会发生 lock 冲突
- 也支持 `.ppsx` 格式
