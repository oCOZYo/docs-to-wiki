#!/usr/bin/env python3
"""Run PaddleOCR on all PDFs.

Collects PDFs from converted output dir + original staging dir (for native PDFs).
Deduplicates by stem (converted takes priority). Splits into batches and runs
ocr_extract.py in parallel.

Requires PADDLEOCR_TOKEN and PADDLEOCR_API_URL environment variables.
"""
import argparse
import os
import shutil
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

def _find_ocr_script() -> Path:
    """Locate ocr_extract.py relative to this script's position in the repo."""
    # This script: <repo>/skills/docs-to-wiki/scripts/03_run_ocr.py
    # OCR script:  <repo>/skills/pdf-to-md/scripts/ocr_extract.py
    ocr = Path(__file__).resolve().parent.parent.parent / "pdf-to-md" / "scripts" / "ocr_extract.py"
    if ocr.exists():
        return ocr
    raise FileNotFoundError(f"Cannot find ocr_extract.py at {ocr}")


OCR_SCRIPT = _find_ocr_script()


def sanitize(name: str) -> str:
    for ch in r"/\:*?\"<>|":
        name = name.replace(ch, "__")
    return name


def collect_pdfs(pdf_dir: Path | None, original_dir: Path | None) -> list[Path]:
    pdfs = []
    if pdf_dir and pdf_dir.exists():
        pdfs.extend(sorted(pdf_dir.glob("*.pdf")))
    if original_dir and original_dir.exists():
        pdfs.extend(sorted(original_dir.glob("*.pdf")))
    seen, unique = set(), []
    for p in pdfs:
        if p.stem not in seen:
            seen.add(p.stem)
            unique.append(p)
    return unique


def prepare_batches(pdfs: list[Path], batch_dir: Path, batch_size: int) -> list[Path]:
    if batch_dir.exists():
        shutil.rmtree(batch_dir)
    batches = []
    for i in range(0, len(pdfs), batch_size):
        chunk = pdfs[i:i + batch_size]
        bp = batch_dir / f"batch_{len(batches)}"
        bp.mkdir(parents=True, exist_ok=True)
        for pdf in chunk:
            safe = sanitize(pdf.name)
            link = bp / safe
            os.symlink(pdf, link)
        batches.append(bp)
    return batches


def run_batch(args: tuple) -> tuple[int, int, list[str]]:
    batch_path, out_dir, token, api_url = args
    env = os.environ.copy()
    env["PADDLEOCR_TOKEN"] = token
    env["PADDLEOCR_API_URL"] = api_url
    try:
        result = subprocess.run(
            ["python3", str(OCR_SCRIPT), str(batch_path), str(out_dir)],
            env=env, capture_output=True, text=True, timeout=3600,
        )
        ok = result.stdout.count("Saved")
        errs = [l for l in result.stderr.split("\n") if "error" in l.lower() or "fail" in l.lower()]
        return ok, len(errs), errs[:3]
    except subprocess.TimeoutExpired:
        return 0, 1, ["batch timeout"]
    except Exception as e:
        return 0, 1, [str(e)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf-dir", help="Directory with converted PDFs")
    ap.add_argument("--original-pdf-dir", help="Staging dir with original PDFs")
    ap.add_argument("--output", required=True, help="OCR output directory")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=25)
    args = ap.parse_args()

    token = os.environ.get("PADDLEOCR_TOKEN", "")
    api_url = os.environ.get("PADDLEOCR_API_URL", "")
    if not token or not api_url:
        print("ERROR: Set PADDLEOCR_TOKEN and PADDLEOCR_API_URL environment variables")
        return 1

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    batch_dir = output.parent / (output.name + "_batches")

    pdf_dir = Path(args.pdf_dir).resolve() if args.pdf_dir else None
    orig_dir = Path(args.original_pdf_dir).resolve() if args.original_pdf_dir else None

    pdfs = collect_pdfs(pdf_dir, orig_dir)
    print(f"Found {len(pdfs)} unique PDFs to OCR")
    if not pdfs:
        return 0

    batches = prepare_batches(pdfs, batch_dir, args.batch_size)
    print(f"Prepared {len(batches)} batches of ~{args.batch_size}")
    start = time.time()
    total_ok = 0

    tasks = [(b, output / b.name, token, api_url) for b in batches]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_batch, t): i for i, t in enumerate(tasks)}
        for future in as_completed(futures):
            bid = futures[future]
            ok, err, msgs = future.result()
            total_ok += ok
            print(f"Batch {bid}: {ok} ok, {err} errors")
            for m in msgs:
                print(f"  {m}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s — {total_ok} docs processed")


if __name__ == "__main__":
    main()
