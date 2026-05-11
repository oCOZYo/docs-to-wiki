#!/usr/bin/env python3
"""OCR a single slide image via PaddleOCR API, returning structured text + layout.

Usage:
  python slide_ocr.py <image.png>

Requires PADDLEOCR_TOKEN and PADDLEOCR_API_URL environment variables.
Output: Markdown-formatted text with layout structure (headings, paragraphs, tables).
"""

import base64
import os
import sys
from pathlib import Path

def ocr_slide(image_path: Path) -> str:
    """Send image to PaddleOCR API, return structured Markdown text."""
    try:
        import requests
    except ImportError:
        sys.exit("ERROR: pip install requests")

    token = os.environ.get("PADDLEOCR_TOKEN", "")
    api_url = os.environ.get("PADDLEOCR_API_URL", "")
    if not token or not api_url:
        sys.exit("ERROR: Set PADDLEOCR_TOKEN and PADDLEOCR_API_URL")

    blob = image_path.read_bytes()
    b64 = base64.standard_b64encode(blob).decode()

    resp = requests.post(
        api_url,
        headers={"Authorization": f"Bearer {token}"},
        json={"image": f"data:image/png;base64,{b64}"},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()

    # Extract text blocks from PaddleOCR layout-parsing response
    lines = []
    for block in data.get("result", {}).get("blocks", []):
        category = block.get("category", "")
        text = block.get("text", "").strip()
        if not text:
            continue
        if category == "table":
            # Render table as Markdown if structured data available
            cells = block.get("cells", [])
            if cells:
                lines.append("")
                for row in cells:
                    lines.append("| " + " | ".join(str(c) for c in row) + " |")
                lines.append("")
            else:
                lines.append(f"\n```\n{text}\n```\n")
        elif category in ("heading", "title"):
            lines.append(f"\n### {text}\n")
        else:
            lines.append(text)

    return "\n".join(lines) if lines else "*[No text detected]*"


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: slide_ocr.py <image.png>")
    image_path = Path(sys.argv[1])
    if not image_path.exists():
        sys.exit(f"ERROR: File not found: {image_path}")
    result = ocr_slide(image_path)
    print(result)


if __name__ == "__main__":
    main()
