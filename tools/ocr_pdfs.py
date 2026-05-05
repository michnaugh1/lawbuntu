#!/usr/bin/env python3
"""
OCR a directory of PDFs in-place using ocrmypdf.
Skips files that already have a text layer.
"""

import argparse
import sys
from pathlib import Path

from ocr_backend import find_pdfs, process_pdf


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

    pdfs = find_pdfs(directory, recursive=args.recursive)

    if not pdfs:
        print("No PDF files found.")
        sys.exit(0)

    print(f"Found {len(pdfs)} PDF(s) in '{directory}'\n")

    ok = skipped = errors = 0
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name} ... ", end="", flush=True)
        result = process_pdf(pdf, language=args.language, rotate=args.rotate)
        if result["status"] == "ok":
            ok += 1
            print("done")
        elif result["status"] == "skipped":
            skipped += 1
            print("already searchable, skipped")
        else:
            errors += 1
            print(result["message"])

    print(f"\nComplete: {ok} processed, {skipped} skipped, {errors} error(s)")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
