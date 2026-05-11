#!/usr/bin/env python3
"""Retry OCR for unprocessed PDFs.

Checks what's already been processed (any subdir of --ocr-output that contains
a merged/*.md or directly a *.md) and only runs what's missing.
Safe to run multiple times after network interruptions.
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
    ocr = Path(__file__).resolve().parent.parent.parent / "pdf-to-md" / "scripts" / "ocr_extract.py"
    if ocr.exists():
        return ocr
    raise FileNotFoundError(f"Cannot find ocr_extract.py at {ocr}")


OCR_SCRIPT = _find_ocr_script()


def sanitize(name: str) -> str:
    for ch in r"/\:*?\"<>|":
        name = name.replace(ch, "__")
    return name


def get_processed_stems(ocr_output: Path) -> set[str]:
    stems = set()
    for batch_dir in ocr_output.iterdir():
        if not batch_dir.is_dir():
            continue
        for doc_dir in batch_dir.iterdir():
            if doc_dir.is_dir() and (list(doc_dir.glob("*.md")) or list(doc_dir.glob("merged/*.md"))):
                stems.add(doc_dir.name)
    return stems


def collect_remaining(pdf_dir: Path | None, orig_dir: Path | None, processed: set[str]) -> list[Path]:
    pdfs = []
    if pdf_dir and pdf_dir.exists():
        pdfs.extend(sorted(pdf_dir.glob("*.pdf")))
    if orig_dir and orig_dir.exists():
        pdfs.extend(sorted(orig_dir.glob("*.pdf")))
    seen, remaining = set(), []
    for p in pdfs:
        if p.stem not in seen and p.stem not in processed:
            seen.add(p.stem)
            remaining.append(p)
    return remaining


def run_batch(args: tuple) -> tuple[int, list[str]]:
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
        return ok, [l for l in result.stderr.split("\n") if l.strip()][:3]
    except subprocess.TimeoutExpired:
        return 0, ["batch timeout"]
    except Exception as e:
        return 0, [str(e)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf-dir")
    ap.add_argument("--original-pdf-dir")
    ap.add_argument("--ocr-output", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--batch-size", type=int, default=25)
    args = ap.parse_args()

    token = os.environ.get("PADDLEOCR_TOKEN", "")
    api_url = os.environ.get("PADDLEOCR_API_URL", "")
    if not token or not api_url:
        print("ERROR: Set PADDLEOCR_TOKEN and PADDLEOCR_API_URL")
        return 1

    ocr_output = Path(args.ocr_output).resolve()
    batch_dir = ocr_output.parent / (ocr_output.name + "_retry_batches")
    pdf_dir = Path(args.pdf_dir).resolve() if args.pdf_dir else None
    orig_dir = Path(args.original_pdf_dir).resolve() if args.original_pdf_dir else None

    processed = get_processed_stems(ocr_output)
    remaining = collect_remaining(pdf_dir, orig_dir, processed)

    print(f"Already processed: {len(processed)}")
    print(f"Remaining: {len(remaining)} PDFs")
    if not remaining:
        print("Nothing to do.")
        return 0

    if batch_dir.exists():
        shutil.rmtree(batch_dir)
    batches = []
    for i in range(0, len(remaining), args.batch_size):
        chunk = remaining[i:i + args.batch_size]
        bp = batch_dir / f"retry_{len(batches)}"
        bp.mkdir(parents=True, exist_ok=True)
        for pdf in chunk:
            os.symlink(pdf, bp / sanitize(pdf.name))
        batches.append(bp)

    start = time.time()
    total_ok = 0
    tasks = [(b, ocr_output / b.name, token, api_url) for b in batches]

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_batch, t): i for i, t in enumerate(tasks)}
        for future in as_completed(futures):
            bid = futures[future]
            ok, msgs = future.result()
            total_ok += ok
            print(f"Batch {bid}: {ok} docs ok")
            for m in msgs:
                print(f"  {m}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s — {total_ok} new docs processed")


if __name__ == "__main__":
    main()
