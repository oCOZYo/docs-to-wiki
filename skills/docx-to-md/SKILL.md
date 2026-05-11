---
name: docx-to-md
description: 将 DOCX/Word 文档批量转换为结构化 Markdown。直接提取标题、段落、表格（python-docx），并对大尺寸嵌入图片调用 Claude Vision 生成内联描述（按文档原顺序保留位置）。当用户提到"DOCX转Markdown"、"Word转笔记"、"提取Word内容"、"docx转md"、"Word文档转换"时，务必使用本 Skill。
compatibility: 此 Skill 必须安装在 ~/.cc-switch/skills/docx-to-md/（脚本路径依赖此固定位置）。
---

# DOCX → Markdown

DOCX 是结构化 XML，文字可以直接无损提取，无需 OCR；但嵌入图片（架构图、流程图、截图）若占比较大，图文关系本身是信息——本 Skill 对超过阈值的图片调用 Claude Vision 生成文字描述，按原位置内联进 Markdown。

## 工作流

```bash
export ANTHROPIC_API_KEY="..."
~/.venvs/paddleocr/bin/python \
  ~/.cc-switch/skills/docx-to-md/scripts/docx_to_md.py \
  --input "<docx_or_dir>" \
  --output "<output_dir>" \
  --large-image-kb 30 \
  --model claude-haiku-4-5-20251001
```

输出：`<output_dir>/<stem>.md`，包含按原顺序排列的标题、段落、表格，以及大图的 `> **[图片]**` 描述块。

## 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--large-image-kb` | 30 | 图片 blob 超过此值（KB）才送 Vision。30KB 默认能过滤掉徽标/图标 |
| `--no-vision` | — | 纯文字模式，跳过所有图片，零 API 消耗 |
| `--max-images` | 50 | 单文档图片数上限（费用保护） |
| `--model` | `claude-haiku-4-5-20251001` | Haiku 快/便宜；用 `claude-sonnet-4-6` 获得更细的图片描述 |

## 环境

- `~/.venvs/paddleocr/bin/python`：含 `python-docx`、`anthropic`
- `ANTHROPIC_API_KEY`：仅在使用 Vision 时需要（默认开启）

## 注意事项

- 仅对原生 `.docx` 有效；遗留 `.doc` 需先用 LibreOffice 转换：
  `soffice --headless --convert-to docx file.doc`
- 不处理 EMF/WMF 等矢量格式（python-docx 不直接暴露），主要识别 PNG/JPEG 嵌入图
