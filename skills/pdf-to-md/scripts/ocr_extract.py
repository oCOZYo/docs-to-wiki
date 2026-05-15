#!/usr/bin/env python3
"""
ocr_extract.py — Batch OCR documents into structured Markdown.

Two modes:

  Cloud (recommended, no local setup required):
    Set env var:
      export PADDLEOCR_TOKEN="your_token"
    Then run:
      python ocr_extract.py <source_dir> <output_dir>

    Supported formats: PDF, JPG, PNG, BMP, TIFF, WEBP
    Get token at: https://aistudio.baidu.com/paddleocr

    Large PDFs (>45MB) are automatically split into chunks and submitted
    as multiple async jobs. Results are merged in order.

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
import json
import os
import sys
import tempfile
import time
from pathlib import Path

PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

# Async v2 Jobs API
JOB_API_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
DEFAULT_MODEL = "PaddleOCR-VL-1.5"
DEFAULT_POLL_INTERVAL = 5   # seconds
DEFAULT_TIMEOUT = 1800      # 30 min per job
DEFAULT_MAX_FILE_MB = 45    # split threshold

# optionalPayload defaults for PaddleOCR-VL-1.5
OPTIONAL_PAYLOAD_DEFAULTS = {
    "useDocOrientationClassify": True,
    "useDocUnwarping": True,
    "useChartRecognition": True,
    "useLayoutDetection": True,
    "restructurePages": True,
    "mergeTables": True,
    "relevelTitles": True,
    "prettifyMarkdown": True,
    "showFormulaNumber": True,
}


# ── Async cloud mode ─────────────────────────────────────────────────────────

def _build_optional_payload(**overrides):
    payload = dict(OPTIONAL_PAYLOAD_DEFAULTS)
    payload.update(overrides)
    return payload


def _submit_job(file_path, token, api_url, model, optional_payload, page_ranges=None):
    """Submit a file via multipart to the async jobs API. Returns job_id."""
    try:
        import requests
    except ImportError:
        print("Missing dependency: pip install requests")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "model": model,
        "optionalPayload": json.dumps(optional_payload),
    }
    if page_ranges:
        data["pageRanges"] = page_ranges

    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f)}
        resp = requests.post(api_url, headers=headers, data=data, files=files, timeout=120)

    if resp.status_code != 200:
        raise RuntimeError(f"Submit failed (HTTP {resp.status_code}): {resp.text}")

    body = resp.json()
    if body.get("code", -1) != 0:
        raise RuntimeError(f"Submit error: {body.get('msg', body)}")

    return body["data"]["jobId"]


def _poll_job(job_id, token, poll_interval=DEFAULT_POLL_INTERVAL, timeout=DEFAULT_TIMEOUT):
    """Poll until job is done. Returns jsonl_url."""
    try:
        import requests
    except ImportError:
        print("Missing dependency: pip install requests")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()
    last_progress = ""

    while time.time() - start < timeout:
        resp = requests.get(f"{JOB_API_URL}/{job_id}", headers=headers, timeout=30)
        if resp.status_code != 200:
            print(f"  Poll error (HTTP {resp.status_code}), retrying...", flush=True)
            time.sleep(poll_interval)
            continue

        data = resp.json().get("data", {})
        state = data.get("state", "unknown")

        if state == "done":
            progress = data.get("extractProgress", {})
            total = progress.get("totalPages", "?")
            print(f"  完成: {total} 页", flush=True)
            return data["resultUrl"]["jsonUrl"]

        if state == "failed":
            raise RuntimeError(f"Job failed: {data.get('errorMsg', 'unknown')}")

        # Print progress if changed
        progress = data.get("extractProgress", {})
        if progress:
            total = progress.get("totalPages", "?")
            done = progress.get("extractedPages", "?")
            msg = f"  进度: {done}/{total} 页"
            if msg != last_progress:
                print(msg, flush=True)
                last_progress = msg
        elif state != last_progress:
            print(f"  状态: {state}", flush=True)
            last_progress = state

        time.sleep(poll_interval)

    raise TimeoutError(f"Job {job_id} timed out after {timeout}s")


def _fetch_results(jsonl_url):
    """Download JSONL and return list of layoutParsingResults in page order."""
    try:
        import requests
    except ImportError:
        print("Missing dependency: pip install requests")
        sys.exit(1)

    resp = requests.get(jsonl_url, timeout=120)
    resp.raise_for_status()

    all_results = []
    for line in resp.text.strip().split("\n"):
        if not line.strip():
            continue
        parsed = json.loads(line)
        result = parsed.get("result", {})
        all_results.extend(result.get("layoutParsingResults", []))
    return all_results


def _download_images(parsing_results, output_dir, requests_mod):
    """Download images referenced in markdown.images (URL-based)."""
    for res in parsing_results:
        images = res.get("markdown", {}).get("images", {})
        for img_rel_path, img_url in images.items():
            full_path = Path(output_dir) / img_rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                img_bytes = requests_mod.get(img_url, timeout=30).content
                full_path.write_bytes(img_bytes)
            except Exception as e:
                print(f"  警告: 图片下载失败 {img_rel_path}: {e}")


def _extract_pymupdf_pages(pdf_path):
    """Extract text per page using pymupdf. Returns list[str], one per page."""
    try:
        import fitz
    except ImportError:
        return None

    doc = fitz.open(str(pdf_path))
    pages = [page.get_text() for page in doc]
    doc.close()
    return pages


def _split_pdf(pdf_path, max_bytes):
    """Split a large PDF into chunks ≤ max_bytes. Returns list of (temp_path, page_count)."""
    try:
        import fitz
    except ImportError:
        print("ERROR: 大文件拆分需要 pymupdf: pip install pymupdf")
        sys.exit(1)

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    temp_dir = Path(tempfile.mkdtemp(prefix="ocr_split_"))
    chunks = []
    batch_size = max(1, total_pages // 2)  # start with half

    while batch_size >= 1:
        chunks = []
        start = 0
        while start < total_pages:
            end = min(start + batch_size, total_pages)
            chunk_path = temp_dir / f"chunk_{start}_{end}.pdf"
            chunk_doc = fitz.open()
            chunk_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
            chunk_doc.save(str(chunk_path))
            chunk_doc.close()

            size = chunk_path.stat().st_size
            if size > max_bytes and batch_size > 1:
                # This chunk is too large, retry with smaller batch
                chunk_path.unlink(missing_ok=True)
                batch_size = max(1, batch_size // 2)
                chunks = []
                break

            chunks.append((chunk_path, end - start))
            start = end

        if chunks:
            break

    doc.close()

    if not chunks:
        print("  警告: 无法将 PDF 拆分到目标大小，尝试单页上传")
        chunks = []
        doc = fitz.open(str(pdf_path))
        for i in range(total_pages):
            chunk_path = temp_dir / f"chunk_{i}_{i+1}.pdf"
            chunk_doc = fitz.open()
            chunk_doc.insert_pdf(doc, from_page=i, to_page=i)
            chunk_doc.save(str(chunk_path))
            chunk_doc.close()
            chunks.append((chunk_path, 1))
        doc.close()

    return chunks


def _write_output(parsing_results, base_name, file_out_dir, page_offset=0, pymupdf_pages=None):
    """Write per_page and merged markdown files + download images.

    If pymupdf_pages is provided, also saves raw pymupdf text for agent-side fusion.
    """
    try:
        import requests as req
    except ImportError:
        print("Missing dependency: pip install requests")
        sys.exit(1)

    if not parsing_results:
        return

    # Per-page files
    if len(parsing_results) > 1:
        per_page_dir = file_out_dir / "per_page"
        per_page_dir.mkdir(parents=True, exist_ok=True)
        for i, res in enumerate(parsing_results):
            md_path = per_page_dir / f"{base_name}_{page_offset + i}.md"
            md_path.write_text(res["markdown"]["text"], encoding="utf-8")
        print(f"  保存 {len(parsing_results)} 个逐页文件 → {per_page_dir}")

    # Merged file
    merged_dir = file_out_dir / "merged"
    merged_dir.mkdir(parents=True, exist_ok=True)
    merged_text = "\n\n---\n\n".join(r["markdown"]["text"] for r in parsing_results)
    merged_md = merged_dir / f"{base_name}.md"
    merged_md.write_text(merged_text, encoding="utf-8")
    print(f"  保存合并文件 → {merged_md}")

    # Download images into merged dir
    _download_images(parsing_results, merged_dir, req)

    # Save pymupdf raw text for agent-side fusion
    if pymupdf_pages:
        pymupdf_dir = file_out_dir / "pymupdf_raw"
        pymupdf_dir.mkdir(parents=True, exist_ok=True)
        pymupdf_merged = "\n\n---\n\n".join(pymupdf_pages)
        (pymupdf_dir / f"{base_name}.md").write_text(pymupdf_merged, encoding="utf-8")
        print(f"  保存 pymupdf 原文 → {pymupdf_dir / (base_name + '.md')}")


def process_cloud(source_dir, output_dir, token, *,
                  api_url=JOB_API_URL, model=DEFAULT_MODEL,
                  pages=None, poll_interval=DEFAULT_POLL_INTERVAL,
                  timeout=DEFAULT_TIMEOUT, max_file_mb=DEFAULT_MAX_FILE_MB,
                  use_orientation=True, use_unwarping=True,
                  use_chart=True, use_layout=True,
                  restructure_pages=True,
                  merge_tables=True, relevel_titles=True,
                  prettify=True):
    """Process files via PaddleOCR async v2 API."""
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
        print(f"未找到支持的文件: {source_dir}")
        print(f"支持格式: {', '.join(sorted(PDF_EXTS | IMAGE_EXTS))}")
        return

    os.makedirs(output_dir, exist_ok=True)
    max_bytes = max_file_mb * 1024 * 1024

    optional_payload = _build_optional_payload(
        useDocOrientationClassify=use_orientation,
        useDocUnwarping=use_unwarping,
        useChartRecognition=use_chart,
        useLayoutDetection=use_layout,
        restructurePages=restructure_pages,
        mergeTables=merge_tables,
        relevelTitles=relevel_titles,
        prettifyMarkdown=prettify,
    )

    print(f"模式: cloud (async v2)")
    print(f"模型: {model}")
    print(f"找到 {len(files)} 个文件待处理")

    converted = skipped = 0

    for file_idx, file_path in enumerate(files, 1):
        print(f"\n[{file_idx}/{len(files)}] {file_path.name}")

        base_name = file_path.stem
        file_out_dir = Path(output_dir) / base_name

        is_pdf = file_path.suffix.lower() in PDF_EXTS
        file_size = file_path.stat().st_size

        # For PDFs: extract pymupdf text in parallel (before waiting for OCR)
        pymupdf_pages = None
        if is_pdf:
            pymupdf_pages = _extract_pymupdf_pages(file_path)
            if pymupdf_pages:
                rich = sum(1 for t in pymupdf_pages if len(t.strip()) >= 50)
                print(f"  pymupdf 预提取: {len(pymupdf_pages)} 页, {rich} 页有丰富文字")

        # Determine chunks to submit
        if is_pdf and file_size > max_bytes:
            print(f"  文件 {file_size / 1024 / 1024:.1f}MB 超过 {max_file_mb}MB 限制，自动拆分...")
            chunks = _split_pdf(file_path, max_bytes)
            print(f"  拆分为 {len(chunks)} 个子文件")
        else:
            chunks = [(file_path, None)]  # None = don't know page count upfront

        # Submit all chunks
        jobs = []  # list of (job_id, chunk_path, page_count)
        for chunk_path, page_count in chunks:
            try:
                job_id = _submit_job(
                    chunk_path, token, api_url, model,
                    optional_payload, page_ranges=pages,
                )
                print(f"  已提交 job: {job_id}")
                jobs.append((job_id, chunk_path, page_count))
            except Exception as e:
                print(f"  提交失败: {e}")
                skipped += 1
                break
        else:
            # All chunks submitted successfully, poll for results
            all_results = []
            page_offset = 0
            success = True

            for job_id, chunk_path, page_count in jobs:
                try:
                    print(f"  等待 job {job_id}...")
                    jsonl_url = _poll_job(job_id, token, poll_interval, timeout)
                    results = _fetch_results(jsonl_url)

                    if page_count is not None and len(results) != page_count:
                        print(f"  注意: 期望 {page_count} 页结果，实际 {len(results)} 页")

                    all_results.extend(results)
                    page_offset += len(results)
                except Exception as e:
                    print(f"  Job {job_id} 失败: {e}")
                    success = False
                    skipped += 1
                    break

            if success and all_results:
                _write_output(all_results, base_name, file_out_dir, pymupdf_pages=pymupdf_pages)
                converted += 1
                print(f"  → 输出: {file_out_dir}")

        # Clean up temp split files
        if len(chunks) > 1:
            for chunk_path, _ in chunks:
                try:
                    chunk_path.unlink(missing_ok=True)
                    chunk_path.parent.rmdir()
                except OSError:
                    pass

    print(f"\n完成: {converted} 个已转换, {skipped} 个失败/跳过 → {output_dir}")


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
        description="Batch OCR documents into structured Markdown (PaddleOCR async v2 API).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
modes:
  cloud  PADDLEOCR_TOKEN env var (or --token)
         async v2 API with multipart upload, progress feedback,
         auto-split for large files. Supports PDF and images.
  local  --server_url or MLX_SERVER_URL env var
         Supports PDF only; requires ~/.venvs/paddleocr venv
        """,
    )
    parser.add_argument("source_dir", help="Directory containing files to process")
    parser.add_argument("output_dir", help="Directory to write output files")
    parser.add_argument(
        "--token",
        default=os.environ.get("PADDLEOCR_TOKEN"),
        help="PaddleOCR access token (or set PADDLEOCR_TOKEN env var)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"OCR model name (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--pages",
        default=None,
        help="Page ranges, e.g. '2,4-6' or '1--2' (page 1 to second-to-last)",
    )
    parser.add_argument(
        "--server_url",
        default=os.environ.get("MLX_SERVER_URL"),
        help="Local MLX server URL for local mode (or set MLX_SERVER_URL env var)",
    )

    # Feature flags (all default ON, --no-* to disable)
    parser.add_argument("--no-orientation", action="store_true", help="Disable doc orientation correction")
    parser.add_argument("--no-unwarping", action="store_true", help="Disable doc unwarping")
    parser.add_argument("--no-chart", action="store_true", help="Disable chart recognition")
    parser.add_argument("--no-layout", action="store_true", help="Disable layout detection")
    parser.add_argument("--no-restructure", action="store_true", help="Disable cross-page restructuring (prerequisite for mergeTables/relevelTitles)")
    parser.add_argument("--no-merge-tables", action="store_true", help="Disable cross-page table merging")
    parser.add_argument("--no-relevel-titles", action="store_true", help="Disable heading level recognition")
    parser.add_argument("--no-prettify", action="store_true", help="Disable markdown prettification")

    # Timing
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL,
                        help=f"Polling interval in seconds (default: {DEFAULT_POLL_INTERVAL})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Per-job timeout in seconds (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--max-file-mb", type=int, default=DEFAULT_MAX_FILE_MB,
                        help=f"Auto-split PDF threshold in MB (default: {DEFAULT_MAX_FILE_MB})")

    args = parser.parse_args()

    source_dir = os.path.abspath(args.source_dir)
    output_dir = os.path.abspath(args.output_dir)

    if args.token:
        process_cloud(
            source_dir, output_dir, args.token,
            model=args.model,
            pages=args.pages,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
            max_file_mb=args.max_file_mb,
            use_orientation=not args.no_orientation,
            use_unwarping=not args.no_unwarping,
            use_chart=not args.no_chart,
            use_layout=not args.no_layout,
            restructure_pages=not args.no_restructure,
            merge_tables=not args.no_merge_tables,
            relevel_titles=not args.no_relevel_titles,
            prettify=not args.no_prettify,
        )
    else:
        server_url = args.server_url or "http://localhost:8111/"
        process_local(source_dir, output_dir, server_url)

    print("\nAll done!")


if __name__ == "__main__":
    main()
