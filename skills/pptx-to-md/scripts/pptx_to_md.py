#!/usr/bin/env python3
"""Convert PPTX/PPSX to Markdown by converting to PDF and delegating to pdf-to-md.

This skill is intentionally a thin wrapper: PPTX-specific logic stops at the
LibreOffice PDF boundary. All text extraction, image extraction, and Vision
handling lives in pdf-to-md/scripts/pdf_to_md.py — fixes and improvements there
benefit both skills automatically.

Pipeline:
  1. PPTX/PPSX → PDF (LibreOffice headless, profile-isolated for parallel safety)
  2. pdf_to_md.py --input <pdf_dir> --output <output> (one batch call)

Usage:
  # Agent mode (default, zero config):
  python pptx_to_md.py --input deck.pptx --output ./out/

  # Standalone mode:
  python pptx_to_md.py --input deck.pptx --output ./out/ --api-key sk-ant-...

  # Pure text, skip image extraction:
  python pptx_to_md.py --input deck.pptx --output ./out/ --no-images

  # Keep intermediate PDFs for inspection / re-runs:
  python pptx_to_md.py --input deck.pptx --output ./out/ --pdf-dir ./pdfs/
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CONVERTIBLE = {".pptx", ".ppsx"}

SCRIPT_DIR = Path(__file__).resolve().parent
# sibling skill: ../../pdf-to-md/scripts/pdf_to_md.py
PDF_TO_MD = SCRIPT_DIR.parent.parent / "pdf-to-md" / "scripts" / "pdf_to_md.py"


def pptx_to_pdf(pptx_path: Path, pdf_dir: Path, worker_id: int = 0) -> Path | None:
    """Convert one PPTX to PDF via LibreOffice. Returns Path or None on failure."""
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
        return pdf if pdf.exists() and pdf.stat().st_size > 0 else None
    except (subprocess.TimeoutExpired, Exception):
        return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--input", required=True, help="PPTX/PPSX file or directory")
    ap.add_argument("--output", required=True, help="Output directory for .md files")
    ap.add_argument("--large-image-kb", type=int, default=30,
                    help="Embedded images larger than this (KB) are extracted (default: 30)")
    ap.add_argument("--max-images", type=int, default=50,
                    help="Max images to process per document (default: 50)")
    ap.add_argument("--no-images", action="store_true",
                    help="Skip image extraction (text-only output)")
    ap.add_argument("--api-key", default=None,
                    help="Anthropic API key for standalone mode (default: agent mode, no key needed)")
    ap.add_argument("--model", default=os.environ.get("DOCS_TO_WIKI_MODEL", "claude-haiku-4-5-20251001"),
                    help="Vision model for standalone mode (env: DOCS_TO_WIKI_MODEL)")
    ap.add_argument("--pdf-dir", default=None,
                    help="Persist intermediate PDFs here (default: temp dir, deleted after)")
    ap.add_argument("--no-ocr-fallback", action="store_true",
                    help="Disable auto-OCR for scanned PDFs (passed through to pdf_to_md.py)")
    ap.add_argument("--ocr-per-page", action="store_true",
                    help="When OCR fallback runs, also save per-page MD files (passed through)")
    args = ap.parse_args()

    if not PDF_TO_MD.exists():
        sys.exit(f"ERROR: pdf_to_md.py not found at {PDF_TO_MD}\n"
                 f"This skill delegates to pdf-to-md — install both skills together.")

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    files = (
        sorted(f for f in input_path.iterdir() if f.suffix.lower() in CONVERTIBLE)
        if input_path.is_dir()
        else [input_path]
    )
    if not files:
        print("No PPTX/PPSX files found.")
        return

    # Build pass-through args for pdf_to_md.py
    pdf_args = [
        "--large-image-kb", str(args.large_image_kb),
        "--max-images", str(args.max_images),
    ]
    if args.no_images:
        pdf_args.append("--no-images")
    if args.api_key:
        pdf_args += ["--api-key", args.api_key]
    if args.model:
        pdf_args += ["--model", args.model]
    if args.no_ocr_fallback:
        pdf_args.append("--no-ocr-fallback")
    if args.ocr_per_page:
        pdf_args.append("--ocr-per-page")

    # Phase 1: PPTX → PDFs into pdf_dir (persistent if --pdf-dir, else tempdir)
    tmp_ctx = tempfile.TemporaryDirectory() if args.pdf_dir is None else None
    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else Path(tmp_ctx.name)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    print(f"Phase 1: PPTX → PDF ({len(files)} file(s)) → {pdf_dir}")
    converted_pdfs = []
    failed_files = []
    for i, pptx in enumerate(files, 1):
        print(f"  [{i}/{len(files)}] {pptx.name} ...", end=" ", flush=True)
        pdf = pptx_to_pdf(pptx, pdf_dir, worker_id=i % 4)
        if pdf:
            converted_pdfs.append(pdf)
            print("ok")
        else:
            failed_files.append(pptx)
            # Write failure stub so the output dir reflects the failure
            (output_dir / (pptx.stem + ".md")).write_text(
                f"# {pptx.stem}\n\n*[PDF conversion failed]*\n"
            )
            print("FAILED")

    if not converted_pdfs:
        print("\nNo PDFs produced — nothing to delegate.")
        if tmp_ctx:
            tmp_ctx.cleanup()
        return

    # Phase 2: one batch call to pdf_to_md.py
    print(f"\nPhase 2: delegating {len(converted_pdfs)} PDF(s) to pdf-to-md ...")
    cmd = [sys.executable, str(PDF_TO_MD),
           "--input", str(pdf_dir),
           "--output", str(output_dir),
           *pdf_args]
    result = subprocess.run(cmd)

    if tmp_ctx:
        tmp_ctx.cleanup()

    print(f"\nTotal: {len(files)} PPTX, {len(converted_pdfs)} converted, "
          f"{len(failed_files)} failed → {output_dir}")
    if result.returncode != 0:
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
