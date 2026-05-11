#!/usr/bin/env python3
"""
ocr_extract.py — Batch OCR documents into structured Markdown.

Two modes:

  Cloud (recommended, no local setup required):
    Set env vars once:
      export PADDLEOCR_TOKEN="your_token"
      export PADDLEOCR_API_URL="https://xxxx.aistudio-app.com/layout-parsing"
    Then run:
      python ocr_extract.py <source_dir> <output_dir>

    Or pass inline:
      python ocr_extract.py <source_dir> <output_dir> \\
        --token <token> --api_url <url>

    Supported formats: PDF, JPG, PNG, BMP, TIFF, WEBP
    Get token + API URL at: https://aistudio.baidu.com/paddleocr

  Local (requires MLX VLM server + paddleocr venv):
    python ocr_extract.py <source_dir> <output_dir> --server_url http://localhost:8111/
    Or set env var: MLX_SERVER_URL=http://...

    Supported formats: PDF only

Output structure per file (e.g. "report.pdf"):
    output_dir/
      report/
        per_page/   page-by-page MD files
        merged/     single concatenated MD file
"""

import argparse
import base64
import os
import sys
from pathlib import Path

PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


# ── Cloud mode ────────────────────────────────────────────────────────────────

def process_cloud(source_dir, output_dir, token, api_url):
    try:
        import requests
    except ImportError:
        print("Missing dependency: pip install requests")
        sys.exit(1)

    source_path = Path(source_dir)
    files = sorted(
        f for f in source_path.iterdir()
        if f.suffix.lower() in PDF_EXTS | IMAGE_EXTS
    )
    if not files:
        print(f"No supported files found in: {source_dir}")
        print(f"Supported: {', '.join(sorted(PDF_EXTS | IMAGE_EXTS))}")
        return

    print(f"\nFound {len(files)} file(s) to process (cloud mode).")
    os.makedirs(output_dir, exist_ok=True)

    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
    }

    for file_path in files:
        print(f"\nProcessing: {file_path.name}")
        file_type = 0 if file_path.suffix.lower() == ".pdf" else 1

        with open(file_path, "rb") as f:
            file_data = base64.b64encode(f.read()).decode("ascii")

        payload = {
            "file": file_data,
            "fileType": file_type,
            "useDocOrientationClassify": True,
            "useDocUnwarping": True,
        }

        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=300)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"  Error calling API: {e}")
            continue

        parsing_results = response.json().get("result", {}).get("layoutParsingResults", [])
        if not parsing_results:
            print(f"  No results returned for {file_path.name}")
            continue

        base_name = file_path.stem
        file_out_dir = Path(output_dir) / base_name

        # per_page: save each result as a separate file (only when multiple pages returned)
        if len(parsing_results) > 1:
            per_page_dir = file_out_dir / "per_page"
            per_page_dir.mkdir(parents=True, exist_ok=True)
            for i, res in enumerate(parsing_results):
                md_path = per_page_dir / f"{base_name}_{i}.md"
                md_path.write_text(res["markdown"]["text"], encoding="utf-8")
            print(f"  Saved {len(parsing_results)} per-page files → {per_page_dir}")

        # merged: concatenate all pages into one file
        merged_dir = file_out_dir / "merged"
        merged_dir.mkdir(parents=True, exist_ok=True)
        merged_text = "\n\n".join(r["markdown"]["text"] for r in parsing_results)
        merged_md = merged_dir / f"{base_name}.md"
        merged_md.write_text(merged_text, encoding="utf-8")
        print(f"  Saved merged Markdown → {merged_md}")

        # download embedded images
        _download_images(parsing_results, merged_dir, requests)

        print(f"  → All outputs in: {file_out_dir}")


def _download_images(parsing_results, output_dir, requests):
    for res in parsing_results:
        images = res.get("markdown", {}).get("images", {})
        for img_rel_path, img_url in images.items():
            full_path = Path(output_dir) / img_rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                img_bytes = requests.get(img_url, timeout=30).content
                full_path.write_bytes(img_bytes)
            except Exception as e:
                print(f"  Warning: failed to download image {img_rel_path}: {e}")


# ── Local mode ────────────────────────────────────────────────────────────────

def _check_local_deps():
    missing = []
    try:
        import paddle  # noqa: F401
    except ImportError:
        missing.append("paddlepaddle")
    try:
        import paddleocr  # noqa: F401
    except ImportError:
        missing.append("paddleocr[doc-parser]")
    if missing:
        print("Missing dependencies. Use the paddleocr venv:")
        print("  ~/.venvs/paddleocr/bin/python ocr_extract.py ...")
        print()
        print("To set up the venv from scratch:")
        print("  python3.13 -m venv ~/.venvs/paddleocr")
        print("  ~/.venvs/paddleocr/bin/pip install paddlepaddle==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/")
        print("  ~/.venvs/paddleocr/bin/pip install -U 'paddleocr[doc-parser]'")
        print()
        print("Or use cloud mode instead (no local install needed):")
        print("  export PADDLEOCR_TOKEN=your_token")
        print("  export PADDLEOCR_API_URL=https://xxxx.aistudio-app.com/layout-parsing")
        sys.exit(1)


