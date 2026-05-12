---
name: docs-to-wiki
description: >
  Converts a directory of business documents (PPTX, PDF, DOCX) into a
  structured Obsidian-compatible wiki knowledge base. Orchestrates three
  atomic conversion skills (pdf-to-md, docx-to-md, pptx-to-md) plus
  parallel batch OCR, source merging, and LLM-synthesized wiki pages.
  Use this skill whenever the user wants to build a knowledge base, wiki,
  or Obsidian vault from a folder of slides, reports, or documents — even
  if they say "process these docs", "make a knowledge base", "turn our
  slides into something searchable", or similar. Especially useful for
  large corporate document corpuses (50–1000+ files).
---

# Docs → Wiki Pipeline

This skill is an **orchestrator**. The actual format conversion is delegated
to three single-purpose atomic skills:

| Atomic skill | Handles | Method |
|--------------|---------|--------|
| `pdf-to-md` (`~/.cc-switch/skills/pdf-to-md/`) | PDF (text + scanned), images | pymupdf direct + PaddleOCR fallback |
| `docx-to-md` (`~/.cc-switch/skills/docx-to-md/`) | DOCX | python-docx + Vision for large images |
| `pptx-to-md` (`~/.cc-switch/skills/pptx-to-md/`) | PPTX/PPSX | per-slide PNG + Vision |

`docs-to-wiki` adds: collection, parallel batch OCR, output merging,
source-link rebuilding, and the wiki synthesis stage on top of those.

## Quick Reference

| Stage | Script / Skill | Time |
|-------|---------------|------|
| 0. Gather parameters | — | minutes |
| 1. Collect | `01_collect_docs.py` | seconds |
| 2a. DOCX → MD | `docx-to-md` skill | ~2s/doc + Vision |
| 2b. PPTX → MD | `pptx-to-md` skill | ~10s/file (5 slides parallel) |
| 2b†. PPTX→PDF fallback | `02_convert_to_pdf.py` | ~5 min/100 files |
| 2c. Native PDF → MD | `pdf-to-md` skill (Step 1) | ~1s/page, instant |
| 3. OCR (scanned PDF) | `03_run_ocr.py` (parallel wrapper around `pdf-to-md` Step 2) | ~3 hrs/400 files |
| 3†. OCR retry | `04_run_ocr_remaining.py` | varies |
| 4. Merge OCR | `05_merge_ocr.py` | seconds |
| 5. Build wiki | (inline instructions) | ~20 min |
| 6. Post-process | `06_rebuild_source_links.py` | seconds |
| 7. Pipeline report | (inline, write to `pipeline_report.md`) | minutes |

Orchestration scripts are in `~/.claude/skills/docs-to-wiki/scripts/`.
Atomic skill scripts live inside their own skill directories.
All scripts accept `--help` for usage.

---

## Step 0 — Gather Parameters

Before running anything, confirm with the user:

```
SOURCE_DIR     the root directory containing the documents
COMPANY_NAME   display name used in the wiki (e.g. "数美科技")
WIKI_DIR       where to create the wiki (default: SOURCE_DIR/../<slug>_wiki)
WORKERS        parallel workers for LibreOffice and OCR (default: 4)
```

Check for credentials:
- `ANTHROPIC_API_KEY` — required for Vision-based DOCX/PPTX extraction
- `PADDLEOCR_TOKEN` / `PADDLEOCR_API_URL` — required for scanned PDF OCR

Also check `DOCS_TO_WIKI_MODEL`. If not set, ask the user:

> 请问要用哪个 Claude 模型进行 Vision 处理？直接回车使用默认（`claude-haiku-4-5-20251001`）。

- User provides a model name → pass `--model <name>` to all atomic skill commands below
- User presses Enter → omit `--model`; scripts use the built-in default

---

## Stage 1 — Collect Documents

```bash
python ~/.claude/skills/docs-to-wiki/scripts/01_collect_docs.py \
  --source SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_staging
```

Collects PPTX, PDF, DOCX, PPSX. Skips Excel/CSV, hidden files, temp files
(`~$` prefix), and the wiki/OCR output directories themselves.
Creates a flat staging directory with sanitized filenames (path separators
replaced with `__`).

Report: total collected, format breakdown.

---

## Stage 2a — DOCX → Markdown (delegate to `docx-to-md`)

```bash
export ANTHROPIC_API_KEY="..."
~/.venvs/paddleocr/bin/python \
  ~/.cc-switch/skills/docx-to-md/scripts/docx_to_md.py \
  --input SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_sources_tmp/ \
  --large-image-kb 30 \
  --model claude-haiku-4-5-20251001
```

The `docx-to-md` skill writes one `.md` per DOCX directly into the output
directory. See `~/.cc-switch/skills/docx-to-md/SKILL.md` for full flag reference.

After it runs, move each `.md` into the per-doc folder layout that the
wiki-build stage expects:
```
<slug>_sources/<docname>/<docname>.md
```

---

## Stage 2b — PPTX/PPSX → Markdown (delegate to `pptx-to-md`)

```bash
export ANTHROPIC_API_KEY="..."
~/.venvs/paddleocr/bin/python \
  ~/.cc-switch/skills/pptx-to-md/scripts/pptx_to_md.py \
  --input SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_sources_tmp/ \
  --dpi 150 \
  --concurrent 5 \
  --model claude-haiku-4-5-20251001
```

