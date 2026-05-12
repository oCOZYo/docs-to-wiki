---
name: pptx-to-md
description: 将 PPTX/PPSX 演示文稿批量转换为结构化 Markdown。每张幻灯片渲染为 PNG 保存到磁盘，可选 PaddleOCR 并行提取文字作为 Vision 上下文，生成逐页持久化的 per_page/slide_NNN.md 桩文件——由 Claude agent 填写描述后 --merge-only 合并，无需单独 API Key。支持中断续跑（resume）。当用户提到"PPTX转Markdown"、"PPT转笔记"、"演示文稿提取"、"幻灯片转md"、"PPT转Markdown"时，务必使用本 Skill。
---

# PPTX → Markdown

PPTX 中信息往往通过视觉布局（左右对比、流程图箭头、图表）呈现——单纯文字提取会丢失大量结构。本 Skill 将每张幻灯片渲染成 PNG，可选用 PaddleOCR 并行提取文字作为 Vision 提示词上下文，由 Claude agent 用内置 Vision 描述完整内容。**无需单独 Anthropic API Key**。

## 流程

```
PPTX → PDF (LibreOffice) → PNG 96dpi (pymupdf)
  → [可选] PaddleOCR 并行 OCR → per_page/slide_NNN.md 桩文件
  → Agent mode: subagents 填写 per_page MDs → --merge-only 合并
  → Standalone mode（仅用户明确要求）: Vision+OCR 单次调用 → 自动合并
```

## Workflow（agent 模式 — 默认，零配置）

### Step 1 — 运行渲染脚本

```bash
~/.venvs/general/bin/python \
  ~/.cc-switch/skills/pptx-to-md/scripts/pptx_to_md.py \
  --input "<pptx_or_dir>" \
  --output "<output_dir>"
```

输出：
- `<output_dir>/<stem>/slides/slide_NNN.png` — 96dpi PNG（持久保存，agent 可 Read）
- `<output_dir>/<stem>/per_page/slide_NNN.md` — 桩文件（含图片绝对路径 + OCR 文字，如有）
- `<output_dir>/<stem>.md` — 初步合并（桩状态，用于索引；最终由 --merge-only 更新）

若设置了 `PADDLEOCR_TOKEN` 和 `PADDLEOCR_API_URL`，脚本会自动并行 OCR 所有幻灯片，将文字写入桩文件供 Vision 参考。未设置则跳过 OCR，桩文件仍正常生成。

**桩文件格式示例**（含 OCR）：
```
<!-- pptx-to-md:stub -->
<!-- png: /Users/zen/out/deck/slides/slide_003.png -->

<!-- ocr:
顺丰统保项目背景
顺丰于2022年启动车辆全国统保项目...
-->
```

### Step 2 — 填写幻灯片描述

用 Read tool 读取桩文件（获取 PNG 绝对路径 + OCR 文字），再 Read 图片，Write 覆写桩文件。**按幻灯片数量选择策略**：

- **≤ 5 张**：直接逐张处理（见下方"单张处理方法"）
- **> 5 张**：spawn subagents，**每批 ≤ 8 张**（96dpi ≈ 300KB/张，base64 约 400KB，8 张 ≈ 3.2MB，远低于 32MB 限制）

**单张处理方法**（直接或 subagent 内执行）：

1. Read `per_page/slide_NNN.md`，提取：
   - 图片路径：第二行 `<!-- png: /absolute/path -->` 中的路径
   - OCR 文字（如有）：`<!-- ocr:` … `-->` 块内容
2. Read 图片（绝对路径）
3. 结合 OCR 文字（辅助核对词语）+ 图片内容，描述幻灯片：标题/副标题、正文层级、流程图节点与箭头、图表数值与坐标轴、对比布局、完整表格
4. Write **覆写** `per_page/slide_NNN.md`，写入纯 Markdown 描述  
   （**不要**写 `## Slide N` 标题；**不要**写 `![](...)` 图片链接；**不要**保留 sentinel）

**每个 Subagent Prompt 模板**（传入 ≤8 个 per_page 路径）：