def process_local(source_dir, output_dir, server_url):
    _check_local_deps()
    # Skip external connectivity check — irrelevant when using a local/intranet VLM server
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    from paddleocr import PaddleOCRVL

    all_files = sorted(
        f for f in os.listdir(source_dir)
        if Path(f).suffix.lower() in PDF_EXTS | IMAGE_EXTS
    )
    if not all_files:
        print(f"No supported files found in: {source_dir}")
        print(f"Supported: {', '.join(sorted(PDF_EXTS | IMAGE_EXTS))}")
        return

    print(f"\nFound {len(all_files)} file(s) to process (local mode).")
    os.makedirs(output_dir, exist_ok=True)

    print(f"Initializing PaddleOCRVL pipeline with MLX server: {server_url}")
    pipeline = PaddleOCRVL(
        vl_rec_backend="mlx-vlm-server",
        vl_rec_server_url=server_url,
        vl_rec_api_model_name="PaddlePaddle/PaddleOCR-VL-1.5",
        use_layout_detection=True,
        use_doc_orientation_classify=True,
        use_doc_unwarping=True,
    )

    for pdf_file in all_files:
        pdf_path = os.path.join(source_dir, pdf_file)
        base_name = os.path.splitext(pdf_file)[0]
        pdf_out_dir = os.path.join(output_dir, base_name)

        print(f"\nProcessing: {pdf_file}")
        try:
            print("  - Running VLM inference on all pages...")
            pages_res = list(pipeline.predict(pdf_path))
            print(f"    Got {len(pages_res)} pages")

            print("  - Restructuring per-page (merge_tables + relevel_titles)...")
            per_page_res = pipeline.restructure_pages(
                pages_res, merge_tables=True, relevel_titles=True,
            )
            per_page_list = per_page_res if isinstance(per_page_res, list) else [per_page_res]

            per_page_dir = os.path.join(pdf_out_dir, "per_page")
            os.makedirs(per_page_dir, exist_ok=True)
            for i, item in enumerate(per_page_list):
                try:
                    item.save_to_markdown(save_path=per_page_dir)
                except Exception as e:
                    print(f"    page {i} save_to_markdown failed: {e}")
                try:
                    item.save_to_json(save_path=per_page_dir)
                except Exception as e:
                    print(f"    page {i} save_to_json failed: {e}")

            per_page_files = [f for f in os.listdir(per_page_dir) if f.endswith(".md")]
            print(f"    Saved {len(per_page_files)} per-page MD + JSON → {per_page_dir}")

            print("  - Restructuring merged (concatenate_pages=True)...")
            merged_res = pipeline.restructure_pages(
                pages_res, merge_tables=True, relevel_titles=True, concatenate_pages=True,
            )
            merged_list = merged_res if isinstance(merged_res, list) else [merged_res]

            merged_dir = os.path.join(pdf_out_dir, "merged")
            os.makedirs(merged_dir, exist_ok=True)
            for item in merged_list:
                try:
                    item.save_to_markdown(save_path=merged_dir)
                except Exception as e:
                    print(f"    merged save_to_markdown failed: {e}")
                try:
                    item.save_to_json(save_path=merged_dir)
                except Exception as e:
                    print(f"    merged save_to_json failed: {e}")

            print(f"  → All outputs in: {pdf_out_dir}")

        except Exception as e:
            print(f"  Error processing {pdf_file}: {str(e)}")
            import traceback
            traceback.print_exc()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Batch OCR documents into structured Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
modes:
  cloud  PADDLEOCR_TOKEN + PADDLEOCR_API_URL env vars (or --token + --api_url)
         supports PDF and images; only requires: pip install requests
  local  --server_url or MLX_SERVER_URL env var
         supports PDF only; requires ~/.venvs/paddleocr venv
        """,
    )
    parser.add_argument("source_dir", help="Directory containing files to process")
    parser.add_argument("output_dir", help="Directory to write output files")
    parser.add_argument(
        "--token",
        default=os.environ.get("PADDLEOCR_TOKEN"),
        help="AI Studio token for cloud mode (or set PADDLEOCR_TOKEN env var)",
    )
    parser.add_argument(
        "--api_url",
        default=os.environ.get("PADDLEOCR_API_URL"),
        help="Cloud API URL (or set PADDLEOCR_API_URL env var)",
    )
    parser.add_argument(
        "--server_url",
        default=os.environ.get("MLX_SERVER_URL"),
        help="Local MLX server URL for local mode (or set MLX_SERVER_URL env var)",
    )
    args = parser.parse_args()

    source_dir = os.path.abspath(args.source_dir)
    output_dir = os.path.abspath(args.output_dir)

    if args.token:
        if not args.api_url:
            print("Error: --api_url is required in cloud mode (or set PADDLEOCR_API_URL env var).")
            sys.exit(1)
        process_cloud(source_dir, output_dir, args.token, args.api_url)
    else:
        server_url = args.server_url or "http://localhost:8111/"
        process_local(source_dir, output_dir, server_url)

    print("\nAll done!")


if __name__ == "__main__":
    main()
