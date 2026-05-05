#!/usr/bin/env python3
"""
OCR a directory of PDFs in-place using ocrmypdf.
Skips files that already have a text layer.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def ocr_pdf(pdf_path: Path, language: str, rotate: bool) -> str:
    """Run ocrmypdf on a single file, replacing it in-place. Returns 'skipped', 'ok', or 'error'."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    cmd = [
        "ocrmypdf",
        "--skip-text",
        "--output-type", "pdf",
        "--quiet",
        "-l", language,
    ]
    if rotate:
        cmd.append("--rotate-pages")
    cmd += [str(pdf_path), str(tmp_path)]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Exit code 6 = already has text and --skip-text was used (all pages skipped)
    if result.returncode == 6:
        tmp_path.unlink(missing_ok=True)
        return "skipped"
    elif result.returncode == 0:
        shutil.move(str(tmp_path), str(pdf_path))
        return "ok"
    else:
        tmp_path.unlink(missing_ok=True)
        return f"error: {result.stderr.strip()}"


def main():
    parser = argparse.ArgumentParser(
        description="OCR a directory of PDFs in-place, skipping already-searchable files."
    )
    parser.add_argument("directory", help="Directory containing PDF files")
    parser.add_argument(
        "-l", "--language", default="eng",
        help="OCR language code(s), e.g. 'eng' or 'eng+fra' (default: eng)"
    )
    parser.add_argument(
        "-r", "--rotate", action="store_true",
        help="Auto-rotate pages based on detected text orientation"
    )
    parser.add_argument(
        "--recursive", action="store_true",
        help="Process PDFs in subdirectories as well"
    )
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"Error: '{directory}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    pattern = "**/*.pdf" if args.recursive else "*.pdf"
    pdfs = sorted(directory.glob(pattern))

    if not pdfs:
        print("No PDF files found.")
        sys.exit(0)

    print(f"Found {len(pdfs)} PDF(s) in '{directory}'\n")

    ok = skipped = errors = 0
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name} ... ", end="", flush=True)
        status = ocr_pdf(pdf, args.language, args.rotate)
        if status == "ok":
            ok += 1
            print("done")
        elif status == "skipped":
            skipped += 1
            print("already searchable, skipped")
        else:
            errors += 1
            print(status)

    print(f"\nComplete: {ok} processed, {skipped} skipped, {errors} error(s)")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
