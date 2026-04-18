#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


# ---------------------------------------------------------------------------
# OCR Worker Functions — importable without a display server
# ---------------------------------------------------------------------------

def find_pdfs(directory, recursive=True):
    """Return a sorted list of Path objects for all PDFs in directory."""
    path = Path(directory)
    pattern = '**/*.pdf' if recursive else '*.pdf'
    return sorted(path.glob(pattern))


def check_ocrmypdf_installed():
    """Return True if ocrmypdf is available on PATH."""
    return shutil.which('ocrmypdf') is not None


def process_pdf(pdf_path, language='eng', rotate=False):
    """
    Run ocrmypdf on a single PDF, replacing it in-place on success.

    Returns a dict: {'status': 'ok'|'skipped'|'error', 'message': str}
    Exit code 6 from ocrmypdf means all pages already had text (--skip-text).
    """
    pdf_path = Path(pdf_path)
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp_path = Path(tmp.name)

    cmd = ['ocrmypdf', '--skip-text', '--quiet', '-l', language,
           str(pdf_path), str(tmp_path)]
    if rotate:
        cmd.insert(-2, '--rotate-pages')

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 6:
        tmp_path.unlink(missing_ok=True)
        return {'status': 'skipped', 'message': 'Already searchable'}
    elif result.returncode == 0:
        shutil.move(str(tmp_path), str(pdf_path))
        return {'status': 'ok', 'message': ''}
    else:
        tmp_path.unlink(missing_ok=True)
        stderr = result.stderr.strip().lower()
        if 'encrypt' in stderr or 'password' in stderr:
            msg = 'Could not process \u2014 file may be password-protected'
        elif 'invalid' in stderr or 'not a pdf' in stderr or 'damaged' in stderr:
            msg = 'Could not process \u2014 file may be damaged'
        else:
            msg = 'Could not process \u2014 unknown error'
        return {'status': 'error', 'message': msg}
