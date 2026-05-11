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
| `pdf-to-md` (`${CLAUDE_SKILL_DIR}/../pdf-to-md/`) | PDF (text + scanned), images | pymupdf direct + PaddleOCR fallback |
| `docx-to-md` (`${CLAUDE_SKILL_DIR}/../docx-to-md/`) | DOCX | python-docx + agent Vision for images |
| `pptx-to-md` (`${CLAUDE_SKILL_DIR}/../pptx-to-md/`) | PPTX/PPSX | per-slide PNG + agent Vision |

`docs-to-wiki` adds: collection, parallel batch OCR, output merging,
source-link rebuilding, and the wiki synthesis stage on top of those.

## Quick Reference

| Stage | Script / Skill | Time |
|-------|---------------|------|
| 1. Collect | `${CLAUDE_SKILL_DIR}/scripts/01_collect_docs.py` | seconds |
| 2a. DOCX → MD | `docx-to-md` skill | ~2s/doc |
| 2b. PPTX → MD | `pptx-to-md` skill | ~10s/file |
| 2b†. PPTX→PDF fallback | `${CLAUDE_SKILL_DIR}/scripts/02_convert_to_pdf.py` | ~5 min/100 files |
| 2c. Native PDF → MD | `pdf-to-md` skill (Step 1) | ~1s/page |
| 3. OCR (scanned PDF) | `${CLAUDE_SKILL_DIR}/scripts/03_run_ocr.py` | ~3 hrs/400 files |
| 4. OCR retry | `${CLAUDE_SKILL_DIR}/scripts/04_run_ocr_remaining.py` | varies |
| 5. Merge | `${CLAUDE_SKILL_DIR}/scripts/05_merge_ocr.py` | seconds |
| 6. Build wiki | (inline instructions) | ~20 min |
| 7. Post-process | `${CLAUDE_SKILL_DIR}/scripts/06_rebuild_source_links.py` | seconds |

All scripts accept `--help` for usage.

---

## Step 0 — Gather Parameters

Before running anything, confirm with the user:

```
SOURCE_DIR     the root directory containing the documents
COMPANY_NAME   display name used in the wiki (e.g. "Acme Corp")
WIKI_DIR       where to create the wiki (default: SOURCE_DIR/../<slug>_wiki)
WORKERS        parallel workers for LibreOffice and OCR (default: 4)
```

