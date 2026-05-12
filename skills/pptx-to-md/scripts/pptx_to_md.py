#!/usr/bin/env python3
"""Convert PPTX/PPSX to Markdown by rendering each slide as a PNG.

Pipeline:
  1. PPTX → PDF (LibreOffice headless)
  2. PDF  → per-slide PNG (pymupdf, 96 dpi by default)
  3. [Optional] OCR all PNGs in parallel (PaddleOCR cloud, if PADDLEOCR_TOKEN set)
  4. Write per_page/slide_NNN.md stubs with sentinel + OCR text (if any)
  5a. Agent mode: stubs left for Claude agent/subagents to fill, then --merge-only
  5b. Standalone mode: Vision call per slide (OCR text in prompt) → overwrite stub → merge

Output structure:
  output_dir/
    stem.md                       ← final merged output
    stem/
      slides/slide_NNN.png        ← persistent PNGs for agent Read
      per_page/slide_NNN.md       ← per-page MD (stub or filled)

Usage:
  # Agent mode (default, zero config):
  python pptx_to_md.py --input file.pptx --output ./out/

  # With OCR context (set env vars, no extra flags needed):
  export PADDLEOCR_TOKEN=... PADDLEOCR_API_URL=...
  python pptx_to_md.py --input file.pptx --output ./out/

  # Merge after agent fills per_page MDs:
  python pptx_to_md.py --input file.pptx --output ./out/ --merge-only

  # Standalone mode (only when user explicitly requests):
  python pptx_to_md.py --input file.pptx --output ./out/ --api-key sk-ant-...
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

STUB_SENTINEL = "<!-- pptx-to-md:stub -->"

VISION_PROMPT_NO_OCR = """这是一张PPT幻灯片的截图。请描述幻灯片的完整内容：
- 标题和副标题（保留原文）
- 正文内容（保留层级结构，转为 Markdown 列表）
- 如果有流程图/架构图：描述各节点名称和连接关系（箭头方向、层级）
- 如果有图表/数据：提取数值、坐标轴标签、趋势
- 如果有对比布局（左右/上下）：分别描述各部分并说明对比关系
- 如果有表格：完整输出为 Markdown 表格
直接输出 Markdown，不要添加引导语。"""

VISION_PROMPT_WITH_OCR = """这是一张PPT幻灯片的截图。以下是 OCR 提取的文字（可能含识别误差）：

<ocr_text>
{ocr_text}
</ocr_text>

