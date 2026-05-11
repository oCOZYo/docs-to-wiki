# Doc-to-MD Skills

[![Skills.sh](https://skills.sh/badge)](https://skills.sh/oCOZYo/doc-to-md-skills)

Three skills that convert business documents (PDF, DOCX, PPTX) to structured Markdown using Vision LLM.

## Install

```bash
npx skills add oCOZYo/doc-to-md-skills
```

## Skills

| Skill | Formats | Method |
|-------|---------|--------|
| [pdf-to-md](skills/pdf-to-md/) | PDF (native text + scanned), images | pymupdf direct + PaddleOCR fallback |
| [docx-to-md](skills/docx-to-md/) | DOCX | python-docx text/tables + Claude Vision for large images |
| [pptx-to-md](skills/pptx-to-md/) | PPTX, PPSX | per-slide PNG + Claude Vision |

## Prerequisites

```bash
# Python dependencies
pip install pymupdf python-docx anthropic requests

# For scanned PDF OCR (optional)
export PADDLEOCR_TOKEN="your_token"
export PADDLEOCR_API_URL="https://xxxx.aistudio-app.com/layout-parsing"

# For Vision features
export ANTHROPIC_API_KEY="your_key"
```

## Usage

Skills activate automatically when you mention the relevant format:

- "Convert this PDF to markdown" → `pdf-to-md`
- "Extract this Word document" → `docx-to-md`
- "Convert these slides to markdown" → `pptx-to-md`

Or use scripts directly:

```bash
python skills/pdf-to-md/scripts/pdf_to_md.py --input docs/ --output out/
python skills/docx-to-md/scripts/docx_to_md.py --input doc.docx --output out/
python skills/pptx-to-md/scripts/pptx_to_md.py --input slides.pptx --output out/
```

## Key Features

- **Auto-detection**: PDFs classified as text (>50 chars/page) or scanned automatically
- **Vision LLM**: Images, diagrams, slides described at their original position
- **Heading detection**: Font-size-based heading extraction from PDFs
- **Parallel processing**: PPTX slides processed concurrently
- **Cost control**: `--max-slides`, `--max-images`, `--large-image-kb` flags

## License

MIT