Check for credentials:
- `PADDLEOCR_TOKEN` / `PADDLEOCR_API_URL` — required for scanned PDF OCR and PPTX text-heavy slide routing (free tier at https://aistudio.baidu.com/paddleocr)

No API key is needed for format conversion — the agent describes images using its built-in Vision capability.

---

## Stage 1 — Collect Documents

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/01_collect_docs.py" \
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
python3 "${CLAUDE_SKILL_DIR}/../docx-to-md/scripts/docx_to_md.py" \
  --input SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_sources_tmp/ \
  --large-image-kb 30
```

In agent mode (default), `docx_to_md.py` extracts text and tables, saves
large images to disk, and emits `![](...)` placeholders in the Markdown.
After conversion completes, describe the images using your Read tool or
subagents — see `docx-to-md/SKILL.md` Step 2 for the exact procedure.

After it runs, move each `.md` into the per-doc folder layout that the
wiki-build stage expects:
```
<slug>_sources/<docname>/<docname>.md
```

---

## Stage 2b — PPTX/PPSX → Markdown (delegate to `pptx-to-md`)

```bash
python3 "${CLAUDE_SKILL_DIR}/../pptx-to-md/scripts/pptx_to_md.py" \
  --input SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_sources_tmp/ \
  --dpi 150
```

In agent mode, each slide is rendered as a PNG and referenced via
`![](...)` placeholders. The pptx-to-md skill uses intelligent routing:
visual slides are described via Vision, text-heavy slides are first processed
by PaddleOCR for precise text extraction. See `pptx-to-md/SKILL.md` Steps 2–4.

### Stage 2b (fallback) — PPTX/PPSX → PDF only

If you prefer to skip per-slide rendering and let PaddleOCR handle
everything, convert to PDF first:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/02_convert_to_pdf.py" \
  --source SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_pdf \
  --workers WORKERS
```

---

## Stage 2c — Native Text PDF → Markdown (delegate to `pdf-to-md`)

Run on original PDF files. The `pdf-to-md` skill auto-detects text vs scanned
and only outputs `.md` for text PDFs (scanned ones are skipped, to be picked
up by Stage 3).

```bash
python3 "${CLAUDE_SKILL_DIR}/../pdf-to-md/scripts/pdf_to_md.py" \
  --input SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_sources_tmp/ \
  --large-image-kb 30
```

---

## Stage 3 — OCR for Scanned PDFs

The atomic skill's OCR script runs sequentially. For large corpora,
`docs-to-wiki` adds a parallel batch wrapper:

```bash
export PADDLEOCR_TOKEN="..."
export PADDLEOCR_API_URL="..."
python3 "${CLAUDE_SKILL_DIR}/scripts/03_run_ocr.py" \
  --pdf-dir SOURCE_DIR/../<slug>_pdf \
  --original-pdf-dir SOURCE_DIR \
  --output SOURCE_DIR/../<slug>_ocr \
  --workers WORKERS \
  --batch-size 25
```

Internally calls `pdf-to-md/scripts/ocr_extract.py` in parallel batches.
Deduplicates by filename stem.

After it finishes, run the retry script to catch any that failed or timed out:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/04_run_ocr_remaining.py" \
  --pdf-dir SOURCE_DIR/../<slug>_pdf \
  --original-pdf-dir SOURCE_DIR \
  --ocr-output SOURCE_DIR/../<slug>_ocr \
  --workers WORKERS \
  --batch-size 25
```

The retry script checks what's already been processed and only runs what's missing.
Repeat until the remaining count is stable.

---

## Stage 4 — Merge Output

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/05_merge_ocr.py" \
  --ocr-dir SOURCE_DIR/../<slug>_ocr \
  --output SOURCE_DIR/../<slug>_sources
```

Consolidates batch/remaining subdirectories from OCR plus the per-doc `.md`
files from Stages 2a/2b/2c into a flat structure:
```
<slug>_sources/
  <docname>/
    <docname>.md
    imgs/             ← extracted images (OCR path only)
```

---

## Stage 5 — Build Wiki

This is the core synthesis stage. Read `${CLAUDE_SKILL_DIR}/references/wiki-build-guide.md`
for the full instructions before starting.

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
python3 "${CLAUDE_SKILL_DIR}/scripts/06_rebuild_source_links.py" \
  --wiki-dir WIKI_DIR
```

Reads each wiki page's YAML frontmatter `sources:` list, and replaces the
`## Sources` / `## 来源` section with proper `[[sources/xxx|display_name]]` wikilinks.
Requires `pyyaml` (`pip install pyyaml`).

---

## Stage 7 — Pipeline Report

After post-processing, write `WIKI_DIR/pipeline_report.md` with:

- **Raw file collection**: count by format (PPTX/PDF/DOCX/etc.)
- **Format conversion**: count by atomic skill (docx-to-md / pptx-to-md / pdf-to-md text path)
- **OCR**: input PDFs, success, failure, success rate, images extracted, size
- **Wiki**: page count by category, source coverage rate
- **Directory structure**: final tree

See `${CLAUDE_SKILL_DIR}/references/pipeline-report-template.md` for the exact format.

---

## Important Notes

- **Atomic skills are independent** — `pdf-to-md`, `docx-to-md`, `pptx-to-md`
  can each be invoked directly without `docs-to-wiki`. Don't duplicate their
  conversion logic here; always delegate.
- **Never add bulk image galleries** to wiki pages. Source files already
  have images inline at logical positions. Wiki pages are text-only synthesis;
  readers click into `sources/` to see illustrated content.
- **Sub-agents must write each page immediately after reading its sources** —
  do not batch all reads before writing, or agents will stall.
- **OCR is idempotent**: the retry script checks for existing output, so it's
  safe to run multiple times after network interruptions.
