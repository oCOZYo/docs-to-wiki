#!/usr/bin/env python3
"""Convert DOCX to Markdown with Vision-enhanced image understanding.

Text, headings, and tables are extracted directly via python-docx (lossless).
Embedded images larger than the threshold are sent to Claude Vision for
a markdown description inserted at their original position in the document.

Usage:
  python convert_docx_to_md.py --input file.docx --output ./out/
  python convert_docx_to_md.py --input file.docx --output ./out/ --no-vision
  python convert_docx_to_md.py --input file.docx --output ./out/ --large-image-kb 50 --model claude-haiku-4-5-20251001
"""
import argparse
import base64
import os
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError:
    sys.exit("ERROR: pip install python-docx")

VISION_PROMPT = (
    "请描述这张图片的完整内容。"
    "如果是流程图或架构图，描述各节点名称和它们之间的连接关系（箭头方向、流程顺序）；"
    "如果是图表或数据表，提取关键数字、坐标轴标签和趋势；"
    "如果是界面截图，描述关键功能区域和显示的数据；"
    "如果是对比图，说明左右/上下各自代表什么及其差异。"
    "直接输出 Markdown 格式内容，不要添加前言或后记。"
)

# Bytes that identify raster image formats we can send to Vision
RASTER_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"GIF8": "image/gif",
    b"BM": "image/bmp",
    b"RIFF": "image/webp",  # RIFF....WEBP
}


def detect_media_type(blob: bytes) -> str | None:
    for sig, mime in RASTER_SIGNATURES.items():
        if blob[: len(sig)] == sig:
            return mime
    return None


def iter_block_items(doc: Document):
    """Yield Paragraph and Table objects in document body order."""
    from docx.oxml.ns import qn as _qn

    body = doc.element.body
    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def heading_prefix(para: Paragraph) -> str:
    style = para.style.name if para.style else ""
    if style.startswith("Heading"):
        try:
            level = int(style.split()[-1])
            return "#" * min(level, 6) + " "
        except ValueError:
            pass
    return ""


def para_to_md(para: Paragraph) -> str:
    prefix = heading_prefix(para)
    text = para.text.strip()
    if not text:
        return ""
    return prefix + text


def table_to_md(table: Table) -> str:
    rows = []
    for i, row in enumerate(table.rows):
        cells = [c.text.strip().replace("\n", " ") for c in row.cells]
        rows.append("| " + " | ".join(cells) + " |")
        if i == 0:
            rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(rows)


def extract_images_from_para(para: Paragraph, doc: Document) -> list[tuple[str, bytes]]:
    """Return list of (relationship_id, blob) for all inline images in the paragraph."""
    images = []
    for blip in para._element.findall(".//" + qn("a:blip")):
        r_id = blip.get(qn("r:embed"))
        if not r_id:
            continue
        try:
            part = doc.part.related_parts[r_id]
            images.append((r_id, part.blob))
        except (KeyError, AttributeError):
            pass
    return images


def call_vision(blob: bytes, media_type: str, model: str, client) -> str:
    b64 = base64.standard_b64encode(blob).decode()
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }
        ],
    )
    return resp.content[0].text.strip()


def convert(
    docx_path: Path,
    output_dir: Path,
    use_vision: bool,
    large_image_kb: int,
    model: str,
    max_images: int,
) -> Path:
    doc = Document(str(docx_path))
    client = None
    if use_vision:
        try:
            import anthropic
            client = anthropic.Anthropic()
        except ImportError:
            print("WARNING: anthropic not installed — falling back to --no-vision")
            use_vision = False

    threshold = large_image_kb * 1024
    lines: list[str] = []
    images_processed = 0

    for block in iter_block_items(doc):
        if isinstance(block, Table):
            md = table_to_md(block)
            if md:
                lines.append(md)
                lines.append("")
        elif isinstance(block, Paragraph):
            # Check for embedded images first
            if use_vision and images_processed < max_images:
                for r_id, blob in extract_images_from_para(block, doc):
                    if len(blob) < threshold:
                        continue
                    media_type = detect_media_type(blob)
                    if not media_type:
                        continue  # skip EMF/WMF/vector
                    try:
                        description = call_vision(blob, media_type, model, client)
                        lines.append(f"\n> **[图片]**\n>\n{description}\n")
                        images_processed += 1
                        if images_processed >= max_images:
                            lines.append(
                                f"\n> *（达到单文档最大图片处理数 {max_images}，"
                                "后续图片已跳过）*\n"
                            )
                    except Exception as e:
                        lines.append(f"\n> *[图片处理失败: {e}]*\n")

            text = para_to_md(block)
            if text:
                lines.append(text)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / (docx_path.stem + ".md")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="DOCX file or directory of DOCX files")
    ap.add_argument("--output", required=True, help="Output directory for .md files")
    ap.add_argument(
        "--large-image-kb",
        type=int,
        default=30,
        help="Images larger than this (KB) are sent to Vision (default: 30)",
    )
    ap.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Claude model for Vision calls",
    )
    ap.add_argument(
        "--max-images",
        type=int,
        default=50,
        help="Max images to process per document (cost guard)",
    )
    ap.add_argument(
        "--no-vision",
        action="store_true",
        help="Disable Vision calls (text-only extraction)",
    )
    args = ap.parse_args()

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    use_vision = not args.no_vision

    if not os.environ.get("ANTHROPIC_API_KEY") and use_vision:
        print("WARNING: ANTHROPIC_API_KEY not set — Vision calls will fail")

    docx_files = (
        sorted(input_path.glob("*.docx"))
        if input_path.is_dir()
        else [input_path]
    )

    if not docx_files:
        print("No DOCX files found.")
        return

    total_images = 0
    for i, docx_path in enumerate(docx_files, 1):
        print(f"[{i}/{len(docx_files)}] {docx_path.name} ...", end=" ", flush=True)
        out = convert(
            docx_path,
            output_dir,
            use_vision=use_vision,
            large_image_kb=args.large_image_kb,
            model=args.model,
            max_images=args.max_images,
        )
        # Count vision calls made (rough: count "> **[图片]**" in output)
        content = out.read_text(encoding="utf-8")
        n_imgs = content.count("> **[图片]**")
        total_images += n_imgs
        print(f"done ({n_imgs} images described)")

    print(f"\nTotal: {len(docx_files)} docs, {total_images} images described → {output_dir}")


if __name__ == "__main__":
    main()
