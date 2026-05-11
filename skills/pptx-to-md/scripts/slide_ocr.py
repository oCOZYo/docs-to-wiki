#!/usr/bin/env python3
"""OCR a single slide image via PaddleOCR, returning structured text + layout.

Two modes:

  Cloud (default, no local setup):
    export PADDLEOCR_TOKEN="your_token"
    export PADDLEOCR_API_URL="https://xxxx.aistudio-app.com/layout-parsing"
    python slide_ocr.py <image.png>

  Local (MLX VLM server with PaddleOCR-VL):
    python slide_ocr.py <image.png> --server_url http://localhost:8111/
    Or set env var: MLX_SERVER_URL=http://...

Output: Markdown-formatted text with layout structure (headings, paragraphs, tables).
"""

import base64
import os
import sys
from pathlib import Path


def ocr_slide_cloud(image_path: Path) -> str:
    """Send image to PaddleOCR cloud API, return structured Markdown text."""
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

    lines = []
    for block in data.get("result", {}).get("blocks", []):
        category = block.get("category", "")
        text = block.get("text", "").strip()
        if not text:
            continue
        if category == "table":
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


def ocr_slide_local(image_path: Path, server_url: str) -> str:
    """Use local MLX VLM server with PaddleOCR-VL for OCR."""
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        from paddleocr import PaddleOCRVL
    except ImportError:
        sys.exit("ERROR: Local mode requires paddleocr. pip install paddleocr[doc-parser]")

    pipeline = PaddleOCRVL(
        vl_rec_backend="mlx-vlm-server",
        vl_rec_server_url=server_url,
        vl_rec_api_model_name="PaddlePaddle/PaddleOCR-VL-1.5",
        use_layout_detection=True,
        use_doc_orientation_classify=True,
        use_doc_unwarping=True,
    )

    results = list(pipeline.predict(str(image_path)))
    if not results:
        return "*[No text detected]*"

    lines = []
    for res in results:
        for item in getattr(res, "rec_texts", []):
            text = item.strip() if isinstance(item, str) else str(item).strip()
            if text:
                lines.append(text)

    return "\n\n".join(lines) if lines else "*[No text detected]*"


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: slide_ocr.py <image.png> [--server_url URL]")

    image_path = Path(sys.argv[1])
    if not image_path.exists():
        sys.exit(f"ERROR: File not found: {image_path}")

    server_url = None
    if "--server_url" in sys.argv:
        idx = sys.argv.index("--server_url")
        server_url = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None

    if not server_url:
        server_url = os.environ.get("MLX_SERVER_URL")

    if server_url:
        result = ocr_slide_local(image_path, server_url)
    else:
        result = ocr_slide_cloud(image_path)

    print(result)


if __name__ == "__main__":
    main()
