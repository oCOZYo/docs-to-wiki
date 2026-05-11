#!/usr/bin/env python3
"""Convert PPTX/PPSX to Markdown using Vision LLM per slide.

Pipeline:
  1. PPTX → PDF  (LibreOffice headless, reliable conversion)
  2. PDF  → per-page PNG  (pymupdf, high-quality rendering at 150dpi)
  3. PNG  → Markdown description  (Claude Vision, parallel)
  4. All slide descriptions → single .md file

Usage:
  python convert_pptx_to_md.py --input file.pptx --output ./out/
  python convert_pptx_to_md.py --input slides_dir/ --output ./out/ --workers 4
  python convert_pptx_to_md.py --input file.pptx --output ./out/ --dpi 200 --model claude-sonnet-4-6
"""
import argparse
import base64
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import fitz  # pymupdf
except ImportError:
    sys.exit("ERROR: pip install pymupdf")

VISION_PROMPT = """这是一张PPT幻灯片的截图。请描述幻灯片的完整内容：
- 标题和副标题（保留原文）
- 正文内容（保留层级结构，转为 Markdown 列表）
- 如果有流程图/架构图：描述各节点名称和连接关系（箭头方向、层级）
- 如果有图表/数据：提取数值、坐标轴标签、趋势
- 如果有对比布局（左右/上下）：分别描述各部分并说明对比关系
- 如果有表格：完整输出为 Markdown 表格
直接输出 Markdown，不要添加引导语。"""

CONVERTIBLE = {".pptx", ".ppsx"}


def pptx_to_pdf(pptx_path: Path, pdf_dir: Path, worker_id: int = 0) -> Path | None:
    """Convert PPTX to PDF via LibreOffice. Returns path to PDF or None on failure."""
    profile = f"/tmp/lo_profile_pptx2md_{worker_id}"
    try:
        result = subprocess.run(
            [
                "soffice", "--headless",
                "--convert-to", "pdf",
                "--outdir", str(pdf_dir),
                f"-env:UserInstallation=file://{profile}",
                str(pptx_path),
            ],
            capture_output=True, timeout=120,
        )
        pdf = pdf_dir / (pptx_path.stem + ".pdf")
        if pdf.exists() and pdf.stat().st_size > 0:
            return pdf
        return None
    except (subprocess.TimeoutExpired, Exception):
        return None


def pdf_to_pngs(pdf_path: Path, png_dir: Path, dpi: int = 150) -> list[Path]:
    """Render each PDF page to a PNG. Returns sorted list of PNG paths."""
    png_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    pngs = []
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for i, page in enumerate(doc):
        png_path = png_dir / f"slide_{i + 1:03d}.png"
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        pix.save(str(png_path))
        pngs.append(png_path)
    doc.close()
    return pngs


def describe_slide(png_path: Path, slide_num: int, model: str, client) -> tuple[int, str]:
    """Send one slide PNG to Vision. Returns (slide_num, markdown_description)."""
    blob = png_path.read_bytes()
    b64 = base64.standard_b64encode(blob).decode()
    try:
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
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": VISION_PROMPT},
                    ],
                }
            ],
        )
        return slide_num, resp.content[0].text.strip()
    except Exception as e:
        return slide_num, f"*[Slide {slide_num} Vision error: {e}]*"


def convert(
    pptx_path: Path,
    output_dir: Path,
    dpi: int,
    model: str,
    max_slides: int,
    concurrent: int,
    worker_id: int,
    client,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Step 1: PPTX → PDF
        pdf = pptx_to_pdf(pptx_path, tmp_path, worker_id)
        if not pdf:
            out = output_dir / (pptx_path.stem + ".md")
            out.write_text(f"# {pptx_path.stem}\n\n*[PDF conversion failed]*\n")
            return out

        # Step 2: PDF → per-slide PNGs
        pngs = pdf_to_pngs(pdf, tmp_path / "pngs", dpi)
        if not pngs:
            out = output_dir / (pptx_path.stem + ".md")
            out.write_text(f"# {pptx_path.stem}\n\n*[No slides rendered]*\n")
            return out

        pngs = pngs[:max_slides]

        # Step 3: Vision per slide (parallel)
        results: dict[int, str] = {}
        with ThreadPoolExecutor(max_workers=concurrent) as pool:
            futures = {
                pool.submit(describe_slide, png, i + 1, model, client): i + 1
                for i, png in enumerate(pngs)
            }
            for future in as_completed(futures):
                num, desc = future.result()
                results[num] = desc

        # Step 4: Assemble markdown
        lines = [f"# {pptx_path.stem}\n"]
        for i in range(1, len(pngs) + 1):
            lines.append(f"\n## Slide {i}\n")
            lines.append(results.get(i, "*[missing]*"))

        out = output_dir / (pptx_path.stem + ".md")
        out.write_text("\n".join(lines), encoding="utf-8")
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True, help="PPTX/PPSX file or directory")
    ap.add_argument("--output", required=True, help="Output directory for .md files")
    ap.add_argument("--dpi", type=int, default=150, help="Slide render resolution (default: 150)")
    ap.add_argument(
        "--model", default="claude-haiku-4-5-20251001",
        help="Claude model for Vision calls"
    )
    ap.add_argument(
        "--max-slides", type=int, default=200,
        help="Max slides per file (cost guard, default: 200)"
    )
    ap.add_argument(
        "--concurrent", type=int, default=5,
        help="Parallel Vision calls per file (default: 5)"
    )
    ap.add_argument(
        "--workers", type=int, default=2,
        help="Parallel files to process (default: 2)"
    )
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY not set")

    try:
        import anthropic
        client = anthropic.Anthropic()
    except ImportError:
        sys.exit("ERROR: pip install anthropic")

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    files = (
        sorted(f for f in input_path.iterdir() if f.suffix.lower() in CONVERTIBLE)
        if input_path.is_dir()
        else [input_path]
    )

    if not files:
        print("No PPTX/PPSX files found.")
        return

    print(f"Processing {len(files)} file(s) → {output_dir}")

    from concurrent.futures import ProcessPoolExecutor
    total_slides = 0

    # Process files (sequential if workers=1, else parallel)
    for i, pptx_path in enumerate(files):
        print(f"[{i+1}/{len(files)}] {pptx_path.name} ...", end=" ", flush=True)
        out = convert(
            pptx_path, output_dir,
            dpi=args.dpi,
            model=args.model,
            max_slides=args.max_slides,
            concurrent=args.concurrent,
            worker_id=i % 4,
            client=client,
        )
        content = out.read_text(encoding="utf-8")
        n = content.count("\n## Slide ")
        total_slides += n
        print(f"done ({n} slides)")

    print(f"\nTotal: {len(files)} files, {total_slides} slides → {output_dir}")


if __name__ == "__main__":
    main()