请基于截图（视觉优先）+ OCR 文字（辅助参考）描述幻灯片完整内容：
- 标题和副标题：以截图为准，参考 OCR 文字纠正用词
- 正文内容：保留层级结构，转为 Markdown 列表
- 如果有流程图/架构图：描述各节点名称和连接关系（箭头方向、层级）
- 如果有图表/数据：提取数值、坐标轴标签、趋势（参考 OCR 数字）
- 如果有对比布局（左右/上下）：分别描述各部分并说明对比关系
- 如果有表格：完整输出为 Markdown 表格
直接输出 Markdown，不要添加引导语。"""

CONVERTIBLE = {".pptx", ".ppsx"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_stub(md_path: Path) -> bool:
    """Return True if per-page MD has not yet been filled by an agent."""
    if not md_path.exists():
        return False
    try:
        return md_path.read_bytes()[:32].startswith(b"<!-- pptx-to-md:stub -->")
    except OSError:
        return False


def write_stub(per_page_dir: Path, slide_num: int, png_abs: Path, ocr_text: str) -> Path:
    """Write a per-page stub MD with sentinel, PNG path, and optional OCR text."""
    p = per_page_dir / f"slide_{slide_num:03d}.md"
    lines = [STUB_SENTINEL, f"<!-- png: {png_abs} -->", ""]
    if ocr_text.strip():
        lines += ["<!-- ocr:", ocr_text.strip(), "-->", ""]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def merge_per_page(per_page_dir: Path, stem: str, output_dir: Path) -> tuple[Path, int, int]:
    """Merge all per-page MDs into stem.md. Returns (path, total, unfilled_count)."""
    mds = sorted(per_page_dir.glob("slide_*.md"))
    lines = [f"# {stem}\n"]
    unfilled = 0
    for md in mds:
        n = int(md.stem.split("_")[1])
        png_rel = f"{stem}/slides/slide_{n:03d}.png"
        lines.append(f"\n## Slide {n}\n")
        lines.append(f"![]({png_rel})\n")
        if is_stub(md):
            unfilled += 1
            lines.append(f"*[Slide {n} not yet described — run agent or standalone]*\n")
        else:
            content = md.read_text(encoding="utf-8").strip()
            if content:
                lines.append(content + "\n")
    out = output_dir / (stem + ".md")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out, len(mds), unfilled


# ── OCR ───────────────────────────────────────────────────────────────────────

def ocr_slide(png_path: Path, token: str, api_url: str) -> str:
    """OCR a single slide PNG via PaddleOCR cloud API. Returns text or '' on failure."""
    try:
        import requests
    except ImportError:
        return ""
    b64 = base64.b64encode(png_path.read_bytes()).decode("ascii")
    payload = {
        "file": b64,
        "fileType": 1,
        "useDocOrientationClassify": True,
        "useDocUnwarping": False,
    }
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        results = resp.json().get("result", {}).get("layoutParsingResults", [])
        return results[0]["markdown"]["text"].strip() if results else ""
    except Exception:
        return ""


def ocr_all_slides(pngs: list[Path], token: str, api_url: str, concurrent: int = 5) -> dict[int, str]:
    """OCR all PNGs in parallel. Returns {slide_num (1-based): ocr_text}."""
    if not token or not api_url:
        return {}
    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=concurrent) as pool:
        futures = {
            pool.submit(ocr_slide, png, token, api_url): i + 1
            for i, png in enumerate(pngs)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


# ── Conversion ────────────────────────────────────────────────────────────────

def pptx_to_pdf(pptx_path: Path, pdf_dir: Path, worker_id: int = 0) -> Path | None:
    """Convert PPTX to PDF via LibreOffice. Returns path to PDF or None on failure."""
    profile = f"/tmp/lo_profile_pptx2md_{worker_id}"
    try:
        subprocess.run(
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


def pdf_to_pngs(pdf_path: Path, png_dir: Path, dpi: int = 96) -> list[Path]:
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


def describe_slide(
    png_path: Path, slide_num: int, model: str, client, ocr_text: str = ""
) -> tuple[int, str]:
    """Send one slide PNG to Vision. Returns (slide_num, markdown_description)."""
    blob = png_path.read_bytes()
    b64 = base64.standard_b64encode(blob).decode()
    prompt = (
        VISION_PROMPT_WITH_OCR.format(ocr_text=ocr_text.strip())
        if ocr_text.strip()
        else VISION_PROMPT_NO_OCR
    )
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64",
                     "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return slide_num, resp.content[0].text.strip()
    except Exception as e:
        return slide_num, f"*[Slide {slide_num} Vision error: {e}]*"


def convert(
    pptx_path: Path,
    output_dir: Path,
    dpi: int,
    max_slides: int,
    worker_id: int,
    standalone_client=None,
    model: str = "claude-haiku-4-5-20251001",
    concurrent: int = 5,
    ocr_token: str = "",
    ocr_api_url: str = "",
    resume: bool = True,
) -> tuple[Path, int]:
    """Convert one PPTX file. Returns (output_path, slide_count)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = pptx_path.stem
    slides_dir = output_dir / stem / "slides"
    per_page_dir = output_dir / stem / "per_page"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Step 1: PPTX → PDF
        pdf = pptx_to_pdf(pptx_path, tmp_path, worker_id)
        if not pdf:
            out = output_dir / (stem + ".md")
            out.write_text(f"# {stem}\n\n*[PDF conversion failed]*\n")
            return out, 0

        # Step 2: PDF → PNGs (resume: skip if correct count already exists)
        existing = sorted(slides_dir.glob("slide_*.png")) if slides_dir.exists() else []
        doc = fitz.open(str(pdf))
        expected = min(len(doc), max_slides)
        doc.close()

        if resume and len(existing) == expected:
            print(f"  [resume] {expected} PNGs exist, skipping re-render", end=" ", flush=True)
            pngs = existing
        else:
            slides_dir.mkdir(parents=True, exist_ok=True)
            pngs = pdf_to_pngs(pdf, slides_dir, dpi)[:max_slides]

    # Step 3: OCR all PNGs in parallel (if credentials available)
    ocr_enabled = bool(ocr_token and ocr_api_url)
    if ocr_enabled:
        print(f"OCR ({len(pngs)} slides)...", end=" ", flush=True)
    ocr_map = ocr_all_slides(pngs, ocr_token, ocr_api_url, concurrent)
    if ocr_enabled:
        hit = sum(1 for v in ocr_map.values() if v)
        print(f"{hit}/{len(pngs)} extracted", end=" ", flush=True)

    # Step 4: Write per-page stubs
    per_page_dir.mkdir(parents=True, exist_ok=True)
    for i, png in enumerate(pngs, 1):
        stub_path = per_page_dir / f"slide_{i:03d}.md"
        if resume and stub_path.exists() and not is_stub(stub_path):
            continue  # already filled by agent, preserve
        write_stub(per_page_dir, i, png.resolve(), ocr_map.get(i, ""))

    # Step 5a: Agent mode — stubs ready, agent/subagents will fill them
    if standalone_client is None:
        # Emit a minimal stem.md (stubs only) for reference; --merge-only updates it
        out, total, _ = merge_per_page(per_page_dir, stem, output_dir)
        return out, len(pngs)

    # Step 5b: Standalone mode — Vision per slide, then merge
    def process_slide(args: tuple[Path, int]) -> None:
        png, n = args
        stub_path = per_page_dir / f"slide_{n:03d}.md"
        if resume and stub_path.exists() and not is_stub(stub_path):
            return  # already filled
        _, desc = describe_slide(png, n, model, standalone_client, ocr_map.get(n, ""))
        stub_path.write_text(desc, encoding="utf-8")  # no sentinel = filled

    with ThreadPoolExecutor(max_workers=concurrent) as pool:
        futures = [pool.submit(process_slide, (png, i + 1)) for i, png in enumerate(pngs)]
        for f in as_completed(futures):
            f.result()  # re-raise exceptions; partial results already on disk

    out, total, unfilled = merge_per_page(per_page_dir, stem, output_dir)
    if unfilled:
        print(f"warning: {unfilled} slides failed Vision", end=" ", flush=True)
    return out, len(pngs)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--input", required=True, help="PPTX/PPSX file or directory")
    ap.add_argument("--output", required=True, help="Output directory")
    ap.add_argument("--dpi", type=int, default=96,
                    help="Slide render resolution (default: 96; text-heavy: 72; dense charts: 120)")
    ap.add_argument("--max-slides", type=int, default=200,
                    help="Max slides per file (cost guard, default: 200)")
    ap.add_argument("--ocr-concurrent", type=int, default=5,
                    help="Parallel OCR API calls (default: 5)")
    ap.add_argument("--merge-only", action="store_true",
                    help="Skip render/OCR; just merge existing per_page MDs into stem.md")
    ap.add_argument("--no-resume", dest="resume", action="store_false",
                    help="Re-process all slides even if already filled")
    ap.add_argument(
        "--api-key", default=None,
        help="Anthropic API key for standalone mode (only pass when user explicitly requests "
             "unattended processing — default agent mode needs no API key)",
    )
    ap.add_argument(
        "--model", default=os.environ.get("DOCS_TO_WIKI_MODEL", "claude-haiku-4-5-20251001"),
        help="Vision model for standalone mode (env: DOCS_TO_WIKI_MODEL)",
    )
    ap.add_argument("--concurrent", type=int, default=5,
                    help="Parallel Vision calls in standalone mode (default: 5)")
    args = ap.parse_args()

    # OCR credentials from env only (tokens don't belong in shell history)
    ocr_token = os.environ.get("PADDLEOCR_TOKEN", "")
    ocr_api_url = os.environ.get("PADDLEOCR_API_URL", "")

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    standalone_client = None
    if args.api_key:
        try:
            import anthropic
        except ImportError:
            sys.exit("ERROR: --api-key requires `pip install anthropic`")
        standalone_client = anthropic.Anthropic(api_key=args.api_key)

    files = (
        sorted(f for f in input_path.iterdir() if f.suffix.lower() in CONVERTIBLE)
        if input_path.is_dir()
        else [input_path]
    )
    if not files:
        print("No PPTX/PPSX files found.")
        return

    mode = "standalone" if standalone_client else "agent"
    ocr_status = "OCR on" if (ocr_token and ocr_api_url) else "OCR off (no PADDLEOCR_TOKEN)"

    # --merge-only: skip render/OCR, just merge existing per_page MDs
    if args.merge_only:
        print(f"Merge-only mode → {output_dir}")
        for pptx_path in files:
            per_page_dir = output_dir / pptx_path.stem / "per_page"
            if not per_page_dir.exists():
                print(f"  SKIP {pptx_path.stem}: no per_page/ dir found")
                continue
            out, total, unfilled = merge_per_page(per_page_dir, pptx_path.stem, output_dir)
            status = f"({unfilled} stubs remaining)" if unfilled else "(complete)"
            print(f"  {pptx_path.stem}.md — {total} slides merged {status}")
        return

    print(f"Mode: {mode} | {ocr_status} | DPI: {args.dpi}")
    print(f"Processing {len(files)} file(s) → {output_dir}")

    total_slides = 0
    for i, pptx_path in enumerate(files):
        print(f"[{i+1}/{len(files)}] {pptx_path.name} ...", end=" ", flush=True)
        _out, n = convert(
            pptx_path, output_dir,
            dpi=args.dpi,
            max_slides=args.max_slides,
            worker_id=i % 4,
            standalone_client=standalone_client,
            model=args.model,
            concurrent=args.concurrent,
            ocr_token=ocr_token,
            ocr_api_url=ocr_api_url,
            resume=args.resume,
        )
        total_slides += n
        print(f"done ({n} slides)")

    print(f"\nTotal: {len(files)} files, {total_slides} slides → {output_dir}")
    if mode == "agent" and total_slides > 0:
        print("\nNext steps:")
        print("  1. Ask Claude Code to fill in the per_page/slide_NNN.md stubs")
        print("     (subagents read stub for PNG path + OCR context, write description)")
        print("  2. Run --merge-only to produce the final stem.md:")
        print(f"     python pptx_to_md.py --input {args.input} --output {args.output} --merge-only")


if __name__ == "__main__":
    main()