See `~/.cc-switch/skills/pptx-to-md/SKILL.md` for full flag reference (dpi,
concurrent, max-slides, model).

### Stage 2b (fallback) — PPTX/PPSX → PDF only (no Vision)

If Vision is not available or cost is a concern, fall back to LibreOffice PDF
conversion and let PaddleOCR handle it via Stage 3:

```bash
python ~/.claude/skills/docs-to-wiki/scripts/02_convert_to_pdf.py \
  --source SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_pdf \
  --workers WORKERS
```

---

## Stage 2c — Native Text PDF → Markdown (delegate to `pdf-to-md` Step 1)

Run on original PDF files. The `pdf-to-md` skill auto-detects text vs scanned
and only outputs `.md` for text PDFs (scanned ones are skipped, to be picked
up by Stage 3).

```bash
~/.venvs/paddleocr/bin/python \
  ~/.cc-switch/skills/pdf-to-md/scripts/pdf_to_md.py \
  --input SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_sources_tmp/ \
  --large-image-kb 30
```

See `~/.cc-switch/skills/pdf-to-md/SKILL.md` for the full PDF → MD workflow.

---

## Stage 3 — OCR for Scanned PDFs (parallel wrapper around `pdf-to-md` Step 2)

The atomic skill's OCR script runs sequentially. For large corpora,
`docs-to-wiki` adds a parallel batch wrapper:

```bash
export PADDLEOCR_TOKEN="..."
export PADDLEOCR_API_URL="..."
python ~/.claude/skills/docs-to-wiki/scripts/03_run_ocr.py \
  --pdf-dir SOURCE_DIR/../<slug>_pdf \
  --original-pdf-dir SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_ocr \
  --workers WORKERS \
  --batch-size 25
```

Internally calls `~/.cc-switch/skills/pdf-to-md/scripts/ocr_extract.py` in
parallel batches. Deduplicates by filename stem.

After it finishes, run the retry script to catch any that failed or timed out:

```bash
python ~/.claude/skills/docs-to-wiki/scripts/04_run_ocr_remaining.py \
  --pdf-dir SOURCE_DIR/../<slug>_pdf \
  --original-pdf-dir SOURCE_DIR \
  --ocr-output SOURCE_DIR/../<slug>_ocr \
  --workers WORKERS \
  --batch-size 25
```

The retry script checks what's already been processed and only runs what's missing.
Repeat until the remaining count is stable.

---

## Stage 4 — Merge OCR Output

```bash
python ~/.claude/skills/docs-to-wiki/scripts/05_merge_ocr.py \
  --ocr-dir SOURCE_DIR/../<slug>_ocr \
  --output SOURCE_DIR/../<slug>_sources
```

Consolidates batch/remaining subdirectories from OCR plus the per-doc `.md`
files from Stages 2a/2b/2c into a flat structure:
```
<slug>_sources/
  <docname>/
    <docname>.md
    imgs/             ← extracted images (inline in the .md, OCR path only)
```

---

## Stage 5 — Build Wiki

This is the core synthesis stage. Read `references/wiki-build-guide.md` for
the full instructions before starting.

High-level steps:
1. Sample ~20 source doc names to understand the domain
2. Design wiki categories and write a `classify()` function
3. Build the source map
4. Initialize wiki structure (CLAUDE.md, index.md, log.md)
5. Spawn parallel sub-agents (one per category group) to write wiki pages
6. Move `<slug>_sources/` into `wiki/sources/`
7. Run `06_rebuild_source_links.py` to convert plain-text 来源 to wikilinks

---

## Stage 6 — Post-process Wikilinks

```bash
~/.venvs/paddleocr/bin/python \
  ~/.claude/skills/docs-to-wiki/scripts/06_rebuild_source_links.py \
  --wiki-dir WIKI_DIR
```

Reads each wiki page's YAML frontmatter `sources:` list, and replaces the
`## 来源` section with proper `[[sources/xxx|display_name]]` wikilinks.
Requires `pyyaml`.

---

## Stage 7 — Pipeline Report

After post-processing, write `WIKI_DIR/pipeline_report.md` with:

- **Raw file collection**: count by format (PPTX/PDF/DOCX/etc.)
- **Format conversion**: count by atomic skill (docx-to-md / pptx-to-md / pdf-to-md text path)
- **OCR**: input PDFs, success, failure, success rate, images extracted, size
- **Wiki**: page count by category, source coverage rate
- **Directory structure**: final tree

See `references/pipeline-report-template.md` for the exact format.

---

## Important Notes

- **Atomic skills are independent** — `pdf-to-md`, `docx-to-md`, `pptx-to-md`
  can each be invoked directly by the user without `docs-to-wiki`. Don't
  duplicate their conversion logic here; always delegate.
- **Never add bulk image galleries** to wiki pages. Source files already
  have images inline at logical positions. Wiki pages are text-only synthesis;
  readers click into `sources/` to see illustrated content.
- **Sub-agents must write each page immediately after reading its sources** —
  do not batch all reads before writing, or agents will stall.
- **OCR is idempotent**: the retry script checks for existing output, so it's
  safe to run multiple times after network interruptions.
