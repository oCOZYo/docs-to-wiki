#!/usr/bin/env python3
"""Convert native-text PDFs to Markdown via pymupdf (fast, no OCR needed).

Auto-detects whether a PDF has extractable text:
- Text PDF (avg >50 chars/page): extract directly — lossless, instant
- Scanned PDF (avg ≤50 chars/page): print warning, skip (use OCR instead)

Large embedded images (>threshold KB) are optionally sent to Claude Vision.

Usage:
  python convert_pdf_to_md.py --input file.pdf --output ./out/
  python convert_pdf_to_md.py --input docs/ --output ./out/ --no-vision
  python convert_pdf_to_md.py --input file.pdf --output ./out/ --large-image-kb 50
"""
import argparse
import base64
import os
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("ERROR: pip install pymupdf")

VISION_PROMPT = """这是一份PDF文档中的嵌入图片。请描述图片的完整内容：
- 如果是流程图/架构图：描述各节点名称和连接关系
- 如果是图表/数据：提取数值、坐标轴和趋势
- 如果是表格：完整输出为 Markdown 表格
- 如果是截图：描述关键内容和数据
直接输出 Markdown，不要添加引导语。"""

# Minimum avg chars/page to classify as text PDF
TEXT_THRESHOLD = 50


def is_text_pdf(doc: fitz.Document) -> tuple[bool, float]:
    total = sum(len(page.get_text()) for page in doc)
    avg = total / len(doc) if len(doc) else 0
    return avg > TEXT_THRESHOLD, avg


def median_font_size(blocks: list) -> float:
    sizes = []
    for b in blocks:
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                if span.get("text", "").strip():
                    sizes.append(span["size"])
    if not sizes:
        return 10.0
    sizes.sort()
    return sizes[len(sizes) // 2]


def heading_level(size: float, body: float) -> int:
    ratio = size / body if body else 1
    if ratio > 2.0:
        return 1
    if ratio > 1.5:
        return 2
    if ratio > 1.2:
        return 3
    return 0


def blocks_to_md(page: fitz.Page) -> str:
    data = page.get_text("dict")
    blocks = data.get("blocks", [])
    body = median_font_size(blocks)

    lines_out = []
    prev_y = None

    for b in blocks:
        if b.get("type") != 0:  # skip non-text blocks (images handled separately)
            continue

        block_lines = []
        for line in b.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            # Heading detection: use the dominant (largest) span size in the line
            max_size = max(s.get("size", 10) for s in spans)
            level = heading_level(max_size, body)
            if level:
                block_lines.append("#" * level + " " + text)
            else:
                block_lines.append(text)

        if block_lines:
            # Add blank line between blocks when there's vertical gap
            y0 = b["bbox"][1]
            if prev_y is not None and (y0 - prev_y) > body * 1.5:
                lines_out.append("")
            lines_out.extend(block_lines)
            prev_y = b["bbox"][3]

    return "\n".join(lines_out)


def extract_page_images(page: fitz.Page, doc: fitz.Document) -> list[bytes]:
    """Return blobs for images embedded in this page."""
    blobs = []
    for img in page.get_images(full=False):
        xref = img[0]
        try:
            info = doc.extract_image(xref)
            if info and info.get("image"):
                blobs.append(info["image"])
        except Exception:
            pass
    return blobs


def call_vision(blob: bytes, media_type: str, model: str, client) -> str:
    b64 = base64.standard_b64encode(blob).decode()
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
    )
    return resp.content[0].text.strip()


RASTER_SIGS = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"GIF8": "image/gif",
}


def detect_media_type(blob: bytes) -> str | None:
    for sig, mime in RASTER_SIGS.items():
        if blob[: len(sig)] == sig:
            return mime
    return None


def convert(
    pdf_path: Path,
    output_dir: Path,
    use_vision: bool,
    large_image_kb: int,
    model: str,
    max_images: int,
    client,
) -> tuple[Path | None, str]:
    """Convert one PDF. Returns (output_path, status) where status is 'text'|'scanned'|'error'."""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        return None, f"error: {e}"

    is_text, avg_chars = is_text_pdf(doc)
    if not is_text:
        doc.close()
        return None, f"scanned (avg {avg_chars:.0f} ch/pg)"

    threshold = large_image_kb * 1024
    images_processed = 0
    page_sections = []

    for page in doc:
        parts = []

        # Text content
        text_md = blocks_to_md(page)
        if text_md.strip():
            parts.append(text_md)

        # Large embedded images → Vision
        if use_vision and images_processed < max_images:
            for blob in extract_page_images(page, doc):
                if len(blob) < threshold:
                    continue
                media_type = detect_media_type(blob)
                if not media_type:
                    continue
                try:
                    desc = call_vision(blob, media_type, model, client)
                    parts.append(f"\n> **[图片]**\n>\n{desc}\n")
                    images_processed += 1
                except Exception as e:
                    parts.append(f"\n> *[图片处理失败: {e}]*\n")

        if parts:
            page_sections.append("\n\n".join(parts))

    doc.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / (pdf_path.stem + ".md")
    out.write_text("\n\n---\n\n".join(page_sections), encoding="utf-8")
    return out, f"text (avg {avg_chars:.0f} ch/pg, {images_processed} images)"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="PDF file or directory of PDFs")
    ap.add_argument("--output", required=True, help="Output directory for .md files")
    ap.add_argument("--large-image-kb", type=int, default=30,
                    help="Images larger than this (KB) sent to Vision (default: 30)")
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--max-images", type=int, default=50)
    ap.add_argument("--no-vision", action="store_true")
    args = ap.parse_args()

    use_vision = not args.no_vision
    client = None
    if use_vision:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("WARNING: ANTHROPIC_API_KEY not set — Vision disabled")
            use_vision = False
        else:
            try:
                import anthropic
                client = anthropic.Anthropic()
            except ImportError:
                print("WARNING: anthropic not installed — Vision disabled")
                use_vision = False

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    pdfs = (
        sorted(input_path.glob("*.pdf"))
        if input_path.is_dir()
        else [input_path]
    )

    if not pdfs:
        print("No PDF files found.")
        return

    skipped = converted = 0
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name} ...", end=" ", flush=True)
        out, status = convert(
            pdf, output_dir,
            use_vision=use_vision,
            large_image_kb=args.large_image_kb,
            model=args.model,
            max_images=args.max_images,
            client=client,
        )
        print(status)
        if out:
            converted += 1
        else:
            skipped += 1

    print(f"\nDone: {converted} converted, {skipped} skipped (scanned/error) → {output_dir}")
    if skipped:
        print("  Skipped files need PaddleOCR — run 03_run_ocr.py on them.")


if __name__ == "__main__":
    main()
