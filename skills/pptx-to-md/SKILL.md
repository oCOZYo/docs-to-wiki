---
name: pptx-to-md
description: 将 PPTX/PPSX 演示文稿批量转换为结构化 Markdown。先用 LibreOffice 将 PPTX 转 PDF，再委托 pdf-to-md skill 完成文字提取、嵌入图保存和 Vision 描述。本 Skill 是薄包装层，所有文字/图片处理逻辑统一由 pdf-to-md 维护——无需单独 API Key。当用户提到"PPTX转Markdown"、"PPT转笔记"、"演示文稿提取"、"幻灯片转md"、"PPT转Markdown"时，务必使用本 Skill。
---
# PPTX → Markdown

本 Skill 是 **pdf-to-md 的薄包装层**：PPTX/PPSX 先经 LibreOffice 转 PDF，
然后整批委托 `pdf_to_md.py` 处理。文字提取、嵌入大图保存、Vision 描述等所有
能力统一由 pdf-to-md 维护——避免重复实现，pdf-to-md 的优化自动惠及 PPTX。

## 流程

```
PPTX/PPSX → PDF (LibreOffice headless) → pdf-to-md 标准流程
                                          ├─ 原生文字 → pymupdf 直提（默认路径）
                                          ├─ 扫描/低文字密度 PDF → 自动 fork PaddleOCR
                                          │   （设置 PADDLEOCR_TOKEN 后启用）
                                          ├─ 嵌入大图 → 保存到磁盘 + 占位符
                                          └─ Agent 用 Vision 填写图片描述
```

LibreOffice 转出的 PDF 通常是**原生文字 PDF**（幻灯片文字保留为 PDF text objects），
所以会走 pdf-to-md 的快速路径——零 OCR 消耗，秒级完成。如果遇到从扫描图嵌入而成的
"图片型"幻灯片，`pdf_to_md.py` 会自动把整个 PDF 交给 `ocr_extract.py`（PaddleOCR
异步 API，直接吃 PDF）。

## Workflow（agent 模式 — 默认，零配置）

```bash
~/.venvs/general/bin/python \
  ~/.cc-switch/skills/pptx-to-md/scripts/pptx_to_md.py \
  --input "<pptx_or_dir>" \
  --output "<output_dir>"
```

执行两阶段：

1. **Phase 1（PPTX → PDF）**：逐个调用 `soffice --convert-to pdf`，
   独立 profile 隔离防 lock 冲突，120 秒超时
2. **Phase 2（PDF → MD）**：一次性调用 `pdf_to_md.py --input <pdf_dir> --output <output>`
   批处理所有 PDF

输出（与 pdf-to-md 一致）：

- `<output_dir>/<stem>.md` — 文字 + <code>![](…)</code> 图片占位符
- `<output_dir>/<stem>/imgs/img_NNN.{ext}` — 提取的嵌入大图（持久保存）

之后由 Claude agent 用内置 Vision 填写 `![](...)` 占位符（参考 pdf-to-md SKILL.md
的 Step 1b）：

- **≤ 5 张**：直接用 Read tool 逐张读取，Edit 替换占位符
- **> 5 张**：spawn subagents（每个 10–20 张），图片字节只进 subagent 上下文

## Standalone 模式（后台 / cron）

```bash
~/.venvs/general/bin/python \
  ~/.cc-switch/skills/pptx-to-md/scripts/pptx_to_md.py \
  --input deck.pptx --output out/ \
  --api-key sk-ant-... \
  --model claude-haiku-4-5-20251001
```

`--api-key` 透传给 `pdf_to_md.py`，由其自行调用 Vision。

也可用环境变量统一覆盖模型：`export DOCS_TO_WIKI_MODEL=claude-sonnet-4-6`

## 关键参数（均透传给 pdf_to_md.py）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--large-image-kb` | 30 | 嵌入图超过此值（KB）才提取/描述 |
| `--no-images` | — | 纯文字模式，跳过所有图片，零 API 消耗 |
| `--max-images` | 50 | 单文档图片数上限（费用保护） |
| `--api-key` | — | 传入则启用 standalone 模式 |
| `--model` | `DOCS_TO_WIKI_MODEL` / `claude-haiku-4-5-20251001` | Vision 模型 |
| `--pdf-dir` | — | 持久化中间 PDF 到该目录（默认走 tempdir，处理完删除） |
| `--no-ocr-fallback` | — | 禁用扫描件自动 OCR（透传给 `pdf_to_md.py`） |

## 环境

- `~/.venvs/general/bin/python`：含 `pymupdf`、`requests`（pdf-to-md 依赖）
- LibreOffice（命令 `soffice`，macOS: `brew install --cask libreoffice`）
- `PADDLEOCR_TOKEN`（可选）：设置后，扫描型幻灯片会自动走 PaddleOCR fallback
- `anthropic` 包 + `ANTHROPIC_API_KEY`：仅 standalone 模式（`--api-key`）需要
- `DOCS_TO_WIKI_MODEL`（可选）：standalone 模式统一覆盖模型
- **依赖 pdf-to-md skill**：本 Skill 调用 `~/.cc-switch/skills/pdf-to-md/scripts/pdf_to_md.py`，
  两个 skill 必须一起安装

## 注意事项

- **视觉布局简化**：本 Skill 走 PDF 文字路径，PPTX 中通过空间布局表达的信息
  （流程图箭头、左右对比、架构图连接线）在 PDF 文字化后变成线性阅读顺序，
  会丢失部分视觉关系。如果幻灯片本来就是图片导出（无文字层），`pdf_to_md.py`
  会自动走 OCR fallback——版式信息靠 PaddleOCR 的 layout 还原
- LibreOffice profile 隔离（`-env:UserInstallation`）已内建，多次运行不冲突
- 也支持 `.ppsx` 格式
- 嵌入图持久保存在 `<stem>/imgs/`，agent 可在任意时间点 Read
- PPTX 转 PDF 失败时，写入 `*[PDF conversion failed]*` 占位 .md，继续处理其他文件
