#!/usr/bin/env python3
"""Collect convertible docs from source dir into a flat staging directory.

Skips Excel/CSV, temp files (~$), hidden dirs, and known output dirs.
Sanitizes filenames by replacing path separators with __.
"""
import argparse
import os
import shutil
from pathlib import Path

EXTENSIONS = {".pptx", ".pdf", ".docx", ".ppsx"}


def sanitize(name: str) -> str:
    for ch in r"/\:*?\"<>|":
        name = name.replace(ch, "__")
    return name


def collect(source: Path, output: Path, skip_dirs: set[str]) -> dict:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    counts = {}
    for root, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for fname in files:
            if fname.startswith("~$") or fname.startswith("."):
                continue
            ext = Path(fname).suffix.lower()
            if ext not in EXTENSIONS:
                continue
            src = Path(root) / fname
            rel = src.relative_to(source)
            safe = sanitize(str(rel))
            link = output / safe
            i = 2
            while link.exists():
                link = output / f"{Path(safe).stem}_{i}{Path(safe).suffix}"
                i += 1
            os.symlink(src, link)
            counts[ext] = counts.get(ext, 0) + 1

    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--skip-dirs", nargs="*", default=[])
    args = ap.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    skip_dirs = set(args.skip_dirs) | {output.name, ".git", "__pycache__"}

    counts = collect(source, output, skip_dirs)
    total = sum(counts.values())
    print(f"Collected {total} docs into {output}")
    for ext, n in sorted(counts.items()):
        print(f"  {ext}: {n}")


if __name__ == "__main__":
    main()
