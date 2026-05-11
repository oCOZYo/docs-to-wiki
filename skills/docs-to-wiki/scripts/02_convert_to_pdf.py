#!/usr/bin/env python3
"""Convert PPTX/DOCX/PPSX to PDF using LibreOffice headless.

Each worker uses its own UserInstallation profile to avoid lock conflicts.
"""
import argparse
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

CONVERTIBLE = {".pptx", ".docx", ".ppsx"}
SKIP_DIRS_DEFAULT = {".git", "__pycache__"}


def collect_files(source: Path, skip_dirs: set[str]) -> list[Path]:
    files = []
    for root, dirs, fnames in source.walk():
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for fname in fnames:
            if fname.startswith("~$") or fname.startswith("."):
                continue
            p = Path(root) / fname
            if p.suffix.lower() in CONVERTIBLE and p.is_file():
                files.append(p)
    return sorted(files)


def convert_one(args: tuple) -> tuple[str, str | None]:
    src, dst_dir, worker_id, profile_prefix = args
    profile = f"/tmp/{profile_prefix}_{worker_id}"
    try:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf",
             "--outdir", str(dst_dir),
             f"-env:UserInstallation=file://{profile}",
             str(src)],
            capture_output=True, timeout=120,
        )
        expected = dst_dir / (src.stem + ".pdf")
        if expected.exists() and expected.stat().st_size > 0:
            return "ok", None
        return "error", f"PDF not created: {src.name}"
    except subprocess.TimeoutExpired:
        return "error", f"timeout: {src.name}"
    except Exception as e:
        return "error", f"{src.name}: {e}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--skip-dirs", nargs="*", default=[])
    ap.add_argument("--profile-prefix", default="lo_profile")
    args = ap.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    skip_dirs = set(args.skip_dirs) | SKIP_DIRS_DEFAULT | {output.name}

    files = collect_files(source, skip_dirs)
    print(f"Found {len(files)} files to convert")
    if not files:
        return

    stats = {"ok": 0, "error": 0}
    errors = []
    start = time.time()

    tasks = [(f, output, i % args.workers, args.profile_prefix) for i, f in enumerate(files)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(convert_one, t): t[0] for t in tasks}
        for i, future in enumerate(as_completed(futures), 1):
            src = futures[future]
            status, msg = future.result()
            stats[status] = stats.get(status, 0) + 1
            if msg:
                errors.append(msg)
                if len(errors) <= 20:
                    print(f"[{i}/{len(files)}] ✗ {msg}")
            elif i % 50 == 0 or i == len(files):
                print(f"[{i}/{len(files)}] ✓ {stats['ok']} ok so far")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s — ok:{stats['ok']} error:{stats['error']}")
    rate = stats["ok"] / len(files) * 100 if files else 0
    print(f"Success rate: {rate:.1f}%")
    if errors:
        print("First 10 errors:")
        for e in errors[:10]:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
