# Doc-to-MD Skills for Claude Code

Three Claude Code skills that convert business documents to structured Markdown using Vision LLM.

## Skills

| Skill | Formats | Method |
|-------|---------|--------|
| **[pdf-to-md](pdf-to-md/)** | PDF (native text + scanned), images | pymupdf direct extraction + PaddleOCR fallback |
| **[docx-to-md](docx-to-md/)** | DOCX | python-docx text/tables + Claude Vision for large images |
| **[pptx-to-md](pptx-to-md/)** | PPTX, PPSX | per-slide PNG rendering + Claude Vision |

## Installation

```bash
# Clone the repo
git clone https://github.com/oCOZYo/doc-to-md-skills.git
cd doc-to-md-skills

# Install skills (pick what you need)
cp -r pdf-to-md ~/.cc-switch/skills/
cp -r docx-to-md ~/.cc-switch/skills/
cp -r pptx-to-md ~/.cc-switch/skills/
```

## Prerequisites

```bash
# Python venv with dependencies
pip install pymupdf python-docx anthropic requests

# For PDF OCR (scanned docs):
# Get token + API URL at https://aistudio.baidu.com/paddleocr
export PADDLEOCR_TOKEN="your_token"
export PADDLEOCR_API_URL="https://xxxx.aistudio-app.com/layout-parsing"

# For Vision features:
export ANTHROPIC_API_KEY="your_key"
```

## Usage

After installation, each skill activates automatically when you mention the relevant format in Claude Code:

- "Convert this PDF to markdown" → triggers `pdf-to-md`
- "Extract this Word document" → triggers `docx-to-md`
- "Convert these slides to markdown" → triggers `pptx-to-md`

Or use the scripts directly:

```bash
# PDF (auto-detects text vs scanned)
python pdf-to-md/scripts/pdf_to_md.py --input docs/ --output out/

# DOCX with Vision for images
python docx-to-md/scripts/docx_to_md.py --input doc.docx --output out/ --model claude-haiku-4-5

# PPTX (each slide → Vision description)
python pptx-to-md/scripts/pptx_to_md.py --input slides.pptx --output out/ --model claude-haiku-4-5
```

## Key Features

- **Auto-detection**: PDFs are classified as text (>50 chars/page) or scanned automatically
- **Vision LLM**: Large images, diagrams, and slides are described by Claude Vision at their original position in the document
- **Heading detection**: Font-size-based heading extraction from PDFs
- **Parallel processing**: PPTX files process slides concurrently (configurable workers)
- **Cost control**: `--max-slides`, `--max-images`, `--large-image-kb` flags to limit Vision API calls

## License

MIT