> 对以下桩文件路径列表，按顺序逐一处理每张幻灯片：
>
> 路径：
> - /path/to/per_page/slide_003.md
> - /path/to/per_page/slide_004.md
> （最多 8 条）
>
> 对每个路径：
> 1. Read 该 .md 文件——第二行含图片绝对路径，`<!-- ocr: -->` 块含 OCR 文字（可能没有）
> 2. Read 图片（绝对路径）
> 3. 生成完整 Markdown 描述（标题、正文层级、流程图、图表数值、对比布局、完整表格）；参考 OCR 文字辅助识别词语
> 4. Write 覆写该 .md 文件，内容为纯 Markdown 描述，不含 sentinel、不含图片链接、不含 `## Slide N` 标题
>
> **Resume check**：Write 前先检查文件首行是否含 `<!-- pptx-to-md:stub -->`；若没有则跳过（已处理）。
>
> 所有幻灯片处理完毕后，报告处理了哪些路径（以便主 agent 确认）。

### Step 3 — 合并（所有 subagents 完成后）

```bash
~/.venvs/general/bin/python \
  ~/.cc-switch/skills/pptx-to-md/scripts/pptx_to_md.py \
  --input "<pptx_or_dir>" \
  --output "<output_dir>" \
  --merge-only
```

输出：`<output_dir>/<stem>.md`（每张幻灯片含 `## Slide N`、图片链接、Markdown 描述）

---

## Standalone 模式（仅用户明确要求时）

**何时使用**：仅当用户明确要求"无人值守批处理"、"后台运行"、"cron 定时任务"等场景时才使用。**即使环境中存在 `ANTHROPIC_API_KEY`，也不要自动传入 `--api-key`——默认始终走 Agent 模式。**

```bash
~/.venvs/general/bin/python \
  ~/.cc-switch/skills/pptx-to-md/scripts/pptx_to_md.py \
  --input deck.pptx --output out/ \
  --api-key sk-ant-... \
  --model claude-haiku-4-5-20251001 \
  --concurrent 5
```

Standalone 模式支持 resume：中途崩溃后重跑同一命令，自动跳过已填写的幻灯片。

询问用户选择模型（standalone 模式下）：
> 请问要用哪个 Claude 模型进行 Vision 处理？直接回车使用默认（`claude-haiku-4-5-20251001`）。

---

## 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--dpi` | 96 | 幻灯片渲染分辨率。文字为主用 72；密集图表用 120 |
| `--max-slides` | 200 | 单文件幻灯片数上限（费用保护） |
| `--merge-only` | — | 仅合并已有 per_page MDs，不重新渲染/OCR |
| `--ocr-concurrent` | 5 | 并行 OCR API 调用数 |
| `--no-resume` | — | 强制重新处理所有幻灯片（忽略已填写文件） |
| `--api-key` | — | Standalone 模式触发（仅用户明确要求时传入） |
| `--model` | `DOCS_TO_WIKI_MODEL` / `claude-haiku-4-5-20251001` | standalone 模式 Vision 模型 |
| `--concurrent` | 5 | standalone 模式并行 Vision 调用数 |

## 环境

- `~/.venvs/general/bin/python`：含 `pymupdf`、`requests`
- LibreOffice（命令 `soffice`，macOS: `brew install --cask libreoffice`）
- `PADDLEOCR_TOKEN` / `PADDLEOCR_API_URL`（可选，存在时启用 OCR 阶段）
- `anthropic` 包 + `ANTHROPIC_API_KEY`：仅 standalone 模式（`--api-key`）需要
- `DOCS_TO_WIKI_MODEL`（可选）：standalone 模式统一覆盖模型

## 注意事项

- LibreOffice 在 macOS 下 `--convert-to png` 只导出第一张幻灯片，因此本 Skill 走 PDF→PNG 路径
- LibreOffice profile 隔离（`-env:UserInstallation`）已内建，并行运行时不会发生 lock 冲突
- 也支持 `.ppsx` 格式
- **32MB 批次限制**：96dpi 时平均约 300KB/张，base64 后约 400KB，每批 8 张 ≈ 3.2MB，远低于 32MB 上限。高 DPI（120+）或内容密集时建议缩小批次（4–5 张）
- PNG 文件持久保存在 `<stem>/slides/`，per_page MDs 保存在 `<stem>/per_page/`，agent 可在任意时间点 Read
- **Resume**：重新运行脚本时，已 filled 的 per_page MD（无 sentinel）不会被覆写；已渲染的 PNGs 也不会重渲
