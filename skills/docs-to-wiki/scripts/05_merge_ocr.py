#!/usr/bin/env python3
"""Merge all OCR batch output into a clean flat structure.

Input:  <ocr-dir>/<batch_N>/<docname>/{merged/*.md + merged/imgs/}
         or    <ocr-dir>/<batch_N>/<docname>/<docname>.md + imgs/
Output: <output>/<docname>/<docname>.md + imgs/

Both flat and nested structures are handled.
"""
import argparse
import shutil
from pathlib import Path


def merge(ocr_dir: Path, output: Path) -> dict:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    stats = {"docs": 0, "images": 0}

    for batch_dir in sorted(ocr_dir.iterdir()):
        if not batch_dir.is_dir():
            continue
        for doc_dir in sorted(batch_dir.iterdir()):
            if not doc_dir.is_dir():
                continue

            # Detect structure: nested (merged/) vs flat
            merged_mds = list(doc_dir.glob("merged/*.md"))
            flat_mds = [f for f in doc_dir.glob("*.md")]

            if merged_mds:
                src_md_dir = doc_dir / "merged"
                mds = merged_mds
                img_dirs = ["images", "imgs"]
                img_src_roots = [src_md_dir]
            elif flat_mds:
                mds = flat_mds
                img_dirs = ["images", "imgs"]
                img_src_roots = [doc_dir]
            else:
                continue

            out_doc = output / doc_dir.name
            out_doc.mkdir(parents=True, exist_ok=True)

            for md in mds:
                shutil.copy2(md, out_doc / md.name)

            for root in img_src_roots:
                for img_dir_name in img_dirs:
                    img_src = root / img_dir_name
                    if img_src.exists():
                        img_dst = out_doc / img_dir_name
                        if img_dst.exists():
                            shutil.rmtree(img_dst)
                        shutil.copytree(img_src, img_dst)
                        stats["images"] += len(list(img_dst.rglob("*.jpg")))
                        stats["images"] += len(list(img_dst.rglob("*.png")))

            stats["docs"] += 1

    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ocr-dir", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    ocr_dir = Path(args.ocr_dir).resolve()
    output = Path(args.output).resolve()

    print(f"Merging OCR output from {ocr_dir} → {output}")
    stats = merge(ocr_dir, output)
    print(f"Done: {stats['docs']} docs, {stats['images']} images")

    total_size = sum(f.stat().st_size for f in output.rglob("*") if f.is_file())
    print(f"Total size: {total_size / 1024 / 1024:.0f} MB")


if __name__ == "__main__":
    main()
