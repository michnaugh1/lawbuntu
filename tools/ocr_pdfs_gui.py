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
