---
name: pptx-to-md
description: Convert PPTX/PPSX presentations to structured Markdown by rendering each slide as a PNG with intelligent per-slide processing. Text-heavy slides with tables and dense content are routed through PaddleOCR for precise text extraction and layout analysis; visual slides (diagrams, charts, flowcharts) are described via Claude Vision. Preserves spatial relationships that shape-text extraction (markitdown, pandoc) silently drops. No separate API key required. Use this skill whenever the user wants to convert slides to Markdown, extract content from a presentation, or process decks into notes — even if they say "PPT → md", "extract these slides", or "turn this deck into a doc".
---

# PPTX → Markdown

PPTX information lives in visual layout — side-by-side comparisons, flowchart arrows, charts, dense tables. Plain shape-text extraction silently drops this structure. This skill renders each slide as a PNG, then intelligently routes it: visual slides go through Claude Vision, text-heavy slides get PaddleOCR's precise layout analysis first.

## Pipeline

```
PPTX → PDF (LibreOffice) → per-slide PNG (pymupdf, 150 dpi) → .md with ![](...) placeholders
→ classify slides → route by type → fill in descriptions
```

## Workflow (agent mode — default, zero config)

### Step 1 — Run the renderer

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pptx_to_md.py" \
  --input <pptx_or_dir> \
  --output <output_dir>
```

Output:
- `<output_dir>/<stem>.md` — one `## Slide N` section per slide with `![](...)` placeholder
- `<output_dir>/<stem>/slides/slide_NNN.png` — per-slide images

### Step 2 — Classify slides

Before describing slides, classify each one to determine the best processing path. Spawn a subagent to read all PNGs and classify them:

**Subagent prompt:**
> Read each slide PNG in this list and classify into one of three types:
>
> **Type A — visual**: cover slides, transition slides, architecture diagrams, flowcharts, charts, infographics, side-by-side comparisons. Content is primarily visual/spatial.
>
> **Type B — text_heavy**: slides with dense text, bullet lists, multi-column text, data tables, comparison tables, scorecards, or any content where text accuracy is critical. A slide is "text_heavy" if it has more than ~50 words of visible text or contains table structures.
>
> **Type C — minimal**: mostly blank, logos only, or very simple (single sentence + background image).
>
> Return a JSON array: `[{path, type, reason}]` where type is "visual" / "text_heavy" / "minimal".

### Step 3 — Process by type

**Type A (visual) and Type C (minimal)** — use Vision directly:
- Read the PNG with the Read tool
- Describe the full content: title, subtitle, diagram nodes & connections, chart values & trends, comparison layout
- For ≤5 visual slides: describe inline in the main agent
- For >5: spawn subagents (10–20 slides each)

**Type B (text_heavy)** — use PaddleOCR + Vision for best accuracy:
1. Run PaddleOCR to extract precise text and layout structure:

   **Cloud mode** (no local setup, requires API credentials):
   ```bash
   export PADDLEOCR_TOKEN="..."
   export PADDLEOCR_API_URL="..."
   python3 "${CLAUDE_SKILL_DIR}/scripts/slide_ocr.py" <slide.png>
   ```

   **Local mode** (MLX VLM server with PaddleOCR-VL, no API key needed):
   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/slide_ocr.py" <slide.png> \
     --server_url http://localhost:8111/
   ```
2. Read the PNG with the Read tool (for visual elements)
3. Combine both: use PaddleOCR's extracted text as the authoritative source for text content, and Vision for understanding diagrams/charts/visual elements that PaddleOCR can't interpret

The PaddleOCR output provides:
- Exact text transcription (no hallucination)
- Layout structure (reading order, multi-column detection)
- Table structure (rows, columns, cell contents)

Vision provides:
- Diagram/chart interpretation (node relationships, data trends)
- Visual context (colors, positions, emphasis)
- Non-text content understanding

### Step 4 — Merge into the Markdown

Replace each `![](...)` placeholder with the synthesized description. For text_heavy slides, the description should lead with the OCR-extracted text (preserving accuracy), then add Vision's visual interpretation of any diagrams/charts.

Example for a text_heavy slide:
```markdown
## Slide 5

> **[slide]**
>
> **核心算法 - 半监督图挖掘算法--半监督算法**
>
> AI算法决策层将AI算法和业务经验深度融合，实现了多个算法在审计领域的落地应用...
>
> *(visual: the slide shows a triangular diagram with nodes representing different entity types — 风险客户, 各类型客户, 监测客户 — mapped against an algorithm decision boundary)*
```

## Standalone mode (backend / cron)

For headless automation outside Claude Code, pass `--api-key` to have the script call Vision itself with parallel requests:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/pptx_to_md.py" \
  --input deck.pptx --output out/ \
  --api-key sk-ant-... --model claude-haiku-4-5 --concurrent 5
```

## Flags

| Flag | Default | Notes |
|------|---------|-------|
| `--dpi` | `150` | Slide render resolution. 100 for text-heavy decks; 200 for dense diagrams. |
| `--max-slides` | `200` | Per-file slide cap (cost guard). |
| `--api-key` | — | Standalone mode (script calls Vision). Default is agent mode. |
| `--model` | `claude-haiku-4-5` | Vision model when `--api-key` is set. |
| `--concurrent` | `5` | Parallel Vision calls per file in standalone mode. |

## Requirements

- Python 3.10+ with `pymupdf`
- LibreOffice (`soffice` command). macOS: `brew install --cask libreoffice`. Debian/Ubuntu: `apt install libreoffice`.
- For PaddleOCR routing on text-heavy slides (choose one):
  - **Cloud**: `pip install requests` + `PADDLEOCR_TOKEN` / `PADDLEOCR_API_URL` (free tier at https://aistudio.baidu.com/paddleocr)
  - **Local**: `pip install paddleocr[doc-parser]` + MLX VLM server running PaddleOCR-VL
- For `--api-key` standalone mode only: `pip install anthropic`

## Notes

- LibreOffice's `--convert-to png` only exports the first slide on macOS, so this skill uses the PDF → PNG route (which works reliably).
- LibreOffice profile isolation (`-env:UserInstallation`) is built in — safe for concurrent runs.
- `.ppsx` is supported the same way as `.pptx`.
- PaddleOCR routing is optional but recommended for text-heavy decks — Vision alone may miss or hallucinate text in dense slides.
